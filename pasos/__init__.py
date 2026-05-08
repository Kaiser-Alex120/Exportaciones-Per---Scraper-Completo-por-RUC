# pasos/ — módulos del scraper de exportaciones Perú
# Cada módulo expone su función principal para ser llamada desde main.py

from .sunat           import consultar_sunat
from .buscar_url      import buscar_url_empresa
from .contactos_web   import extraer_contactos_web
from .aduanet         import extraer_exportaciones_aduanet
from .exportar_excel  import exportar_excel, importar_excel_aduanet

__all__ = [
    "consultar_sunat",
    "buscar_url_empresa",
    "extraer_contactos_web",
    "extraer_exportaciones_aduanet",
    "exportar_excel",
    "importar_excel_aduanet",
]
