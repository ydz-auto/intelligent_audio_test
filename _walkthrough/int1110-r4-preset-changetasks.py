"""
INT-1110 返工（审计 01a15e8a 新 P1 修复后）走查——预选任务直达阶段 2 →「更换任务」回阶段 1 任务列表非空。
P1 根因：preset 挂载走 loadCandidates（阶段 2 分支），allCandidates 从未加载；
「更换任务」旧实现仅翻转 phase 无加载调用 → 阶段 1 恒空。修复：goChangeTasks() = phase 置 tasks + loadAllCandidates()。
连本 run dev server :5535（连常驻后端 :5000），登录 admin/admin123。
产出：浅/深截图 + preset 探针 + Network 捕获（candidates per_page=200 真实请求）。
"""
import json
import pathlib
from playwright.sync_api import sync_playwright

OUT_DIR = pathlib.Path(__file__).parent / "shots" / "int1110-r4-preset-changetasks"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:5535"
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
            if msg.type == "error":
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

        # ---- 日常任务 tab：勾选 ≥1 任务 →「开始挑选」（preset 路径直达阶段 2）----
        page.goto(f"{BASE}/#/tasks", wait_until="domcontentloaded")
        page.wait_for_selector(".start-pick-btn", timeout=20000)
        dismiss_banner()
        page.wait_for_timeout(800)
        # 搜索框过滤出 INT314SMOKE 冒烟任务（当前库中唯一有可挑选候选的任务）
        search_input = page.query_selector(".search-input")
        if search_input:
            search_input.fill("INT314SMOKE")
            page.wait_for_timeout(1200)
        task_cbs = page.query_selector_all(".task-checkbox")
        print("daily task checkboxes after search:", len(task_cbs))
        # 定位 INT314SMOKE_70ed974e（有可挑选候选；_a7104c3a 为 stopped 态无候选）
        smoke_card = next(
            (c for c in page.query_selector_all(".task-card") if "70ed974e" in (c.inner_text() or "")),
            None,
        )
        if smoke_card:
            smoke_cb = smoke_card.query_selector(".task-checkbox")
            if smoke_cb:
                smoke_cb.check()
                probe["preset_task"] = "INT314SMOKE_70ed974e (task 1257)"
        elif task_cbs:
            task_cbs[0].check()
            probe["preset_task"] = f"first task (70ed974e card not found; cbs={len(task_cbs)})"
        else:
            print("FATAL: no task checkbox — preset path unreachable")
            probe["fatal"] = "no task checkbox"
            browser.close()
            _dump()
            return
        page.wait_for_timeout(300)
        # 记录预设任务名（阶段 2 摘要条应显示）
        page.screenshot(path=str(OUT_DIR / "1-daily-selected-light.png"), full_page=False)
        page.click(".start-pick-btn")

        # ---- preset 直达阶段 2（§3.8.1）----
        page.wait_for_selector(".cpw-phase-title", timeout=15000)
        page.wait_for_timeout(1200)  # 候选加载等待
        dismiss_banner()
        phase2_title = page.query_selector(".cpw-phase-title").inner_text()
        print("phase2 title:", phase2_title)
        probe["preset_phase2_title"] = phase2_title
        probe["preset_summary"] = page.query_selector(".cpw-task-summary").inner_text() if page.query_selector(".cpw-task-summary") else None

        # 阶段 2 勾选 1 条结果（跨阶段保留口径）
        page.wait_for_selector(".cpw-tree .case-card, .cpw-tree .pt-leaf .pt-checkbox", timeout=15000)
        page.wait_for_timeout(500)
        pcc = page.query_selector(".cpw-tree .pcc-check")
        pt = page.query_selector(".cpw-tree .pt-checkbox")
        if pcc:
            pcc.click()
        elif pt:
            pt.click()
        else:
            print("no result checkbox in stage 2 tree")
        page.wait_for_timeout(500)
        selected_before = page.query_selector(".cpw-toolbar-info").inner_text() if page.query_selector(".cpw-toolbar-info") else ""
        print("selected before change:", selected_before)
        probe["selected_before_change"] = selected_before
        page.screenshot(path=str(OUT_DIR / "2-phase2-preset-light.png"), full_page=False)

        # ---- 更换任务 → 阶段 1（P1 修复点：任务列表非空）----
        change_btn = page.get_by_text("更换任务", exact=False).first
        change_btn.click()
        page.wait_for_selector(".pts-title", timeout=15000)
        page.wait_for_timeout(1200)  # loadAllCandidates 返回等待
        dismiss_banner()
        phase1_title = page.query_selector(".pts-title").inner_text()
        rows = page.query_selector_all(".pts-row")
        row_texts = [r.inner_text() for r in rows]
        print("phase1 title:", phase1_title)
        print("phase1 task row count:", len(rows))
        probe["after_change_tasks_pts_title"] = phase1_title
        probe["task_row_count"] = len(rows)
        probe["task_row_texts"] = row_texts
        page.screenshot(path=str(OUT_DIR / "3-phase1-after-change-tasks-light.png"), full_page=False)

        # 深色：阶段 1 任务列表
        page.evaluate("document.documentElement.classList.add('dark')")
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT_DIR / "4-phase1-after-change-tasks-dark.png"), full_page=False)
        page.evaluate("document.documentElement.classList.remove('dark')")
        page.wait_for_timeout(300)

        # ---- 更换任务 → 重新勾选 → 下一步 → 阶段 2（勾选保留）----
        if len(rows) > 1:
            # 预选任务仍勾选（跨阶段保留），追加第 2 个任务
            rows[1].query_selector('input[type="checkbox"]').check()
            page.wait_for_timeout(300)
        next_btn = page.query_selector(".pts-btn-primary")
        if next_btn:
            next_btn.click()
        else:
            page.get_by_text("下一步", exact=False).first.click()
        page.wait_for_selector(".cpw-phase-title", timeout=15000)
        page.wait_for_timeout(1200)
        dismiss_banner()
        selected_after = page.query_selector(".cpw-toolbar-info").inner_text() if page.query_selector(".cpw-toolbar-info") else ""
        print("selected after round-trip:", selected_after)
        probe["selected_after_roundtrip"] = selected_after
        probe["phase2_back_title"] = page.query_selector(".cpw-phase-title").inner_text()
        page.screenshot(path=str(OUT_DIR / "5-phase2-back-after-roundtrip-light.png"), full_page=False)

        browser.close()

    _dump()


def _dump():
    (OUT_DIR / "preset-probe.json").write_text(
        json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "network-cherry-picks.json").write_text(
        json.dumps(cherry_requests, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== preset probe ===")
    print(json.dumps(probe, ensure_ascii=False, indent=2))
    print(f"cherry-picks requests captured: {len(cherry_requests)}")
    for r in cherry_requests:
        print(f"  {r['method']} {r['url']}")
    print(f"console errors: {len(console_errors)}")
    for e in console_errors[:10]:
        print(f"  ERR: {e}")


if __name__ == "__main__":
    main()
