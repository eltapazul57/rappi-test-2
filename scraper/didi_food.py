"""
didi_food.py — Scraper para DiDi Food México (food.didiglobal.com).

Flujo de navegación:
1. Abrir homepage → permitir geolocalización o ingresar dirección manualmente
2. Ingresar dirección en el campo de búsqueda
3. Ver catálogo de restaurantes disponibles
4. Buscar McDonald's o tienda de conveniencia
5. Entrar al restaurante → buscar producto → extraer datos

Notas de anti-detección conocidas para DiDi Food:
- Menos agresivo en anti-bot que Rappi/Uber Eats
- Puede redirigir a la app móvil si detecta comportamiento automatizado
- La URL de la zona cambia con el slug de la ciudad (/cdmx/ o similar)
- DiDi Food tiene menos cobertura geográfica — Iztapalapa puede no tener
  restaurantes disponibles (registrar como not_available, no error)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from scraper.base import AbstractScraper, ScrapeResult
from scraper.config import (
    Address,
    Product,
    PLATFORM_BASE_URLS,
    REQUEST_TIMEOUT_MS,
    PAGE_LOAD_TIMEOUT_MS,
)
from scraper.utils import random_delay, retry, get_random_user_agent, parse_price, parse_time_minutes

logger = logging.getLogger(__name__)


class DiDiFoodScraper(AbstractScraper):
    """Scraper para DiDi Food México."""

    platform = "didi_food"
    BASE_URL = PLATFORM_BASE_URLS["didi_food"]

    # ------------------------------------------------------------------
    # Setup / Teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """
        Inicializa Playwright para DiDi Food.
        DiDi Food tiene protección anti-bot menos agresiva, pero sí
        detecta automatización por viewport inusual o falta de movimiento
        de mouse. Se simula viewport de laptop estándar.
        """
        playwright = sync_playwright().start()
        self._playwright = playwright

        self._browser: Browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        self._context: BrowserContext = self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=get_random_user_agent(),
            locale="es-MX",
            timezone_id="America/Mexico_City",
            geolocation={"latitude": 19.4326, "longitude": -99.1332},
            permissions=["geolocation"],
        )

        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        self._page: Page = self._context.new_page()
        self._page.set_default_timeout(REQUEST_TIMEOUT_MS)
        logger.info("DiDiFoodScraper: browser iniciado")

    def teardown(self) -> None:
        """Cierra browser y Playwright."""
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as exc:
            logger.warning("Error en teardown de DiDiFoodScraper: %s", exc)

    # ------------------------------------------------------------------
    # Flujo de scraping
    # ------------------------------------------------------------------

    def set_delivery_address(self, address: Address) -> bool:
        """
        Establece la dirección de entrega en DiDi Food.

        Flujo esperado:
        1. Navegar a BASE_URL
        2. Permitir/ignorar prompt de geolocalización del browser
        3. Encontrar campo de dirección y escribir la dirección
        4. Seleccionar sugerencia del autocomplete
        5. Confirmar y esperar catálogo

        Diferencia clave: DiDi Food a veces lleva directo a /cdmx/ sin
        pedir dirección. En ese caso, buscar el botón de "cambiar dirección".
        """
        # TODO: implementar
        # Considerar que DiDi Food puede tener una URL directa por ciudad:
        #   food.didiglobal.com/mx/cdmx/
        # Selectores a investigar:
        #   - Input de dirección: input[placeholder*="dirección"] o similar
        #   - Confirmación: botón "Buscar" o "Confirmar dirección"
        raise NotImplementedError(
            "set_delivery_address no implementado — ver flujo en docstring"
        )

    def search_product(self, product: Product) -> bool:
        """
        Busca el restaurante/tienda en DiDi Food.

        Para big_mac: buscar "McDonald's"
        Para coca_cola_600ml: buscar "OXXO" o "FEMSA" (DiDi tiene convenio con OXXO)
        """
        # TODO: implementar búsqueda
        # DiDi Food puede tener categorías en el catálogo — navegar a la
        # categoría correcta puede ser más eficiente que la búsqueda libre
        raise NotImplementedError(
            "search_product no implementado — ver flujo en docstring"
        )

    def extract_data(self, address: Address, product: Product) -> ScrapeResult:
        """
        Extrae datos del producto en DiDi Food.

        Notas específicas de DiDi Food:
        - Los precios pueden estar en formato "$XX.XX MXN" o solo "$XX"
        - El delivery fee puede ser parte de una subscripción (DiDi Pass)
        - Las promociones aparecen como stickers/overlays en las tarjetas
        - El ETA puede ser "~XX min" (con tilde de aproximación)
        """
        # TODO: implementar extracción
        # Documentar selectores encontrados con fecha:
        #   [Selector] → [Dato] — validado: YYYY-MM-DD
        raise NotImplementedError(
            "extract_data no implementado — ver flujo en docstring"
        )

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _check_coverage(self, address: Address) -> bool:
        """
        Verifica si DiDi Food tiene cobertura en la zona.
        DiDi tiene menor cobertura que Rappi/Uber en zonas periféricas.

        Returns:
            True si hay cobertura, False si no (registrar como not_available).
        """
        # TODO: buscar mensaje de "no hay restaurantes disponibles" o similar
        # Zonas con potencial falta de cobertura: Iztapalapa (address_id=5)
        return True

    def _get_city_url(self) -> str:
        """
        Construye la URL correcta para CDMX en DiDi Food.
        DiDi usa slugs de ciudad en la URL.
        """
        # TODO: verificar el slug correcto para CDMX
        # Posibles valores: /mx/cdmx/, /cdmx/, /ciudad-de-mexico/
        return f"{self.BASE_URL}/mx/cdmx/"
