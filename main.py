"""
Scraper completo: RUC → SUNAT → Web/Contactos → Aduanet → Excel

Pasos:
  1. Pide el RUC y los años a consultar
  2. Consulta SUNAT para obtener razón social y dirección
  3. Busca la web de la empresa y extrae contactos
  4. Consulta Aduanet para obtener exportaciones
  5. Exporta todo a un Excel con formato

Uso:
  python main.py
"""

import sys
import time
import requests

from pasos import (
    consultar_sunat,
    buscar_url_empresa,
    extraer_contactos_web,
    extraer_exportaciones_aduanet,
    exportar_excel,
)

# Pausa entre pasos para no sobrecargar los servidores
PAUSA = 2


def banner():
    print()
    print("=" * 60)
    print("   EXPORTACIONES PERU - SCRAPER POR RUC")
    print("   Fuentes: SUNAT + Web de empresa + Aduanet")
    print("=" * 60)


def pedir_ruc() -> str:
    while True:
        ruc = input("\n  Ingresa el RUC (11 dígitos): ").strip()
        if len(ruc) == 11 and ruc.isdigit():
            return ruc
        print("  [!] RUC inválido — debe tener exactamente 11 dígitos.")


def pedir_anios() -> list:
    print("\n  Años disponibles: 2018 - 2025")
    entrada = input(
        "  Ingresa los años separados por coma (ej: 2023,2024,2025): "
    ).strip()
    anios = []
    for a in entrada.split(","):
        a = a.strip()
        if a.isdigit() and 2000 <= int(a) <= 2030:
            anios.append(int(a))
    if not anios:
        print("  No se ingresaron años válidos. Usando 2025 por defecto.")
        anios = [2025]
    return sorted(set(anios))


def main():
    banner()
    ruc   = pedir_ruc()
    anios = pedir_anios()

    print(f"\n  RUC  : {ruc}")
    print(f"  Años : {anios}")
    confirmar = input("\n  Continuar? [S/n]: ").strip().lower()
    if confirmar == "n":
        print("  Cancelado.")
        sys.exit(0)

    session = requests.Session()

    # Estructura que se va llenando en cada paso y al final se exporta a Excel
    resultado = {
        "ruc":              ruc,
        "razon_social":     "",
        "url":              "",
        "direccion_sunat":  "",
        "estado_web":       "sin_web",
        "mensaje":          "",
        "productos":        [],
        "paginas_visitadas": [],
        "anios":            anios,
        "contactos": {
            "telefonos":      [],
            "emails":         [],
            "direccion":      "",
            "redes_sociales": [],
        },
    }

    # Paso 1: SUNAT
    print(f"\n  [1/3] Consultando SUNAT para RUC {ruc}...")
    sunat = consultar_sunat(ruc, session)
    if sunat.get("ok"):
        resultado["razon_social"]    = sunat["razon_social"]
        resultado["direccion_sunat"] = sunat.get("direccion", "")
        print(f"        Empresa      : {sunat['razon_social']}")
        print(f"        Estado       : {sunat.get('estado', '-')}")
        print(f"        Localización : {sunat.get('direccion', '-')[:80]}")
    else:
        resultado["razon_social"] = f"EMPRESA RUC {ruc}"
        print("        [!] SUNAT no respondió. Se usará el RUC como nombre.")

    # Paso 2: Buscar web y extraer contactos
    print(f"\n  [2/3] Buscando web y contactos de: {resultado['razon_social'][:50]}...")
    time.sleep(PAUSA)

    url_data = buscar_url_empresa(resultado["razon_social"], ruc)
    if url_data["encontrado"]:
        resultado["url"] = url_data["url"]
        print(f"        [OK] URL: {url_data['url']}")
        print(f"        Extrayendo contactos...")

        contactos = extraer_contactos_web(url_data["url"])
        if contactos.get("ok"):
            resultado["contactos"] = {
                "telefonos":      contactos.get("telefonos", []),
                "emails":         contactos.get("emails", []),
                "direccion":      contactos.get("direccion", ""),
                "redes_sociales": contactos.get("redes_sociales", []),
            }
            tel   = ", ".join(contactos.get("telefonos", [])[:2]) or "-"
            mail  = ", ".join(contactos.get("emails", [])[:2]) or "-"
            direc = contactos.get("direccion", "")[:60] or "-"
            print(f"        Teléfonos : {tel}")
            print(f"        Emails    : {mail}")
            print(f"        Dirección : {direc}")
            if contactos.get("redes_sociales"):
                print(f"        Redes     : {contactos['redes_sociales'][0]}")
        else:
            print("        [!] No se pudieron extraer contactos.")
    else:
        resultado["estado_web"] = "sin_web"
        print("        [X] No se encontró página web para esta empresa.")

    # Paso 3: Aduanet - exportaciones
    print(f"\n  [3/3] Consultando Aduanet para años: {anios}...")

    aduanet = extraer_exportaciones_aduanet(ruc, anios)
    n_prod  = len(aduanet.get("productos", []))
    resultado["productos"]         = aduanet.get("productos", [])
    resultado["paginas_visitadas"] = aduanet.get("paginas_visitadas", [])
    resultado["mensaje"]           = aduanet.get("mensaje", "")

    if aduanet["estado"] == "ok":
        resultado["estado_web"] = "ok"
        print(f"\n  [OK] {n_prod} registros de exportación encontrados")
        print("\n  Primeros registros:")
        for p in resultado["productos"][:5]:
            print(f"    DUA: {p.get('dua', '-')} | Operador: {p.get('operador', '')[:40]}")
            print(f"    Mes: {p.get('mes', '')} | Aduana: {p.get('aduana', '')} | País: {p.get('pais', '')}")
            if p.get("fob"):
                print(f"    FOB: US$ {p['fob']}")
            print()
    else:
        resultado["estado_web"] = "sin_productos"
        print(f"  [!] Sin exportaciones en Aduanet: {aduanet['mensaje']}")

    # Exportar a Excel
    print("\n  Exportando a Excel...")
    ruta = exportar_excel([resultado])

    # Resumen final
    print(f"\n{'=' * 60}")
    print("  RESUMEN")
    print(f"  RUC          : {ruc}")
    print(f"  Empresa      : {resultado['razon_social']}")
    print(f"  Localización : {resultado['direccion_sunat'] or '-'}")
    print(f"  URL          : {resultado['url'] or '- sin web -'}")
    print(f"  Teléfonos    : {', '.join(resultado['contactos']['telefonos'][:2]) or '-'}")
    print(f"  Emails       : {', '.join(resultado['contactos']['emails'][:2]) or '-'}")
    print(f"  Exportaciones: {n_prod}")
    print(f"  Excel        : {ruta}")
    print(f"{'=' * 60}\n")

    print("  ¿Consultar otra empresa? [S/n]: ", end="")
    if input().strip().lower() != "n":
        main()


if __name__ == "__main__":
    main()
