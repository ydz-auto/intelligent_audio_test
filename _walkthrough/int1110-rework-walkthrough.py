"""
INT-1110 返工走查——挑选合并两阶段 + 三视图 + 入口按钮（18 §3.8，INT-1034/INT-1047/INT-1048）。
返工点：基线合入 INT-1103 统一用例卡，三视图/购物车用例节点复用
common/test-case/PickCaseCard.vue（hideMeta + 前导三态勾选 + pcc-toggle 展开）。
连本 run dev server :5516（连常驻后端 :5000），登录 admin/admin123。
产出：每场景 浅/深 PNG + Network cherry-picks 请求汇总 + 统一卡渲染探针。
"""
import json
import pathlib
from playwright.sync_api import sync_playwright

OUT_DIR = pathlib.Path(__file__).parent / "shots" / "int1110-r2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:5516"
cherry_requests = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1560, "height": 980})
        page = ctx.new_page()

        def dismiss_banner():
            try:
                btn = page.query_selector(".auth-mode-banner__close")
                if btn:
                    btn.click()
                    page.wait_for_timeout(200)
            except Exception:
                pass

        def track_request(req):
            if "/tasks/cherry-picks/" in req.url or "/tasks/cherry-picks" in req.url:
                cherry_requests.append({"url": req.url, "method": req.method})

        page.on("request", track_request)

        # ---- 登录 ----
        page.goto(f"{BASE}/#/login", wait_until="domcontentloaded")
        page.wait_for_selector(".login-btn", timeout=15000)
        page.fill('input[type="text"]', "admin")
        page.fill('input[type="password"]', "admin123")
        page.click(".login-btn")
        page.wait_for_selector(".page-header, .dashboard, .sidebar", timeout=20000)
        dismiss_banner()

        # ---- 日常任务 tab（入口按钮） ----
        page.goto(f"{BASE}/#/tasks", wait_until="domcontentloaded")
        page.wait_for_selector(".start-pick-btn", timeout=20000)
        dismiss_banner()
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT_DIR / "1-daily-start-pick-light.png"), full_page=False)

        # ---- 开始挑选 → 阶段 1：选择任务 ----
        page.click(".start-pick-btn")
        page.wait_for_selector(".pts-title", timeout=15000)
        dismiss_banner()
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT_DIR / "2-phase1-tasks-light.png"), full_page=False)

        # ---- 阶段 1：勾选任务 + 下一步 ----
        task_rows = page.query_selector_all(".pts-row")
        print("phase1 task rows:", len(task_rows))
        for row in task_rows[:2]:
            cb = row.query_selector('input[type="checkbox"]')
            if cb:
                cb.check()
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT_DIR / "3-phase1-selected-light.png"), full_page=False)
        next_btn = page.query_selector(".pts-btn-primary")
        if next_btn:
            next_btn.click()
        else:
            page.get_by_text("下一步").click()

        # ---- 阶段 2：用例视图（统一用例卡 compact） ----
        page.wait_for_selector(".cpw-phase-title", timeout=15000)
        page.wait_for_selector(".cpw-tree .pt-row, .cpw-tree .case-card", timeout=15000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT_DIR / "4-phase2-caseview-light.png"), full_page=False)

        # 统一卡渲染探针：.case-card + .pcc-check 前导三态勾选 + .pcc-count 计数 + .pcc-toggle 展开
        case_cards = page.query_selector_all(".cpw-tree .case-card")
        pcc_checks = page.query_selector_all(".cpw-tree .pcc-check")
        pcc_counts = page.query_selector_all(".cpw-tree .pcc-count-label")
        pcc_toggles = page.query_selector_all(".cpw-tree .pcc-toggle")
        print(f"unified card probe: case-card={len(case_cards)} pcc-check={len(pcc_checks)} "
              f"pcc-count={len(pcc_counts)} pcc-toggle={len(pcc_toggles)}")
        probe = {
            "phase2_caseview": {
                "case_card": len(case_cards),
                "pcc_check": len(pcc_checks),
                "pcc_count": len(pcc_counts),
                "pcc_toggle": len(pcc_toggles),
            }
        }

        # 展开第一个用例卡（pcc-toggle 三角）
        if case_cards:
            toggle = case_cards[0].query_selector(".pcc-toggle")
            if toggle:
                toggle.click()
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUT_DIR / "5-phase2-caseview-expanded-light.png"), full_page=False)

        # ---- 设备视图 ----
        page.get_by_text("设备视图", exact=False).first.click()
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT_DIR / "6-phase2-deviceview-light.png"), full_page=False)

        # ---- 结果类型视图 ----
        page.get_by_text("结果类型视图", exact=False).first.click()
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT_DIR / "7-phase2-resulttypeview-light.png"), full_page=False)

        # ---- 深色：用例视图 ----
        page.evaluate("document.documentElement.classList.add('dark')")
        page.wait_for_timeout(400)
        page.get_by_text("用例视图", exact=False).first.click()
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT_DIR / "8-phase2-caseview-dark.png"), full_page=False)
        page.evaluate("document.documentElement.classList.remove('dark')")
        page.wait_for_timeout(300)

        # ---- 购物车抽屉（统一用例卡 compact） ----
        page.goto(f"{BASE}/#/tasks", wait_until="domcontentloaded")
        page.wait_for_selector(".pick-cart-entry", timeout=15000)
        dismiss_banner()
        page.click(".pick-cart-entry")
        page.wait_for_selector(".cd-drawer", timeout=15000)
        page.wait_for_timeout(800)
        # 展开任务节点 → 用例卡
        chev = page.query_selector(".cd-drawer .ctr-row .ctr-chevron")
        if chev:
            chev.click()
            page.wait_for_timeout(600)
        cart_cases = page.query_selector_all(".cd-drawer .case-card")
        cart_pcc = page.query_selector_all(".cd-drawer .pcc-check")
        cart_pcc_count = page.query_selector_all(".cd-drawer .pcc-count-label")
        print(f"cart unified card probe: case-card={len(cart_cases)} pcc-check={len(cart_pcc)} pcc-count={len(cart_pcc_count)}")
        probe["cart_drawer"] = {
            "case_card": len(cart_cases),
            "pcc_check": len(cart_pcc),
            "pcc_count": len(cart_pcc_count),
        }
        page.screenshot(path=str(OUT_DIR / "9-cart-drawer-light.png"), full_page=False)
        # 购物车深色
        page.evaluate("document.documentElement.classList.add('dark')")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT_DIR / "10-cart-drawer-dark.png"), full_page=False)
        page.evaluate("document.documentElement.classList.remove('dark')")
        page.wait_for_timeout(300)

        browser.close()

    # ---- 汇总 ----
    (OUT_DIR / "network-cherry-picks.json").write_text(
        json.dumps(cherry_requests, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "probe.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cherry-picks requests captured: {len(cherry_requests)}")
    for r in cherry_requests:
        print(f"  {r['method']} {r['url']}")


if __name__ == "__main__":
    main()
