# -*- coding: utf-8 -*-
"""定位 TestCaseManager 页「API测试/端到端测试/E2E」文本出现位置与可见性。"""
import json, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5540"
AUTH = "接线测试_admin"
PWD = "JieXianTest@2026"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("localStorage.setItem('iatp:theme:v1','light');")
    page = ctx.new_page()
    page.goto(BASE + "/#/login", wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    page.fill('input[placeholder*="用户名"]', AUTH)
    page.fill('input[placeholder*="密码"]', PWD)
    page.click("button.login-btn")
    page.wait_for_timeout(4000)
    page.goto(BASE + "/#/TestCaseManager", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    # 遍历所有包含关键词的元素
    hits = page.evaluate("""() => {
      const kws = ['API测试','端到端测试','API 测试','E2E'];
      const out = [];
      const all = document.querySelectorAll('*');
      for (const el of all) {
        if (el.children.length) continue;
        const t = (el.textContent || '').trim();
        if (!t) continue;
        for (const k of kws) {
          if (t.includes(k)) {
            const vis = el.offsetParent !== null;
            const rect = el.getBoundingClientRect();
            out.push({kw:k, text:t.slice(0,60), visible:vis, tag:el.tagName, cls:(el.className||'').toString().slice(0,40), rect:rect.width>0&&rect.height>0});
          }
        }
      }
      return out;
    }""")
    print(json.dumps(hits, ensure_ascii=False, indent=2))
    # 工具栏 badges
    badges = page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('.badge-filter, .filter-group, .badge, .chip, [class*=filter] [class*=badge]').forEach(b => {
        const t = (b.textContent||'').trim();
        if (t) out.push(t.slice(0,50));
      });
      return [...new Set(out)].slice(0, 30);
    }""")
    print("FILTER/BADGE texts:", json.dumps(badges, ensure_ascii=False, indent=2))
    b.close()
