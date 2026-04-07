"""
base.py — Clase abstracta base para todos los scrapers de plataforma.

Define el contrato que deben cumplir RappiScraper, UberEatsScraper y
DiDiFoodScraper. La lógica de loop (dirección × producto) vive aquí para
evitar duplicación; cada subclase solo implementa scrape_one().
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from scraper.config import Address, Product, ADDRESSES, PRODUCTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resultado de un scrape individual
# ---------------------------------------------------------------------------

@dataclass
class ScrapeResult:
    """
    Representa una fila del CSV final.
    Campos opcionales son None cuando no se pudo extraer el dato.
    """
    timestamp: str
    platform: str
    address_id: int
    zone: str
    product: str
    price: Optional[float]
    delivery_fee: Optional[float]
    estimated_time_min: Optional[int]
    promotions: str = ""
    scrape_status: str = "success"  # "success" | "error" | "not_available"
    error_message: str = ""         # solo se llena si scrape_status == "error"

    @classmethod
    def error(
        cls,
        platform: str,
        address: Address,
        product: Product,
        error_message: str,
    ) -> "ScrapeResult":
        """Factory para crear resultados de error de forma consistente."""
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            address_id=address.id,
            zone=address.zone,
            product=product.key,
            price=None,
            delivery_fee=None,
            estimated_time_min=None,
            promotions="",
            scrape_status="error",
            error_message=error_message,
        )

    @classmethod
    def not_available(
        cls,
        platform: str,
        address: Address,
        product: Product,
    ) -> "ScrapeResult":
        """Factory para cuando el producto no está disponible en esa zona."""
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            address_id=address.id,
            zone=address.zone,
            product=product.key,
            price=None,
            delivery_fee=None,
            estimated_time_min=None,
            promotions="",
            scrape_status="not_available",
        )


# ---------------------------------------------------------------------------
# Clase abstracta base
# ---------------------------------------------------------------------------

class AbstractScraper(ABC):
    """
    Contrato base para scrapers de plataformas de delivery.

    Uso:
        scraper = RappiScraper()
        results = scraper.scrape_all()   # devuelve lista de ScrapeResult
    """

    # Cada subclase declara su nombre de plataforma
    platform: str = ""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._browser = None
        self._context = None
        self._page = None

    def before_scrape_one(self, address: Address, product: Product) -> None:
        """
        Hook opcional para resetear estado transitorio antes de cada scrape.
        Las subclases pueden sobreescribirlo cuando guardan datos intermedios.
        """
        return None

    # ------------------------------------------------------------------
    # Métodos abstractos — cada scraper los implementa
    # ------------------------------------------------------------------

    @abstractmethod
    def setup(self) -> None:
        """
        Inicializa el browser Playwright con las opciones anti-detección
        correspondientes a la plataforma (headers, viewport, etc.).
        Debe asignar self._browser, self._context, self._page.
        """
        ...

    @abstractmethod
    def teardown(self) -> None:
        """
        Cierra browser y libera recursos. Siempre debe llamarse en finally.
        """
        ...

    @abstractmethod
    def set_delivery_address(self, address: Address) -> bool:
        """
        Navega a la plataforma e ingresa la dirección de entrega.

        Returns:
            True si la dirección fue aceptada, False si no hay cobertura.
        """
        ...

    @abstractmethod
    def search_product(self, product: Product) -> bool:
        """
        Busca el producto dentro de la plataforma (ya con dirección seteada).

        Returns:
            True si encontró resultados, False si no hay disponibilidad.
        """
        ...

    @abstractmethod
    def extract_data(
        self, address: Address, product: Product
    ) -> ScrapeResult:
        """
        Extrae precio, delivery fee, ETA y promociones de la página actual.
        Asume que set_delivery_address() y search_product() ya fueron llamados.

        Returns:
            ScrapeResult con los datos extraídos o status error/not_available.
        """
        ...

    # ------------------------------------------------------------------
    # Lógica de loop — heredada por todas las subclases
    # ------------------------------------------------------------------

    def scrape_one(self, address: Address, product: Product) -> ScrapeResult:
        """
        Ejecuta el flujo completo para una combinación dirección+producto.
        Maneja errores y devuelve siempre un ScrapeResult válido.
        """
        self.logger.info(
            "Scraping %s — zone=%s product=%s",
            self.platform,
            address.zone,
            product.key,
        )
        try:
            self.before_scrape_one(address, product)

            address_ok = self.set_delivery_address(address)
            if not address_ok:
                return ScrapeResult.not_available(self.platform, address, product)

            product_ok = self.search_product(product)
            if not product_ok:
                return ScrapeResult.not_available(self.platform, address, product)

            return self.extract_data(address, product)

        except Exception as exc:
            self.logger.error(
                "Error scraping %s zone=%s product=%s: %s",
                self.platform,
                address.zone,
                product.key,
                exc,
                exc_info=True,
            )
            return ScrapeResult.error(self.platform, address, product, str(exc))

    def scrape_all(
        self,
        addresses: list[Address] | None = None,
        products: list[Product] | None = None,
    ) -> list[ScrapeResult]:
        """
        Itera sobre todas las combinaciones dirección × producto.
        Si no se pasan listas, usa las globales de config.py.

        Returns:
            Lista de ScrapeResult (una por combinación).
        """
        addresses = addresses or ADDRESSES
        products = products or PRODUCTS
        combinations = [(address, product) for address in addresses for product in products]
        results: list[ScrapeResult] = []

        setup_error: Exception | None = None
        try:
            try:
                self.setup()
            except Exception as exc:
                setup_error = exc
                self.logger.error(
                    "Error en setup de %s: %s",
                    self.platform,
                    exc,
                    exc_info=True,
                )

            if setup_error is not None:
                for address, product in combinations:
                    results.append(
                        ScrapeResult.error(
                            self.platform,
                            address,
                            product,
                            f"setup_failed: {setup_error}",
                        )
                    )
                return results

            for address, product in combinations:
                result = self.scrape_one(address, product)
                results.append(result)
        finally:
            try:
                self.teardown()
            except Exception as exc:
                self.logger.warning(
                    "Error en teardown de %s: %s",
                    self.platform,
                    exc,
                )

        self.logger.info(
            "%s: %d resultados (%d exitosos, %d errores)",
            self.platform,
            len(results),
            sum(1 for r in results if r.scrape_status == "success"),
            sum(1 for r in results if r.scrape_status == "error"),
        )
        return results
