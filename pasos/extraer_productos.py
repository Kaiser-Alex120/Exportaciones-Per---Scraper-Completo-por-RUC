"""Recorre el sitio web de una empresa y extrae tablas de exportaciones.
Busca partidas arancelarias, descripción y valor FOB usando Selenium."""

import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin, urlparse
from collections import deque
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
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
}

# Palabras clave que indican una página de exportaciones / productos
PALABRAS_EXPORTACION = {
    "exportaci", "exportacion", "exportaciones", "producto", "products",
    "catalogo", "catálogo", "portafolio", "portfolio", "produccion",
    "producción", "mineral", "minerales", "concentrado", "operaciones",
    "negocio", "negocios", "linea", "línea", "negocios", "servicios",
    "oferta", "ofertas", "unidad", "unidades",
}

# Palabras que indican tablas de datos de exportación (partidas arancelarias, FOB)
PALABRAS_TABLA_EXPORTACION = {
    "partida", "arancel", "descripci", "fob", "valor", "exportaci",
    "aduana", "tonelada", "tm", "us$", "dólar", "dolar",
}

# Máximos para no tardar demasiado
MAX_PAGINAS  = 20   # máximo de páginas a visitar por empresa
MAX_PRODUCTOS = 100  # máximo de productos a extraer


def extraer_productos_de_web(url_base: str) -> dict:
    """
    Recorre el sitio web de la empresa y extrae productos de exportación.
    Busca tablas con partidas arancelarias, descripción y valor FOB.
    Retorna:
      {
        "productos": [ {"partida": ..., "descripcion": ..., "valor_fob": ...}, ... ],
        "paginas_visitadas": [...],
        "estado": "ok" | "sin_productos" | "error",
        "mensaje": "..."
      }
    """
    resultado = {
        "productos": [],
        "paginas_visitadas": [],
        "estado": "error",
        "mensaje": "",
    }

    # Normalizar URL base
    if not url_base.startswith("http"):
        url_base = "https://" + url_base

    dominio = urlparse(url_base).netloc

    try:
        # Paso 1: cargar la página principal
        print("    📄 Cargando página principal con Selenium...")
        html_home = _get_html_selenium(url_base)
        
        if not html_home:
            # Intentar con www si falla sin www
            if not url_base.startswith("https://www."):
                url_base_www = url_base.replace("https://", "https://www.")
                html_home = _get_html_selenium(url_base_www)
                if html_home:
                    url_base = url_base_www

        if not html_home:
            # Fallback a requests
            print("    ⚠ Selenium falló, usando requests...")
            html_home = _get_html(url_base)

        if not html_home:
            resultado["mensaje"] = "No se pudo acceder al sitio web"
            return resultado

        resultado["paginas_visitadas"].append(url_base)
        print(f"    ✔ Página cargada: {url_base[:60]}")

        # Paso 2: descubrir páginas internas relevantes
        urls_a_visitar = _descubrir_urls(html_home, url_base, dominio)
        print(f"    📍 {len(urls_a_visitar)} páginas internas encontradas")
        
        # Primero revisar si la página principal tiene tabla de exportaciones
        prod_home = _extraer_tabla_exportaciones(html_home, url_base)
        if prod_home:
            resultado["productos"].extend(prod_home)
            print(f"    ✔ {len(prod_home)} productos de exportación encontrados en página principal")

        # Paso 3: recorrer páginas y buscar tablas
        todas_las_paginas_html = [(url_base, html_home)]
        visitadas = {url_base}

        cola = deque(urls_a_visitar)
        intentos_fallos = 0
        
        while cola and len(visitadas) < MAX_PAGINAS and intentos_fallos < 3:
            url_actual = cola.popleft()
            if url_actual in visitadas:
                continue

            # Intentar con Selenium primero
            html = _get_html_selenium(url_actual, timeout=10)
            
            if not html:
                # Fallback a requests
                html = _get_html(url_actual)
                if not html:
                    intentos_fallos += 1
                    continue
            
            visitadas.add(url_actual)

            if html:
                todas_las_paginas_html.append((url_actual, html))
                resultado["paginas_visitadas"].append(url_actual)
                
                # Seguir descubriendo más URLs dentro de esa página
                sub_urls = _descubrir_urls(html, url_actual, dominio)
                for u in sub_urls:
                    if u not in visitadas and len(visitadas) < MAX_PAGINAS:
                        cola.append(u)
            
            time.sleep(0.5)

        # Paso 4: extraer productos de todo el HTML recopilado
        print(f"    🔍 Buscando tablas de exportaciones en {len(todas_las_paginas_html)} páginas...")
        productos_vistos = set()
        
        # Si ya encontramos en home, no buscar de nuevo en home
        urls_ya_revisadas = {url_base} if prod_home else set()
        
        for url_pag, html_pag in todas_las_paginas_html:
            if url_pag in urls_ya_revisadas:
                continue
            urls_ya_revisadas.add(url_pag)
            
            nuevos = _extraer_tabla_exportaciones(html_pag, url_pag)
            if nuevos:
                for p in nuevos:
                    clave = (p.get("partida","") + p.get("descripcion","")).lower()[:80]
                    if clave and clave not in productos_vistos:
                        productos_vistos.add(clave)
                        resultado["productos"].append(p)
                # Si encontramos tabla de exportaciones, probablemente es la principal
                break
            
            if len(resultado["productos"]) >= MAX_PRODUCTOS:
                break

        # Resultado final
        if resultado["productos"]:
            resultado["estado"] = "ok"
            resultado["mensaje"] = f"{len(resultado['productos'])} productos de exportación encontrados"
            print(f"    ✔ {len(resultado['productos'])} productos de exportación extraídos")
        else:
            resultado["estado"] = "sin_productos"
            resultado["mensaje"] = "La web de la empresa no publica información de productos de exportación y valor FOB"
            print(f"    ⚠ No se encontró información de exportaciones en la web de la empresa")

    except Exception as e:
        resultado["estado"] = "error"
        resultado["mensaje"] = f"Error: {str(e)}"
        print(f"    ✖ Error: {str(e)}")

    return resultado


