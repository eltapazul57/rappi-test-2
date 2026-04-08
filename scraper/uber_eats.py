"""
uber_eats.py — Scraper para Uber Eats México (www.ubereats.com/mx).

Selectores validados: 2026-04-07

Flujo:
1. Navegar a homepage
2. Setear dirección via #location-typeahead-home-input
3. Seleccionar sugerencia via li:has-text(...)
4. Redireccion automática al feed con catálogo
5. Buscar restaurante via input[placeholder*="Buscar"]
6. Extraer datos de tarjetas de búsqueda (ETA) y página del restaurante (precio)

Notas de Uber Eats:
- Usa Google Places para autocomplete de dirección
- El feed se carga automáticamente al seleccionar dirección
- Tiene banner de cookies que bloquea — hacer click en "Aceptar"
- La navegación directa por URL activa el challenge anti-bot;
  se prefiere click natural en los elementos
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
    "coca_cola_600ml": ["Coca-Cola 600ml", "Coca Cola 600"],
}

PRODUCT_MATCH_PATTERNS: dict[str, list[str]] = {
    "big_mac": ["Big Mac"],
    "coca_cola_600ml": ["Coca-Cola 600", "Coca Cola 600", "Coca.Cola.*600", "600.*[Cc]oca"],
}


class UberEatsScraper(AbstractScraper):
    """Scraper para Uber Eats México."""

    platform = "uber_eats"
    BASE_URL = PLATFORM_BASE_URLS["uber_eats"]

    def __init__(self) -> None:
        super().__init__()
        self._playwright: Playwright | None = None
        self._search_eta: int | None = None
        self._search_fee: float | None = None
        self._search_promo: str = ""

    def before_scrape_one(self, address: Address, product: Product) -> None:
        self._search_eta = None
        self._search_fee = None
        self._search_promo = ""

    # ------------------------------------------------------------------
    # Setup / Teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        pw = sync_playwright().start()
        self._playwright = pw
        self._browser: Browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--lang=es-MX"],
        )
        self._context: BrowserContext = self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=get_random_user_agent(),
            locale="es-MX",
            timezone_id="America/Mexico_City",
            geolocation={"latitude": 19.4326, "longitude": -99.1332},
            permissions=["geolocation"],
            extra_http_headers={"Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8"},
        )
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._page: Page = self._context.new_page()
        self._page.set_default_timeout(REQUEST_TIMEOUT_MS)
        logger.info("UberEatsScraper: browser iniciado")

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

    def _screenshot(self, label: str) -> None:
        try:
            from scraper.config import ROOT_DIR
            path = ROOT_DIR / "logs" / f"uber_{label}.png"
            self._page.screenshot(path=str(path), full_page=True)
            logger.info("UberEats: screenshot guardado en %s", path)
        except Exception as exc:
            logger.debug("UberEats: no se pudo guardar screenshot: %s", exc)

    def _wait_for_page_ready(self) -> None:
        page = self._page
        try:
            page.wait_for_load_state("domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        except PlaywrightTimeout:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            pass

    def _dismiss_popups(self) -> None:
        page = self._page
        for sel in ["button:has-text('Aceptar')", "button:has-text('Accept')", "button:has-text('Cerrar')"]:
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
        search_text = f"{address.street}, {address.neighborhood}, Ciudad de México"
        _SKIP = {"av.", "avenida", "pasaje", "blvd.", "boulevard", "calle"}
        address_keyword = next(
            (w for w in address.street.split() if w.lower().rstrip(".") not in _SKIP and len(w) > 3),
            address.street.split()[0],
        )
        logger.info("UberEats: seteando dirección zone=%s keyword='%s'", address.zone, address_keyword)

        page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        self._wait_for_page_ready()
        self._dismiss_popups()
        random_delay()

        # Address input — Uber Eats uses #location-typeahead-home-input
        addr_input = page.locator("#location-typeahead-home-input")
        if not addr_input.is_visible(timeout=5000):
            # Fallback: any text input
            addr_input = page.locator('input[type="text"]').first
            if not addr_input.is_visible(timeout=3000):
                logger.warning("UberEats: input de dirección no visible para zone=%s", address.zone)
                return False

        addr_input.click()
        page.wait_for_timeout(500)
        addr_input.type(search_text, delay=60)
        random_delay(min_seconds=2.5, max_seconds=4.0)

        # Select first suggestion
        suggestion = page.locator(f'li:has-text("{address_keyword}")').first
        if suggestion.is_visible(timeout=5000):
            suggestion.click()
            random_delay(min_seconds=3.0, max_seconds=5.0)
        else:
            page.keyboard.press("Enter")
            random_delay(min_seconds=3.0, max_seconds=5.0)

        self._wait_for_page_ready()
        self._dismiss_popups()

        # Uber Eats puede redirigir a /category-feed/... que no tiene search input.
        # Navegar explícitamente al feed principal preservando el parámetro de dirección.
        current_url = page.url
        if "/feed" not in current_url or "category-feed" in current_url:
            # Extraer el parámetro pl= de la URL actual para preservar la dirección
            import re as _re
            pl_match = _re.search(r"[?&](pl=[^&]+)", current_url)
            feed_url = self.BASE_URL + "/feed"
            if pl_match:
                feed_url += "?" + pl_match.group(1) + "&diningMode=DELIVERY"
            logger.info("UberEats: redirigido a %s, navegando a feed: %s", current_url, feed_url)
            page.goto(feed_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            self._wait_for_page_ready()
            self._dismiss_popups()

        logger.info("UberEats: dirección seteada para zone=%s — url=%s", address.zone, page.url)
        return True

    def search_product(self, product: Product) -> bool:
        page = self._page
        terms = SEARCH_TERMS.get(product.key, [product.display_name])
        logger.info("UberEats: buscando producto %s", product.key)

        for term in terms:
            # Dismiss overlays BEFORE locating the search input
            self._dismiss_popups()

            # Try multiple selectors — Uber Eats placeholder varies by locale
            search_input = page.locator(
                'input[placeholder*="Buscar"], input[placeholder*="Search"], '
                'input[type="search"], input[data-testid*="search"], '
                'input[placeholder*="Busca"]'
            ).first
            try:
                search_input.wait_for(state="visible", timeout=8000)
            except Exception:
                logger.warning("UberEats: barra de búsqueda no visible para '%s' — url=%s", term, page.url)
                # Log all inputs to find the correct selector
                try:
                    all_inputs = page.locator("input").all()
                    logger.warning("  Total inputs en página: %d", len(all_inputs))
                    for i, inp in enumerate(all_inputs[:10]):
                        try:
                            logger.warning("  input[%d]: type=%s placeholder=%s visible=%s",
                                i, inp.get_attribute("type"), inp.get_attribute("placeholder"),
                                inp.is_visible(timeout=200))
                        except Exception:
                            pass
                except Exception:
                    pass
                self._screenshot(f"no_search_input_{term.replace(' ', '_')}")
                continue

            search_input.scroll_into_view_if_needed()
            search_input.click()
            page.wait_for_timeout(500)
            search_input.fill("")
            page.wait_for_timeout(300)
            search_input.type(term, delay=60)
            random_delay(min_seconds=2.0, max_seconds=3.0)
            page.keyboard.press("Enter")
            random_delay(min_seconds=3.0, max_seconds=5.0)
            self._wait_for_page_ready()

            # Extract store info from search result cards
            self._extract_store_info_from_search(term)

            # Click first result — for product searches the card won't have the
            # product name, so fall back to the first store link found.
            result = page.locator(f'h3:has-text("{term}")').first
            if not result.is_visible(timeout=3000):
                result = page.locator(f'a:has-text("{term}")').first
            if not result.is_visible(timeout=3000):
                result = page.locator('a[href*="/store/"], a[href*="/tienda/"]').first
            if not result.is_visible(timeout=3000):
                result = page.locator("main a[href]").first

            if result.is_visible(timeout=5000):
                result.click()
                random_delay(min_seconds=3.0, max_seconds=5.0)
                self._wait_for_page_ready()
                if "challenge" in page.url:
                    logger.warning("UberEats: challenge detectado al entrar al restaurante")
                    page.go_back()
                    random_delay()
                    return True
                logger.info("UberEats: entró al resultado para '%s'", term)
                return True

            logger.warning("UberEats: no se encontró resultado para '%s'", term)

        return False

    def _extract_store_info_from_search(self, term: str) -> None:
        """Extrae ETA y fee del resultado de búsqueda (tarjeta del restaurante)."""
        page = self._page
        self._search_eta = None
        self._search_fee = None
        self._search_promo = ""

        try:
            # Uber Eats search results: "McDonald's Antara\n4.5\n(15,000+)\n•\n18 min"
            # Also: "Costo de envío de $0 con Uber One."
            # Also: "Gasta $300, ahorra $120"

            # Get the section text near the first result
            result_heading = page.locator(f'h3:has-text("{term}")').first
            if not result_heading.is_visible(timeout=3000):
                return

            # Get parent card text
            card = result_heading.locator("xpath=ancestor::*[5]")
            card_text = card.inner_text()

            # ETA: "XX min"
            eta_match = re.search(r"(\d+)\s*min", card_text)
            if eta_match:
                self._search_eta = int(eta_match.group(1))

            # Fee from global banner: "Costo de envío de $X" or "Envío gratis"
            fee_banner = page.locator('text=/Costo de env[íi]o/i').first
            if fee_banner.is_visible(timeout=2000):
                fee_text = fee_banner.inner_text()
                if re.search(r"gratis|free|\$\s*0", fee_text, re.IGNORECASE):
                    self._search_fee = 0.0
                else:
                    fee_match = re.search(r"\$\s*([\d,.]+)", fee_text)
                    if fee_match:
                        self._search_fee = parse_price(f"${fee_match.group(1)}")

            # Promos
            promo_els = page.locator('text=/ahorro|descuento|Oferta/i').all()
            promos = []
            for el in promo_els[:2]:
                try:
                    if el.is_visible(timeout=1000):
                        promos.append(el.inner_text().strip()[:80])
                except (PlaywrightTimeout, Exception):
                    pass
            self._search_promo = "; ".join(promos) if promos else ""

            logger.info("UberEats search: fee=%s eta=%s promo='%s'",
                        self._search_fee, self._search_eta, self._search_promo)
        except (PlaywrightTimeout, Exception) as exc:
            logger.debug("No se pudo extraer info de búsqueda: %s", exc)

    def extract_data(self, address: Address, product: Product) -> ScrapeResult:
        page = self._page
        logger.info("UberEats: extrayendo datos para %s en %s", product.key, address.zone)

        price = self._extract_product_price(product)
        fee = self._search_fee
        eta = self._search_eta

        # If we're on the restaurant page, try to extract from there too
        if "challenge" not in page.url:
            if price is None:
                price = self._extract_product_price(product)
            if fee is None:
                fee = self._extract_fee_from_restaurant()
            if eta is None:
                eta = self._extract_eta_from_restaurant()

        if price is None:
            logger.warning("UberEats: precio no encontrado para %s/%s", product.key, address.zone)
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
            promotions=self._search_promo,
            scrape_status="success",
        )

    def _extract_product_price(self, product: Product) -> float | None:
        """Busca el precio del producto en la página del restaurante."""
        page = self._page
        patterns = PRODUCT_MATCH_PATTERNS.get(product.key, [product.display_name])

        for pattern in patterns:
            try:
                items = page.locator(f'text=/{pattern}/i').all()
                for item in items[:8]:
                    if not item.is_visible(timeout=1000):
                        continue
                    for level in range(2, 5):
                        ancestor = item.locator(f"xpath=ancestor::*[{level}]")
                        text = ancestor.inner_text()
                        if "$" not in text:
                            continue
                        # Find price pattern
                        prices = re.findall(r"\$\s*([\d,.]+)", text)
                        for p in prices:
                            val = parse_price(f"${p}")
                            if val and 15 < val < 500:
                                # Skip combos
                                before_price = text.split(f"${p}")[0]
                                if "McTrío" in before_price or "combo" in before_price.lower():
                                    continue
                                logger.info("UberEats: precio %s = $%.2f", pattern, val)
                                return val
            except (PlaywrightTimeout, Exception):
                continue

        # Fallback: first $ element
        try:
            for el in page.locator('text=/^\\$\\s*\\d/').all()[:10]:
                if el.is_visible(timeout=500):
                    val = parse_price(el.inner_text())
                    if val and 15 < val < 500:
                        return val
        except (PlaywrightTimeout, Exception):
            pass
        return None

    def _extract_fee_from_restaurant(self) -> float | None:
        page = self._page
        try:
            # "Envío gratis" / "Entrega gratis" wins immediately
            gratis = page.locator(r'text=/[Ee]nv[íi]o\s*gratis|[Ee]ntrega\s*gratis/').first
            if gratis.is_visible(timeout=1500):
                return 0.0

            for sel in ['text=/Tarifa de entrega/i', 'text=/Costo de env[íi]o/i', 'text=/env[íi]o/i']:
                el = page.locator(sel).first
                if not el.is_visible(timeout=1500):
                    continue
                text = el.inner_text()
                if re.search(r"gratis|free|\$\s*0\b", text, re.IGNORECASE):
                    return 0.0
                price = parse_price(text)
                if price is not None:
                    return price
                # Check parent element which may include the price value
                try:
                    parent_text = el.locator("xpath=..").inner_text()
                    price = parse_price(parent_text)
                    if price is not None:
                        return price
                except Exception:
                    pass
        except (PlaywrightTimeout, Exception):
            pass
        return None

    def _extract_eta_from_restaurant(self) -> int | None:
        page = self._page
        try:
            for el in page.locator('text=/\\d+\\s*min/').all()[:5]:
                if el.is_visible(timeout=1000):
                    return parse_time_minutes(el.inner_text())
        except (PlaywrightTimeout, Exception):
            pass
        return None
