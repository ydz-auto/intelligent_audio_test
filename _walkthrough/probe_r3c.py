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
    cap = {}
    def on_resp(r):
        if "/api/v1/tasks/1666" in r.url and "progress" not in r.url:
            try:
                cap["tasks1666"] = r.json()
            except Exception:
                pass
    page.on("response", on_resp)
    page.goto(f"{BASE}/#/tasks/1666", wait_until="networkidle", timeout=60000)
    time.sleep(4)
    if "tasks1666" in cap:
        data = cap["tasks1666"].get("data", cap["tasks1666"])
        cases = data.get("cases", [])
        print("case count:", len(cases))
        # find the two with duration
        for c in cases:
            dur = c.get("duration")
            if dur is not None and dur != "":
                print("HAS DURATION:", json.dumps({k: c.get(k) for k in ["name","duration","execution_status"]}, ensure_ascii=False, default=str))
        # also print a sample of raw case keys
        if cases:
            print("sample case keys:", list(cases[0].keys()))
    else:
        print("no cap; sample:", list(cap.keys()))
    b.close()
