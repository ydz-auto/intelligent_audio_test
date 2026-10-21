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
      // find the first task-case-card's Vue parent chain, walk up to the layout component exposing caseRoundMeta
      const el = document.querySelector('.task-case-card');
      let inst = el && el.__vueParentComponent;
      let found = null;
      while (inst) {
        const s = inst.setupState || inst.proxy || {};
        if (s && s.caseRoundMeta && typeof s.caseRoundMeta === 'function') { found = inst; break; }
        inst = inst.parent;
      }
      if (!found) return { error: 'component not found' };
      const cases = found.setupState.filteredAssociatedCases || [];
      const brief = [];
      for (const c of cases.slice(0, 8)) {
        brief.push({ name: (c.name||'').slice(0,30), duration: c.duration, executionStatus: c.executionStatus, rp: c.roundProgress });
      }
      // also compute meta for the target case
      const target = cases.find(c => c.name && c.name.includes('1792215843'));
      let meta = null;
      if (target) {
        meta = found.setupState.caseRoundMeta(target);
      }
      return { brief, targetMeta: meta, targetFound: !!target };
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    b.close()
