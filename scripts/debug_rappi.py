"""
debug_rappi.py — Script de diagnóstico interactivo para Rappi.

Corre con headless=False para ver el browser en pantalla y hace pausa
en cada paso clave. Usa solo la primera zona (polanco) y big_mac.

Uso:
    cd ~/Documents/rappi/rappi-test-2
    .venv/bin/python scripts/debug_rappi.py
"""

import logging
import time
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("debug_rappi")

BASE_URL = "https://www.rappi.com.mx"
ADDRESS_TEXT = "Presidente Masaryk 360, Polanco V Sección"
ADDRESS_KEYWORD = "Presidente"
SEARCH_TERM = "McDonald's"


def pause(msg: str, seconds: float = 2.0) -> None:
    logger.info(">>> %s (esperando %.0fs...)", msg, seconds)
    time.sleep(seconds)


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,  # VER el browser en pantalla
        slow_mo=300,     # ralentizar para poder seguir visualmente
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="es-MX",
        timezone_id="America/Mexico_City",
        geolocation={"latitude": 19.4326, "longitude": -99.1995},
        permissions=["geolocation"],
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.new_page()

    # ── 1. Cargar homepage ──────────────────────────────────────────────────
    logger.info("Navegando a %s", BASE_URL)
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.screenshot(path="logs/debug_01_homepage.png")
    logger.info("Título de página: %s", page.title())
    pause("Homepage cargada")

    # ── 2. Buscar input de dirección ────────────────────────────────────────
    addr_input = page.locator('input[placeholder*="Dónde quieres"]')
    logger.info("input[placeholder*='Dónde quieres'] visible: %s", addr_input.is_visible(timeout=5000))

    # Si no visible, mostrar todos los inputs disponibles
    if not addr_input.is_visible(timeout=1000):
        logger.warning("Input no visible — listando todos los inputs en la página:")
        all_inputs = page.locator("input").all()
        for i, inp in enumerate(all_inputs[:10]):
            try:
                logger.warning("  input[%d]: type=%s placeholder=%s visible=%s",
                               i,
                               inp.get_attribute("type"),
                               inp.get_attribute("placeholder"),
                               inp.is_visible(timeout=200))
            except Exception:
                pass
        page.screenshot(path="logs/debug_02_no_addr_input.png")
        logger.error("BLOQUEADO en paso 2 — revisar debug_02_no_addr_input.png")
        pause("Ver screenshot", 5)
    else:
        # ── 3. Escribir dirección ───────────────────────────────────────────
        addr_input.click()
        time.sleep(0.5)
        addr_input.type(ADDRESS_TEXT, delay=60)
        page.screenshot(path="logs/debug_03_typing_address.png")
        pause("Dirección escrita, esperando sugerencias", 3)

        # ── 4. Inspeccionar sugerencias ─────────────────────────────────────
        logger.info("Buscando li con texto '%s'", ADDRESS_KEYWORD)
        all_li = page.locator("li").all()
        logger.info("Total <li> en página: %d", len(all_li))
        for i, li in enumerate(all_li[:15]):
            try:
                txt = li.inner_text().strip().replace("\n", " ")
                vis = li.is_visible(timeout=200)
                if txt:
                    logger.info("  li[%d] visible=%s: %s", i, vis, txt[:80])
            except Exception:
                pass
        page.screenshot(path="logs/debug_04_suggestions.png")
        pause("Sugerencias inspeccionadas")

        suggestion = page.locator(f'li:has-text("{ADDRESS_KEYWORD}")').first
        logger.info("Sugerencia 'li:has-text(\"%s\")' visible: %s", ADDRESS_KEYWORD, suggestion.is_visible(timeout=3000))

        if suggestion.is_visible(timeout=1000):
            suggestion.click()
            time.sleep(2)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.screenshot(path="logs/debug_05_after_address.png")
            pause("Dirección seteada")

            # ── 5. Cerrar banners / manejar redirect ANTES de buscar el input ──
            # Dismiss only safe close buttons (never navigation buttons like PROMOCIONES)
            for sel in ["button:has-text('Ok, entendido')", "button:has-text('Aceptar')", "button:has-text('Cerrar')"]:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=800):
                        logger.info("Cerrando banner: %s", sel)
                        btn.click(timeout=1000)
                        time.sleep(0.5)
                except Exception:
                    pass

            # If Rappi redirected to /promociones or similar, go back to home
            current_url = page.url
            if "/promocion" in current_url or current_url.rstrip("/") != BASE_URL.rstrip("/"):
                logger.info("Rappi redirigió a %s — volviendo a home", current_url)
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            page.screenshot(path="logs/debug_06_after_dismiss.png")

            # ── 6. Buscar barra de search ───────────────────────────────────
            # Esperar a que el input esté visible Y habilitado antes de interactuar
            search_input = page.locator('input[type="search"]').first
            logger.info("Esperando input[type=search] visible y editable...")
            try:
                search_input.wait_for(state="visible", timeout=10000)
            except Exception:
                logger.error("input[type=search] no se volvió visible en 10s")
            logger.info("input[type=search] visible: %s", search_input.is_visible(timeout=1000))
            page.screenshot(path="logs/debug_06b_search_bar.png")

            if search_input.is_visible(timeout=1000):
                search_input.scroll_into_view_if_needed()
                search_input.click()
                time.sleep(0.8)
                search_input.fill("")
                time.sleep(0.3)
                search_input.type(SEARCH_TERM, delay=60)
                page.keyboard.press("Enter")
                time.sleep(4)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                page.screenshot(path="logs/debug_07_search_results.png")
                logger.info("Resultado de búsqueda para '%s' guardado", SEARCH_TERM)
                pause("Resultados de búsqueda", 4)
            else:
                logger.error("BLOQUEADO en paso 5 — search bar no visible")
                page.screenshot(path="logs/debug_06_no_search.png")
        else:
            logger.error("BLOQUEADO en paso 4 — sugerencia no encontrada")

    logger.info("=== Diagnóstico completo. Screenshots en logs/debug_*.png ===")
    pause("Cerrando browser", 3)
    browser.close()
