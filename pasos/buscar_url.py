"""Busca en Google la URL oficial de una empresa por su nombre.
Usa Selenium para evitar bloqueos. Si no encuentra nada, retorna encontrado=False."""

import requests
from bs4 import BeautifulSoup
import time
import re
import urllib.parse
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0=8",
}

# Dominios que NO son páginas web de empresa
DOMINIOS_EXCLUIDOS = {
    "google", "facebook", "instagram", "twitter", "youtube", "linkedin",
    "wikipedia", "sunat", "gob.pe", "produce.gob", "indecopi", "bcrp",
    "yelp", "tripadvisor", "booking", "amazon", "mercadolibre",
    "infobel", "páginas amarillas", "kompass", "traducido", "reddit",
    "pinterest", "tiktok", "spotify", "ebay", "alibaba", "instagram.com",
    "universidadperu", "blogspot", "blogger", "wordpress.com", "wordpress.org",
    "es-la.facebook", "fb.watch",
}


def buscar_url_empresa(nombre_empresa: str, ruc: str = "") -> dict:
    """
    Busca en Google la URL oficial de la empresa usando Selenium.
    Retorna:
      {
        "url": "https://www.antamina.com",
        "encontrado": True,
        "fuente": "google"
      }
    Si no encuentra:
      {
        "url": None,
        "encontrado": False,
        "motivo": "No cuenta con página web"
      }
    """
    resultado = {"url": None, "encontrado": False, "motivo": "No cuenta con página web"}

    # Construir queries simples usando directamente el nombre de SUNAT
    queries = [
        f'{nombre_empresa} sitio web',
        f'{nombre_empresa} Peru',
        f'{nombre_empresa} web oficial',
        f'{nombre_empresa}',
    ]

    for query in queries:
        print(f"    [BUSCA] Buscando: {query[:60]}...")
        url = _buscar_google_selenium(query)
        if url:
            resultado.update({"url": url, "encontrado": True, "fuente": "google"})
            return resultado
        time.sleep(1)

    return resultado


def _buscar_google_selenium(query: str) -> str | None:
    """Busca en Google usando Selenium para evitar bloqueos."""
    driver = None
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--user-agent=" + HEADERS["User-Agent"])
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--lang=es-PE")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        
        # Ir a Google
        search_url = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(query)
            + "&num=10&hl=es&gl=pe"
        )
        
        driver.get(search_url)
        time.sleep(2)
        
        # Extraer URLs de los resultados
        urls_encontradas = []
        
        # Buscar en los resultados
        resultados = driver.find_elements(By.CSS_SELECTOR, "div.yuRUbf a")
        
        for resultado_elem in resultados[:5]:
            try:
                href = resultado_elem.get_attribute("href")
                if href:
                    url = _extraer_url_google(href)
                    if url and _es_url_valida(url):
                        urls_encontradas.append(url)
            except:
                continue
        
        if urls_encontradas:
            return urls_encontradas[0]
        
        return None
        
    except Exception as e:
        print(f"    [!] Error en busqueda Selenium: {str(e)}")
        # Fallback a requests
        return _buscar_google(query)
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def _buscar_google(query: str) -> str | None:
    """Fallback: Hace una búsqueda en Google con requests y retorna la primera URL válida."""
    try:
        url_busqueda = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(query)
            + "&num=10&hl=es"
        )
        resp = requests.get(url_busqueda, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extraer URLs de los resultados de búsqueda
        urls_encontradas = []

        # Método 1: tags <a> con href que contengan URLs
        for a in soup.find_all("a", href=True):
            href = a["href"]
            url = _extraer_url_google(href)
            if url and _es_url_valida(url):
                urls_encontradas.append(url)

        # Método 2: buscar en el texto plano
        if not urls_encontradas:
            texto = soup.get_text()
            urls_texto = re.findall(r'https?://[^\s<>"]+', texto)
            for u in urls_texto:
                if _es_url_valida(u):
                    urls_encontradas.append(u)

        return urls_encontradas[0] if urls_encontradas else None

    except Exception:
        return None


def _limpiar_nombre(nombre: str) -> str:
    """Elimina términos legales del nombre para mejorar la búsqueda."""
    terminos_legales = [
        r"\bS\.A\.C\b\.?", r"\bS\.A\b\.?", r"\bS\.R\.L\b\.?",
        r"\bE\.I\.R\.L\b\.?", r"\bS\.A\.A\b\.?", r"\bLTDA\b\.?",
        r"\bSUCURSAL DEL PERÚ\b", r"\bDEL PERU\b",
        r"\bSOCIEDAD ANONIMA CERRADA\b", r"\bSOCIEDAD ANONIMA\b",
    ]
    resultado = nombre
    for termino in terminos_legales:
        resultado = re.sub(termino, "", resultado, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", resultado).strip()


def _buscar_google(query: str) -> str | None:
    """Hace una búsqueda en Google y retorna la primera URL válida."""
    try:
        url_busqueda = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(query)
            + "&num=10&hl=es"
        )
        resp = requests.get(url_busqueda, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extraer URLs de los resultados de búsqueda
        urls_encontradas = []

        # Método 1: tags <a> con href que contengan URLs
        for a in soup.find_all("a", href=True):
            href = a["href"]
            url = _extraer_url_google(href)
            if url and _es_url_valida(url):
                urls_encontradas.append(url)

        # Método 2: buscar en el texto plano
        if not urls_encontradas:
            texto = soup.get_text()
            urls_texto = re.findall(r'https?://[^\s<>"]+', texto)
            for u in urls_texto:
                if _es_url_valida(u):
                    urls_encontradas.append(u)

        return urls_encontradas[0] if urls_encontradas else None

    except Exception:
        return None


def _extraer_url_google(href: str) -> str | None:
    """Extrae URL limpia de un href de Google (que puede venir con prefijos)."""
    if href.startswith("/url?q="):
        href = href[7:]
        href = href.split("&")[0]
        href = urllib.parse.unquote(href)

    if href.startswith("http") and "google.com" not in href:
        # Quedarse solo con dominio + path principal
        partes = urllib.parse.urlparse(href)
        return f"{partes.scheme}://{partes.netloc}"

    return None


def _es_url_valida(url: str) -> bool:
    """Verifica que la URL no sea de un dominio excluido."""
    url_lower = url.lower()
    return not any(excl in url_lower for excl in DOMINIOS_EXCLUIDOS)


# Prueba rápida: ejecutar este archivo directamente
if __name__ == "__main__":
    nombre = "COMPAÑIA MINERA ANTAMINA"
    print(f"Buscando URL para: {nombre}")
    res = buscar_url_empresa(nombre, "20330262428")
    print(f"  Resultado: {res}")