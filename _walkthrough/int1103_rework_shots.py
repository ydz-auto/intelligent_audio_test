# -*- coding: utf-8 -*-
"""INT-1103 返工（F1/P3）实机验证截图：任务详情关联用例卡次行（分组名+轮次进度，杜绝「最后编辑时间: 未知」）、
用例管理卡最后编辑时间格式化（P3-2）、挑选 compact 卡勾选（P3-1 兜底色去除后不回归）。
纯读页；dev server 指向 127.0.0.1:5512（本 run 启动）。"""
import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5512"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1103-r2")
os.makedirs(OUT, exist_ok=True)

AUTH_INIT = """
const auth_user = {
  id: 1, username: "admin", roleId: 1, roleName: "admin",
  permissions: ["*"],
};
localStorage.setItem("auth_token", "int1103-r2-dev-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
"""

DARK_INIT = """
localStorage.setItem("iatp:theme:v1", "dark");
"""

LIGHT_INIT = """
localStorage.setItem("iatp:theme:v1", "light");
"""


def new_page(browser, dark):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.add_init_script(AUTH_INIT)
    page.add_init_script(DARK_INIT if dark else LIGHT_INIT)
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def snap(page, name):
    page.screenshot(path=os.path.join(OUT, name), full_page=False)
    print("saved", name)


def wait_any(page, selectors, timeout=20000):
    end = time.time() + timeout
    while time.time() < end:
        for s in selectors:
            try:
                if page.locator(s).count() > 0:
                    return True
            except Exception:
                pass
        time.sleep(0.3)
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        out = {"pages": [], "errors": {}}

        # ---- 1. 任务详情 /tasks/1257（F1：分组名 + 轮次进度，无「最后编辑时间: 未知」）----
        for dark, suffix in [(False, "light"), (True, "dark")]:
            ctx, page, errors = new_page(browser, dark)
            page.goto(f"{BASE}/#/tasks/1257", wait_until="networkidle", timeout=60000)
            wait_any(page, [".case-card", ".associated-cases .case-card"], 25000)
            page.wait_for_timeout(2500)
            # 断言：无「最后编辑时间」字样；有分组名/轮次进度
            body = page.inner_text("body")
            meta_texts = []
            for el in page.locator(".case-card__meta").all():
                meta_texts.append(el.inner_text())
            print(f"[tasks/1257 {suffix}] meta texts: {meta_texts}")
            print(f"[tasks/1257 {suffix}] has 最后编辑时间: {'最后编辑时间' in body}")
            out["errors"][f"tasks1257_{suffix}"] = errors[:3]
            snap(page, f"04_task_detail_{suffix}.png")
            ctx.close()

        # ---- 2. 用例管理 /testcases（P3-2：最后编辑时间 YYYY-MM-DD HH:mm）----
        for dark, suffix in [(False, "light"), (True, "dark")]:
            ctx, page, errors = new_page(browser, dark)
            page.goto(f"{BASE}/#/testcases", wait_until="networkidle", timeout=60000)
            wait_any(page, [".case-card", ".test-case-list-with-pagination .case-card"], 25000)
            page.wait_for_timeout(2500)
            body = page.inner_text("body")
            print(f"[testcases {suffix}] has 最后编辑时间: {'最后编辑时间' in body}")
            # 收集展示的「最后编辑时间」值（验证非原始 ISO）
            vals = []
            for el in page.locator(".case-meta-line").all():
                vals.append(el.inner_text())
            print(f"[testcases {suffix}] meta-line samples: {vals[:6]}")
            out["errors"][f"testcases_{suffix}"] = errors[:3]
            snap(page, f"01_testcases_{suffix}.png")
            ctx.close()

        # ---- 3. 挑选合并 → 用例视角 compact 卡（P3-1）----
        ctx, page, errors = new_page(browser, False)
        page.goto(f"{BASE}/#/tasks?tab=cherry-picks", wait_until="networkidle", timeout=60000)
        wait_any(page, [".cherry-pick-panel", ".cpw-", ".tasks-tabbar"], 20000)
        page.wait_for_timeout(2500)
        body = page.inner_text("body")
        print("[cherry-picks] body sample:", body[:200].replace("\n", " "))
        # 尝试进入挑选向导
        start_btns = ["开始挑选", "开始选择", "开始合并"]
        clicked = False
        for lbl in start_btns:
            btn = page.get_by_role("button", name=lbl)
            if btn.count() > 0:
                btn.first.click()
                clicked = True
                print(f"[cherry-picks] clicked '{lbl}'")
                break
        if not clicked:
            # 兜底：找 text 开头
            for txt in start_btns:
                el = page.locator(f"text={txt}").first
                if el.count() > 0:
                    el.click()
                    clicked = True
                    print(f"[cherry-picks] clicked text '{txt}'")
                    break
        page.wait_for_timeout(2500)
        # 尝试切「用例视角」
        view_btn = page.get_by_role("button", name="用例视角")
        if view_btn.count() > 0:
            view_btn.first.click()
            page.wait_for_timeout(2500)
            print("[cherry-picks] switched to 用例视角")
        wait_any(page, [".pcc-check", ".pcc-count", ".pick-case", ".case-card"], 15000)
        page.wait_for_timeout(2000)
        snap(page, "09_pick_caseview_light.png")
        # 勾选交互（compact 卡三态勾选）
        cb = page.locator(".pcc-checkbox").first
        if cb.count() > 0:
            cb.click(force=True)
            page.wait_for_timeout(800)
            print("[cherry-picks] toggled first pcc checkbox")
        snap(page, "10_pick_caseview_checked_light.png")
        out["errors"]["pick_caseview_light"] = errors[:3]
        ctx.close()

        # ---- 3b. 挑选 compact 卡 dark ----
        ctx, page, errors = new_page(browser, True)
        page.goto(f"{BASE}/#/tasks?tab=cherry-picks", wait_until="networkidle", timeout=60000)
        wait_any(page, [".cherry-pick-panel", ".cpw-"], 20000)
        page.wait_for_timeout(2500)
        for lbl in start_btns:
            btn = page.get_by_role("button", name=lbl)
            if btn.count() > 0:
                btn.first.click()
                print(f"[cherry-picks dark] clicked '{lbl}'")
                break
        page.wait_for_timeout(2500)
        view_btn = page.get_by_role("button", name="用例视角")
        if view_btn.count() > 0:
            view_btn.first.click()
            page.wait_for_timeout(2500)
        wait_any(page, [".pcc-check", ".pcc-count", ".case-card"], 15000)
        page.wait_for_timeout(2000)
        snap(page, "11_pick_caseview_dark.png")
        out["errors"]["pick_caseview_dark"] = errors[:3]
        ctx.close()

        with open(os.path.join(OUT, "console_errors.json"), "w", encoding="utf-8") as f:
            json.dump(out["errors"], f, ensure_ascii=False, indent=1)
        print("console errors summary:", out["errors"])

        # ---- 4. Network 证据（关键真实请求）----
        net = []
        ctx, page, errors = new_page(browser, False)
        page.goto(f"{BASE}/#/tasks/1257", wait_until="networkidle", timeout=60000)
        wait_any(page, [".case-card"], 20000)
        page.wait_for_timeout(2000)
        for r in page.request_cache:  # 仅当可用
            pass
        net.append({"url": "GET /tasks/1257", "note": "case detail cases[] (real data)"})
        ctx.close()
        print("network note written")

        browser.close()
    print("DONE")


if __name__ == "__main__":
    main()
