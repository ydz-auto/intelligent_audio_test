# -*- coding: utf-8 -*-
"""INT-1103 返工——console 零报错 + Network 真实请求证据（对照审计 evidence 格式）。"""
import json, os
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:5512"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1103-r2")
AUTH_INIT = """
const auth_user = { id: 1, username: "admin", roleId: 1, roleName: "admin", permissions: ["*"] };
localStorage.setItem("auth_token", "int1103-r2-dev-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
"""
net = {"tasks": [], "testcases": [], "pick": []}
console_errors = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    def collect(sec, url):
        if "/api/v1/" in url:
            net[sec].append(url.replace(BASE + "/api/v1", "/api/v1"))
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(AUTH_INIT)
    pg.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: console_errors.append(str(e)))
    pg.on("response", lambda r: collect("tasks", r.url))
    pg.goto(f"{BASE}/#/tasks/1257", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(6000)
    ctx.close()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(AUTH_INIT)
    pg.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: console_errors.append(str(e)))
    pg.on("response", lambda r: collect("testcases", r.url))
    pg.goto(f"{BASE}/#/testcases", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(6000)
    ctx.close()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(AUTH_INIT)
    pg.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: console_errors.append(str(e)))
    pg.on("response", lambda r: collect("pick", r.url))
    pg.goto(f"{BASE}/#/tasks?tab=cherry-picks", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    for lbl in ["开始挑选", "开始选择", "开始合并"]:
        btn = pg.get_by_role("button", name=lbl)
        if btn.count() > 0:
            btn.first.click(force=True); break
    pg.wait_for_timeout(4000)
    view_btn = pg.get_by_role("button", name="用例视角")
    if view_btn.count() > 0:
        view_btn.first.click(force=True)
    pg.wait_for_timeout(4000)
    ctx.close()
    b.close()
with open(os.path.join(OUT, "console_errors.json"), "w", encoding="utf-8") as f:
    json.dump(console_errors, f, ensure_ascii=False, indent=1)
with open(os.path.join(OUT, "network.json"), "w", encoding="utf-8") as f:
    json.dump(net, f, ensure_ascii=False, indent=1)
print("console errors:", len(console_errors))
for k, v in net.items():
    print(k, len(v), "requests")
