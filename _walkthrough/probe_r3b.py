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
      const cards = document.querySelectorAll('.case-card');
      const metas = [];
      for (const c of cards) {
        const meta = c.querySelector('.case-card__meta');
        metas.push({
          metaText: meta ? meta.innerText.replace(new RegExp(String.fromCharCode(92)+'n','g'),' | ') : null,
          roundLabel: c.querySelector('.round-progress-label') ? c.querySelector('.round-progress-label').innerText : null,
          fillWidth: c.querySelector('.round-progress-fill') ? c.querySelector('.round-progress-fill').style.width : null,
          nameText: ((c.querySelector('.case-name, .card-title, .case-title') || {}).innerText || '').slice(0, 40),
        });
      }
      return { cardCount: cards.length, metas: metas.slice(0, 15) };
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1)[:3500])
    b.close()
