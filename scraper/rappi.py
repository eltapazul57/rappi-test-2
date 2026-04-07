"""
rappi.py — Scraper para Rappi México (www.rappi.com.mx).

Flujo de navegación:
1. Abrir homepage → modal de dirección aparece automáticamente
2. Ingresar dirección en el campo de búsqueda → seleccionar de autocomplete
3. Buscar restaurante (McDonald's para Big Mac, OXXO/7-Eleven para Coca-Cola)
4. Navegar al menú → encontrar el producto → extraer precio
5. Extraer delivery fee y ETA del header/cart del restaurante

Notas de anti-detección conocidas para Rappi:
- Usa Cloudflare — esperar a que el challenge pase (generalmente < 5s)
- El modal de dirección a veces requiere click extra para activarse
- Los precios están en elementos con clase dinámica; buscar por data-testid
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


class RappiScraper(AbstractScraper):
    """Scraper para Rappi México."""

    platform = "rappi"
    BASE_URL = PLATFORM_BASE_URLS["rappi"]

    # ------------------------------------------------------------------
    # Setup / Teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """
        Inicializa Playwright con opciones anti-detección para Rappi.
        Rappi usa Cloudflare, por lo que se usa headed mode en desarrollo
        y headless con stealth en producción/demo.
        """
        playwright = sync_playwright().start()
        self._playwright = playwright

        # TODO: considerar usar playwright-stealth si Cloudflare bloquea
        self._browser: Browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        self._context: BrowserContext = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=get_random_user_agent(),
            locale="es-MX",
            timezone_id="America/Mexico_City",
            # Simular geolocalización en CDMX
            geolocation={"latitude": 19.4326, "longitude": -99.1332},
            permissions=["geolocation"],
        )

        # Inyectar script para ocultar navigator.webdriver
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        self._page: Page = self._context.new_page()
        self._page.set_default_timeout(REQUEST_TIMEOUT_MS)
        logger.info("RappiScraper: browser iniciado")

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
            logger.warning("Error en teardown de RappiScraper: %s", exc)

    # ------------------------------------------------------------------
    # Flujo de scraping
    # ------------------------------------------------------------------

    def set_delivery_address(self, address: Address) -> bool:
        """
        Navega a Rappi y establece la dirección de entrega.

        Flujo esperado:
        1. Navegar a BASE_URL
        2. Esperar a que aparezca el modal/campo de dirección
        3. Escribir address.street + address.neighborhood
        4. Seleccionar la primera sugerencia del autocomplete
        5. Confirmar y esperar redirección al catálogo de la zona
        """
        # TODO: implementar navegación y selección de dirección
        # Selectores a investigar:
        #   - Input de dirección: [data-testid="address-input"] o similar
        #   - Dropdown de sugerencias: [data-testid="address-suggestion"]
        #   - Botón de confirmar: buscar por texto "Confirmar" o "Entregar aquí"
        raise NotImplementedError(
            "set_delivery_address no implementado — ver flujo en docstring"
        )

    def search_product(self, product: Product) -> bool:
        """
        Busca el restaurante/tienda que tiene el producto en Rappi.

        Para big_mac: buscar "McDonald's" en la barra de búsqueda
        Para coca_cola_600ml: buscar "OXXO" o "7-Eleven"
        """
        # TODO: implementar búsqueda de restaurante
        # 1. Encontrar barra de búsqueda principal
        # 2. Escribir el nombre del restaurante
        # 3. Seleccionar el primer resultado relevante
        # 4. Navegar al menú del restaurante
        raise NotImplementedError(
            "search_product no implementado — ver flujo en docstring"
        )

    def extract_data(self, address: Address, product: Product) -> ScrapeResult:
        """
        Extrae precio, delivery fee, ETA y promociones de la página del restaurante.

        Selectores a investigar en Rappi (sujetos a cambio con deploys):
        - Precio del producto: buscar el nombre del producto, luego el precio adyacente
        - Delivery fee: generalmente en el header del restaurante
        - ETA: minutos estimados junto al fee
        - Promociones: badges/banners en la página del restaurante
        """
        # TODO: implementar extracción con selectores CSS/XPath
        # Usar parse_price() y parse_time_minutes() de utils.py
        # Documentar aquí los selectores encontrados con fecha de validación
        raise NotImplementedError(
            "extract_data no implementado — ver flujo en docstring"
        )

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _wait_for_page_ready(self) -> None:
        """Espera a que la página cargue completamente y el JS se estabilice."""
        # TODO: implementar espera inteligente
        # Opciones: wait_for_load_state("networkidle") o esperar selector específico
        pass

    def _handle_cloudflare_challenge(self) -> bool:
        """
        Detecta y espera a que pase el challenge de Cloudflare.

        Returns:
            True si pasó el challenge, False si timeout.
        """
        # TODO: detectar presencia de challenge (título "Just a moment...")
        # Hacer wait_for_selector con timeout corto; si no aparece, no hay challenge
        return True
