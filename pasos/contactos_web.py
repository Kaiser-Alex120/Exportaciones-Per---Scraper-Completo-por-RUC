"""Extrae contactos de la web de una empresa (teléfonos, emails, redes sociales, dirección).
Prioriza footer y header, luego busca en la página de contacto y en el resto del body."""

import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-PE,es;q=0.9",
}

# Patrones mejorados para extraer contactos
# Teléfonos peruanos: +51, 01, 9xx xxx xxx, formatos variados
RE_TELEFONO = re.compile(
    r'(?:\+51[\s\-\.]?)?'          # Código de país +51 opcional
    r'(?:\(?0?1\)?[\s\-\.]?)?'     # Código de Lima (01) opcional
    r'(?:9\d{2})'                  # Celular: 9xx
    r'[\s\-\.]?'                    # Separador
    r'\d{3}'                        # XXX
    r'[\s\-\.]?'                    # Separador
    r'\d{3,4}'                      # XXXX (3-4 dígitos finales)
    r'(?:[\s\-\.]?(?:anexo|ext|ext\.?)[\s\-\.]?\d{1,4})?',  # Extensión opcional
    re.IGNORECASE
)

# Teléfonos fijos peruanos (01, formatos de área)
RE_TELEFONO_FIJO = re.compile(
    r'(?:\(?0?1\)?[\s\-\.]?)'      # Código 01
    r'\d{3}'                        # XXX
    r'[\s\-\.]?'                    # Separador
    r'\d{4}'                        # XXXX
    r'(?:[\s\-\.]?(?:anexo|ext|ext\.?)[\s\-\.]?\d{1,4})?',
    re.IGNORECASE
)

RE_EMAIL = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
)

# Redes sociales - incluye más dominios y variantes
RE_RED_SOCIAL = re.compile(
    r'https?://(?:www\.)?(?:facebook|fb|instagram|ig|linkedin|twitter|x|youtube|yt|tiktok|pinterest)\.com/[^\s"<>]+',
    re.IGNORECASE
)

