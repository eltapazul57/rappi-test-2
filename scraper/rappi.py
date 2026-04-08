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
    "coca_cola_600ml": ["Coca-Cola 600ml", "Coca Cola 600"],
}

PRODUCT_MATCH_PATTERNS: dict[str, list[str]] = {
    "big_mac": ["Big Mac"],
    "coca_cola_600ml": ["Coca-Cola 600", "Coca Cola 600", "Coca.Cola.*600", "600.*[Cc]oca"],
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

    def _screenshot(self, label: str) -> None:
        """Guarda un screenshot en logs/ para diagnóstico."""
        try:
            from scraper.config import ROOT_DIR
            path = ROOT_DIR / "logs" / f"rappi_{label}.png"
            self._page.screenshot(path=str(path), full_page=True)
            logger.info("Rappi: screenshot guardado en %s", path)
        except Exception as exc:
            logger.debug("Rappi: no se pudo guardar screenshot: %s", exc)

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
        for sel in [
            "button:has-text('Ok, entendido')",
            "button:has-text('Aceptar')",
            "button:has-text('Cerrar')",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    loc.click(timeout=2000)
                    page.wait_for_timeout(400)
            except (PlaywrightTimeout, Exception):
                pass

    # ------------------------------------------------------------------
    # Scraping flow
    # ------------------------------------------------------------------

    def set_delivery_address(self, address: Address) -> bool:
        page = self._page
        search_text = f"{address.street}, {address.neighborhood}"
        # Pick the most distinctive word from the street to match suggestions.
        # Skip leading "Av." / "Avenida" / "Pasaje" etc. which are too generic.
        _SKIP = {"av.", "avenida", "pasaje", "blvd.", "boulevard", "calle"}
        address_keyword = next(
            (w for w in address.street.split() if w.lower().rstrip(".") not in _SKIP and len(w) > 3),
            address.street.split()[0],
        )
        logger.info("Rappi: seteando dirección zone=%s keyword='%s'", address.zone, address_keyword)

        page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        self._wait_for_page_ready()
        self._dismiss_popups()
        random_delay()

        # Address input — validated selector
        addr_input = page.locator('input[placeholder*="Dónde quieres"]')
        if not addr_input.is_visible(timeout=5000):
            # Context may be stale from a previous failed navigation; recreate and retry once
            self._screenshot(f"no_addr_input_{address.zone}")
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
            # Log what suggestions ARE visible to help debug the selector
            try:
                all_li = page.locator("li").all()
                visible_texts = [li.inner_text() for li in all_li[:10] if li.is_visible(timeout=300)]
                logger.warning("Rappi: sugerencia no encontrada para '%s'. LIs visibles: %s", address_keyword, visible_texts)
            except Exception:
                pass
            self._screenshot(f"no_suggestion_{address.zone}")
            return False

        suggestion.click()
        random_delay(min_seconds=2.0, max_seconds=3.0)
        self._wait_for_page_ready()
        self._dismiss_popups()

        # Rappi a veces redirige a /promociones u otras páginas tras setear la dirección.
        # Volver a la home para asegurar que el search bar esté activo.
        current_url = page.url
        if "/promocion" in current_url or current_url.rstrip("/") != self.BASE_URL.rstrip("/"):
            logger.info("Rappi: redirigió a %s, volviendo a home", current_url)
            page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            self._wait_for_page_ready()
            self._dismiss_popups()

        logger.info("Rappi: dirección seteada para zone=%s (url=%s)", address.zone, page.url)
        return True

    def search_product(self, product: Product) -> bool:
        page = self._page
        terms = SEARCH_TERMS.get(product.key, [product.display_name])
        logger.info("Rappi: buscando producto %s", product.key)

        for term in terms:
            # Dismiss overlays BEFORE locating the search input, so it's not covered
            self._dismiss_popups()

            search_input = page.locator('input[type="search"]').first
            try:
                search_input.wait_for(state="visible", timeout=8000)
            except Exception:
                logger.warning("Rappi: barra de búsqueda no visible para '%s'", term)
                continue

            search_input.scroll_into_view_if_needed(timeout=3000)
            search_input.click(timeout=5000)
            page.wait_for_timeout(500)
            try:
                search_input.fill("", timeout=10000)
            except Exception:
                # Last resort: force=True bypasses visibility check
                try:
                    search_input.fill("", force=True, timeout=5000)
                except Exception as exc:
                    logger.warning("Rappi: fill falló incluso con force=True: %s", exc)
                    self._screenshot(f"fill_failed_{product.key}")
                    continue
            page.wait_for_timeout(300)
            search_input.type(term, delay=60)
            random_delay(min_seconds=1.5, max_seconds=2.5)
            page.keyboard.press("Enter")
            random_delay(min_seconds=3.0, max_seconds=5.0)
            self._wait_for_page_ready()

            # Extract ETA and fee from search result cards BEFORE entering restaurant
            self._extract_store_info_from_search(term)

            # Click first result card — for product searches the link won't have the
            # product name, so fall back to the first anchor in the results area.
            result_link = page.locator(f'a:has-text("{term}")').first
            if not result_link.is_visible(timeout=3000):
                # Take the first clickable store card link on the page
                result_link = page.locator('a[href*="/tienda/"], a[href*="/store/"]').first
            if not result_link.is_visible(timeout=3000):
                result_link = page.locator("a[href]").first

            if result_link.is_visible(timeout=5000):
                result_link.click()
                random_delay(min_seconds=3.0, max_seconds=5.0)
                self._wait_for_page_ready()
                logger.info("Rappi: entró al resultado para '%s'", term)
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
            # Rappi search cards structure (each line separated by \n):
            #   "McDonald's Polanco\n4.5\n12 min\n•\nEnvío Gratis\n•\nAplican TyC"
            #   "McDonald's Roma\n4.3\n18 min\n•\n$ 29.00\n•\n..."
            # The fee appears AFTER the ETA and a bullet separator.
            # The raw "$" before the fee could be confused with a product price,
            # so we parse line-by-line and use context.

            card = page.locator(f'a:has-text("{term}")').first
            if not card.is_visible(timeout=3000):
                card = page.locator('a[href*="/tienda/"], a[href*="/store/"]').first
                if not card.is_visible(timeout=2000):
                    return
            card_text = card.inner_text()
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]

            # ETA: "12 min" or "12-18 min"
            eta_match = re.search(r"(\d+)\s*(?:[-–]\s*\d+\s*)?min", card_text)
            if eta_match:
                self._store_eta = parse_time_minutes(eta_match.group(0))

            # Fee: Look for fee-specific patterns line by line.
            # The fee line typically comes after ETA and a "•" separator.
            # It shows as "Envío Gratis", "$ 0.00", "$ 29.00", "Gratis", etc.
            found_eta = False
            for line in lines:
                line_lower = line.lower()

                # Track when we've passed the ETA line
                if re.search(r"\d+\s*min", line):
                    found_eta = True
                    continue

                # Skip separator bullets
                if line in ("•", "·", "|"):
                    continue

                # "Envío Gratis" or "Gratis" on its own line
                if re.search(r"env[íi]o\s*gratis|^gratis$", line_lower):
                    self._store_fee = 0.0
                    break

                # "$ 0.00" after ETA = free delivery
                if found_eta and re.match(r"^\$\s*0[.,]?0*$", line.strip()):
                    self._store_fee = 0.0
                    break

                # "$ 29.00" after ETA = delivery fee (not a product price)
                if found_eta and re.match(r"^\$\s*[\d,.]+$", line.strip()):
                    val = parse_price(line.strip())
                    if val is not None and val < 100:  # fees are typically < $100
                        self._store_fee = val
                        break

                # Explicit label: "Envío $ 29" or "Envío de $ 15"
                fee_label = re.search(r"env[íi]o\s*(?:de\s*)?\$\s*([\d,.]+)", line_lower)
                if fee_label:
                    self._store_fee = parse_price(f"${fee_label.group(1)}")
                    break

            # --- Promos ---
            promos = []
            promo_patterns = [
                r"env[íi]o\s*gratis",
                r"descuento",
                r"aplican\s*TyC",
                r"primer\s*pedido",
                r"\d+%\s*(?:de\s*)?desc",
                r"2\s*x\s*1",
                r"ahorra",
                r"oferta",
                r"promo",
                r"gratis",
            ]
            for line in lines:
                for pat in promo_patterns:
                    if re.search(pat, line, re.IGNORECASE):
                        if line not in promos and len(line) < 100:
                            promos.append(line)
                        break
            self._store_promo = "; ".join(promos[:3]) if promos else ""

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
            # 1. "Envío Gratis" / "Entrega Gratis" wins immediately
            gratis = page.locator(r'text=/[Ee]nv[íi]o\s*[Gg]ratis|[Ee]ntrega\s*[Gg]ratis/').first
            if gratis.is_visible(timeout=2000):
                return 0.0

            # 2. Look for fee labels and extract the price nearby
            for sel in [
                r'text=/[Cc]osto de env[íi]o/',
                r'text=/[Tt]arifa de entrega/',
                'text=/[Ee]nv[íi]o/',
            ]:
                for el in page.locator(sel).all()[:5]:
                    try:
                        if not el.is_visible(timeout=500):
                            continue
                        text = el.inner_text()
                        if re.search(r"gratis|free", text, re.IGNORECASE):
                            return 0.0
                        # Extract price from the element text itself
                        fee_match = re.search(r"\$\s*([\d,.]+)", text)
                        if fee_match:
                            val = parse_price(f"${fee_match.group(1)}")
                            if val is not None and val < 100:
                                return val
                        # Try parent and sibling which may contain the price value
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
                    except Exception:
                        continue
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
