"""
rappi.py — Scraper para Rappi México (www.rappi.com.mx).

Flujo por producto:
    Big Mac       → busca "McDonald's" → entra al primer resultado → header (fee + ETA) → "Big Mac" en menú
    Coca-Cola     → busca "OXXO"       → entra al primer resultado → header (fee + ETA) → "Coca-Cola 600" en menú

El fee y ETA se extraen del HEADER del restaurante (más confiable que las tarjetas de búsqueda).
El precio se extrae del menú dentro del restaurante.
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

# Qué cadena buscar para cada producto
STORE_SEARCH: dict[str, str] = {
    "big_mac": "McDonald's",
    "coca_cola_600ml": "OXXO",
}

# Patrones para encontrar el producto dentro del menú de la tienda
PRODUCT_MATCH_PATTERNS: dict[str, list[str]] = {
    "big_mac": [r"Big Mac\b"],
    "coca_cola_600ml": [r"Coca[\s\-]Cola.*600", r"Coca.*Cola.*600", r"600.*[Cc]oca"],
}

# Precio máximo razonable por producto (para descartar falsos positivos)
PRICE_CEILING: dict[str, float] = {
    "big_mac": 300.0,
    "coca_cola_600ml": 80.0,
}

# Precio mínimo razonable por producto
PRICE_FLOOR: dict[str, float] = {
    "big_mac": 80.0,
    "coca_cola_600ml": 15.0,
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
        try:
            from scraper.config import ROOT_DIR
            path = ROOT_DIR / "logs" / f"rappi_{label}.png"
            self._page.screenshot(path=str(path), full_page=False)
            logger.info("Rappi: screenshot → %s", path)
        except Exception as exc:
            logger.debug("Rappi: screenshot falló: %s", exc)

    def _reset_context(self) -> None:
        for resource in (getattr(self, "_page", None), getattr(self, "_context", None)):
            try:
                if resource:
                    resource.close()
            except Exception:
                pass
        self._context = self._browser.new_context(
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
        self._page = self._context.new_page()
        self._page.set_default_timeout(REQUEST_TIMEOUT_MS)
        logger.info("RappiScraper: contexto reiniciado")

    def _wait_for_page_ready(self) -> None:
        import time
        page = self._page
        try:
            page.wait_for_load_state("domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        except Exception:
            pass
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
            "button:has-text('Continuar')",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=800):
                    loc.click(timeout=2000)
                    page.wait_for_timeout(400)
            except (PlaywrightTimeout, Exception):
                pass

    # ------------------------------------------------------------------
    # Address
    # ------------------------------------------------------------------

    def set_delivery_address(self, address: Address) -> bool:
        page = self._page
        search_text = f"{address.street}, {address.neighborhood}"
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

        # Rappi puede cargar con una dirección ya seteada (geolocalización automática).
        # En ese caso el input "Dónde quieres" no aparece; en su lugar hay un botón
        # en el header con la dirección actual. Hay que clickearlo para abrir el modal.
        addr_input = self._open_address_input()
        if addr_input is None:
            logger.warning("Rappi: no se pudo abrir el input de dirección zone=%s", address.zone)
            self._screenshot(f"no_addr_input_{address.zone}")
            return False

        addr_input.click()
        page.wait_for_timeout(500)
        addr_input.fill("", timeout=5000)
        page.wait_for_timeout(200)
        addr_input.type(search_text, delay=60)
        random_delay(min_seconds=2.0, max_seconds=3.5)

        suggestion = page.locator(f'li:has-text("{address_keyword}")').first
        if not suggestion.is_visible(timeout=5000):
            try:
                all_li = page.locator("li").all()
                visible_texts = [li.inner_text() for li in all_li[:10] if li.is_visible(timeout=300)]
                logger.warning("Rappi: sugerencia no encontrada para '%s'. LIs: %s", address_keyword, visible_texts)
            except Exception:
                pass
            self._screenshot(f"no_suggestion_{address.zone}")
            return False

        suggestion.click()
        random_delay(min_seconds=2.0, max_seconds=3.0)
        self._wait_for_page_ready()
        self._dismiss_popups()

        current_url = page.url
        if "/promocion" in current_url or current_url.rstrip("/") != self.BASE_URL.rstrip("/"):
            logger.info("Rappi: redirigió a %s, volviendo a home", current_url)
            page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            self._wait_for_page_ready()
            self._dismiss_popups()

        logger.info("Rappi: dirección seteada zone=%s url=%s", address.zone, page.url)
        return True

    def _open_address_input(self):
        """
        Devuelve el input de dirección listo para escribir.

        Rappi tiene dos estados posibles en el home:
        1. Sin dirección → aparece `input[placeholder*="Dónde quieres"]` directamente.
        2. Con dirección (geolocalización automática) → el header muestra la dirección
           actual como botón; hay que clickearlo para abrir el modal con el input.
        """
        page = self._page

        # Estado 1: input directo ya visible
        direct = page.locator('input[placeholder*="Dónde quieres"]').first
        if direct.is_visible(timeout=3000):
            return direct

        # Estado 2: hay una dirección activa en el header — intentar abrirla
        header_btn_selectors = [
            # Botón de dirección en el header (contiene ícono de pin + texto)
            'header [data-testid*="address"]',
            'header [data-testid*="location"]',
            'header button:has([data-icon*="pin"])',
            'header button:has([data-icon*="location"])',
            # Fallback genérico: el texto de la dirección actual en el header es un botón/link
            'header button:has(svg)',
            '[class*="address-bar"]',
            '[class*="location-bar"]',
            '[class*="delivery-address"]',
            # Selector por aria
            'button[aria-label*="direcci"]',
            'button[aria-label*="ubicaci"]',
        ]
        for sel in header_btn_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1500):
                    btn.click()
                    page.wait_for_timeout(800)
                    # Ahora debe aparecer el input dentro del modal
                    for input_sel in [
                        'input[placeholder*="Dónde quieres"]',
                        'input[placeholder*="Busca"]',
                        'input[placeholder*="direcci"]',
                        'input[type="search"]',
                        'input[type="text"]',
                    ]:
                        inp = page.locator(input_sel).first
                        if inp.is_visible(timeout=3000):
                            return inp
            except Exception:
                continue

        # Último recurso: cualquier input visible en la página después de esperar
        page.wait_for_timeout(1000)
        for input_sel in [
            'input[placeholder*="Dónde quieres"]',
            'input[placeholder*="Busca"]',
            'input[placeholder*="direcci"]',
        ]:
            inp = page.locator(input_sel).first
            if inp.is_visible(timeout=2000):
                return inp

        return None

    # ------------------------------------------------------------------
    # Search: store first, then product inside
    # ------------------------------------------------------------------

    def search_product(self, product: Product) -> bool:
        """
        Busca la CADENA (McDonald's / OXXO) en el buscador de Rappi,
        entra al primer resultado, y deja la página lista para extract_data().
        """
        page = self._page
        store_name = STORE_SEARCH.get(product.key, product.display_name)
        logger.info("Rappi: buscando tienda '%s' para producto %s", store_name, product.key)

        self._dismiss_popups()

        search_input = page.locator('input[type="search"]').first
        try:
            search_input.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeout:
            logger.warning("Rappi: barra de búsqueda no visible para '%s'", store_name)
            self._screenshot(f"no_search_input_{product.key}")
            return False

        search_input.scroll_into_view_if_needed(timeout=3000)
        search_input.click(timeout=5000)
        page.wait_for_timeout(400)
        search_input.fill("", timeout=5000)
        page.wait_for_timeout(200)
        search_input.type(store_name, delay=60)
        random_delay(min_seconds=1.5, max_seconds=2.5)
        page.keyboard.press("Enter")
        random_delay(min_seconds=3.0, max_seconds=5.0)
        self._wait_for_page_ready()

        # Click the first store result card
        entered = self._click_first_store_result(store_name)
        if not entered:
            self._screenshot(f"no_store_result_{product.key}")
            logger.warning("Rappi: no se encontró tienda '%s'", store_name)
            return False

        random_delay(min_seconds=2.5, max_seconds=4.0)
        self._wait_for_page_ready()
        self._dismiss_popups()

        # Now we are inside the restaurant/store page — extract header info
        self._extract_header_info(store_name, product)

        logger.info("Rappi: dentro de '%s' — fee=%s eta=%s", store_name, self._store_fee, self._store_eta)
        return True

    def _click_first_store_result(self, store_name: str) -> bool:
        """Intenta hacer click en la primera tarjeta de la tienda en resultados."""
        page = self._page

        # Strategy 1: link with store name in text (most reliable)
        for sel in [
            f'a:has-text("{store_name}")',
            f'[class*="store"]:has-text("{store_name}")',
            f'[class*="card"]:has-text("{store_name}")',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=3000):
                    loc.click()
                    return True
            except Exception:
                continue

        # Strategy 2: first store/tienda link regardless of text
        for sel in [
            'a[href*="/tienda/"]',
            'a[href*="/store/"]',
            'a[href*="/restaurante/"]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    return True
            except Exception:
                continue

        return False

    def _extract_header_info(self, store_name: str, product: Product) -> None:
        """
        Extrae delivery fee, ETA y promos del header de la página del restaurante.
        En Rappi el header contiene algo como:
            "McDonald's Polanco · 4.8 · 14 min · Envío Gratis"
            "OXXO Insurgentes · 3.9 · 20 min · $ 29.00"
        """
        page = self._page

        # -- ETA --
        try:
            eta_els = page.locator('text=/\\d+\\s*(?:–|-)?\\s*\\d*\\s*min/').all()
            for el in eta_els[:5]:
                if el.is_visible(timeout=800):
                    eta = parse_time_minutes(el.inner_text())
                    if eta:
                        self._store_eta = eta
                        break
        except Exception:
            pass

        # -- Fee: check gratis first, then look for $XX --
        try:
            gratis = page.locator('text=/[Ee]nv[íi]o\\s*[Gg]ratis|[Ee]ntrega\\s*[Gg]ratis/').first
            if gratis.is_visible(timeout=2000):
                self._store_fee = 0.0
        except Exception:
            pass

        if self._store_fee is None:
            # Look for fee in the page header area — walk all visible short text nodes
            try:
                # Rappi header uses a bar with "· $XX ·" or similar
                header_candidates = page.locator(
                    'header *, [class*="header"] *, [class*="restaurant-info"] *, [class*="store-info"] *'
                ).all()
                for el in header_candidates[:40]:
                    try:
                        if not el.is_visible(timeout=300):
                            continue
                        text = el.inner_text().strip()
                        if not text or len(text) > 60:
                            continue
                        if re.search(r"gratis|free", text, re.IGNORECASE):
                            self._store_fee = 0.0
                            break
                        m = re.search(r"^\$\s*([\d,.]+)$", text)
                        if m:
                            val = parse_price(f"${m.group(1)}")
                            if val is not None and 0 < val < 100:
                                self._store_fee = val
                                break
                    except Exception:
                        continue
            except Exception:
                pass

        if self._store_fee is None:
            # Fallback: scan entire page top section for first fee-like pattern
            try:
                page_text = page.locator("body").inner_text()
                # Look for fee right after ETA pattern
                m = re.search(
                    r"\d+\s*min[^$\n]{0,30}\$\s*([\d,.]+)",
                    page_text[:3000],
                )
                if m:
                    val = parse_price(f"${m.group(1)}")
                    if val is not None and 0 < val < 100:
                        self._store_fee = val
            except Exception:
                pass

        # -- Promos --
        try:
            promo_patterns = [
                r"env[íi]o\s*gratis",
                r"entrega\s*gratis",
                r"\d+\s*%\s*(?:de\s*)?(?:desc|off)",
                r"2\s*x\s*1",
                r"ahorra",
                r"oferta",
                r"primer\s*pedido",
                r"promo",
            ]
            page_top = page.locator("body").inner_text()[:4000]
            promos = []
            for line in page_top.split("\n"):
                line = line.strip()
                if not line or len(line) > 120:
                    continue
                for pat in promo_patterns:
                    if re.search(pat, line, re.IGNORECASE):
                        if line not in promos:
                            promos.append(line)
                        break
            self._store_promo = "; ".join(promos[:3])
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def extract_data(self, address: Address, product: Product) -> ScrapeResult:
        page = self._page
        logger.info("Rappi: extrayendo datos para %s en %s", product.key, address.zone)

        price = self._extract_product_price(product)

        if price is None:
            self._screenshot(f"no_price_{product.key}_{address.zone}")
            logger.warning("Rappi: precio no encontrado para %s/%s", product.key, address.zone)
            return ScrapeResult.not_available(self.platform, address, product)

        fee = self._store_fee
        eta = self._store_eta

        # Last-resort fee extraction from restaurant page if header parse failed
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
        """Busca el precio del producto en el menú del restaurante/tienda."""
        page = self._page
        patterns = PRODUCT_MATCH_PATTERNS.get(product.key, [re.escape(product.display_name)])
        floor = PRICE_FLOOR.get(product.key, 10.0)
        ceiling = PRICE_CEILING.get(product.key, 500.0)

        for pattern in patterns:
            try:
                items = page.locator(f"text=/{pattern}/i").all()
                for item in items:
                    if not item.is_visible(timeout=800):
                        continue
                    # Walk up to find the container with both name and price
                    for level in range(2, 6):
                        try:
                            ancestor = item.locator(f"xpath=ancestor::*[{level}]")
                            text = ancestor.inner_text()
                            lines = [l.strip() for l in text.split("\n") if l.strip()]

                            # Must have name line matching pattern
                            has_name = any(re.search(pattern, l, re.IGNORECASE) for l in lines)
                            if not has_name:
                                continue

                            # Skip combo/McTrío containers
                            combined = " ".join(lines)
                            if re.search(r"McTr[íi]o|combo|paquete|\+", combined, re.IGNORECASE):
                                # Only skip if the combo keyword appears before the price
                                # (it's a combo item, not an individual product)
                                continue

                            # Find price lines
                            for line in lines:
                                if line.startswith("$"):
                                    val = parse_price(line)
                                    if val and floor <= val <= ceiling:
                                        logger.info("Rappi: precio %s = $%.2f", pattern, val)
                                        return val
                        except Exception:
                            continue
            except (PlaywrightTimeout, Exception):
                continue

        # Fallback: first price in range anywhere on page
        try:
            price_els = page.locator('text=/^\\$\\s*\\d/').all()
            for el in price_els[:20]:
                if el.is_visible(timeout=400):
                    val = parse_price(el.inner_text())
                    if val and floor <= val <= ceiling:
                        logger.info("Rappi: precio fallback %s = $%.2f", product.key, val)
                        return val
        except (PlaywrightTimeout, Exception):
            pass

        return None

    def _extract_fee_from_page(self) -> float | None:
        """Last-resort fee extraction from restaurant page."""
        page = self._page
        try:
            gratis = page.locator('text=/[Ee]nv[íi]o\\s*[Gg]ratis|[Ee]ntrega\\s*[Gg]ratis/').first
            if gratis.is_visible(timeout=1500):
                return 0.0

            for sel in [
                'text=/[Cc]osto de env[íi]o/',
                'text=/[Tt]arifa de entrega/',
                'text=/[Ee]nv[íi]o/',
            ]:
                for el in page.locator(sel).all()[:5]:
                    try:
                        if not el.is_visible(timeout=400):
                            continue
                        text = el.inner_text()
                        if re.search(r"gratis|free", text, re.IGNORECASE):
                            return 0.0
                        m = re.search(r"\$\s*([\d,.]+)", text)
                        if m:
                            val = parse_price(f"${m.group(1)}")
                            if val is not None and val < 100:
                                return val
                        for xpath in ["xpath=..", "xpath=following-sibling::*[1]"]:
                            try:
                                related_text = el.locator(xpath).inner_text()
                                if re.search(r"gratis|free|\$\s*0\b", related_text, re.IGNORECASE):
                                    return 0.0
                                m = re.search(r"\$\s*([\d,.]+)", related_text)
                                if m:
                                    val = parse_price(f"${m.group(1)}")
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
        """Last-resort ETA extraction."""
        page = self._page
        try:
            for el in page.locator('text=/\\d+\\s*min/').all()[:5]:
                if el.is_visible(timeout=800):
                    return parse_time_minutes(el.inner_text())
        except (PlaywrightTimeout, Exception):
            pass
        return None
