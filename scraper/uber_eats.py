"""
uber_eats.py — Scraper para Uber Eats México (www.ubereats.com/mx).

Flujo de navegación:
1. Abrir homepage → campo de dirección visible en hero
2. Escribir dirección → seleccionar de Google Places autocomplete
3. Presionar Enter o "Buscar" → ver catálogo de restaurantes
4. Buscar "McDonald's" o la tienda correspondiente
5. Entrar al restaurante → encontrar producto → extraer datos

Notas de anti-detección conocidas para Uber Eats:
- Usa reCAPTCHA v3 (score-based, invisible) — menos agresivo que Cloudflare
- El campo de dirección usa Google Places API, el autocomplete es más lento
- Los precios pueden estar en shadow DOM — requiere evaluación JS
- Uber Eats muestra precios en USD si detecta VPN/proxy; verificar locale
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


class UberEatsScraper(AbstractScraper):
    """Scraper para Uber Eats México."""

    platform = "uber_eats"
    BASE_URL = PLATFORM_BASE_URLS["uber_eats"]

    # ------------------------------------------------------------------
    # Setup / Teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """
        Inicializa Playwright para Uber Eats.
        Uber Eats es más tolerante con headless que Rappi, pero requiere
        que el locale y timezone estén correctamente configurados para
        mostrar precios en MXN.
        """
        playwright = sync_playwright().start()
        self._playwright = playwright

        self._browser: Browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--lang=es-MX",
            ],
        )

        self._context: BrowserContext = self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=get_random_user_agent(),
            locale="es-MX",
            timezone_id="America/Mexico_City",
            geolocation={"latitude": 19.4326, "longitude": -99.1332},
            permissions=["geolocation"],
            extra_http_headers={
                "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8",
            },
        )

        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        self._page: Page = self._context.new_page()
        self._page.set_default_timeout(REQUEST_TIMEOUT_MS)
        logger.info("UberEatsScraper: browser iniciado")

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
            logger.warning("Error en teardown de UberEatsScraper: %s", exc)

    # ------------------------------------------------------------------
    # Flujo de scraping
    # ------------------------------------------------------------------

    def set_delivery_address(self, address: Address) -> bool:
        """
        Establece la dirección de entrega en Uber Eats.

        Flujo esperado:
        1. Navegar a BASE_URL
        2. Encontrar el campo de dirección (generalmente en el hero o modal)
        3. Escribir la dirección → esperar sugerencias de Google Places
        4. Seleccionar primera sugerencia relevante
        5. Esperar a que cargue el catálogo de restaurantes de la zona

        Diferencia con Rappi: Uber Eats usa Google Places API para el
        autocomplete, lo que significa que el campo puede tener un delay
        mayor antes de mostrar sugerencias.
        """
        # TODO: implementar
        # Selectores a investigar:
        #   - Input: [data-testid="address-input"] o input[placeholder*="dirección"]
        #   - Sugerencias: lista con clase que incluya "places-suggestion"
        #   - Botón buscar: button[type="submit"] o texto "Buscar restaurantes"
        raise NotImplementedError(
            "set_delivery_address no implementado — ver flujo en docstring"
        )

    def search_product(self, product: Product) -> bool:
        """
        Busca el restaurante en el catálogo de Uber Eats.

        Para big_mac: buscar "McDonald's"
        Para coca_cola_600ml: buscar "OXXO" (Uber Eats tiene convenio)
        """
        # TODO: implementar
        # 1. Usar la barra de búsqueda del catálogo (diferente al input de dirección)
        # 2. Escribir nombre del restaurante
        # 3. Hacer click en el primer resultado
        # 4. Esperar a que cargue el menú del restaurante
        raise NotImplementedError(
            "search_product no implementado — ver flujo en docstring"
        )

    def extract_data(self, address: Address, product: Product) -> ScrapeResult:
        """
        Extrae datos del producto en Uber Eats.

        Notas específicas de Uber Eats:
        - El delivery fee puede aparecer como "Envío $XX" o "Envío gratis"
        - El ETA aparece como "XX–XX min" (rango) — usar promedio
        - Los precios de productos están en el menú como items de lista
        - Las promociones aparecen como chips/badges en la parte superior
        """
        # TODO: implementar extracción
        # Usar parse_price() de utils.py para normalizar precios
        # Usar parse_time_minutes() para el rango de ETA
        raise NotImplementedError(
            "extract_data no implementado — ver flujo en docstring"
        )

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _dismiss_cookie_banner(self) -> None:
        """Cierra el banner de cookies si aparece (bloquea clicks en mobile view)."""
        # TODO: buscar botón "Aceptar" o "Accept" y hacer click si existe
        pass

    def _is_restaurant_open(self) -> bool:
        """
        Verifica si el restaurante está abierto en el horario actual.
        Uber Eats muestra "Cerrado" cuando el restaurante no opera.

        Returns:
            True si está abierto, False si cerrado/no disponible.
        """
        # TODO: buscar indicador de estado del restaurante
        return True
