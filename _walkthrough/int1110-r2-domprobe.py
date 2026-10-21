"""INT-1110-r2 DOM 探针：阶段2用例视图 + 购物车 统一用例卡文本内容（返工证据）。"""
import json
import pathlib
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5516"
OUT = pathlib.Path(__file__).parent / "shots" / "int1110-r2"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1560, "height": 980})
        page = ctx.new_page()

        def dismiss_banner():
            try:
                b = page.query_selector(".auth-mode-banner__close")
                if b:
                    b.click()
                    page.wait_for_timeout(200)
            except Exception:
                pass

        page.goto(f"{BASE}/#/login", wait_until="domcontentloaded")
        page.wait_for_selector(".login-btn", timeout=20000)
        page.wait_for_timeout(500)
        page.fill('input[type="text"]', "admin")
        page.fill('input[type="password"]', "admin123")
        page.click(".login-btn")
        try:
            page.wait_for_selector(".page-header, .dashboard, .sidebar", timeout=20000)
        except Exception:
            page.wait_for_selector("#app .sidebar, .layout-shell, .page-header", timeout=20000)
        page.wait_for_timeout(500)
        dismiss_banner()

        page.goto(f"{BASE}/#/tasks", wait_until="domcontentloaded")
        page.wait_for_selector(".start-pick-btn", timeout=20000)
        dismiss_banner()
        page.click(".start-pick-btn")
        page.wait_for_selector(".pts-title", timeout=15000)
        dismiss_banner()
        page.wait_for_timeout(800)
        rows = page.query_selector_all(".pts-row")
        for row in rows[:2]:
            cb = row.query_selector('input[type="checkbox"]')
            if cb:
                cb.check()
        page.wait_for_timeout(600)
        page.wait_for_selector(".pts-btn-primary:not([disabled])", timeout=15000)
        page.click(".pts-btn-primary")

        page.wait_for_selector(".cpw-tree .case-card", timeout=15000)
        page.wait_for_timeout(600)
        cards = page.query_selector_all(".cpw-tree .case-card")
        dump = {"phase2_case_cards": []}
        for i, c in enumerate(cards[:2]):
            dump["phase2_case_cards"].append({
                "index": i,
                "text": (c.inner_text() or "")[:300],
                "has_pcc_checkbox": c.query_selector(".pcc-checkbox") is not None,
                "has_pcc_count": c.query_selector(".pcc-count-label") is not None,
                "has_pcc_toggle": c.query_selector(".pcc-toggle") is not None,
                "has_case_id_badge": c.query_selector(".case-id-row") is not None,
            })

        # 购物车
        page.goto(f"{BASE}/#/tasks", wait_until="domcontentloaded")
        page.wait_for_selector(".pick-cart-entry", timeout=15000)
        dismiss_banner()
        page.click(".pick-cart-entry")
        page.wait_for_selector(".cd-drawer", timeout=15000)
        page.wait_for_timeout(800)
        chev = page.query_selector(".cd-drawer .ctr-row .ctr-chevron")
        if chev:
            chev.click()
            page.wait_for_timeout(600)
        page.wait_for_selector(".cd-drawer .case-card", timeout=15000)
        page.wait_for_timeout(500)
        cart_cards = page.query_selector_all(".cd-drawer .case-card")
        dump["cart_case_cards"] = []
        for i, c in enumerate(cart_cards[:2]):
            dump["cart_case_cards"].append({
                "index": i,
                "text": (c.inner_text() or "")[:300],
                "has_pcc_checkbox": c.query_selector(".pcc-checkbox") is not None,
                "has_pcc_count": c.query_selector(".pcc-count-label") is not None,
                "has_case_id_badge": c.query_selector(".case-id-row") is not None,
            })
        browser.close()

    (OUT / "dom-probe.json").write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dump, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
