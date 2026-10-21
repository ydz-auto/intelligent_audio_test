"""
INT-1110 返工第 3 轮（审计 01a15ddf P1）走查——设备视图/结果类型视图叶行层级与去重。
复现审计缺陷场景：同一条结果在 result_type 平铺叶 + 用例卡内叶并存（2 个 checkbox）；
修复后叶行只在最深分组节点渲染（设备/结果类型视图 = 用例卡内 pt-case-leaves，不重复）。

连本 run dev server :5516（连常驻后端 :5000），登录 admin/admin123。
产出：三视图展开截图（浅/深）+ DOM 叶行计数探针 + Network cherry-picks 请求。
"""
import json
import pathlib
from playwright.sync_api import sync_playwright

OUT_DIR = pathlib.Path(__file__).parent / "shots" / "int1110-r3-p1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:5516"
cherry_requests = []
probe = {}


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

        # ---- 日常任务 tab →「开始挑选」 ----
        page.goto(f"{BASE}/#/tasks", wait_until="domcontentloaded")
        page.wait_for_selector(".start-pick-btn", timeout=20000)
        dismiss_banner()
        page.click(".start-pick-btn")
        page.wait_for_selector(".pts-title", timeout=15000)
        dismiss_banner()
        page.wait_for_timeout(600)

        # ---- 阶段 1：勾选全部可挑选任务 + 下一步 ----
        rows = page.query_selector_all(".pts-row")
        print("phase1 task rows:", len(rows))
        for row in rows:
            cb = row.query_selector('input[type="checkbox"]')
            if cb:
                cb.check()
        page.wait_for_timeout(300)
        page.wait_for_selector(".pts-btn-primary:not([disabled])", timeout=15000)
        page.click(".pts-btn-primary")

        # ---- 阶段 2：等待候选加载（用例卡就绪） ----
        page.wait_for_selector(".cpw-phase-title", timeout=15000)
        page.wait_for_selector(".cpw-tree .case-card", timeout=20000)
        page.wait_for_timeout(800)
        dismiss_banner()

        def expand_all_and_wait():
            page.get_by_text("全部展开", exact=False).first.click()
            page.wait_for_timeout(600)

        def count_leaves():
            """返回 (总叶行数, 卡内叶行数, 卡外平铺叶行数, 叶勾选框数)"""
            total = len(page.query_selector_all(".cpw-tree .pt-leaf"))
            in_card = len(page.query_selector_all(".cpw-tree .pt-case-leaves .pt-leaf"))
            # 卡外平铺叶 = 不在 .pt-case-leaves 内的 .pt-leaf（审计 P1 的错误层级叶行）
            outside = page.evaluate(
                """() => {
                    const leaves = Array.from(document.querySelectorAll('.cpw-tree .pt-leaf'));
                    return leaves.filter(el => !el.closest('.pt-case-leaves')).length;
                }"""
            )
            checkboxes = len(page.query_selector_all(".cpw-tree .pt-leaf input.pt-checkbox"))
            return total, in_card, outside, checkboxes

        def probe_view(view_label, key):
            total, in_card, outside, checkboxes = count_leaves()
            print(f"[{view_label}] pt-leaf={total} in_card={in_card} outside_card={outside} checkbox={checkboxes}")
            probe[key] = {
                "pt_leaf_total": total,
                "in_case_card": in_card,
                "outside_case_card": outside,
                "checkbox": checkboxes,
            }

        # ---- 用例视图：全部展开 ----
        expand_all_and_wait()
        page.screenshot(path=str(OUT_DIR / "1-phase2-caseview-expanded-light.png"), full_page=False)
        probe_view("用例视图", "case_view")

        # ---- 设备视图：全部展开（审计 P1 场景） ----
        page.get_by_text("设备视图", exact=False).first.click()
        page.wait_for_timeout(800)
        expand_all_and_wait()
        page.screenshot(path=str(OUT_DIR / "2-phase2-deviceview-expanded-light.png"), full_page=False)
        probe_view("设备视图", "device_view")

        # ---- 结果类型视图：全部展开（审计 P1 场景） ----
        page.get_by_text("结果类型视图", exact=False).first.click()
        page.wait_for_timeout(800)
        expand_all_and_wait()
        page.screenshot(path=str(OUT_DIR / "3-phase2-resulttypeview-expanded-light.png"), full_page=False)
        probe_view("结果类型视图", "result_type_view")

        # ---- 深色：设备视图（审计截图同场景，修复后） ----
        page.evaluate("document.documentElement.classList.add('dark')")
        page.wait_for_timeout(400)
        page.get_by_text("设备视图", exact=False).first.click()
        page.wait_for_timeout(800)
        expand_all_and_wait()
        page.screenshot(path=str(OUT_DIR / "4-phase2-deviceview-expanded-dark.png"), full_page=False)
        page.evaluate("document.documentElement.classList.remove('dark')")
        page.wait_for_timeout(300)

        browser.close()

    # ---- 汇总 ----
    (OUT_DIR / "network-cherry-picks.json").write_text(
        json.dumps(cherry_requests, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "leaf-probe.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== leaf probe ===")
    print(json.dumps(probe, ensure_ascii=False, indent=2))
    print(f"cherry-picks requests captured: {len(cherry_requests)}")
    for r in cherry_requests:
        print(f"  {r['method']} {r['url']}")


if __name__ == "__main__":
    main()
