"""
runner.py — Orquestador del sistema de scraping competitivo.

Uso desde línea de comando:
    python -m scraper.runner                  # scraping completo, sobreescribe CSV
    python -m scraper.runner --append         # agrega al CSV existente (series de tiempo)
    python -m scraper.runner --platforms rappi uber_eats   # solo algunas plataformas
    python -m scraper.runner --dry-run        # carga backup sin scraping real

El output siempre es data/competitive_data.csv en el formato definido en CONTEXT.md.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scraper.base import ScrapeResult
from scraper.config import OUTPUT_CSV, BACKUP_CSV, PLATFORMS
from scraper.rappi import RappiScraper
from scraper.uber_eats import UberEatsScraper
from scraper.didi_food import DiDiFoodScraper
from scraper.utils import setup_logging, random_delay

logger = logging.getLogger(__name__)

# Mapa de nombre de plataforma → clase scraper
SCRAPER_CLASSES = {
    "rappi": RappiScraper,
    "uber_eats": UberEatsScraper,
    "didi_food": DiDiFoodScraper,
}

# Columnas en el orden del esquema del CONTEXT.md
CSV_COLUMNS = [
    "timestamp",
    "platform",
    "address_id",
    "zone",
    "product",
    "price",
    "delivery_fee",
    "estimated_time_min",
    "promotions",
    "scrape_status",
]


# ---------------------------------------------------------------------------
# Conversión de resultados a DataFrame
# ---------------------------------------------------------------------------

def results_to_dataframe(results: list[ScrapeResult]) -> pd.DataFrame:
    """
    Convierte una lista de ScrapeResult al DataFrame del esquema CSV.
    La columna error_message se omite del CSV final (es solo para logging).
    """
    rows = []
    for r in results:
        rows.append({
            "timestamp": r.timestamp,
            "platform": r.platform,
            "address_id": r.address_id,
            "zone": r.zone,
            "product": r.product,
            "price": r.price,
            "delivery_fee": r.delivery_fee,
            "estimated_time_min": r.estimated_time_min,
            "promotions": r.promotions,
            "scrape_status": r.scrape_status,
        })
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


# ---------------------------------------------------------------------------
# Guardado del CSV
# ---------------------------------------------------------------------------

def save_results(df: pd.DataFrame, append: bool = False) -> Path:
    """
    Guarda el DataFrame en data/competitive_data.csv.

    Args:
        df: DataFrame con los resultados del scraping.
        append: si True, agrega filas al CSV existente en lugar de sobreescribir.

    Returns:
        Path del archivo guardado.
    """
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    if append and OUTPUT_CSV.exists():
        existing = pd.read_csv(OUTPUT_CSV)
        df = pd.concat([existing, df], ignore_index=True)
        logger.info("Modo append: %d filas existentes + %d nuevas", len(existing), len(df) - len(existing))

    df.to_csv(OUTPUT_CSV, index=False)
    logger.info("CSV guardado en %s (%d filas)", OUTPUT_CSV, len(df))
    return OUTPUT_CSV


# ---------------------------------------------------------------------------
# Función principal de scraping
# ---------------------------------------------------------------------------

def run_scraping(
    platforms: list[str] | None = None,
    append: bool = False,
) -> pd.DataFrame:
    """
    Ejecuta el scraping en las plataformas indicadas y guarda el CSV.

    Args:
        platforms: lista de plataformas a scrapear. None = todas.
        append: si True, agrega al CSV existente.

    Returns:
        DataFrame con todos los resultados (éxitos + errores).
    """
    platforms = platforms or PLATFORMS
    all_results: list[ScrapeResult] = []

    logger.info(
        "Iniciando scraping — plataformas: %s — %s",
        ", ".join(platforms),
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    for platform_name in platforms:
        scraper_class = SCRAPER_CLASSES.get(platform_name)
        if not scraper_class:
            logger.warning("Plataforma desconocida: %s — ignorando", platform_name)
            continue

        logger.info("--- Iniciando scraper: %s ---", platform_name)
        scraper = scraper_class()

        try:
            results = scraper.scrape_all()
            all_results.extend(results)
            logger.info(
                "%s: completado — %d resultados",
                platform_name,
                len(results),
            )
        except Exception as exc:
            logger.error("Error fatal en scraper %s: %s", platform_name, exc, exc_info=True)

        # Delay entre plataformas (además del delay interno entre requests)
        if platform_name != platforms[-1]:
            random_delay(min_seconds=5.0, max_seconds=10.0)

    if not all_results:
        logger.error("No se obtuvieron resultados. Verificar conectividad y anti-bot.")
        return pd.DataFrame(columns=CSV_COLUMNS)

    df = results_to_dataframe(all_results)
    save_results(df, append=append)

    # Resumen de resultados
    success_count = df[df["scrape_status"] == "success"].shape[0]
    error_count = df[df["scrape_status"] == "error"].shape[0]
    na_count = df[df["scrape_status"] == "not_available"].shape[0]
    logger.info(
        "Resumen: %d éxitos | %d errores | %d no disponibles | %d total",
        success_count, error_count, na_count, len(df),
    )

    return df


# ---------------------------------------------------------------------------
# Modo dry-run (para demo sin scraping real)
# ---------------------------------------------------------------------------

def run_dry_run() -> pd.DataFrame:
    """
    Copia el backup CSV a competitive_data.csv sin ejecutar scraping.
    Útil para demo cuando las plataformas están bloqueando.
    """
    if not BACKUP_CSV.exists():
        logger.error("Backup CSV no encontrado en %s", BACKUP_CSV)
        sys.exit(1)

    df = pd.read_csv(BACKUP_CSV)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    logger.info("Dry-run: copiado backup → %s (%d filas)", OUTPUT_CSV, len(df))
    return df


# ---------------------------------------------------------------------------
# Entry point CLI
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Sistema de scraping competitivo para Rappi vs Uber Eats vs DiDi Food"
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=PLATFORMS,
        default=None,
        help="Plataformas a scrapear. Default: todas.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Agregar resultados al CSV existente en lugar de sobreescribir.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Usar datos del backup sin ejecutar scraping real.",
    )

    args = parser.parse_args()

    if args.dry_run:
        run_dry_run()
    else:
        run_scraping(platforms=args.platforms, append=args.append)


if __name__ == "__main__":
    main()
