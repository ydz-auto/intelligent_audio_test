# -*- coding: utf-8 -*-
"""INT-1103 返工——DOM 断言式复测（F1/P3-2/P3-1）。纯读页。"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5512"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1103-r2")
os.makedirs(OUT, exist_ok=True)

AUTH_INIT = """
const auth_user = { id: 1, username: "admin", roleId: 1, roleName: "admin", permissions: ["*"] };
localStorage.setItem("auth_token", "int1103-r2-dev-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
"""


def new_page(browser, dark):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.add_init_script(AUTH_INIT)
    if dark:
        page.add_init_script('localStorage.setItem("iatp:theme:v1", "dark");')
    else:
        page.add_init_script('localStorage.setItem("iatp:theme:v1", "light");')
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def wait_any(page, selectors, timeout=15000):
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
        report = {"fail": []}

        def check(cond, label):
            print(("PASS" if cond else "FAIL") + " | " + label, flush=True)
            if not cond:
                report["fail"].append(label)

        # ---- F1：任务详情 1257 关联用例卡次行 ----
        ctx, page, errors = new_page(browser, False)
        page.goto(f"{BASE}/#/tasks/1257", wait_until="domcontentloaded", timeout=45000)
        wait_any(page, [".case-card__meta"], 25000)
        page.wait_for_timeout(3000)
        metas = [el.inner_text() for el in page.locator(".case-card__meta").all()]
        print("task1257 meta:", json.dumps(metas, ensure_ascii=False), flush=True)
        joined = " || ".join(metas)
        check("最后编辑时间" not in joined, "F1: 任务详情卡无「最后编辑时间」回退")
        check(any("组" in m or m.strip() for m in metas), "F1: 任务详情卡 meta 恒有内容")
        check(("第 " in joined) and ("轮" in joined), "F1: 任务详情卡显示轮次进度行")
        check(any("INT314SMOKE" in m for m in metas), "F1: 任务详情卡显示分组名（真实数据）")
        snap_light = page.screenshot(path=os.path.join(OUT, "04_task_detail_light.png"), full_page=False)
        ctx.close()

        ctx, page, errors = new_page(browser, True)
        page.goto(f"{BASE}/#/tasks/1257", wait_until="domcontentloaded", timeout=45000)
        wait_any(page, [".case-card__meta"], 25000)
        page.wait_for_timeout(3000)
        metas_dark = [el.inner_text() for el in page.locator(".case-card__meta").all()]
        print("task1257 dark meta:", json.dumps(metas_dark, ensure_ascii=False), flush=True)
        check("最后编辑时间" not in (" || ".join(metas_dark)), "F1 dark: 任务详情卡无「最后编辑时间」回退")
        page.screenshot(path=os.path.join(OUT, "04_task_detail_dark.png"), full_page=False)
        ctx.close()

        # ---- P3-2：用例管理最后编辑时间格式 ----
        ctx, page, errors = new_page(browser, False)
        page.goto(f"{BASE}/#/testcases", wait_until="domcontentloaded", timeout=45000)
        wait_any(page, [".case-card__meta", ".case-meta-line"], 25000)
        page.wait_for_timeout(3000)
        vals = [el.inner_text() for el in page.locator(".case-meta-line").all()]
        print("testcases meta-line:", json.dumps(vals[:8], ensure_ascii=False), flush=True)
        bad = [v for v in vals if "T" in v and ":" in v]
        check(len(bad) == 0, "P3-2: 用例管理卡最后编辑时间已格式化（无原始 ISO 含 T）")
        check(any("最后编辑时间: 20" in v for v in vals), "P3-2: 用例管理卡显示最后编辑时间")
        page.screenshot(path=os.path.join(OUT, "01_testcases_light.png"), full_page=False)
        ctx.close()

        ctx, page, errors = new_page(browser, True)
        page.goto(f"{BASE}/#/testcases", wait_until="domcontentloaded", timeout=45000)
        wait_any(page, [".case-card__meta", ".case-meta-line"], 25000)
        page.wait_for_timeout(3000)
        vals_dark = [el.inner_text() for el in page.locator(".case-meta-line").all()]
        bad_dark = [v for v in vals_dark if "T" in v and ":" in v]
        check(len(bad_dark) == 0, "P3-2 dark: 用例管理卡最后编辑时间已格式化")
        page.screenshot(path=os.path.join(OUT, "01_testcases_dark.png"), full_page=False)
        ctx.close()

        # ---- P3-1：挑选合并 → 用例视角 compact 卡（勾选） ----
        for dark, suffix in [(False, "light"), (True, "dark")]:
            ctx, page, errors = new_page(browser, dark)
            page.goto(f"{BASE}/#/tasks?tab=cherry-picks", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            body = page.inner_text("body")
            print(f"[cherry {suffix}] page sample: {body[:150].strip()[:150]}", flush=True)
            # 尝试进入挑选向导
            clicked = False
            for lbl in ["开始挑选", "开始选择", "开始合并", "开始挑"]:
                btn = page.get_by_role("button", name=lbl)
                if btn.count() > 0:
                    btn.first.click(force=True)
                    clicked = True
                    print(f"[cherry {suffix}] clicked {lbl}", flush=True)
                    break
            if not clicked:
                for txt in ["开始挑选", "开始选择", "开始合并"]:
                    el = page.locator(f"text={txt}").first
                    if el.count() > 0:
                        el.click(force=True)
                        clicked = True
                        print(f"[cherry {suffix}] clicked text {txt}", flush=True)
                        break
            page.wait_for_timeout(3500)
            view_btn = page.get_by_role("button", name="用例视角")
            if view_btn.count() > 0:
                view_btn.first.click(force=True)
                page.wait_for_timeout(3000)
                print(f"[cherry {suffix}] switched 用例视角", flush=True)
            has_pcc = wait_any(page, [".pcc-check", ".pcc-count"], 12000)
            check(has_pcc, f"P3-1 {suffix}: 用例视角 compact 卡渲染（PickCaseCard）")
            pcc = page.locator(".pcc-checkbox").first
            if pcc.count() > 0:
                checked_before = pcc.is_checked()
                pcc.click(force=True)
                page.wait_for_timeout(600)
                checked_after = pcc.is_checked()
                check(checked_after != checked_before, f"P3-1 {suffix}: compact 卡勾选切换生效")
                print(f"[cherry {suffix}] pcc checked {checked_before} -> {checked_after}", flush=True)
            page.screenshot(path=os.path.join(OUT, f"0{9 if suffix=='light' else 11}_pick_caseview_{suffix}.png"), full_page=False)
            ctx.close()

        with open(os.path.join(OUT, "console_errors.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print("ERRORS:", flush=True)
        for e in errors:
            print(" ", e, flush=True)
        print("RESULT:", "ALL PASS" if not report["fail"] else f"FAILURES: {report['fail']}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
