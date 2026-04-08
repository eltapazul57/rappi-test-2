# Competitive Intelligence — Rappi vs Uber Eats vs DiDi Food

Sistema local de inteligencia competitiva que recolecta precios, delivery fees y tiempos de entrega de las principales plataformas de delivery en CDMX, con un dashboard interactivo para análisis.

---

## Instalación y uso

### Requisitos

- Python 3.11+
- Conexión a internet

### Setup

**1. Clonar el repositorio**

```bash
git clone <repo-url>
cd rappi-test-2
```

**2. Crear y activar entorno virtual**

| OS            | Comando                                               |
| ------------- | ----------------------------------------------------- |
| macOS / Linux | `python -m venv .venv && source .venv/bin/activate` |
| Windows       | `python -m venv .venv && .venv\Scripts\activate`    |

**3. Instalar dependencias**

```bash
pip install -r requirements.txt
playwright install chromium
```

> En Linux puede ser necesario: `playwright install-deps chromium` antes de `playwright install chromium`

**4. Correr el dashboard**

```bash
streamlit run app/app.py
```

El dashboard abre en `http://localhost:8501`. Desde ahí se puede **ejecutar el scraper directamente** usando el botón en la pestaña "Datos & Scraping" — no es necesario correr ningún comando adicional desde la terminal.

### Insights con IA

```bash
cp .env.example .env
# Agregar OPENAI_API_KEY en .env
```

---

## Arquitectura

```
/
├── scraper/
│   ├── config.py       # Direcciones, productos y constantes
│   ├── base.py         # Clase abstracta AbstractScraper + ScrapeResult
│   ├── rappi.py        # Scraper Rappi (Playwright)
│   ├── uber_eats.py    # Scraper Uber Eats (Playwright)
│   ├── didi_food.py    # Scraper DiDi Food (Playwright, no funcional — ver nota)
│   ├── runner.py       # Orquestador CLI
│   └── utils.py        # Rate limiting, retry, logging, parseo de precios
├── app/
│   ├── app.py          # Dashboard Streamlit
│   ├── charts.py       # Visualizaciones Plotly
│   └── ai_insights.py  # Generación de insights con OpenAI (opcional)
├── data/
│   └── competitive_data.csv   # Output del scraper (generado en runtime)
└── scripts/
    ├── debug_rappi.py          # Diagnóstico visual para Rappi
    └── scrape_loop.sh          # Loop con backups automáticos
```

### Stack técnico

- **Playwright** — automatización de browser para scraping (anti-bot real)
- **Streamlit** — dashboard interactivo
- **Plotly** — visualizaciones
- **Pandas** — procesamiento del CSV
- **OpenAI API** — generación de insights

### Flujo de datos

1. `runner.py` orquesta los scrapers en paralelo por plataforma y dirección
2. Cada scraper extiende `AbstractScraper` e implementa `scrape(product, address) → ScrapeResult`
3. Los resultados se consolidan en `data/competitive_data.csv`
4. El dashboard lee el CSV y genera análisis en tiempo real

---

## Cobertura geográfica y productos

### Zonas de CDMX

| ID | Zona              | Dirección                 | Criterio                             |
| -- | ----------------- | -------------------------- | ------------------------------------ |
| 1  | Polanco           | Presidente Masaryk 360     | Zona premium, alto poder adquisitivo |
| 2  | Condesa / Roma    | Av. Ámsterdam 101         | Alta competencia entre plataformas   |
| 3  | Centro Histórico | Madero 32                  | Alta densidad, logística compleja   |
| 4  | Coyoacán         | Francisco Sosa 58          | Residencial clase media              |
| 5  | Iztapalapa        | Av. Telecomunicaciones 320 | Periferia, menor cobertura           |

Las zonas fueron seleccionadas para representar distintos perfiles socioeconómicos y niveles de cobertura en CDMX.

### Productos de referencia

| Producto        | Categoría   | Justificación                    |
| --------------- | ------------ | --------------------------------- |
| Big Mac         | Restaurante  | Benchmark universal de precios    |
| Whopper         | Restaurante  | Competidor directo de Big Mac     |
| Pizza Pepperoni | Restaurante  | Ticket medio, alta demanda        |
| Coca-Cola 600ml | Conveniencia | Producto de referencia en tiendas |

---

## Estado de las plataformas

| Plataforma | Estado       | Notas                                                                                                                       |
| ---------- | ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Rappi      | Funcional    | Cloudflare puede bloquear en headless mode                                                                                  |
| Uber Eats  | Funcional    | —                                                                                                                          |
| DiDi Food  | No funcional | Requiere número de teléfono para mostrar productos; limitación de tiempo impidió implementar el flujo de autenticación |

DiDi Food exige autenticación vía SMS antes de mostrar cualquier listado de productos, lo que hace inviable el scraping sin un flujo de login automatizado. Todos sus resultados se registran como `not_available`.

---

## Esquema del CSV

| Columna                | Tipo     | Descripción                                   |
| ---------------------- | -------- | ---------------------------------------------- |
| `timestamp`          | ISO 8601 | Momento del scrape                             |
| `platform`           | string   | `rappi` \| `uber_eats` \| `didi_food`    |
| `address_id`         | int      | 1–5, referencia a dirección en `config.py` |
| `zone`               | string   | Nombre de la zona                              |
| `product`            | string   | Clave del producto                             |
| `price`              | float    | Precio en MXN                                  |
| `delivery_fee`       | float    | Fee de envío en MXN                           |
| `estimated_time_min` | int      | Tiempo estimado en minutos                     |
| `promotions`         | string   | Texto libre, vacío si no hay                  |
| `scrape_status`      | string   | `success` \| `error` \| `not_available`  |

---

## Limitaciones conocidas

1. **Anti-bot**: Rappi usa Cloudflare; puede fallar en headless mode. Ver `scripts/debug_rappi.py` para diagnóstico visual.
2. **Selectores CSS frágiles**: Cualquier deploy de las plataformas puede romperlos.
3. **Sin proxies rotativos**: Solución cost-effective; mayor riesgo de bloqueo.
4. **Datos puntuales**: Snapshot del momento de scraping, no promedio histórico.
5. **Solo CDMX**: 5 zonas representativas, no estadísticamente significativo para producción.

### Troubleshooting rápido

```bash
# Timeout — aumentar en scraper/config.py:
REQUEST_TIMEOUT_MS = 60_000
PAGE_LOAD_TIMEOUT_MS = 120_000

# Cloudflare bloquea Rappi — en scraper/rappi.py:
playwright.chromium.launch(headless=False)  # modo visual para debugging
```

---

## Consideraciones éticas

- Rate limiting de 3–6 segundos entre requests
- ~30 requests por ejecución completa
- Diseñado para análisis puntual, no monitoreo continuo
