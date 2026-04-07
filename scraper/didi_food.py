"""
didi_food.py — Scraper para DiDi Food México (food.didiglobal.com).

Selectores validados: 2026-04-07

Estado actual: DiDi Food salió del mercado mexicano. El dominio
food.didiglobal.com ya no resuelve DNS. Este scraper mantiene la
estructura para compatibilidad y documentará correctamente el error
como "not_available" en el CSV.

Si DiDi Food vuelve a operar o cambia de dominio, actualizar BASE_URL
en config.py y los selectores de este archivo.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
    Playwright,
    Error as PlaywrightError,
)

from scraper.base import AbstractScraper, ScrapeResult
from scraper.config import (
    Address,
    Product,
    PLATFORM_BASE_URLS,
    REQUEST_TIMEOUT_MS,
    PAGE_LOAD_TIMEOUT_MS,
)
from scraper.utils import (
    random_delay,
    get_random_user_agent,
    parse_price,
    parse_time_minutes,
)

logger = logging.getLogger(__name__)


class DiDiFoodScraper(AbstractScraper):
    """Scraper para DiDi Food México."""

    platform = "didi_food"
    BASE_URL = PLATFORM_BASE_URLS["didi_food"]

    def __init__(self) -> None:
        super().__init__()
        self._playwright: Playwright | None = None
        self._platform_available: bool = True

    def before_scrape_one(self, address: Address, product: Product) -> None:
        # Mantener explícito el contrato del hook para consistencia entre scrapers.
        return None

    # ------------------------------------------------------------------
    # Setup / Teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        pw = sync_playwright().start()
        self._playwright = pw
        self._browser: Browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
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

        # Pre-check: try to reach the platform
        self._platform_available = self._check_platform_reachable()

    def teardown(self) -> None:
        for resource in (
            getattr(self, "_page", None),
            getattr(self, "_context", None),
            getattr(self, "_browser", None),
        ):
            try:
                if resource:
                    resource.close()
            except Exception:
                pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    def _check_platform_reachable(self) -> bool:
        """Verifica si el dominio de DiDi Food es alcanzable."""
        page = self._page
        try:
            response = page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=15000)
            if response and response.ok:
                logger.info("DiDiFood: plataforma alcanzable")
                return True
            logger.warning("DiDiFood: respuesta HTTP %s", response.status if response else "None")
            return False
        except (PlaywrightTimeout, PlaywrightError) as exc:
            logger.warning("DiDiFood: plataforma no alcanzable — %s", exc)
            return False

    # ------------------------------------------------------------------
    # Scraping flow
    # ------------------------------------------------------------------

    def set_delivery_address(self, address: Address) -> bool:
        if not self._platform_available:
            logger.info("DiDiFood: plataforma no disponible, zone=%s marcada como not_available", address.zone)
            return False

        page = self._page
        full_address = f"{address.street}, {address.neighborhood}, CDMX"
        logger.info("DiDiFood: seteando dirección zone=%s", address.zone)

        try:
            page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        except (PlaywrightTimeout, PlaywrightError):
            logger.warning("DiDiFood: no se pudo cargar la página")
            return False

        random_delay()

        # Address input
        addr_input = None
        for sel in ['input[placeholder*="dirección"]', 'input[placeholder*="ubicación"]', 'input[type="text"]']:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=3000):
                    addr_input = loc
                    break
            except (PlaywrightTimeout, Exception):
                continue

        if not addr_input:
            logger.warning("DiDiFood: input de dirección no encontrado para zone=%s", address.zone)
            return False

        addr_input.click()
        page.wait_for_timeout(500)
        addr_input.type(full_address, delay=80)
        random_delay(min_seconds=2.0, max_seconds=3.5)

        # Select suggestion
        for sel in ['li:has-text("{}")'.format(address.street.split()[0]), '[role="option"]', 'li']:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=3000):
                    loc.click()
                    page.wait_for_timeout(1500)
                    break
            except (PlaywrightTimeout, Exception):
                continue

        random_delay()
        logger.info("DiDiFood: dirección seteada para zone=%s", address.zone)
        return True

    def search_product(self, product: Product) -> bool:
        if not self._platform_available:
            return False

        page = self._page
        terms = {"big_mac": ["McDonald's"], "coca_cola_600ml": ["OXXO"]}.get(product.key, [product.display_name])
        logger.info("DiDiFood: buscando producto %s", product.key)

        for term in terms:
            search_input = None
            for sel in ['input[placeholder*="Buscar"]', 'input[type="search"]', 'input[type="text"]']:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=3000):
                        search_input = loc
                        break
                except (PlaywrightTimeout, Exception):
                    continue

            if not search_input:
                logger.warning("DiDiFood: barra de búsqueda no encontrada")
                continue

            search_input.click()
            page.wait_for_timeout(500)
            search_input.fill("")
            search_input.type(term, delay=60)
            random_delay(min_seconds=2.0, max_seconds=3.0)
            page.keyboard.press("Enter")
            random_delay(min_seconds=3.0, max_seconds=5.0)

            result = page.locator(f'a:has-text("{term}")').first
            if result.is_visible(timeout=5000):
                result.click()
                random_delay(min_seconds=3.0, max_seconds=5.0)
                return True

        return False

    def extract_data(self, address: Address, product: Product) -> ScrapeResult:
        if not self._platform_available:
            return ScrapeResult.not_available(self.platform, address, product)

        page = self._page
        logger.info("DiDiFood: extrayendo datos para %s en %s", product.key, address.zone)

        price = self._extract_price(product)
        fee = self._extract_fee()
        eta = self._extract_eta()
        promos = self._extract_promotions()

        if price is None:
            return ScrapeResult.not_available(self.platform, address, product)

        return ScrapeResult(
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=self.platform,
            address_id=address.id,
            zone=address.zone,
            product=product.key,
            price=price,
            delivery_fee=fee,
            estimated_time_min=eta,
            promotions=promos or "",
            scrape_status="success",
        )

    def _extract_price(self, product: Product) -> float | None:
        page = self._page
        patterns = {"big_mac": ["Big Mac"], "coca_cola_600ml": ["Coca-Cola"]}.get(product.key, [product.display_name])
        for pattern in patterns:
            try:
                items = page.locator(f'text=/{pattern}/i').all()
                for item in items[:5]:
                    if not item.is_visible(timeout=1000):
                        continue
                    ancestor = item.locator("xpath=ancestor::*[3]")
                    text = ancestor.inner_text()
                    if "$" in text:
                        val = parse_price(text.split("$")[-1].split("\n")[0])
                        if val and val > 10:
                            return val
            except (PlaywrightTimeout, Exception):
                continue
        return None

    def _extract_fee(self) -> float | None:
        page = self._page
        try:
            for sel in ['text=/envío/i', 'text=/delivery/i']:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    text = el.inner_text()
                    if "gratis" in text.lower():
                        return 0.0
                    return parse_price(text)
        except (PlaywrightTimeout, Exception):
            pass
        return None

    def _extract_eta(self) -> int | None:
        page = self._page
        try:
            for el in page.locator('text=/\\d+\\s*min/').all()[:5]:
                if el.is_visible(timeout=1000):
                    return parse_time_minutes(el.inner_text())
        except (PlaywrightTimeout, Exception):
            pass
        return None

    def _extract_promotions(self) -> str:
        page = self._page
        try:
            for el in page.locator('[class*="promo"], [class*="discount"]').all()[:3]:
                if el.is_visible(timeout=1000):
                    text = el.inner_text().strip()
                    if text and len(text) < 100:
                        return text
        except (PlaywrightTimeout, Exception):
            pass
        return ""
