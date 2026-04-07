"""
utils.py — Utilidades compartidas para los scrapers.

Incluye:
- setup_logging(): configura el logger raíz con formato consistente
- random_delay(): sleep aleatorio entre RATE_LIMIT_MIN y RATE_LIMIT_MAX
- retry(): decorador de reintentos con backoff exponencial (sin dependencias externas)
- get_random_user_agent(): rota User-Agents para evitar fingerprinting
- parse_price(): normaliza strings de precio a float (maneja "$89.00", "89", "89,00")
"""

from __future__ import annotations

import functools
import logging
import random
import re
import time
from typing import Callable, TypeVar

from scraper.config import RATE_LIMIT_MIN, RATE_LIMIT_MAX, USER_AGENTS

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(level: int = logging.INFO) -> None:
    """
    Configura el logger raíz con formato legible.
    Llamar una vez al inicio de runner.py o del dashboard.

    Decisión: un solo handler a stdout (no a archivo) para no llenar disco
    en ejecuciones de demo. El CSV ya es el output persistente.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def random_delay(
    min_seconds: float = RATE_LIMIT_MIN,
    max_seconds: float = RATE_LIMIT_MAX,
) -> None:
    """
    Sleep por un tiempo aleatorio dentro del rango configurado.
    Llamar entre requests para respetar el rate limiting ético.

    Por qué aleatorio y no fijo: los patrones fijos de timing son más
    detectables por sistemas anti-bot que los intervalos variables.
    """
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug("Rate limit delay: %.2fs", delay)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def retry(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Decorador de reintentos con backoff exponencial.

    Args:
        max_attempts: número máximo de intentos (incluyendo el primero)
        base_delay: segundos de espera base; se multiplica por 2^intento
        exceptions: tupla de excepciones que disparan el retry

    Uso:
        @retry(max_attempts=3, exceptions=(TimeoutError, PlaywrightError))
        def mi_funcion():
            ...

    Decisión: implementado sin tenacity para no agregar dependencias.
    El backoff exponencial (2, 4, 8s) es suficiente para el volumen bajo
    de este proyecto (~30 requests por ejecución).
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_attempts:
                        logger.error(
                            "%s falló después de %d intentos: %s",
                            func.__name__,
                            max_attempts,
                            exc,
                        )
                        raise
                    wait = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "%s — intento %d/%d falló (%s). Reintentando en %.1fs...",
                        func.__name__,
                        attempt,
                        max_attempts,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
            raise last_exception  # nunca llega aquí, pero satisface el type checker
        return wrapper  # type: ignore[return-value]
    return decorator


# ---------------------------------------------------------------------------
# User-Agent rotation
# ---------------------------------------------------------------------------

def get_random_user_agent() -> str:
    """Devuelve un User-Agent aleatorio de la lista configurada en config.py."""
    return random.choice(USER_AGENTS)


# ---------------------------------------------------------------------------
# Parseo de precios
# ---------------------------------------------------------------------------

def parse_price(raw: str) -> float | None:
    """
    Convierte un string de precio extraído del DOM a float.

    Maneja formatos comunes en apps mexicanas:
        "$89.00"  → 89.0
        "89"      → 89.0
        "89,00"   → 89.0   (formato europeo que a veces aparece)
        "Gratis"  → 0.0
        "N/A"     → None

    Returns:
        float con el precio, 0.0 si es gratis, None si no parseable.
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.strip().lower()

    if raw in ("gratis", "free", "$0", "0"):
        return 0.0

    # Remover símbolos de moneda y espacios
    cleaned = re.sub(r"[$ mxn\s]", "", raw, flags=re.IGNORECASE)

    # Normalizar separador decimal: "89,00" → "89.00"
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned)
    except ValueError:
        logger.debug("No se pudo parsear precio: %r", raw)
        return None


def parse_time_minutes(raw: str) -> int | None:
    """
    Convierte un string de ETA a entero de minutos.

    Maneja formatos como:
        "25-35 min"  → 30  (promedio)
        "25 min"     → 25
        "1 hr"       → 60
        "1h 30min"   → 90

    Returns:
        int con los minutos estimados, None si no parseable.
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.strip().lower()

    # Rango: "25-35 min" → promedio
    range_match = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*min", raw)
    if range_match:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        return (lo + hi) // 2

    # Horas + minutos: "1h 30min" o "1 hr 30 min"
    hm_match = re.search(r"(\d+)\s*h[r]?\s*(\d+)\s*min", raw)
    if hm_match:
        return int(hm_match.group(1)) * 60 + int(hm_match.group(2))

    # Solo horas: "1 hr"
    h_match = re.search(r"(\d+)\s*h[r]?", raw)
    if h_match:
        return int(h_match.group(1)) * 60

    # Solo minutos: "25 min"
    m_match = re.search(r"(\d+)\s*min", raw)
    if m_match:
        return int(m_match.group(1))

    logger.debug("No se pudo parsear tiempo: %r", raw)
    return None
