"""Consulta SUNAT por RUC y retorna razón social, estado y dirección.
Usa Selenium primero (más confiable con reCAPTCHA) y requests como fallback."""

import requests
from bs4 import BeautifulSoup
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

SUNAT_URL = "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias"
SUNAT_PAGE = "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-PE,es;q=0.9",
    "Referer": SUNAT_PAGE,
    "Content-Type": "application/x-www-form-urlencoded",
}


def consultar_sunat(ruc: str, session: requests.Session = None) -> dict:
    """
    Consulta SUNAT por RUC de forma más robusta.
    El sitio SUNAT usa reCAPTCHA v3 y protecciones anti-bot.
    
    Retorna:
      {
        "ruc": "20330262428",
        "razon_social": "COMPAÑIA MINERA ANTAMINA S.A.",
        "estado": "ACTIVO",
        "direccion": "...",
        "ok": True
      }
    Si falla retorna ok=False.
    """
    resultado = {
        "ruc": ruc,
        "razon_social": "",
        "estado": "",
        "direccion": "",
        "ok": False,
    }

    # Intentar con Selenium primero (es más confiable)
    driver = None
    try:
        print("    [INFO] Intentando consulta con Selenium...")
        resultado_selenium = _consultar_sunat_selenium(ruc)
        if resultado_selenium.get("ok"):
            return resultado_selenium
    except Exception as e:
        print(f"    [!] Selenium error: {str(e)[:80]}")
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    # Fallback a requests
    print("    [INFO] Intentando consulta con requests...")
    return _consultar_sunat_requests(ruc, session)


def _consultar_sunat_selenium(ruc: str) -> dict:
    """
    Consulta SUNAT usando Selenium para manejar reCAPTCHA v3.
    """
    driver = None
    resultado = {
        "ruc": ruc,
        "razon_social": "",
        "estado": "",
        "direccion": "",
        "ok": False,
    }

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
        
        print("    [INFO] Cargando pagina de SUNAT...")
        driver.get(SUNAT_PAGE)
        time.sleep(3)  # Esperar a que cargue reCAPTCHA
        
        # Esperar a que el campo de RUC esté visible
        wait = WebDriverWait(driver, 15)
        ruc_input = wait.until(
            EC.presence_of_element_located((By.ID, "txtRuc"))
        )
        
        print(f"    [INFO] Ingresando RUC: {ruc}")
        ruc_input.clear()
        ruc_input.send_keys(ruc.strip())
        time.sleep(1)
        
        # Esperar a que reCAPTCHA se ejecute
        print("    [INFO] Esperando reCAPTCHA...")
        time.sleep(3)
        
        # Hacer clic en el botón Buscar
        print("    [INFO] Buscando boton...")
        btn_buscar = wait.until(
            EC.element_to_be_clickable((By.ID, "btnAceptar"))
        )
        
        print("    [INFO] Haciendo clic en Buscar...")
        driver.execute_script("arguments[0].click();", btn_buscar)
        
        # Esperar a que se procese la búsqueda
        time.sleep(5)
        
        # Extraer el HTML de la respuesta
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        # Buscar los datos en la respuesta usando un parser específico de la UI de SUNAT
        datos = _parse_sunat_result_page(soup, ruc)
        razon = datos.get("razon_social", "")
        estado = datos.get("estado", "")
        direccion = datos.get("direccion", "")

        if not razon:
            razon = _extraer_campo(soup, ["Razón Social", "RAZON SOCIAL", "Nombre Comercial", 
                                          "Razón social", "razonSocial"])
            if not razon:
                razon = _buscar_en_tabla(soup, ruc)

        resultado.update({
            "razon_social": limpiar_texto(razon),
            "estado": limpiar_texto(estado),
            "direccion": limpiar_texto(direccion),
            "ok": bool(razon and len(razon) > 3),
        })
        
        if resultado["ok"]:
            print(f"    [OK] SUNAT respondio: {razon[:50]}")
        
    except Exception as e:
        resultado["error"] = str(e)
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return resultado



def _consultar_sunat_requests(ruc: str, session: requests.Session = None) -> dict:
    """Consulta SUNAT usando requests (fallback)."""
    if session is None:
        session = requests.Session()

    resultado = {
        "ruc": ruc,
        "razon_social": "",
        "estado": "",
        "direccion": "",
        "ok": False,
    }

    try:
        print("    [INFO] Obteniendo formulario de SUNAT...")
        
        # Obtener la página inicial para extraer el token y otros parámetros
        resp_main = session.get(
            SUNAT_PAGE,
            headers=HEADERS,
            timeout=20,
        )
        resp_main.raise_for_status()
        
        soup_main = BeautifulSoup(resp_main.text, "html.parser")
        
        # Extraer el token del formulario
        token_input = soup_main.find("input", {"name": "token"})
        token = token_input.get("value", "") if token_input else ""
        
        if not token:
            print("    [!] No se pudo extraer el token")
            return resultado
        
        print(f"    [INFO] Consultando RUC: {ruc}")
        
        # Preparar los datos del formulario
        payload = {
            "accion": "consPorRuc",
            "nroRuc": ruc.strip(),
            "razSoc": "",
            "nrodoc": "",
            "tipdoc": "",
            "codigo": "",
            "token": token,
            "contexto": "ti-it",
            "modo": "1",
        }
        
        # Enviar la consulta
        resp = session.post(
            "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias",
            data=payload,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True
        )
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Buscar los datos en la respuesta usando un parser específico de la UI de SUNAT
        datos = _parse_sunat_result_page(soup, ruc)
        razon = datos.get("razon_social", "")
        estado = datos.get("estado", "")
        direccion = datos.get("direccion", "")

        if not razon:
            razon = _extraer_campo(soup, ["Razón Social", "RAZON SOCIAL", "Nombre Comercial", 
                                          "Razón social", "razonSocial", "EMPRESA"])
            if not razon:
                razon = _buscar_en_tabla(soup, ruc)

        resultado.update({
            "razon_social": limpiar_texto(razon),
            "estado": limpiar_texto(estado),
            "direccion": limpiar_texto(direccion),
            "ok": bool(razon and len(razon) > 3),
        })
        
        if resultado["ok"]:
            print(f"    [OK] Resultado: {razon[:60]}")

    except requests.exceptions.RequestException as e:
        print(f"    [!] Error de conexion: {str(e)[:80]}")
        resultado["error"] = str(e)
    except Exception as e:
        print(f"    [!] Error: {str(e)[:80]}")
        resultado["error"] = str(e)

    return resultado


