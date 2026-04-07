# Competitive Intelligence — Rappi vs Uber Eats vs DiDi Food

Sistema local de inteligencia competitiva que recolecta precios, delivery fees y tiempos de entrega de las 3 principales plataformas de delivery en CDMX.

---

## Setup

### Requisitos
- Python 3.11+
- Conexión a internet (para scraping real) o datos de backup pre-generados

### Instalación

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd rappi-test-2

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Instalar browsers de Playwright
# IMPORTANTE: este paso es necesario además del pip install
playwright install chromium
```

---

## Cómo correr el scraper

### Opción A — Scraping completo (todas las plataformas)
```bash
python -m scraper.runner
```
Output: `data/competitive_data.csv`

### Opción B — Solo algunas plataformas
```bash
python -m scraper.runner --platforms rappi uber_eats
```

### Opción C — Modo dry-run (sin scraping real, usa datos de backup)
```bash
python -m scraper.runner --dry-run
```
Útil para demo cuando las plataformas están aplicando bloqueos anti-bot.

### Opción D — Append (agrega al CSV sin sobreescribir)
```bash
python -m scraper.runner --append
```
Útil para recolectar múltiples snapshots en el tiempo.

---

## Cómo correr el dashboard

```bash
streamlit run app/app.py
```

El dashboard abre automáticamente en `http://localhost:8501`.

**El dashboard siempre funciona**: si no existe `data/competitive_data.csv`, carga automáticamente `data/competitive_data_backup.csv` con datos pre-generados.

### Pestañas del dashboard
- **Datos & Scraping**: tabla interactiva, KPIs, botón para ejecutar el scraper desde la UI
- **Insights Competitivos**: Top 5 findings con visualizaciones Plotly

---

## Estructura del proyecto

```
/
├── scraper/
│   ├── config.py       # Direcciones, productos, constantes
│   ├── base.py         # Clase abstracta AbstractScraper + ScrapeResult
│   ├── rappi.py        # Scraper Rappi (Playwright)
│   ├── uber_eats.py    # Scraper Uber Eats (Playwright)
│   ├── didi_food.py    # Scraper DiDi Food (Playwright)
│   ├── runner.py       # Orquestador CLI
│   └── utils.py        # Rate limiting, retry, logging, parseo de precios
├── data/
│   ├── competitive_data.csv          # Output del scraper (generado)
│   └── competitive_data_backup.csv   # Datos pre-generados (siempre disponible)
├── app/
│   ├── app.py          # Dashboard Streamlit
│   └── charts.py       # Visualizaciones Plotly
└── requirements.txt
```

---

## Esquema del CSV

| Columna | Tipo | Descripción |
|---|---|---|
| `timestamp` | ISO 8601 | Momento del scrape |
| `platform` | string | `rappi` \| `uber_eats` \| `didi_food` |
| `address_id` | int | 1-5, referencia a dirección en `config.py` |
| `zone` | string | Nombre de la zona (`polanco`, `condesa_roma`, etc.) |
| `product` | string | `big_mac` \| `coca_cola_600ml` |
| `price` | float | Precio del producto en MXN |
| `delivery_fee` | float | Fee de envío en MXN |
| `estimated_time_min` | int | Tiempo estimado en minutos |
| `promotions` | string | Texto libre, vacío si no hay |
| `scrape_status` | string | `success` \| `error` \| `not_available` |

---

## Limitaciones conocidas

1. **Anti-bot**: Las 3 plataformas detectan automatización. El scraping puede fallar. Usar `--dry-run` si ocurre en demo.

2. **Selectores CSS frágiles**: Cualquier deploy de las plataformas puede romper los scrapers. Los selectores fueron validados en la fecha indicada en cada archivo `scraper/*.py`.

3. **Datos puntuales**: Los precios son un snapshot del momento de scraping, no un promedio. Los precios dinámicos pueden variar por hora y demanda.

4. **Sin proxies rotativos**: Trade-off aceptado. Mayor riesgo de bloqueo, pero solución cost-effective como el caso requiere.

5. **Solo CDMX**: El análisis cubre 5 zonas representativas de CDMX. No es estadísticamente significativo para decisiones de pricing en producción.

6. **DiDi Food — cobertura limitada**: DiDi Food no tiene cobertura en todas las zonas (ej. Iztapalapa). Estos casos se registran como `not_available` en el CSV.

---

## Troubleshooting

### El scraper falla con `TimeoutError`
Las plataformas están tardando más de lo esperado. Intentar:
```bash
# Aumentar timeout en scraper/config.py:
REQUEST_TIMEOUT_MS = 60_000   # subir de 30s a 60s
PAGE_LOAD_TIMEOUT_MS = 120_000
```

### Cloudflare bloquea Rappi
Rappi usa Cloudflare. En headless mode puede fallar. Opción temporal:
```python
# En scraper/rappi.py, cambiar headless=True por headless=False
# para debugging visual
playwright.chromium.launch(headless=False)
```

### `playwright install` falla
```bash
# Instalar dependencias del sistema (Linux)
playwright install-deps chromium
playwright install chromium
```

### El dashboard muestra datos vacíos
Verificar que `data/competitive_data_backup.csv` existe. Si no:
```bash
python -m scraper.runner --dry-run
```

---

## Consideraciones éticas

- Rate limiting de 3-6 segundos entre requests (configurable en `scraper/config.py`)
- Volumen mínimo de requests: ~30 por ejecución completa
- Diseñado para análisis puntual, no monitoreo continuo
- No se usan proxies ni técnicas de evasión agresivas
