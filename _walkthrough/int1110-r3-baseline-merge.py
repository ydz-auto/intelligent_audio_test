"""
INT-1110 返工（审计 01a15e49 新 P1 修复后）走查——合入当前基线 INT-1174（含 INT-1130 §11-7）后：
- 阶段 2 用例视图组织控件（分组视图/标签视图/平铺/交叉）仍常显；
- 分组视图桶头 = 真实组名（候选返 group_id/group_name），标签视图兜底桶「未设置标签」；
- 三视图切换正常、无控制台错误、Network 捕获 cherry-picks 真实请求。
连本 run dev server :5533（连常驻后端 :5000），登录 admin/admin123。
产出：浅/深截图 + org 探针 + Network 列表。
"""
import json
import pathlib
from playwright.sync_api import sync_playwright

OUT_DIR = pathlib.Path(__file__).parent / "shots" / "int1110-r3-baseline"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:5533"
cherry_requests = []
console_errors = []
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
            if "/tasks/cherry-picks" in req.url:
                cherry_requests.append({"url": req.url, "method": req.method})

        def track_error(msg):
            t = msg.type
            if t == "error":
                console_errors.append(msg.text)

        page.on("request", track_request)
        page.on("console", track_error)

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

        def dump_org(label, key):
            btns = [b.inner_text().strip() for b in page.query_selector_all(".pcol-btn")]
            buckets = []
            for b in page.query_selector_all(".pcol-bucket"):
                name_el = b.query_selector(".pcol-bucket-name")
                count_el = b.query_selector(".pcol-bucket-count")
                hdr = b.query_selector(".pcol-bucket-header")
                buckets.append({
                    "name": (name_el.inner_text() if name_el else "").strip(),
                    "count": (count_el.inner_text() if count_el else "").strip(),
                    "muted": "pcol-muted" in (hdr.get_attribute("class") or "") if hdr else False,
                })
            print(f"[{label}] org buttons: {btns}")
            print(f"[{label}] buckets: {buckets}")
            probe[key] = {"org_buttons": btns, "buckets": buckets}

        # ---- 用例视图：分组视图 ----
        # 组织控件默认分组视图，先确认分组桶（真实组名）
        dump_org("用例视图·分组", "case_group")
        page.screenshot(path=str(OUT_DIR / "1-phase2-caseview-group-light.png"), full_page=False)

        # ---- 标签视图 ----
        page.query_selector_all(".pcol-btn")[1].click()  # 标签视图
        page.wait_for_timeout(500)
        dump_org("用例视图·标签", "case_tag")
        page.screenshot(path=str(OUT_DIR / "2-phase2-caseview-tag-light.png"), full_page=False)

        # ---- 设备视图 / 结果类型视图：全部展开后叶行计数 ----
        def expand_all_and_count(view_label, key):
            page.get_by_text("全部展开", exact=False).first.click()
            page.wait_for_timeout(600)
            total = len(page.query_selector_all(".cpw-tree .pt-leaf"))
            in_card = len(page.query_selector_all(".cpw-tree .pt-case-leaves .pt-leaf"))
            checkboxes = len(page.query_selector_all(".cpw-tree .pt-leaf input.pt-checkbox"))
            print(f"[{view_label}] pt-leaf={total} in_card={in_card} checkbox={checkboxes}")
            probe[key] = {"pt_leaf_total": total, "in_case_card": in_card, "checkbox": checkboxes}

        page.get_by_text("设备视图", exact=False).first.click()
        page.wait_for_timeout(800)
        expand_all_and_count("设备视图", "device_view")
        page.screenshot(path=str(OUT_DIR / "3-phase2-deviceview-expanded-light.png"), full_page=False)

        page.get_by_text("结果类型视图", exact=False).first.click()
        page.wait_for_timeout(800)
        expand_all_and_count("结果类型视图", "result_type_view")

        # ---- 深色：用例视图分组 ----
        page.get_by_text("用例视图", exact=False).first.click()
        page.wait_for_timeout(600)
        page.evaluate("document.documentElement.classList.add('dark')")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT_DIR / "4-phase2-caseview-group-dark.png"), full_page=False)
        page.evaluate("document.documentElement.classList.remove('dark')")
        page.wait_for_timeout(300)

        browser.close()

    (OUT_DIR / "network-cherry-picks.json").write_text(
        json.dumps(cherry_requests, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "org-probe.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== org probe ===")
    print(json.dumps(probe, ensure_ascii=False, indent=2))
    print(f"cherry-picks requests captured: {len(cherry_requests)}")
    for r in cherry_requests:
        print(f"  {r['method']} {r['url']}")
    print(f"console errors: {len(console_errors)}")
    for e in console_errors[:10]:
        print(f"  ERR: {e}")


if __name__ == "__main__":
    main()
