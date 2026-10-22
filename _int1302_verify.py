# -*- coding: utf-8 -*-
"""INT-1302 新Vue 移除「任务类型/E2E测试」概念 实机验证截图 + 断言。

连 dev server 127.0.0.1:5540（本 run 启动，VITE_API_TARGET=5700 真实库栈 intelligent_audio_test）。
真实登录（接线测试_admin / JieXianTest@2026，RSA 加密由前端完成）后逐页复核：
- 报告统计分析 /report-statistics：维度下拉与维度卡 = 时间/设备类型/评估维度（无「任务类型」）
- 日志查看 /LogView：模块下拉 = 所有模块/API模块/设备管理（无「E2E测试」）
- 用例管理 /TestCaseManager：页描述无「端到端/API测试」
- 使用手册 /user-guide：正文无「端到端/API测试/E2E」
- 关于 /about：正文无「端到端/API测试/E2E」
浅色+深色截图各一张 + Network 抓对应接口。
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5540"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_int1302_shots")
os.makedirs(OUT, exist_ok=True)

USERNAME = "接线测试_admin"
PASSWORD = "JieXianTest@2026"

LIGHT_INIT = """localStorage.setItem("iatp:theme:v1", "light");"""
DARK_INIT = """localStorage.setItem("iatp:theme:v1", "dark");"""

PAGES = [
    ("report-statistics", "/#/report-statistics",
     [".rst-control-section", ".rst-dimension-grid"],
     ["/reports/statistics"],
     ["任务类型"]),
    ("logview", "/#/LogView",
     [".filter-section", ".log-view"],
     ["/logs/stats", "/logs"],
     ["E2E测试"]),
    ("testcase-manager", "/#/TestCaseManager",
     [".test-case-manager", ".page-header"],
     ["/testcases", "/groups", "/tags"],
     ["端到端", "API测试"]),
    ("user-guide", "/#/user-guide",
     [".guide-article", ".guide-h1"],
     [],
     ["端到端测试", "API 测试", "E2E测试"]),
    ("about", "/#/about",
     [".about-page", ".about-card"],
     ["/health", "/auth/mode"],
     ["端到端测试", "API 测试", "E2E"]),
]


def wait_any(page, selectors, timeout=30000):
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


def snap(page, name):
    page.screenshot(path=os.path.join(OUT, name), full_page=True)
    print(f"  saved {name}")


def login(page):
    print("[login] 打开登录页并提交真实账号")
    page.goto(BASE + "/#/login", wait_until="domcontentloaded")
    ok = wait_any(page, ["input[placeholder*='用户名']", "input[type='text']"], 20000)
    page.wait_for_timeout(800)
    page.fill('input[placeholder*="用户名"]', USERNAME)
    page.fill('input[placeholder*="密码"]', PASSWORD)
    page.click("button.login-btn")
    end = time.time() + 30000
    while time.time() < end:
        cur = page.evaluate("location.hash")
        if cur and "login" not in cur and "register" not in cur:
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(500)
    err = page.locator(".error-msg").first.text_content() if page.locator(".error-msg").count() else ""
    print(f"[login] 超时未跳转，hash={page.evaluate('location.hash')} error={err}")
    return False


def verify_page(page, tag, path, wait_sels, expect_apis, absent_list, theme):
    """导航到页面，等待加载，截图；返回 (命中的禁用词, 本页 API 调用, 控制台错误)。"""
    api_calls = []
    errors = []
    nav_before = len(api_calls)

    def on_response(r):
        if "/api/v1" in r.url:
            api_calls.append(r.url.split("?")[0])

    def on_pageerror(e):
        errors.append(str(e))

    page.on("response", on_response)
    page.on("pageerror", on_pageerror)

    page.goto(BASE + path, wait_until="domcontentloaded")
    found = wait_any(page, wait_sels, 30000)
    page.wait_for_timeout(2500)
    snap(page, f"{tag}-{theme}.png")

    body = page.evaluate("document.body ? document.body.innerText : ''")
    absent_hits = [a for a in absent_list if a in body]
    call_filtered = [u for u in api_calls]  # 收集从导航开始到截图时的调用
    print(f"[{tag}/{theme}] 加载={found} absent_hits={absent_hits}")
    print(f"  api_calls={sorted(set(call_filtered))}")
    print(f"  console_errors={errors}")
    return absent_hits, sorted(set(call_filtered)), errors


def assert_module_options(page, theme):
    page.goto(BASE + "/#/LogView", wait_until="domcontentloaded")
    wait_any(page, [".filter-section"], 30000)
    page.wait_for_timeout(1500)
    opts = page.evaluate("""() => {
      const groups = document.querySelectorAll('.filter-group');
      for (const g of groups) {
        const lab = g.querySelector('.filter-label');
        if (lab && lab.textContent.includes('模块')) {
          const sel = g.querySelector('select');
          if (sel) return Array.from(sel.options).map(o => o.text);
        }
      }
      return [];
    }""")
    print(f"[logview/{theme}] 模块下拉选项 = {opts}")
    return opts


def main():
    report = {"light": [], "dark": [], "module_options": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for theme, init in (("light", LIGHT_INIT), ("dark", DARK_INIT)):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(init)
            page = ctx.new_page()
            if not login(page):
                print(f"[{theme}] 登录失败，中止")
                return 2
            for tag, path, sels, expect_apis, absent_list in PAGES:
                absent_hits, apis, errs = verify_page(page, tag, path, sels, expect_apis, absent_list, theme)
                report[theme].append({"tag": tag, "absent_hits": absent_hits, "api": apis, "console_errors": errs})
            report["module_options"][theme] = assert_module_options(page, theme)
            ctx.close()
        browser.close()

    print("\n===== 汇总 =====")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    with open(os.path.join(OUT, "_int1302_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
