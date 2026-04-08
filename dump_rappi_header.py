import sys
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-MX",
            geolocation={"latitude": 19.4326, "longitude": -99.1332},
            permissions=["geolocation"],
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()
        page.goto("https://www.rappi.com.mx", timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(5000)
        
        header = page.locator("header").first
        if header.is_visible():
            # Get all elements with svg in header
            elements = header.locator("*").all()
            for el in elements:
                try:
                    if el.locator("svg").count() > 0 and len(el.inner_text().strip()) > 5:
                        print(f"TAG: {el.evaluate('e => e.tagName')}, CLASS: {el.get_attribute('class')}, TEXT: {el.inner_text()}, TESTID: {el.get_attribute('data-testid')}, ARIALABEL: {el.get_attribute('aria-label')}")
                except Exception:
                    pass
        else:
            print("No header found")
        browser.close()

run()
