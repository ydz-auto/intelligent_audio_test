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
    page.goto(f"{BASE}/#/tasks/1666", wait_until="networkidle", timeout=60000)
    time.sleep(4)
    info = page.evaluate("""() => {
      const cards = Array.from(document.querySelectorAll('.case-card'));
      const found = [];
      for (const c of cards) {
        const name = ((c.querySelector('.case-name, .card-title, .case-title') || {}).innerText || '');
        const meta = c.querySelector('.case-card__meta');
        const label = c.querySelector('.round-progress-label');
        const fill = c.querySelector('.round-progress-fill');
        found.push({
          name: name.slice(0, 30),
          meta: meta ? meta.innerText.slice(0, 80) : null,
          label: label ? label.innerText : null,
          width: fill ? fill.style.width : null,
        });
      }
      return { cardCount: cards.length, found };
    }""")
    # print cards whose name matches 1792215843 or that have width not 0%
    for f in info["found"]:
        if "1792215843" in (f["name"] or "") or (f["width"] and f["width"] != "0%"):
            print(json.dumps(f, ensure_ascii=False))
    print("TOTAL CARDS:", info["cardCount"])
    print("CARDS WITH WIDTH>0:", [f for f in info["found"] if f["width"] and f["width"] != "0%"])
    b.close()
