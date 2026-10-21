# -*- coding: utf-8 -*-
import json, os
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:5512"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1103-r2")
AUTH_INIT = """
const auth_user = { id: 1, username: "admin", roleId: 1, roleName: "admin", permissions: ["*"] };
localStorage.setItem("auth_token", "int1103-r2-dev-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
"""
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(AUTH_INIT)
    pg.goto(f"{BASE}/#/tasks/1257", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(6000)
    out["task1257_meta"] = [el.inner_text() for el in pg.locator(".case-card__meta").all()]
    ctx.close()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(AUTH_INIT)
    pg.goto(f"{BASE}/#/testcases", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(6000)
    out["testcases_meta_lines"] = [el.inner_text() for el in pg.locator(".case-meta-line").all()][:10]
    ctx.close()
    b.close()
with open(os.path.join(OUT, "rendered_meta.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("saved")
