# Exportaciones Perú - Scraper Completo por RUC

Sistema automatizado para extraer datos de exportaciones de empresas peruanas combinando información de SUNAT, páginas web oficiales y Aduanet.

## Flujo del Sistema

```
RUC → SUNAT (razón social + localización) → Web (contactos + redes) → Aduanet (exportaciones) → Excel final
```

## Requisitos

- Python 3.10+
- Google Chrome instalado

**Dependencias principales:**
- `selenium` - Automatización de navegador
- `beautifulsoup4` - Scraping web
- `requests` - Peticiones HTTP
- `openpyxl` - Generación de Excel
- `pandas` - Procesamiento de datos
- `webdriver-manager` - Gestión automática de ChromeDriver

## Instalación y Configuración

### 1. Crear entorno virtual (Windows)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Ejecutar el scraper
```bash
python main.py
```

## Modo de Uso

Al ejecutar `main.py`, el programa solicitará por consola:
1. **RUC**: Ingresar 11 dígitos numéricos.
2. **Años**: Separados por coma (ej: `2023,2024,2025`).

El scraper trabajará automáticamente en segundo plano. Al finalizar, generará un reporte en Excel.

### Salida
- Excel final consolidado en la carpeta `output/`
- Hojas generadas: **Resumen Empresas**, **Exportaciones**, y **Sin Página Web**.

## Estructura del Excel Generado

### Hoja 1: Resumen Empresas
Una vista general y profesional del estado de cada empresa consultada.

| Columna | Contenido |
|---------|-----------|
| N, RUC, RAZÓN SOCIAL, URL | Información básica |
| LOCALIZACIÓN | Dirección fiscal según SUNAT |
| TELÉFONO, EMAIL, REDES SOCIALES | Datos de contacto extraídos de la web |
| ESTADO, N° EXPORTACIONES, OBSERVACIÓN | Resultado del procesamiento |

### Hoja 2: Exportaciones
Tabla detallada de productos exportados. Ordenado por MES (más reciente → más antiguo).

| Columna | Fuente |
|---------|--------|
| N° | Auto |
| RUC | SUNAT |
| RAZÓN SOCIAL | SUNAT |
| WEB EMPRESA | Google Search |
| DUA | Aduanet |
| OPERADOR/IMPORTADOR | Aduanet |
| MES | Aduanet |
| AGENTE ADUANERO | Aduanet |
| ADUANA | Aduanet |
| PAÍS DESTINO | Aduanet |
| FOB (US$) | Aduanet |

## Estructura del Proyecto

```
WEB_scrapping/
├── main.py                    # Entrada principal del programa
├── pasos/                     # Módulos del scraper
│   ├── __init__.py
│   ├── sunat.py               # Consulta SUNAT por RUC
│   ├── buscar_url.py          # Búsqueda de URL en Google
│   ├── contactos_web.py       # Extracción de contactos de sitio web
│   ├── aduanet.py             # Scraping de exportaciones en Aduanet
│   ├── extraer_productos.py   # Extracción adicional de info de la web
│   └── exportar_excel.py      # Generación de archivo Excel
├── requirements.txt           # Dependencias del proyecto
├── README.md                  # Este archivo
├── output/                    # Carpeta de archivos generados (se crea automáticamente)
└── .venv/                     # Entorno virtual
```

## Características Implementadas

- **Consulta SUNAT**: Extrae razón social, estado y localización. Compatible con protecciones JavaScript y Cloudflare.
- **Búsqueda Web Inteligente**: Localiza página oficial de la empresa y filtra resultados falsos.
- **Extracción de Contactos**: Detecta teléfonos peruanos (+51, 9xx, 01-xxx-xxxx), emails y redes sociales. Prioriza footer/header del sitio web.
- **Procesamiento Aduanet**: Extrae automáticamente todas las páginas de resultados de exportaciones.
- **Ordenamiento Inteligente**: Exportaciones ordenadas cronológicamente (más reciente primero). Consolidación automática de múltiples años.
- **Compatibilidad**: Windows, Linux y macOS. Gestión automática de ChromeDriver.

## Filtros Web

El buscador automático excluye dominios que no representan webs corporativas, como:
- `blogspot.com`, `blogger.com` (blogs)
- `wordpress.com`, `wordpress.org` (WordPress)
- Redes sociales (`facebook.com`, `instagram.com`, `linkedin.com`, etc.)
- Directorios comerciales genéricos.

## Errores Comunes

| Error | Solución |
|-------|----------|
| `ChromeDriver error` | Instalar Chrome en el equipo o actualizar webdriver-manager. |
| `SUNAT timeout` | Esperar unos minutos antes de reintentar (posible bloqueo temporal). |
| `RUC no encontrado` | Verificar que el RUC sea válido y esté activo. |
| `Sin conexión a Aduanet` | Verificar conexión a internet o intentar más tarde (los servidores de aduanas pueden estar en mantenimiento). |
