# -*- coding: utf-8 -*-
"""INT-1111 报告具体用例卡片组织（分组视图/标签视图 + 平铺/交叉）实机验证截图 + 证据。

连 dev server 127.0.0.1:5530（本 run 启动）→ 报告 65 具体用例：
- 默认 分组视图+平铺：组头=组名+计数「{n} 个用例」，未分类兜底组末尾弱化
- 标签视图：按标签聚合，未设置标签兜底组末尾弱化
- 交叉（分组视图内按标签）
浅/深色截图 + Network 真实请求（/api/v1/reports/65/cases/search）+ console 零报错。
"""
import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5530"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1111")
os.makedirs(OUT, exist_ok=True)

AUTH_INIT = """
const auth_user = {
  id: 1, username: "admin", roleId: 1, roleName: "admin",
  permissions: ["*"],
};
localStorage.setItem("auth_token", "int1111-dev-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
"""

DARK_INIT = 'localStorage.setItem("iatp:theme:v1", "dark");'
LIGHT_INIT = 'localStorage.setItem("iatp:theme:v1", "light");'


def new_page(browser, dark):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.add_init_script(AUTH_INIT)
    page.add_init_script(DARK_INIT if dark else LIGHT_INIT)
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


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


def snap(page, name, full_page=False):
    path = os.path.join(OUT, name)
    page.screenshot(path=path, full_page=full_page)
    print("saved", name)


def main():
    net = []
    console_errors = []
    rendered = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        def collect(url):
            if "/api/v1/reports/" in url and "/cases/search" in url:
                net.append(url.replace(BASE + "/api/v1", "/api/v1"))

        # ---- 默认 分组视图+平铺（light / dark）----
        for dark, suffix in [(False, "light"), (True, "dark")]:
            ctx, page, errors = new_page(browser, dark)
            page.on("response", lambda r: collect(r.url))
            page.goto(f"{BASE}/#/report/65", wait_until="networkidle", timeout=60000)
            ok = wait_any(page, [".specific-case-comparison .case-org-control", ".case-group-header"], 30000)
            page.wait_for_timeout(3500)
            # 滚到具体用例分区，让组织控件 + 组头进入视口
            sec = page.locator("#section-case .specific-case-comparison").first
            if sec.count() > 0:
                sec.scroll_into_view_if_needed()
                page.wait_for_timeout(1200)
            console_errors.extend(errors)
            snap(page, f"01_case_org_group_{suffix}.png", full_page=False)
            # 组头抽样（组名 + 计数「{n} 个用例」）
            groups = []
            for el in page.locator("#section-case .case-group-header").all()[:20]:
                groups.append(el.inner_text().replace("\n", " ").strip())
            rendered[f"group_{suffix}"] = groups
            print(f"[group {suffix}] headers: {groups}")
            ctx.close()

        # ---- 标签视图（light）----
        ctx, page, errors = new_page(browser, False)
        page.on("response", lambda r: collect(r.url))
        page.goto(f"{BASE}/#/report/65", wait_until="networkidle", timeout=60000)
        wait_any(page, [".specific-case-comparison .case-org-control"], 30000)
        page.wait_for_timeout(3500)
        tag_tab = page.get_by_role("button", name="标签视图")
        if tag_tab.count() > 0:
            tag_tab.first.click()
            page.wait_for_timeout(1500)
        sec = page.locator("#section-case .specific-case-comparison").first
        if sec.count() > 0:
            sec.scroll_into_view_if_needed()
            page.wait_for_timeout(1200)
        console_errors.extend(errors)
        snap(page, "02_case_org_tagview_light.png")
        groups = []
        for el in page.locator("#section-case .case-group-header").all()[:20]:
            groups.append(el.inner_text().replace("\n", " ").strip())
        rendered["tagview_light"] = groups
        print("[tagview light] headers:", groups)
        ctx.close()

        # ---- 交叉（分组视图 + 按标签）（light）----
        ctx, page, errors = new_page(browser, False)
        page.on("response", lambda r: collect(r.url))
        page.goto(f"{BASE}/#/report/65", wait_until="networkidle", timeout=60000)
        wait_any(page, [".specific-case-comparison .case-org-control"], 30000)
        page.wait_for_timeout(3500)
        cross_btn = page.get_by_role("button", name="按标签")
        if cross_btn.count() > 0:
            cross_btn.first.click()
            page.wait_for_timeout(1500)
        sec = page.locator("#section-case .specific-case-comparison").first
        if sec.count() > 0:
            sec.scroll_into_view_if_needed()
            page.wait_for_timeout(1200)
        console_errors.extend(errors)
        snap(page, "03_case_org_cross_light.png")
        inner_headers = []
        for el in page.locator("#section-case .case-group-header-inner").all()[:20]:
            inner_headers.append(el.inner_text().replace("\n", " ").strip())
        rendered["cross_inner_headers"] = inner_headers
        print("[cross light] inner headers:", inner_headers)
        ctx.close()

        browser.close()

    # 排序下拉收敛为纯排序：无「按分组/按标签」选项
    # （在 DOM 侧通过 option 文本核对，见下——单独加载一次读 select 内容）
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx, page, errors = new_page(browser, False)
        page.goto(f"{BASE}/#/report/65", wait_until="networkidle", timeout=60000)
        wait_any(page, [".specific-case-comparison .filter-select"], 30000)
        page.wait_for_timeout(3000)
        options = page.locator(".specific-case-comparison .filter-select option").all_inner_texts()
        rendered["sort_options"] = options
        print("[sort] options:", options)
        console_errors.extend(errors)
        ctx.close()
        browser.close()

    with open(os.path.join(OUT, "console_errors.json"), "w", encoding="utf-8") as f:
        json.dump(console_errors, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "network.json"), "w", encoding="utf-8") as f:
        json.dump(net, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "rendered_meta.json"), "w", encoding="utf-8") as f:
        json.dump(rendered, f, ensure_ascii=False, indent=1)

    print("console errors:", len(console_errors))
    print("network searchCases requests:", len(net))
    print("DONE")


if __name__ == "__main__":
    main()
