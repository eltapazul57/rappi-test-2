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
    "whopper": ["Burger King"],
    "pizza_pepperoni": ["Little Caesars", "Little Caesar", "Little Caesars Pizza"],
    "coca_cola_600ml_711": ["7 Eleven", "7-Eleven"],
}

PRODUCT_MATCH_PATTERNS: dict[str, list[str]] = {
    "big_mac": ["Big Mac"],
    "coca_cola_600ml": ["Coca-Cola 600", "Coca Cola 600", "Coca.Cola.*600", "600.*[Cc]oca"],
    "whopper": ["Whopper"],
    "pizza_pepperoni": ["Pizza Pepperoni", "Pepperoni", "Hot N Ready Pepperoni"],
    "coca_cola_600ml_711": ["Coca-Cola 600", "Coca Cola 600", "Coca.Cola.*600", "600.*[Cc]oca"],
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
        self._reset_context()

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

    def _reset_context(self) -> None:
        for resource in (getattr(self, "_page", None), getattr(self, "_context", None)):
            try:
                if resource:
                    resource.close()
            except Exception:
                pass
        self._context = self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=get_random_user_agent(),
            locale="es-MX",
            timezone_id="America/Mexico_City",
            extra_http_headers={"Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8"},
        )
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(REQUEST_TIMEOUT_MS)
        logger.info("UberEatsScraper: contexto reiniciado")

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
            self._dismiss_popups()

            # Strategy 1: Try clicking the search icon/button to mount the input.
            # Uber Eats renders a clickable search element that only mounts the
            # <input> after interaction.
            search_input = None
            for search_trigger in [
                'a[href*="/search"]',
                'button[aria-label*="earch"]',
                'button[aria-label*="uscar"]',
                '[data-testid*="search"]',
            ]:
                trigger = page.locator(search_trigger).first
                try:
                    if trigger.is_visible(timeout=2000):
                        trigger.click()
                        page.wait_for_timeout(1500)
                        # Now look for the input that should have appeared
                        search_input = page.locator(
                            'input[placeholder*="Buscar"], input[placeholder*="Search"], '
                            'input[type="search"], input[placeholder*="Busca"]'
                        ).first
                        try:
                            search_input.wait_for(state="visible", timeout=3000)
                            break
                        except Exception:
                            search_input = None
                except Exception:
                    continue

            # Strategy 2: If input appeared, use it
            if search_input is not None:
                try:
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
                except Exception as exc:
                    logger.warning("UberEats: error usando search input: %s", exc)
                    # Fall through to Strategy 3
                    search_input = None

            # Strategy 3: Navigate directly to the search results URL.
            # The feed page often has 0 <input> elements — bypass entirely.
            if search_input is None:
                logger.info("UberEats: no search input, navegando a URL de búsqueda directa")
                from urllib.parse import urlencode, urlparse, parse_qs
                current = page.url
                # Preserve the pl= param (encoded address)
                parsed = urlparse(current)
                params = parse_qs(parsed.query)
                search_params: dict[str, str] = {"q": term}
                if "pl" in params:
                    search_params["pl"] = params["pl"][0]
                search_url = f"{self.BASE_URL}/search?{urlencode(search_params)}"
                logger.info("UberEats: navegando a %s", search_url)
                page.goto(search_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
                self._wait_for_page_ready()
                self._dismiss_popups()
                random_delay(min_seconds=2.0, max_seconds=4.0)

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
            self._screenshot(f"no_results_{term.replace(' ', '_')}")

        return False

    def _extract_store_info_from_search(self, term: str) -> None:
        """Extrae ETA y fee del resultado de búsqueda (tarjeta del restaurante)."""
        page = self._page
        self._search_eta = None
        self._search_fee = None
        self._search_promo = ""

        try:
            # Uber Eats search results card structure (varies):
            #   "McDonald's Antara\n4.5\n(15,000+)\n•\n18 min\n$0 Delivery Fee"
            #   "Costo de envío de $29\n15-25 min"
            #   "Envío gratis con Uber One"
            #   "Gasta $300, ahorra $120"

            # Find the card — try multiple ancestor levels to get full card text
            result_heading = page.locator(f'h3:has-text("{term}")').first
            if not result_heading.is_visible(timeout=3000):
                # Fallback: first store link
                result_heading = page.locator('a[href*="/store/"], a[href*="/tienda/"]').first
                if not result_heading.is_visible(timeout=2000):
                    return

            card_text = ""
            for level in range(3, 8):
                try:
                    ancestor = result_heading.locator(f"xpath=ancestor::*[{level}]")
                    card_text = ancestor.inner_text()
                    # Stop when we have enough context (ETA + fee indicators)
                    if "min" in card_text and ("$" in card_text or "gratis" in card_text.lower()):
                        break
                except Exception:
                    continue

            if not card_text:
                return

            # ETA: "XX min" or "XX-YY min"
            eta_match = re.search(r"(\d+)\s*(?:[-–]\s*\d+\s*)?min", card_text)
            if eta_match:
                self._search_eta = parse_time_minutes(eta_match.group(0))

            # --- Fee extraction (multi-strategy) ---
            # 1. Explicit fee labels in card text
            for line in card_text.split("\n"):
                line_lower = line.strip().lower()
                # "Envío gratis" / "Entrega gratis" / "$0 Delivery Fee"
                if re.search(r"env[íi]o\s*gratis|entrega\s*gratis|delivery\s*fee.*\$\s*0|\$\s*0.*delivery", line_lower):
                    self._search_fee = 0.0
                    break
                # "Costo de envío de $29" / "Envío de $15" / "Tarifa de entrega: $19"
                fee_label = re.search(r"(?:costo\s*de\s*env[íi]o|env[íi]o|tarifa\s*de\s*entrega|delivery\s*fee)\s*(?:de\s*)?\$\s*([\d,.]+)", line_lower)
                if fee_label:
                    self._search_fee = parse_price(f"${fee_label.group(1)}")
                    break
                # "$29 delivery" / "$0 envío"
                fee_suffix = re.search(r"\$\s*([\d,.]+)\s*(?:delivery|env[íi]o|entrega)", line_lower)
                if fee_suffix:
                    self._search_fee = parse_price(f"${fee_suffix.group(1)}")
                    break

            # 2. Look for fee elements elsewhere on the page if not found in card
            if self._search_fee is None:
                for sel in [
                    r'text=/[Cc]osto de env[íi]o/',
                    r'text=/[Tt]arifa de entrega/',
                    r'text=/[Dd]elivery [Ff]ee/',
                    r'text=/[Ee]nv[íi]o gratis/',
                    r'text=/[Ee]ntrega gratis/',
                ]:
                    el = page.locator(sel).first
                    try:
                        if el.is_visible(timeout=1500):
                            fee_text = el.inner_text()
                            if re.search(r"gratis|free|\$\s*0\b", fee_text, re.IGNORECASE):
                                self._search_fee = 0.0
                            else:
                                fee_val = re.search(r"\$\s*([\d,.]+)", fee_text)
                                if fee_val:
                                    self._search_fee = parse_price(f"${fee_val.group(1)}")
                            if self._search_fee is not None:
                                break
                    except Exception:
                        continue

            # --- Promos extraction ---
            promos = []
            promo_patterns = [
                r"ahorra?\s*\$?\s*[\d,.]+",
                r"gasta\s*\$\s*[\d,.]+.*ahorra",
                r"\d+%\s*(?:de\s*)?desc",
                r"(?:oferta|promo)",
                r"2\s*x\s*1",
                r"env[íi]o\s*gratis",
                r"entrega\s*gratis",
                r"uber\s*one",
            ]
            for line in card_text.split("\n"):
                line_s = line.strip()
                if not line_s or len(line_s) > 100:
                    continue
                for pat in promo_patterns:
                    if re.search(pat, line_s, re.IGNORECASE):
                        if line_s not in promos:
                            promos.append(line_s)
                        break
            # Also check page-level promo banners
            for sel in [r'text=/ahorra|descuento|[Oo]ferta|2\s*x\s*1|promo/i']:
                try:
                    for el in page.locator(sel).all()[:3]:
                        if el.is_visible(timeout=1000):
                            txt = el.inner_text().strip()[:80]
                            if txt and txt not in promos:
                                promos.append(txt)
                except Exception:
                    pass
            self._search_promo = "; ".join(promos[:3]) if promos else ""

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
            # "Envío gratis" / "Entrega gratis" / "$0 Delivery Fee"
            gratis = page.locator(r'text=/[Ee]nv[íi]o\s*gratis|[Ee]ntrega\s*gratis|\$\s*0\s*[Dd]elivery/').first
            if gratis.is_visible(timeout=1500):
                return 0.0

            for sel in [
                'text=/Tarifa de entrega/i',
                'text=/Costo de env[íi]o/i',
                'text=/Delivery Fee/i',
                'text=/env[íi]o/i',
            ]:
                el = page.locator(sel).first
                if not el.is_visible(timeout=1500):
                    continue
                text = el.inner_text()
                if re.search(r"gratis|free|\$\s*0\b", text, re.IGNORECASE):
                    return 0.0
                fee_match = re.search(r"\$\s*([\d,.]+)", text)
                if fee_match:
                    val = parse_price(f"${fee_match.group(1)}")
                    if val is not None:
                        return val
                # Check parent and sibling elements for the price value
                for xpath in ["xpath=..", "xpath=following-sibling::*[1]"]:
                    try:
                        related = el.locator(xpath)
                        related_text = related.inner_text()
                        if re.search(r"gratis|free|\$\s*0\b", related_text, re.IGNORECASE):
                            return 0.0
                        fee_match = re.search(r"\$\s*([\d,.]+)", related_text)
                        if fee_match:
                            val = parse_price(f"${fee_match.group(1)}")
                            if val is not None and val < 100:
                                return val
                    except Exception:
                        continue
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
