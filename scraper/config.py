"""
config.py — Configuración central del sistema de scraping.

Contiene: direcciones de CDMX, productos de referencia, y constantes
de comportamiento (rate limiting, timeouts, rutas de output).
"""

from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
OUTPUT_CSV = DATA_DIR / "competitive_data.csv"

# ---------------------------------------------------------------------------
# Rate limiting (segundos)
# Ética: mínimo 3-5s entre requests según CONTEXT.md
# ---------------------------------------------------------------------------

RATE_LIMIT_MIN: float = 3.0
RATE_LIMIT_MAX: float = 6.0  # un poco más de margen para evitar patrones detectables
REQUEST_TIMEOUT_MS: int = 30_000  # 30 segundos — Playwright timeout por operación
PAGE_LOAD_TIMEOUT_MS: int = 60_000  # 60 segundos — tiempo máximo para cargar una página

# ---------------------------------------------------------------------------
# Direcciones de CDMX
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Address:
    id: int
    zone: str
    street: str
    neighborhood: str
    lat: float
    lng: float
    description: str  # justificación de la selección


ADDRESSES: list[Address] = [
    Address(
        id=1,
        zone="polanco",
        street="Presidente Masaryk 360",
        neighborhood="Polanco V Sección",
        lat=19.4326,
        lng=-99.1995,
        description="Alto poder adquisitivo, alta densidad de restaurantes. Benchmark zona premium.",
    ),
    Address(
        id=2,
        zone="condesa_roma",
        street="Av. Ámsterdam 101",
        neighborhood="Hipódromo Condesa",
        lat=19.4104,
        lng=-99.1727,
        description="Clase media-alta, mayor competencia entre plataformas.",
    ),
    Address(
        id=3,
        zone="centro_historico",
        street="Madero 32",
        neighborhood="Centro Histórico",
        lat=19.4333,
        lng=-99.1333,
        description="Alta densidad poblacional, logística compleja, alto volumen.",
    ),
    Address(
        id=4,
        zone="coyoacan",
        street="Francisco Sosa 58",
        neighborhood="Coyoacán",
        lat=19.3500,
        lng=-99.1627,
        description="Residencial clase media, zona intermedia.",
    ),
    Address(
        id=5,
        zone="iztapalapa",
        street="Av. Telecomunicaciones 320",
        neighborhood="Iztapalapa",
        lat=19.3557,
        lng=-99.0613,
        description="Periferia, menor cobertura. Edge case / zona de expansión.",
    ),
]

# Índice rápido por id para lookup en scrapers
ADDRESS_BY_ID: dict[int, Address] = {a.id: a for a in ADDRESSES}

# ---------------------------------------------------------------------------
# Productos de referencia
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Product:
    key: str           # identificador interno (snake_case)
    display_name: str  # nombre a buscar en las plataformas
    category: str      # "restaurant" | "convenience"


PRODUCTS: list[Product] = [
    Product(
        key="big_mac",
        display_name="Big Mac",
        category="restaurant",
    ),
    Product(
        key="coca_cola_600ml",
        display_name="Coca-Cola 600ml",
        category="convenience",
    ),
    Product(
        key="whopper",
        display_name="Whopper",
        category="restaurant",
    ),
    Product(
        key="pizza_pepperoni",
        display_name="Pizza Pepperoni",
        category="restaurant",
    ),
    Product(
        key="coca_cola_600ml_711",
        display_name="Coca-Cola 600ml",
        category="convenience",
    ),
]

PRODUCT_BY_KEY: dict[str, Product] = {p.key: p for p in PRODUCTS}

# ---------------------------------------------------------------------------
# Plataformas
# ---------------------------------------------------------------------------

PLATFORMS: list[str] = ["rappi", "uber_eats", "didi_food"]

# ---------------------------------------------------------------------------
# Constantes de scraping por plataforma
# Decisión: centralizar URLs base aquí para que cambios futuros sean un
# solo punto de edición, no requieren tocar los scrapers individuales.
# ---------------------------------------------------------------------------

PLATFORM_BASE_URLS: dict[str, str] = {
    "rappi": "https://www.rappi.com.mx",
    "uber_eats": "https://www.ubereats.com/mx",
    "didi_food": "https://www.didi-food.com/es-MX/food/",
}

# User-Agent realista — se rota aleatoriamente en utils.py
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]
