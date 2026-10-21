# -*- coding: utf-8 -*-
"""INT-1103 返工2 实机验证截图：
P1 —— 报告具体用例「下载日志」两段流程（openLogFileDialog 文件选择 Dialog，INT-1071 流程恢复）
P2 —— 任务详情关联用例卡轮次进度派生对齐 React（已执行 = 第 2/2 轮 50%，非 100%）
纯读页；dev server 指向 127.0.0.1:5513（本 run 启动）。"""
import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5513"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1103-r3")
os.makedirs(OUT, exist_ok=True)

AUTH_INIT = """
const auth_user = {
  id: 1, username: "admin", roleId: 1, roleName: "admin",
  permissions: ["*"],
};
localStorage.setItem("auth_token", "int1103-r3-dev-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
"""

DARK_INIT = """localStorage.setItem("iatp:theme:v1", "dark");"""
LIGHT_INIT = """localStorage.setItem("iatp:theme:v1", "light");"""


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


def wait_any(page, selectors, timeout=25000):
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
    out = {"pages": [], "errors": {}, "round_meta": [], "dialog": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ---- 1. 任务详情 /tasks/1257（P2：已执行 → 第 2/2 轮 50%；无「最后编辑时间」回退）----
        for dark, suffix in [(False, "light"), (True, "dark")]:
            ctx, page, errors = new_page(browser, dark)
            page.goto(f"{BASE}/#/tasks/1257", wait_until="networkidle", timeout=60000)
            wait_any(page, [".case-card", ".associated-cases .case-card"], 25000)
            page.wait_for_timeout(2500)
            body = page.inner_text("body")
            print(f"[tasks/1257 {suffix}] has 最后编辑时间: {'最后编辑时间' in body}")
            # 轮次进度数值验证：填充宽度 %（已执行应为 50，未执行应为 0）
            fills = []
            labels = []
            for el in page.locator(".round-progress-fill").all():
                w = el.get_attribute("style") or ""
                import re
                m = re.search(r"width:\s*([\d.]+)%", w)
                fills.append(m.group(1) if m else w)
            for el in page.locator(".round-progress-label").all():
                labels.append(el.inner_text().strip())
            print(f"[tasks/1257 {suffix}] round-progress-fill widths: {fills[:12]}")
            print(f"[tasks/1257 {suffix}] round-progress labels: {labels[:12]}")
            out["round_meta"].append({suffix: {"fills": fills[:12], "labels": labels[:12]}})
            out["errors"][f"tasks1257_{suffix}"] = errors[:3]
            snap(page, f"04_task_detail_{suffix}.png")
            ctx.close()

        # ---- 1b. 任务详情 /tasks/1666（P2 已执行侧：duration 非空 → 第 2/2 轮 50%，对齐 React）----
        for dark, suffix in [(False, "light"), (True, "dark")]:
            ctx, page, errors = new_page(browser, dark)
            page.goto(f"{BASE}/#/tasks/1666", wait_until="networkidle", timeout=60000)
            wait_any(page, [".case-card", ".associated-cases .case-card"], 25000)
            page.wait_for_timeout(2500)
            body = page.inner_text("body")
            fills = []
            labels = []
            for el in page.locator(".round-progress-fill").all():
                w = el.get_attribute("style") or ""
                import re
                m = re.search(r"width:\s*([\d.]+)%", w)
                fills.append(m.group(1) if m else w)
            for el in page.locator(".round-progress-label").all():
                labels.append(el.inner_text().strip())
            # 有 50% 已执行进度条才算 P2 数值对齐
            has50 = any(f == "50" for f in fills)
            print(f"[tasks/1666 {suffix}] round-progress-fill widths: {fills[:15]}")
            print(f"[tasks/1666 {suffix}] has 50% executed fill: {has50}")
            out["round_meta"].append({f"tasks1666_{suffix}": {"has50": has50, "fills": fills[:15], "labels": labels[:15]}})
            out["errors"][f"tasks1666_{suffix}"] = errors[:3]
            snap(page, f"04_task_detail_executed_{suffix}.png")
            ctx.close()

        # ---- 2. 报告具体用例 /report/65（P1：下载日志 → openLogFileDialog 两段 Dialog）----
        for dark, suffix in [(False, "light"), (True, "dark")]:
            ctx, page, errors = new_page(browser, dark)
            page.goto(f"{BASE}/#/report/65", wait_until="networkidle", timeout=60000)
            wait_any(page, [".case-card", ".no-data-tip", ".download-log-btn"], 30000)
            page.wait_for_timeout(2500)
            # 用例卡已渲染为统一 TestCaseCard
            card_count = page.locator(".case-card").count()
            print(f"[report/65 {suffix}] case-card count: {card_count}")
            dbtn = page.locator(".download-log-btn")
            print(f"[report/65 {suffix}] download-log-btn count: {dbtn.count()}")
            snap(page, f"07_report_specific_{suffix}.png")
            if dbtn.count() > 0:
                dbtn.first.click(force=True)
                page.wait_for_timeout(1200)
                overlay = page.locator(".log-file-select-overlay")
                dialog = page.locator(".log-file-select-dialog")
                print(f"[report/65 {suffix}] log-file-select-overlay visible: {overlay.count() > 0 and overlay.first.is_visible()}")
                print(f"[report/65 {suffix}] log-file-select-dialog visible: {dialog.count() > 0 and dialog.first.is_visible()}")
                # 真实后端：列表端点可能 404 → 错误态（重试/整包下载兜底）；否则文件列表
                err = page.locator(".log-file-select-error")
                rows = page.locator(".log-file-row")
                print(f"[report/65 {suffix}] error-state: {err.count() > 0}, file-rows: {rows.count()}")
                out["dialog"][suffix] = {
                    "overlay": overlay.count() > 0,
                    "dialog": dialog.count() > 0,
                    "error": err.count() > 0,
                    "rows": rows.count(),
                }
                snap(page, f"report_specific_log_dialog_{suffix}.png")
            out["errors"][f"report65_{suffix}"] = errors[:3]
            ctx.close()

        # ---- 3. Network 证据（任务详情 + 报告具体用例真实请求）----
        net = []
        for url, tag in [(f"{BASE}/#/tasks/1257", "tasks/1257"), (f"{BASE}/#/report/65", "report/65")]:
            ctx, page, errors = new_page(browser, False)
            reqs = []
            page.on("request", lambda r, t=tag: reqs.append(f"{r.method} {r.url.split('/api/v1/')[1] if '/api/v1/' in r.url else r.url}") if "/api/v1/" in r.url else None)
            page.goto(url, wait_until="networkidle", timeout=60000)
            wait_any(page, [".case-card", ".download-log-btn", ".no-data-tip"], 25000)
            page.wait_for_timeout(2000)
            net.append({tag: list(dict.fromkeys(reqs))})
            out["errors"].setdefault("network", {})[tag] = errors[:3]
            ctx.close()

        with open(os.path.join(OUT, "network.json"), "w", encoding="utf-8") as f:
            json.dump(net, f, ensure_ascii=False, indent=1)
        with open(os.path.join(OUT, "console_errors.json"), "w", encoding="utf-8") as f:
            json.dump(out["errors"], f, ensure_ascii=False, indent=1)
        with open(os.path.join(OUT, "rendered_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"round_meta": out["round_meta"], "dialog": out["dialog"]}, f, ensure_ascii=False, indent=1)
        print("console errors summary:", out["errors"])
        print("round_meta:", out["round_meta"])
        print("dialog:", out["dialog"])
        browser.close()
    print("DONE")


if __name__ == "__main__":
    main()
