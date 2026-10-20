"""INT-1068 runtime verification: open report -> AI 复核 session dialog, capture screenshots + network."""
import sys, time, re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5500"
OUT = sys.argv[1] if len(sys.argv) > 1 else "shots"
REPORT_ID = sys.argv[2] if len(sys.argv) > 2 else "65"

requests_log = []
responses_log = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    page = ctx.new_page()

    def on_request(req):
        url = req.url
        if "/api/v1/" in url and not re.search(r"\.(js|css|png|jpg|svg|ico|woff2?)", url):
            requests_log.append(f"{req.method} {url}")
    def on_response(resp):
        url = resp.url
        if ("/api/v1/" in url) and re.search(r"(ai-review|/results|cases/search|reports/65)", url):
            try:
                body = resp.json()
            except Exception:
                body = ""
            responses_log.append((url, body))

    page.on("request", on_request)
    page.on("response", on_response)

    # AUTH_MODE=off: auto-login, go straight to report view
    page.goto(f"{BASE}/#/report/{REPORT_ID}", wait_until="networkidle", timeout=45000)
    time.sleep(4)
    page.screenshot(path=f"{OUT}/03-report.png")
    print("URL:", page.url)

    # find AI 复核 button
    ai_btn = page.locator("button:has-text('AI 复核')")
    print("AI 复核 button count:", ai_btn.count())
    if ai_btn.count() > 0:
        ai_btn.first.click(timeout=8000)
        time.sleep(5)
        page.screenshot(path=f"{OUT}/04-ai-review-session-light.png")
        print("Session dialog visible:", page.locator(".ai-review-session-dialog").count())
        # context card content
        ctx_text = page.locator(".ai-review-context-card").inner_text()
        print("=== CONTEXT CARD ===")
        print(ctx_text[:800])
    else:
        print("No AI 复核 button — dumping page text around case area")
        body = page.locator("body").inner_text()
        for line in body.splitlines():
            if "复核" in line:
                print(line[:120])

    # dark theme screenshot
    theme_btn = page.locator("button[title*='主题'], button:has-text('深色'), .theme-toggle, [class*='theme']").first
    try:
        if theme_btn.count() > 0:
            theme_btn.click(timeout=3000)
            time.sleep(1)
    except Exception:
        pass
    # if dialog still open, re-open via localStorage theme if needed
    page.screenshot(path=f"{OUT}/05-ai-review-session-dark.png")

    print("=== NETWORK (ai-review / results / cases) ===")
    seen = set()
    for r in requests_log:
        if r not in seen:
            seen.add(r)
            print(r)

    browser.close()
print("done")