def _get_html_selenium(url: str, timeout: int = 15) -> str | None:
    """Obtiene HTML usando Selenium, esperando a que cargue JavaScript."""
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
        options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        
        # Esperar a que al menos cargue el body
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Scroll para cargar lazy-loading
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        
        return driver.page_source
        
    except Exception as e:
        return None
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def _get_html(url: str) -> str | None:
    """Fallback: Hace GET a una URL con requests y retorna el HTML, o None si falla."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            return resp.text
    except Exception:
        pass
    return None


def _descubrir_urls(html: str, url_base: str, dominio: str) -> list:
    """Encuentra URLs internas relevantes (páginas de productos/servicios)."""
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    vistas = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        url_completa = urljoin(url_base, href)
        parsed = urlparse(url_completa)

        # Solo URLs del mismo dominio
        if dominio not in parsed.netloc:
            continue

        url_limpia = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")

        if url_limpia in vistas:
            continue
        vistas.add(url_limpia)

        # Priorizar páginas que probablemente tengan productos/exportaciones
        texto_link = (a.get_text(strip=True) + " " + href).lower()
        es_relevante = any(p in texto_link for p in PALABRAS_EXPORTACION)
        es_imagen = any(ext in href.lower() for ext in [".jpg", ".png", ".pdf", ".zip", ".mp4"])

        if not es_imagen:
            if es_relevante:
                urls.insert(0, url_limpia)   # páginas relevantes primero
            else:
                urls.append(url_limpia)

    return urls[:30]  # máximo 30 candidatas por página


def _extraer_tabla_exportaciones(html: str, url_fuente: str) -> list:
    """
    Busca tablas con datos de exportaciones (partidas arancelarias, FOB, etc.).
    Retorna lista de dicts con: partida, descripcion, valor_fob
    """
    soup = BeautifulSoup(html, "html.parser")
    productos = []
    
    for tabla in soup.find_all("table"):
        filas = tabla.find_all("tr")
        if len(filas) < 2:
            continue
            
        # Extraer encabezados
        encabezados_raw = filas[0].find_all(["th", "td"])
        encabezados = [th.get_text(strip=True).lower() for th in encabezados_raw]
        
        if not encabezados:
            continue
        
        texto_encabezados = " ".join(encabezados)
        
        # Verificar si la tabla parece de exportaciones/aduanas
        parece_exportacion = any(p in texto_encabezados for p in PALABRAS_TABLA_EXPORTACION)
        parece_producto = any(p in texto_encabezados for p in ["product", "producto", "servicio", "descripci"])
        
        if not parece_exportacion and not parece_producto:
            continue
        
        # Buscar columnas relevantes
        col_partida = col_desc = col_fob = col_valor = None
        for i, enc in enumerate(encabezados):
            if any(p in enc for p in ["partida", "código", "codigo", "n°", "nro"]):
                col_partida = i
            elif any(p in enc for p in ["descripci", "descripti", "detalle", "concepto", "mercancía", "mercancia"]):
                col_desc = i
            elif any(p in enc for p in ["fob", "valor", "us$", "dolar", "dólar", "monto", "total"]):
                col_fob = i
            elif any(p in enc for p in ["precio", "price", "costo"]):
                col_valor = i
        
        # Si no detectamos columnas específicas, intentar inferir por posición
        if col_partida is None and len(encabezados) >= 3:
            # La primera columna suele ser N° o partida
            if any(p in encabezados[0] for p in ["n°", "nro", "nro.", "item", "#"]):
                col_partida = 1  # La segunda suele ser la partida
            elif re.match(r"^\d{8,12}$", encabezados_raw[0].get_text(strip=True).replace(" ", "")):
                col_partida = 0
        
        if col_desc is None and len(encabezados) >= 2:
            # La columna más larga suele ser la descripción
            longest = max(range(len(encabezados)), key=lambda i: len(encabezados[i]))
            if longest != col_partida and longest != col_fob:
                col_desc = longest
        
        for fila in filas[1:]:
            celdas = fila.find_all(["td", "th"])
            if not celdas:
                continue
            
            celdas_texto = [td.get_text(strip=True) for td in celdas]
            if not any(celdas_texto):
                continue
            
            # Extraer valores
            partida = ""
            if col_partida is not None and col_partida < len(celdas_texto):
                partida = celdas_texto[col_partida]
            elif len(celdas_texto) >= 2:
                # Intentar detectar partida arancelaria (números largos)
                for celda in celdas_texto:
                    if re.match(r"^\d{8,12}$", celda.replace(" ", "")):
                        partida = celda
                        break
            
            descripcion = ""
            if col_desc is not None and col_desc < len(celdas_texto):
                descripcion = celdas_texto[col_desc]
            else:
                # Tomar la celda con texto más largo que no sea la partida
                candidatas = [c for c in celdas_texto if c != partida and len(c) > 10]
                if candidatas:
                    descripcion = max(candidatas, key=len)
            
            valor_fob = ""
            if col_fob is not None and col_fob < len(celdas_texto):
                valor_fob = celdas_texto[col_fob]
            elif col_valor is not None and col_valor < len(celdas_texto):
                valor_fob = celdas_texto[col_valor]
            else:
                # Buscar número con formato monetario en las celdas
                for celda in celdas_texto:
                    if re.search(r"[\d.,]+\s*(US\$|\$|USD|S/)?|[\d.,]{5,}", celda):
                        if celda != partida and celda != descripcion:
                            valor_fob = celda
                            break
            
            # Filtrar filas vacías o de totales
            if not descripcion or descripcion.lower() in ["total", "suma", "subtotal", ""]:
                if not partida or partida.lower() in ["total", "suma", "subtotal"]:
                    continue
            
            # Solo agregar si tiene al menos descripción o partida
            if descripcion or partida:
                productos.append({
                    "partida": limpiar(partida),
                    "descripcion": limpiar(descripcion),
                    "valor_fob": limpiar(valor_fob),
                    "url_fuente": url_fuente,
                })
    
    return productos


def limpiar(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


# Prueba rápida: ejecutar este archivo directamente
if __name__ == "__main__":
    url = "https://www.antamina.com"
    print(f"Extrayendo exportaciones de: {url}")
    res = extraer_productos_de_web(url)
    print(f"  Estado: {res['estado']}")
    print(f"  Páginas visitadas: {len(res['paginas_visitadas'])}")
    print(f"  Productos: {len(res['productos'])}")
    for p in res["productos"][:5]:
        print(f"    → Partida: {p['partida']} | Desc: {p['descripcion'][:50]} | FOB: {p['valor_fob']}")