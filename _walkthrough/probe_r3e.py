# -*- coding: utf-8 -*-
import json, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5513"
AUTH = """
const auth_user = { id: 1, username: "admin", roleId: 1, roleName: "admin", permissions: ["*"] };
localStorage.setItem("auth_token", "probe-r3-token");
localStorage.setItem("auth_user", JSON.stringify(auth_user));
localStorage.setItem("iatp:theme:v1", "light");
"""
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.add_init_script(AUTH)
    reqs = []
    resp_dur = {}
    def on_req(r):
        u = r.url
        if "/api/v1/" in u:
            reqs.append(r.method + " " + u.split("/api/v1/")[1])
    def on_resp(r):
        u = r.url
        if "/api/v1/" in u and ("cases" in u or "tasks/1666" in u):
            try:
                j = r.json()
                data = j.get("data", j)
                if isinstance(data, dict) and "cases" in data:
                    resp_dur[u.split("/api/v1/")[1]] = [(c.get("name","")[:25], c.get("duration")) for c in data["cases"] if c.get("duration") is not None]
            except Exception:
                pass
    page.on("request", on_req)
    page.on("response", on_resp)
    page.goto(f"{BASE}/#/tasks/1666", wait_until="networkidle", timeout=60000)
    time.sleep(4)
    print("REQS:")
    for r in list(dict.fromkeys(reqs)):
        print("  ", r)
    print("RESP WITH DURATION:")
    for k, v in resp_dur.items():
        print("  ", k, "->", v)
    b.close()
