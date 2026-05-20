from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_viewport_size({"width": 1400, "height": 900})
    
    page.goto('http://localhost:5173/#/report/11')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    
    page.screenshot(path='report_screenshot.png', full_page=True)
    
    print("Screenshot saved to report_screenshot.png")
    
    browser.close()
