"""Consulta Aduanet por RUC y años, extrae exportaciones (DUA, FOB, mes, aduana, país).
Usa Selenium primero y requests como fallback. Fuente: aduanet.gob.pe"""

import requests
from bs4 import BeautifulSoup
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

ADUANET_URL = (
    "http://www.aduanet.gob.pe/cl-ad-itconsultadwh/ieITS01Alias"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-PE,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": ADUANET_URL,
}


def extraer_exportaciones_aduanet(ruc: str, anios: list) -> dict:
    """
    Consulta Aduanet por RUC y años y extrae exportaciones.

    Retorna:
      {
        "productos": [
          {
            "partida": "2603000000",
            "descripcion": "MINERALES DE COBRE Y SUS CONCENTRADOS",
            "valor_fob": "4127660753",
            "anio": 2025,
            "url_fuente": "http://www.aduanet.gob.pe/..."
          }, ...
        ],
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

    for anio in anios:
        print(f"    [ADUANET] Consultando RUC {ruc}, año {anio}...")

        # Intentar con Selenium primero
        productos_anio = _consultar_selenium(ruc, anio)

        if not productos_anio:
            # Fallback a requests
            print(f"    [!] Selenium fallo, intentando con requests...")
            productos_anio = _consultar_requests(ruc, anio)

        if productos_anio:
            for p in productos_anio:
                p["anio"] = anio
            resultado["productos"].extend(productos_anio)
            resultado["paginas_visitadas"].append(
                f"{ADUANET_URL}?accion=buscarListadoImpoExpo&CG_consulta=1&CG_tipo=4&CG_Codigo={ruc}&CG_Aduana=999&CG_Ano={_codigo_ano(anio)}&CG_Mes=00&CG_regimen=40"
            )
            print(f"    [OK] {len(productos_anio)} registros encontrados para {anio}")
        else:
            print(f"    [WARN] Sin resultados para {anio}")

        time.sleep(1)

    if resultado["productos"]:
        resultado["estado"] = "ok"
        resultado["mensaje"] = f"{len(resultado['productos'])} registros de exportación encontrados"
    else:
        resultado["estado"] = "sin_productos"
        resultado["mensaje"] = "No se encontraron exportaciones para el RUC y años indicados"

    return resultado


def _consultar_selenium(ruc: str, anio: int) -> list:
    """Consulta Aduanet usando Selenium para manejar formularios JS."""
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

        # Cargar el formulario de consulta por importador/exportador
        url_form = f"{ADUANET_URL}?accion=consultar&CG_consulta=1"
        driver.get(url_form)
        time.sleep(3)

        wait = WebDriverWait(driver, 15)

        # El tipo RUC ya viene seleccionado por defecto en CG_tipo=4
        # Solo ingresamos el RUC en el campo correcto CG_Codigo
        try:
            campo_ruc = wait.until(
                EC.presence_of_element_located((By.NAME, "CG_Codigo"))
            )
            campo_ruc.clear()
            campo_ruc.send_keys(ruc)
        except Exception:
            # fallback: buscar input con maxlength=11
            inputs = driver.find_elements(By.CSS_SELECTOR, "input[maxlength='11']")
            if inputs:
                inputs[0].clear()
                inputs[0].send_keys(ruc)

        # Seleccionar año por código (CG_Ano usa código interno)
        try:
            select_anio = driver.find_element(By.NAME, "CG_Ano")
            codigo_anio = _codigo_ano(anio)
            for option in select_anio.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == codigo_anio:
                    option.click()
                    break
        except Exception:
            pass

        # Seleccionar mes = 00 (todo el año)
        try:
            select_mes = driver.find_element(By.NAME, "CG_Mes")
            for option in select_mes.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == "00":
                    option.click()
                    break
        except Exception:
            pass

        # Seleccionar régimen EXPORTACION = 40
        try:
            select_regimen = driver.find_element(By.NAME, "CG_regimen")
            for option in select_regimen.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == "40":
                    option.click()
                    break
        except Exception:
            pass

        # Seleccionar aduana = 999 (todas)
        try:
            select_aduana = driver.find_element(By.NAME, "CG_Aduana")
            for option in select_aduana.find_elements(By.TAG_NAME, "option"):
                if option.get_attribute("value") == "999":
                    option.click()
                    break
        except Exception:
            pass

        # Hacer clic en el botón Consultar (valor="Consultar")
        try:
            btn = driver.find_element(By.XPATH, "//input[@type='button' and @value='Consultar']")
            driver.execute_script("arguments[0].click();", btn)
        except Exception:
            # fallback: cualquier botón que diga Consultar o tenga onclick con jsEnviar
            btns = driver.find_elements(By.TAG_NAME, "input")
            for b in btns:
                val = (b.get_attribute("value") or "").upper()
                if "CONSULTAR" in val or "jsEnviar" in (b.get_attribute("onclick") or ""):
                    driver.execute_script("arguments[0].click();", b)
                    break

        time.sleep(5)

        # Extraer datos de todas las páginas (paginación)
        todos_productos = []
        pagina = 1
        max_paginas = 20

        while pagina <= max_paginas:
            html = driver.page_source
            productos_pag = _parsear_tabla_resultados(html, ruc, anio)
            if productos_pag:
                todos_productos.extend(productos_pag)
                print(f"    [PAG {pagina}] {len(productos_pag)} registros")

            # Buscar botón/link "Siguiente"
            try:
                # Guardar hash del primer registro para detectar si cambió
                html_antes = driver.page_source

                siguiente = None
                # Buscar por texto exacto
                for elem in driver.find_elements(By.XPATH, "//a[contains(text(),'Siguiente')] | //font[contains(text(),'Siguiente')]/ancestor::a | //input[@value='Siguiente']"):
                    if elem.is_displayed() and elem.is_enabled():
                        siguiente = elem
                        break

                # Si no encontró, buscar cualquier link que parezca paginación
                if not siguiente:
                    for elem in driver.find_elements(By.TAG_NAME, "a"):
                        texto = (elem.text or "").strip().upper()
                        if texto == "SIGUIENTE" or "SIGUIENTE" in texto:
                            if elem.is_displayed() and elem.is_enabled():
                                siguiente = elem
                                break

                if not siguiente:
                    break  # No hay más páginas

                driver.execute_script("arguments[0].click();", siguiente)
                time.sleep(4)

                # Verificar que la página realmente cambió
                html_despues = driver.page_source
                if html_antes == html_despues:
                    print(f"    [!] Página no cambio, fin de paginacion")
                    break

                pagina += 1
            except Exception as e:
                print(f"    [!] Fin de paginacion o error: {str(e)[:60]}")
                break

        return todos_productos

    except Exception as e:
        print(f"    [!] Error Selenium: {str(e)[:80]}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _codigo_ano(anio: int) -> str:
    """Aduanet usa código de año = año real - 1992. Ej: 2025 → 33."""
    return str(anio - 1992).zfill(2)


def _consultar_requests(ruc: str, anio: int) -> list:
    """Consulta Aduanet usando requests POST con los campos exactos del formulario."""
    session = requests.Session()
    session.headers.update(HEADERS)

    # Primero GET al formulario para obtener cookies
    try:
        session.get(ADUANET_URL + "?accion=consultar&CG_consulta=1", timeout=15)
    except Exception:
        pass

    data = {
        "accion": "buscarListadoImpoExpo",
        "CG_consulta": "1",
        "CG_tipo": "4",               # 4 = RUC
        "CG_Codigo": ruc,              # campo correcto para RUC
        "CG_DNombre": "",              # vacío cuando consulta por RUC
        "CG_Aduana": "999",            # Todas las aduanas
        "CG_Ano": _codigo_ano(anio),   # código de año, ej 33 para 2025
        "CG_Mes": "00",                # Todo el año
        "CG_regimen": "40",            # 40 = EXPORTACION
    }

    try:
        resp = session.post(
            ADUANET_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if resp.status_code == 200:
            productos = _parsear_tabla_resultados(resp.text, ruc, anio)
            if productos:
                return productos
    except Exception as e:
        print(f"    [!] requests POST error: {str(e)[:80]}")

    return []


def _parsear_tabla_resultados(html: str, ruc: str, anio: int) -> list:
    """
    Parsea el HTML de respuesta de Aduanet y extrae la tabla de
    importador/exportador con DUAS, Mes, Agente, Aduana, País, FOB, CIF, etc.
    Busca específicamente la tabla que contiene filas con montos monetarios.
    """
    soup = BeautifulSoup(html, "html.parser")
    productos = []

    for tabla in soup.find_all("table"):
        filas = tabla.find_all("tr")
        if len(filas) < 3:
            continue

        # Buscar la fila de encabezado de Aduanet dentro de esta tabla
        # Encabezados típicos: LISTAR DUAS, IMPORTADOR/EXPORTADOR, MES, AGENTE, ADUANA, PAÍS, FOB, CIF, ADV, IMP. ARANCEL
        enc_idx = None
        encabezados = []

        for i, fila in enumerate(filas):
            celdas = fila.find_all(["th", "td"])
            if not celdas:
                continue
            textos = [c.get_text(strip=True) for c in celdas]
            texto_unido = " ".join(t.lower() for t in textos)

            # Saltar filas de paginación
            if any(p in texto_unido for p in ["1 a 10 de", "páginas", "siguiente", "anterior", "retroceder"]):
                continue

            # Detectar encabezado por palabras clave de Aduanet
            tiene_aduanet = sum(1 for p in ["duas", "importador", "exportador", "mes", "agente", "aduana", "país", "fob", "cif", "adv", "arancel"] if p in texto_unido)
            if tiene_aduanet >= 3 and i < len(filas) - 1:
                enc_idx = i
                encabezados = textos
                break

        if enc_idx is None:
            continue

        # Mapear columnas por nombre de encabezado
        col_map = {}
        for i_col, enc in enumerate(encabezados):
            enc_l = enc.lower()
            # NOTA: usar "listar" o "duas" (no "dua" sola, porque "aduana" contiene "dua")
            if "listar" in enc_l or "duas" in enc_l:
                col_map["dua"] = i_col
            elif any(x in enc_l for x in ["importador", "exportador"]):
                col_map["operador"] = i_col
            elif "mes" in enc_l:
                col_map["mes"] = i_col
            elif "agente" in enc_l:
                col_map["agente"] = i_col
            elif enc_l == "aduana" or enc_l.startswith("aduana ") or enc_l.endswith(" aduana"):
                col_map["aduana"] = i_col
            elif "país" in enc_l or "pais" in enc_l:
                col_map["pais"] = i_col
            elif "fob" in enc_l:
                col_map["fob"] = i_col
            elif "cif" in enc_l:
                col_map["cif"] = i_col
            elif "adv" in enc_l:
                col_map["adv"] = i_col
            elif "arancel" in enc_l:
                col_map["arancel"] = i_col

        # Si no detectó suficientes columnas, usar posiciones por defecto (layout estándar Aduanet)
        # Aduanet tipicamente: LISTAR DUAS, IMPORTADOR/EXPORTADOR, MES, AGENTE, ADUANA, PAIS, FOB, CIF, ADV, IMP. ARANCEL
        n_cols = len(encabezados)
        if n_cols >= 7:
            if "dua" not in col_map: col_map["dua"] = 0
            if "operador" not in col_map: col_map["operador"] = 1
            if "mes" not in col_map: col_map["mes"] = 2
            if "agente" not in col_map: col_map["agente"] = 3
            if "aduana" not in col_map: col_map["aduana"] = 4
            if "pais" not in col_map: col_map["pais"] = 5
            if "fob" not in col_map: col_map["fob"] = 6
            if n_cols >= 8 and "cif" not in col_map: col_map["cif"] = 7
            if n_cols >= 9 and "adv" not in col_map: col_map["adv"] = 8
            if n_cols >= 10 and "arancel" not in col_map: col_map["arancel"] = 9

        # Parsear filas de datos después del encabezado
        for fila in filas[enc_idx + 1:]:
            celdas = fila.find_all(["td", "th"])
            if not celdas:
                continue

            textos = [c.get_text(strip=True) for c in celdas]
            if not any(textos):
                continue

            texto_unido = " ".join(t.lower() for t in textos)

            # Saltar filas de paginación o totales
            if any(p in texto_unido for p in ["1 a 10 de", "páginas", "siguiente", "anterior", "retroceder", "total", "subtotal"]):
                continue

            # Saltar filas que parecen encabezados repetidos
            if any(t.lower() in ["listar duas", "importador", "exportador", "mes", "agente", "aduana"] for t in textos[:3]):
                continue

            # Una fila válida debe tener al menos un monto monetario (patrón: 1,234,567.89 o similar)
            tiene_montos = any(re.search(r"\d{1,3}(,\d{3})*\.\d{2}", t) for t in textos)
            if not tiene_montos:
                continue

            def get(col_name: str) -> str:
                idx = col_map.get(col_name)
                if idx is not None and idx < len(textos):
                    return textos[idx]
                return ""

            operador = get("operador")
            if not operador:
                continue

            productos.append({
                "dua": _limpiar(get("dua")),
                "operador": _limpiar(operador),
                "mes": _limpiar(get("mes")),
                "agente": _limpiar(get("agente")),
                "aduana": _limpiar(get("aduana")),
                "pais": _limpiar(get("pais")),
                "fob": _limpiar(get("fob")),
                "cif": _limpiar(get("cif")),
                "adv": _limpiar(get("adv")),
                "imp_arancel": _limpiar(get("arancel")),
                "url_fuente": f"{ADUANET_URL}?accion=buscarListadoImpoExpo&CG_consulta=1&CG_tipo=4&CG_Codigo={ruc}&CG_Aduana=999&CG_Ano={_codigo_ano(anio)}&CG_Mes=00&CG_regimen=40",
            })

    return productos


def _limpiar(texto: str) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


# Prueba rápida: ejecutar este archivo directamente
if __name__ == "__main__":
    ruc_test = "20330262428"
    anios_test = [2025]
    print(f"Consultando Aduanet para RUC {ruc_test}, años {anios_test}...")
    res = extraer_exportaciones_aduanet(ruc_test, anios_test)
    print(f"\nEstado : {res['estado']}")
    print(f"Total  : {len(res['productos'])} registros")
    for p in res["productos"][:5]:
        print(f"  • DUA:{p.get('dua','—')} | Operador:{p.get('operador','')[:40]} | Mes:{p.get('mes','')} | FOB:{p.get('fob','')}")
