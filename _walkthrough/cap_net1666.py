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
    page.on("request", lambda r: reqs.append(r.method + " " + r.url.split("/api/v1/")[1]) if "/api/v1/" in r.url else None)
    page.goto(f"{BASE}/#/tasks/1666", wait_until="networkidle", timeout=60000)
    time.sleep(3)
    path = "_walkthrough/shots/int1103-r3/network.json"
    with open(path, "r", encoding="utf-8") as f:
        net = json.load(f)
    net.append({"tasks/1666": list(dict.fromkeys(reqs))})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(net, f, ensure_ascii=False, indent=1)
    print(json.dumps(list(dict.fromkeys(reqs)), ensure_ascii=False, indent=1))
    b.close()
