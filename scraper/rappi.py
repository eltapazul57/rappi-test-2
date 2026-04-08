"""
rappi.py — Scraper para Rappi México (www.rappi.com.mx).

Selectores validados: 2026-04-07

Flujo:
1. Navegar a homepage
2. Setear dirección via input[placeholder*="Dónde quieres"]
3. Seleccionar sugerencia via li:has-text(...)
4. Buscar restaurante/tienda via input[type="search"]
5. Click en primer resultado via a:has-text(...)
6. Extraer precio, fee, ETA del menú del restaurante

Notas de Rappi:
- Cloudflare challenge se resuelve automáticamente en < 5s
- Rappi muestra fee y ETA en las tarjetas de resultado de búsqueda
- Los precios de producto están en el menú con formato "$ XXX.00"
- El Big Mac individual está en la sección "A La Carta Comida"
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
    Playwright,
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

SEARCH_TERMS: dict[str, list[str]] = {
    "big_mac": ["McDonald's"],
    "coca_cola_600ml": ["OXXO", "Turbo"],
}

PRODUCT_MATCH_PATTERNS: dict[str, list[str]] = {
    "big_mac": ["Big Mac"],
    "coca_cola_600ml": ["Coca-Cola 600", "Coca Cola 600", "Coca-Cola"],
}


class RappiScraper(AbstractScraper):
    """Scraper para Rappi México."""

    platform = "rappi"
    BASE_URL = PLATFORM_BASE_URLS["rappi"]

    def __init__(self) -> None:
        super().__init__()
        self._playwright: Playwright | None = None
        self._store_fee: float | None = None
        self._store_eta: int | None = None
        self._store_promo: str = ""

    def before_scrape_one(self, address: Address, product: Product) -> None:
        self._store_fee = None
        self._store_eta = None
        self._store_promo = ""

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
            viewport={"width": 1280, "height": 800},
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
        logger.info("RappiScraper: browser iniciado")

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
    # Helpers
    # ------------------------------------------------------------------

    def _reset_context(self) -> None:
        """Cierra el contexto/página actual y abre uno nuevo con el mismo browser."""
        for resource in (getattr(self, "_page", None), getattr(self, "_context", None)):
            try:
                if resource:
                    resource.close()
            except Exception:
                pass
        self._context: BrowserContext = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
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
        logger.info("RappiScraper: contexto reiniciado")

    def _wait_for_page_ready(self) -> None:
        import time
        page = self._page
        try:
            page.wait_for_load_state("domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        except Exception:
            pass
        # Cloudflare check — use time.sleep to avoid calling page methods while context may be mid-navigation
        for _ in range(6):
            try:
                title = page.title().lower()
            except Exception:
                time.sleep(1.5)
                continue
            if "just a moment" in title or "checking" in title:
                logger.info("Cloudflare challenge, esperando...")
                time.sleep(3)
            else:
                break
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

    def _dismiss_popups(self) -> None:
        page = self._page
        for sel in ["button:has-text('Ok, entendido')", "button:has-text('Aceptar')", "button:has-text('Cerrar')"]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    loc.click(timeout=2000)
                    page.wait_for_timeout(500)
            except (PlaywrightTimeout, Exception):
                pass

    # ------------------------------------------------------------------
    # Scraping flow
    # ------------------------------------------------------------------

    def set_delivery_address(self, address: Address) -> bool:
        page = self._page
        search_text = f"{address.street}, {address.neighborhood}"
        # Keyword from address to match in suggestions
        address_keyword = address.street.split()[0]  # e.g. "Presidente" from "Presidente Masaryk 360"
        logger.info("Rappi: seteando dirección zone=%s", address.zone)

        page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        self._wait_for_page_ready()
        self._dismiss_popups()
        random_delay()

        # Address input — validated selector
        addr_input = page.locator('input[placeholder*="Dónde quieres"]')
        if not addr_input.is_visible(timeout=5000):
            # Context may be stale from a previous failed navigation; recreate and retry once
            logger.warning("Rappi: input no visible, reiniciando contexto para zone=%s", address.zone)
            self._reset_context()
            page = self._page
            addr_input = page.locator('input[placeholder*="Dónde quieres"]')
            page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            self._wait_for_page_ready()
            self._dismiss_popups()
            random_delay()
            if not addr_input.is_visible(timeout=5000):
                logger.warning("Rappi: input de dirección no visible para zone=%s", address.zone)
                return False

        addr_input.click()
        page.wait_for_timeout(500)
        addr_input.type(search_text, delay=60)
        random_delay(min_seconds=2.0, max_seconds=3.5)

        # Select address suggestion — Rappi uses plain <li> elements
        suggestion = page.locator(f'li:has-text("{address_keyword}")').first
        if not suggestion.is_visible(timeout=5000):
            logger.warning("Rappi: sugerencia de dirección no encontrada para zone=%s", address.zone)
            return False

        suggestion.click()
        random_delay(min_seconds=2.0, max_seconds=3.0)
        self._wait_for_page_ready()
        logger.info("Rappi: dirección seteada para zone=%s", address.zone)
        return True

    def search_product(self, product: Product) -> bool:
        page = self._page
        terms = SEARCH_TERMS.get(product.key, [product.display_name])
        logger.info("Rappi: buscando producto %s", product.key)

        for term in terms:
            search_input = page.locator('input[type="search"]').first
            if not search_input.is_visible(timeout=5000):
                logger.warning("Rappi: barra de búsqueda no visible")
                continue

            search_input.click()
            page.wait_for_timeout(500)
            search_input.fill("")
            page.wait_for_timeout(300)
            search_input.type(term, delay=60)
            random_delay(min_seconds=1.5, max_seconds=2.5)
            page.keyboard.press("Enter")
            random_delay(min_seconds=3.0, max_seconds=5.0)
            self._wait_for_page_ready()

            # Extract ETA and fee from search result cards BEFORE entering restaurant
            self._extract_store_info_from_search(term)

            # Click first matching restaurant result
            result_link = page.locator(f'a:has-text("{term}")').first
            if result_link.is_visible(timeout=5000):
                result_link.click()
                random_delay(min_seconds=3.0, max_seconds=5.0)
                self._wait_for_page_ready()
                logger.info("Rappi: entró al restaurante para '%s'", term)
                return True

            logger.warning("Rappi: no se encontró resultado para '%s'", term)

        return False

    def _extract_store_info_from_search(self, term: str) -> None:
        """Extrae ETA, fee y promos de la tarjeta de resultado de búsqueda."""
        page = self._page
        self._store_fee = None
        self._store_eta = None
        self._store_promo = ""

        try:
            # Rappi search cards include: "name\n\nETA\n•\n$fee\n•\nrating\npromo"
            card = page.locator(f'a:has-text("{term}")').first
            if not card.is_visible(timeout=3000):
                return
            card_text = card.inner_text()

            # ETA: "12 min"
            eta_match = re.search(r"(\d+)\s*min", card_text)
            if eta_match:
                self._store_eta = int(eta_match.group(1))

            # Fee: "$ 0.00" or "$ 29.00"
            fee_match = re.search(r"\$\s*([\d,.]+)", card_text)
            if fee_match:
                self._store_fee = parse_price(f"${fee_match.group(1)}")

            # Promo: "Envío Gratis" or similar
            promo_patterns = ["Envío [Gg]ratis", "descuento", "Aplican TyC", "primer pedido"]
            for pat in promo_patterns:
                m = re.search(pat, card_text, re.IGNORECASE)
                if m:
                    # Get the full line containing the promo
                    for line in card_text.split("\n"):
                        if re.search(pat, line, re.IGNORECASE):
                            self._store_promo = line.strip()
                            break
                    break

            logger.info("Rappi search card: fee=%s eta=%s promo='%s'",
                        self._store_fee, self._store_eta, self._store_promo)
        except (PlaywrightTimeout, Exception) as exc:
            logger.debug("No se pudo extraer info de tarjeta: %s", exc)

    def extract_data(self, address: Address, product: Product) -> ScrapeResult:
        page = self._page
        logger.info("Rappi: extrayendo datos para %s en %s", product.key, address.zone)

        price = self._extract_product_price(product)

        if price is None:
            logger.warning("Rappi: precio no encontrado para %s/%s", product.key, address.zone)
            return ScrapeResult.not_available(self.platform, address, product)

        # Fee and ETA from search card (extracted earlier)
        fee = self._store_fee
        eta = self._store_eta

        # Try to extract from restaurant page if not found in search card
        if fee is None:
            fee = self._extract_fee_from_page()
        if eta is None:
            eta = self._extract_eta_from_page()

        return ScrapeResult(
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=self.platform,
            address_id=address.id,
            zone=address.zone,
            product=product.key,
            price=price,
            delivery_fee=fee,
            estimated_time_min=eta,
            promotions=self._store_promo,
            scrape_status="success",
        )

    def _extract_product_price(self, product: Product) -> float | None:
        """Busca el precio del producto específico en el menú."""
        page = self._page
        patterns = PRODUCT_MATCH_PATTERNS.get(product.key, [product.display_name])

        for pattern in patterns:
            try:
                # Find product items containing the exact name with a price
                items = page.locator(f'text=/{pattern}/i').all()
                for item in items:
                    if not item.is_visible(timeout=1000):
                        continue
                    # Navigate up to the container that includes the price
                    for level in range(2, 5):
                        ancestor = item.locator(f"xpath=ancestor::*[{level}]")
                        text = ancestor.inner_text()
                        # Look for a standalone product (not a combo/McTrío)
                        lines = text.strip().split("\n")
                        # Find the line with the product name and the price
                        name_line = None
                        price_val = None
                        for line in lines:
                            if re.search(pattern, line, re.IGNORECASE):
                                name_line = line
                            if line.strip().startswith("$"):
                                price_val = parse_price(line.strip())
                        if name_line and price_val and price_val > 10:
                            # Avoid combo items — skip if "McTrío" or "+" in name
                            if "McTrío" in text.split("$")[0] or "+" in name_line:
                                continue
                            logger.info("Rappi: precio encontrado %s = $%.2f", pattern, price_val)
                            return price_val
            except (PlaywrightTimeout, Exception):
                continue

        # Fallback: grab the first reasonable price from any $ element
        try:
            price_els = page.locator('text=/^\\$\\s*\\d/').all()
            for el in price_els[:15]:
                if el.is_visible(timeout=500):
                    val = parse_price(el.inner_text())
                    if val and 15 < val < 500:
                        return val
        except (PlaywrightTimeout, Exception):
            pass

        return None

    def _extract_fee_from_page(self) -> float | None:
        """Extrae delivery fee de la página del restaurante."""
        page = self._page
        try:
            for sel in ['text=/Envío/i', 'text=/envío/i']:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    text = el.inner_text()
                    if "gratis" in text.lower():
                        return 0.0
                    return parse_price(text)
        except (PlaywrightTimeout, Exception):
            pass
        return None

    def _extract_eta_from_page(self) -> int | None:
        """Extrae ETA de la página del restaurante."""
        page = self._page
        try:
            eta_els = page.locator('text=/\\d+\\s*min/').all()
            for el in eta_els[:5]:
                if el.is_visible(timeout=1000):
                    return parse_time_minutes(el.inner_text())
        except (PlaywrightTimeout, Exception):
            pass
        return None