# Palabras clave para detectar redes sociales en atributos
KEYWORDS_RED_SOCIAL = ['facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 'tiktok', 'pinterest', 'whatsapp']


def extraer_contactos_web(url_base: str) -> dict:
    """
    Visita la página principal y extrae contactos priorizando FOOTER y HEADER.

    Retorna:
      {
        "url": "https://www.antamina.com",
        "telefonos": ["+51 1 ..."],
        "emails": ["contacto@..."],
        "direccion": "...",
        "redes_sociales": ["https://facebook.com/..."],
        "ok": True | False,
        "mensaje": ""
      }
    """
    resultado = {
        "url": url_base,
        "telefonos": [],
        "emails": [],
        "direccion": "",
        "redes_sociales": [],
        "ok": False,
        "mensaje": "",
    }

    if not url_base.startswith("http"):
        url_base = "https://" + url_base

    html = _get_html_selenium(url_base) or _get_html_requests(url_base)

    if not html:
        resultado["mensaje"] = "No se pudo acceder al sitio web"
        return resultado

    soup = BeautifulSoup(html, "html.parser")

    # --- PRIORIDAD 1: Extraer de FOOTER ---
    footer_data = _extraer_de_footer(soup, url_base)
    
    # --- PRIORIDAD 2: Extraer de HEADER ---
    header_data = _extraer_de_header(soup, url_base)
    
    # --- PRIORIDAD 3: Buscar página de contacto ---
    contacto_data = _extraer_de_pagina_contacto(soup, url_base)
    
    # --- PRIORIDAD 4: Extraer del resto de la página ---
    body_data = _extraer_de_body(soup, url_base)
    
    # Combinar resultados (footer tiene prioridad, luego header, luego contacto, luego body)
    resultado["telefonos"] = _combinar_listas(
        footer_data.get("telefonos", []),
        header_data.get("telefonos", []),
        contacto_data.get("telefonos", []),
        body_data.get("telefonos", [])
    )[:5]
    
    resultado["emails"] = _combinar_listas(
        footer_data.get("emails", []),
        header_data.get("emails", []),
        contacto_data.get("emails", []),
        body_data.get("emails", [])
    )[:5]
    
    resultado["redes_sociales"] = _combinar_listas(
        footer_data.get("redes_sociales", []),
        header_data.get("redes_sociales", []),
        body_data.get("redes_sociales", [])
    )[:10]
    
    # Dirección: priorizar footer, luego página de contacto
    resultado["direccion"] = (
        footer_data.get("direccion") or 
        contacto_data.get("direccion") or
        header_data.get("direccion") or 
        body_data.get("direccion") or 
        _buscar_direccion(soup)
    )

    resultado["ok"] = True
    resultado["mensaje"] = f"Contactos extraidos (Footer: {len(footer_data.get('telefonos', []))} tel, {len(footer_data.get('emails', []))} mail, {len(footer_data.get('redes_sociales', []))} redes)"
    return resultado


def _extraer_de_footer(soup: BeautifulSoup, url_base: str) -> dict:
    """Extrae contactos específicamente del footer."""
    data = {"telefonos": [], "emails": [], "redes_sociales": [], "direccion": ""}
    
    # Buscar elementos footer, .footer, #footer
    footers = soup.find_all(["footer"]) + soup.find_all(class_=re.compile(r"footer", re.I)) + soup.find_all(id=re.compile(r"footer", re.I))
    
    for footer in footers:
        texto = footer.get_text(separator=" ", strip=True)
        html_str = str(footer)
        
        # Teléfonos en footer - buscar también links tel:
        data["telefonos"].extend(RE_TELEFONO.findall(texto))
        data["telefonos"].extend(RE_TELEFONO_FIJO.findall(texto))
        
        # Buscar tel: en href
        for a in footer.find_all("a", href=True):
            href = a.get("href", "")
            if href.startswith("tel:"):
                tel = href.replace("tel:", "").replace("-", "").replace(" ", "")
                if tel.startswith("+51") or tel.startswith("01") or tel.startswith("9"):
                    data["telefonos"].append(tel)
        
        # Emails en footer (texto y mailto:)
        data["emails"].extend(RE_EMAIL.findall(texto))
        for a in footer.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email and "@" in email and "." in email.split("@")[-1]:
                    data["emails"].append(email)
        
        # Redes sociales en footer - mejorado para capturar iconos
        for a in footer.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href == "#" or href.startswith("javascript"):
                continue
                
            # Normalizar URL
            if href.startswith("/"):
                href = url_base.rstrip("/") + href
            elif not href.startswith("http"):
                continue
                
            # Detectar por URL
            match = RE_RED_SOCIAL.search(href)
            if match:
                url_limpia = match.group().split("?")[0].rstrip("/")
                if url_limpia not in data["redes_sociales"]:
                    data["redes_sociales"].append(url_limpia)
                continue
            
            # Detectar por clase CSS (face, twitter, instagram, etc.)
            clases = " ".join(a.get("class", [])).lower()
            if any(rs in clases for rs in KEYWORDS_RED_SOCIAL):
                if href not in data["redes_sociales"]:
                    data["redes_sociales"].append(href)
                continue
            
            # Detectar por title/aria-label
            for attr in ["title", "aria-label"]:
                val = a.get(attr, "").lower()
                if any(rs in val for rs in KEYWORDS_RED_SOCIAL):
                    if href not in data["redes_sociales"]:
                        data["redes_sociales"].append(href)
                    break
        
        # Dirección en footer
        direccion = _extraer_direccion_de_texto(texto)
        if direccion:
            data["direccion"] = direccion
    
    return data


def _extraer_de_header(soup: BeautifulSoup, url_base: str) -> dict:
    """Extrae contactos del header/top bar."""
    data = {"telefonos": [], "emails": [], "redes_sociales": [], "direccion": ""}
    
    # Buscar header, .top-bar, .contact-bar, .header-info
    headers = (
        soup.find_all(["header"]) + 
        soup.find_all(class_=re.compile(r"top.?bar|header|contact.?info|topbar|phone|telefono", re.I))
    )
    
    for header in headers:
        texto = header.get_text(separator=" ", strip=True)
        
        data["telefonos"].extend(RE_TELEFONO.findall(texto))
        data["telefonos"].extend(RE_TELEFONO_FIJO.findall(texto))
        data["emails"].extend(RE_EMAIL.findall(texto))
        
        for a in header.find_all("a", href=True):
            href = a.get("href", "")
            # Mailto
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email and "@" in email:
                    data["emails"].append(email)
            # Tel
            elif href.startswith("tel:"):
                tel = href.replace("tel:", "").replace("-", "").replace(" ", "")
                if tel.startswith("+51") or tel.startswith("01") or tel.startswith("9"):
                    data["telefonos"].append(tel)
            # Redes sociales
            elif href.startswith("http"):
                match = RE_RED_SOCIAL.search(href)
                if match:
                    url_limpia = match.group().split("?")[0].rstrip("/")
                    if url_limpia not in data["redes_sociales"]:
                        data["redes_sociales"].append(url_limpia)
    
    return data


def _extraer_de_pagina_contacto(soup: BeautifulSoup, url_base: str) -> dict:
    """Busca link a página de contacto y extrae información adicional."""
    data = {"telefonos": [], "emails": [], "direccion": ""}
    
    # Buscar links a página de contacto
    url_contacto = None
    for a in soup.find_all("a", href=True):
        texto = (a.get_text() or "").lower()
        href = a["href"].lower()
        
        # Detectar por texto o URL
        if any(p in texto or p in href for p in ["contacto", "contactanos", "contact us", "escribenos", "ubicacion", "sede"]):
            url_contacto = a["href"]
            if not url_contacto.startswith("http"):
                url_contacto = url_base.rstrip("/") + ("/" if not url_contacto.startswith("/") else "") + url_contacto
            break
    
    if not url_contacto:
        return data
    
    # Intentar obtener HTML de página de contacto
    try:
        html = _get_html_requests(url_contacto)
        if not html:
            return data
        
        soup_contacto = BeautifulSoup(html, "html.parser")
        texto = soup_contacto.get_text(separator=" ", strip=True)
        
        # Extraer teléfonos de página de contacto
        data["telefonos"] = RE_TELEFONO.findall(texto) + RE_TELEFONO_FIJO.findall(texto)
        
        # Buscar tel: links
        for a in soup_contacto.find_all("a", href=True):
            href = a.get("href", "")
            if href.startswith("tel:"):
                tel = href.replace("tel:", "").replace("-", "").replace(" ", "")
                if tel.startswith("+51") or tel.startswith("01") or tel.startswith("9"):
                    data["telefonos"].append(tel)
        
        # Extraer emails
        data["emails"] = RE_EMAIL.findall(texto)
        for a in soup_contacto.find_all("a", href=True):
            if a["href"].startswith("mailto:"):
                email = a["href"].replace("mailto:", "").split("?")[0].strip()
                if email and "@" in email:
                    data["emails"].append(email)
        
        # Extraer dirección
        data["direccion"] = _extraer_direccion_de_texto(texto)
        
    except Exception:
        pass
    
    return data


def _extraer_de_body(soup: BeautifulSoup, url_base: str) -> dict:
    """Extrae contactos del resto del body (respaldo)."""
    data = {"telefonos": [], "emails": [], "redes_sociales": [], "direccion": ""}
    
    # Excluir footer y header ya procesados
    texto = soup.get_text(separator="\n")
    
    data["telefonos"] = RE_TELEFONO.findall(texto)
    data["emails"] = [e for e in RE_EMAIL.findall(texto) if not e.endswith(('.png', '.jpg', '.gif', '.svg'))]
    
    for a in soup.find_all("a", href=True):
        href = a["href"]
        match = RE_RED_SOCIAL.search(href)
        if match:
            data["redes_sociales"].append(match.group())
    
    return data


def _combinar_listas(*listas) -> list:
    """Combina listas eliminando duplicados manteniendo orden."""
    resultado = []
    for lista in listas:
        for item in lista:
            item_limpio = item.strip() if isinstance(item, str) else item
            if item_limpio and item_limpio not in resultado:
                resultado.append(item_limpio)
    return resultado


def _extraer_direccion_de_texto(texto: str) -> str:
    """Busca dirección en texto del footer."""
    lineas = [l.strip() for l in re.split(r'[\n\r\|]', texto) if len(l.strip()) > 15]
    
    # Palabras clave de direcciones peruanas
    keywords_calle = ["av.", "jr.", "calle", "pasaje", "prol.", "prolongacion", "urb.", "urbanizacion", 
                      "mza.", "manzana", "lt.", "lote", "dpto.", "departamento", "of.", "oficina", 
                      "nro", "n°", "num", "numero", "piso", "torre", "int.", "interior"]
    localidades = ["lima", "peru", "perú", "callao", "arequipa", "cusco", "trujillo", "huancayo",
                   "ica", "piura", "chiclayo", "tacna", "moquegua", "ancash", "junin", "pucallpa",
                   "iquitos", "chimbote", "huaraz"]
    
    # Buscar líneas que parezcan direcciones
    for linea in lineas:
        linea_lower = linea.lower()
        tiene_keyword = any(k in linea_lower for k in keywords_calle)
        tiene_localidad = any(loc in linea_lower for loc in localidades)
        tiene_numero = bool(re.search(r'\d+', linea))
        
        # Debe tener keyword de calle O localidad, y debe tener al menos un número
        if (tiene_keyword or tiene_localidad) and tiene_numero and 25 < len(linea) < 200:
            # Limpiar espacios múltiples y caracteres raros
            linea = re.sub(r'\s+', ' ', linea).strip()
            linea = re.sub(r'[\|\*\#\@\$\%\&\^\(\)\[\]\{\}]+', '', linea)
            # No devolver si parece ser un horario o email
            if any(x in linea_lower for x in ["lunes", "martes", "miércoles", "jueves", "viernes", 
                                               "sábado", "domingo", "horario", "@", "am", "pm"]):
                continue
            return linea
    
    return ""


def _get_html_selenium(url: str) -> str | None:
    driver = None
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--user-agent=" + HEADERS["User-Agent"])
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )
        driver.set_page_load_timeout(15)
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)
        return driver.page_source
    except Exception:
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _get_html_requests(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            return resp.text
    except Exception:
        pass
    return None


def _buscar_direccion(soup: BeautifulSoup) -> str:
    """Busca dirección en footer, sección contacto, etc. (método de respaldo)."""
    # Buscar en footer
    for footer in soup.find_all(["footer", "address"]):
        texto = footer.get_text(separator=" ", strip=True)
        lineas = [l.strip() for l in texto.replace("\r", "\n").split("\n") if len(l.strip()) > 20]
        for linea in lineas:
            if any(k in linea.lower() for k in ["av.", "jr.", "calle", "urb.", "mza.", "lt.", "dpto.", "of.", "lima", "perú", "peru", "nro", "n°", "num", "piso"]):
                if len(linea) < 300:
                    return re.sub(r'\s+', ' ', linea).strip()

    # Buscar en elementos con clase que contenga contacto o dirección
    for elem in soup.find_all(["div", "section", "p", "span"]):
        clases = " ".join(elem.get("class", [])).lower()
        if any(k in clases for k in ["direccion", "dirección", "address", "contacto", "ubicacion", "ubicación", "location", "sede"]):
            texto = elem.get_text(strip=True)
            if any(k in texto.lower() for k in ["av.", "jr.", "calle", "urb.", "lima", "perú", "peru"]) and len(texto) < 300:
                return re.sub(r'\s+', ' ', texto).strip()

    return ""


# Prueba rápida: ejecutar este archivo directamente
if __name__ == "__main__":
    urls_test = [
        "https://www.antamina.com",
        "https://www.southernperu.com",
    ]
    
    for url in urls_test:
        print(f"\n{'='*60}")
        print(f"Extrayendo contactos de: {url}")
        print(f"{'='*60}")
        res = extraer_contactos_web(url)
        print(f"  [OK] {res['ok']}")
        print(f"  [TEL]  Teléfonos: {res['telefonos']}")
        print(f"  [MAIL] Emails: {res['emails']}")
        print(f"  [DIR]  Dirección: {res['direccion'][:100] if res['direccion'] else 'No encontrada'}")
        print(f"  [WEB]  Redes sociales ({len(res['redes_sociales'])}):")
        for rs in res['redes_sociales'][:5]:
            print(f"         - {rs}")
        print(f"  [INFO] {res['mensaje']}")
