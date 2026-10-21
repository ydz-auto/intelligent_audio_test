# -*- coding: utf-8 -*-
import os
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:5512"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1103-r2")
AUTH_INIT = """
const auth_user = { id: 1, username: "admin", roleId: 1, roleName: "admin", permissions: ["*"] };
localStorage.setItem("auth_token", "int1103-r2-dev-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
"""
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(AUTH_INIT)
    pg.goto(f"{BASE}/#/tasks?tab=cherry-picks", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    for lbl in ["开始挑选", "开始选择", "开始合并"]:
        btn = pg.get_by_role("button", name=lbl)
        if btn.count() > 0:
            btn.first.click(force=True); break
    pg.wait_for_timeout(4000)
    vb = pg.get_by_role("button", name="用例视角")
    if vb.count() > 0:
        vb.first.click(force=True)
    pg.wait_for_timeout(4000)
    pg.screenshot(path=os.path.join(OUT, "09_pick_caseview_light.png"), full_page=False)
    cb = pg.locator(".pcc-checkbox").first
    if cb.count() > 0:
        cb.click(force=True)
        pg.wait_for_timeout(800)
    pg.screenshot(path=os.path.join(OUT, "10_pick_caseview_checked_light.png"), full_page=False)
    print("pcc count:", pg.locator(".pcc-checkbox").count())
    ctx.close(); b.close()