def _obtener_token(session: requests.Session) -> str:
    """Obtiene el token de la página principal de SUNAT."""
    try:
        resp = session.get(
            "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp",
            headers=HEADERS,
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        token_input = soup.find("input", {"name": "token"})
        if token_input:
            return token_input.get("value", "")
    except Exception:
        pass
    return ""


def _extraer_campo(soup: BeautifulSoup, etiquetas: list) -> str:
    """Busca una celda de tabla por su etiqueta y retorna el valor siguiente."""
    # Buscar en todas las celdas (td, th, label, span, div)
    celdas = soup.find_all(["td", "th", "label", "span", "div", "p"])
    
    for celda in celdas:
        texto = celda.get_text(strip=True)
        
        for etiq in etiquetas:
            if etiq.lower() in texto.lower():
                # El valor suele estar en la siguiente celda o hermana
                siguiente = celda.find_next_sibling()
                if siguiente:
                    valor = siguiente.get_text(strip=True)
                    if valor and len(valor) > 2:
                        return valor
                
                # O en el padre, buscar la siguiente columna
                padre = celda.parent
                if padre:
                    hijos = padre.find_all(["td", "th", "div"])
                    for i, hijo in enumerate(hijos):
                        if hijo == celda and i + 1 < len(hijos):
                            valor = hijos[i + 1].get_text(strip=True)
                            if valor and len(valor) > 2:
                                return valor
    
    return ""


def _buscar_en_tabla(soup: BeautifulSoup, ruc: str) -> str:
    """Busca la razón social en estructuras de tabla."""
    # Buscar todas las tablas
    for tabla in soup.find_all("table"):
        filas = tabla.find_all("tr")
        for fila in filas:
            celdas = fila.find_all(["td", "th"])
            fila_texto = " ".join([c.get_text(strip=True) for c in celdas])
            
            # Si encontramos el RUC, la razón social está cerca
            if ruc in fila_texto:
                for celda in celdas:
                    texto = celda.get_text(strip=True)
                    if len(texto) > 5 and ruc not in texto and "Razón" not in texto:
                        # Podría ser la razón social
                        if any(word in texto.upper() for word in ["S.A.", "S.A.C", "SRL", "E.I.R.L", "LTDA"]):
                            return texto
    
    # Si no encontró en tabla, buscar en todo el HTML
    texto_completo = soup.get_text()
    lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
    
    for i, linea in enumerate(lineas):
        if ruc in linea:
            # Buscar la siguiente línea no vacía que parezca razón social
            for j in range(i + 1, min(i + 5, len(lineas))):
                candidato = lineas[j]
                if candidato and len(candidato) > 5 and ruc not in candidato:
                    return candidato
    
    return ""


def _parse_sunat_result_page(soup: BeautifulSoup, ruc: str) -> dict:
    """Extrae razón social, estado y domicilio de la página de resultados SUNAT."""
    datos = {}
    for item in soup.select(".list-group-item"):
        heading = item.select_one(".list-group-item-heading, h4")
        if not heading:
            continue
        label = heading.get_text(" ", strip=True).strip()
        if not label:
            continue

        # Evitar capturar texto genérico del pie de página o scripts
        if label.startswith("©") or "derechos reservados" in label.lower():
            continue

        value = ""
        value_elem = item.select_one(".list-group-item-text")
        if value_elem:
            value = value_elem.get_text(" ", strip=True)
        else:
            # El valor puede estar en un segundo h4 o en el resto del contenido
            h4s = item.find_all("h4")
            if len(h4s) > 1:
                value = h4s[1].get_text(" ", strip=True)
            else:
                texto = item.get_text(" ", strip=True)
                value = texto.replace(label, "", 1).strip()

        if value:
            datos[label.lower()] = value

    razon = datos.get("número de ruc:", "")
    if razon and " - " in razon:
        razon = razon.split(" - ", 1)[1].strip()
    if not razon:
        razon = datos.get("nombre comercial:", "") or datos.get("razón social:", "") or datos.get("razon social:", "")

    return {
        "razon_social": limpiar_texto(razon),
        "estado": limpiar_texto(datos.get("estado del contribuyente:", "") or datos.get("estado:", "")),
        "direccion": limpiar_texto(datos.get("domicilio fiscal:", "") or datos.get("dirección:", "") or datos.get("direccion:", "")),
    }


def limpiar_texto(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


# Prueba rápida: ejecutar este archivo directamente
if __name__ == "__main__":
    ruc_prueba = "20330262428"
    print(f"Consultando RUC {ruc_prueba} en SUNAT...")
    resultado = consultar_sunat(ruc_prueba)
    for k, v in resultado.items():
        print(f"  {k}: {v}")