# -*- coding: utf-8 -*-
"""聚焦调试：算法配置模态窗 参数映射→评估映射节 内 DimensionSelect 触发器点击行为。"""
import json, os
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5511'
WORKTREE = r'D:\00_user_data\multica_workspaces_desktop-api.multica.ai\intelligent-95ba6a12369f\int-1106-67442b9dc5e6\worktree'
OUT = os.path.join(WORKTREE, '_int1106_shots')
os.makedirs(OUT, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=False)
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(f'[console.{m.type}] {m.text}') if m.type == 'error' else None)
    page.on('pageerror', lambda e: errs.append(f'[pageerror] {e}'))

    page.goto(BASE + '/#/AlgorithmConfig', wait_until='domcontentloaded')
    page.wait_for_timeout(1500)
    if page.locator('.login-card').count() > 0:
        page.locator('.login-card input[type="text"]').fill('admin')
        page.locator('.login-card input[type="password"]').fill('admin123')
        page.locator('.login-btn').click()
        page.wait_for_timeout(2500)
    page.wait_for_selector('tr:has-text("voice_llm") button:has-text("编辑")', timeout=15000)
    page.locator('tr:has-text("voice_llm") button:has-text("编辑")').first.click()
    page.wait_for_selector('.tab-btn:has-text("参数映射")', timeout=10000)
    page.locator('.tab-btn:has-text("参数映射")').click()
    page.wait_for_timeout(800)

    scope_loc = page.locator('.mapping-section', has_text='评估参数映射')
    print('section count:', scope_loc.count())
    triggers = scope_loc.locator('.dimension-select-trigger:visible')
    print('visible trigger count:', triggers.count())

    # 前 3 个触发器的边界与文本
    for i in range(min(3, triggers.count())):
        t = triggers.nth(i)
        box = t.bounding_box()
        print(f'trigger[{i}] box={box} text={t.inner_text()[:40]!r}')

    # 点第一个，逐步观察（先滚动到可见区）
    t = triggers.first
    t.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    t.click()
    for delay in (100, 500, 1500):
        page.wait_for_timeout(delay)
        state = page.evaluate("""() => {
          const panels = document.querySelectorAll('.ds-panel');
          const overlay = document.querySelector('.modal-overlay');
          return {
            panelCount: panels.length,
            panelVisible: panels.length > 0 ? getComputedStyle(panels[0]).display : null,
            panelZ: panels.length > 0 ? getComputedStyle(panels[0]).zIndex : null,
            overlayZ: overlay ? getComputedStyle(overlay).zIndex : null,
            panelText: panels.length > 0 ? panels[0].innerText.slice(0, 80) : null,
          };
        }""")
        print(f'after {delay}ms:', json.dumps(state, ensure_ascii=False))
    page.screenshot(path=os.path.join(OUT, '_diag_mappings_debug.png'))
    print('console errors:', json.dumps(errs, ensure_ascii=False))

    # 用 JS 直接点击触发器（绕过可操作性检查），再观察
    page.evaluate("""() => {
      const scope = [...document.querySelectorAll('.mapping-section')].find(
        s => s.innerText.includes('评估参数映射'));
      const t = scope.querySelector('.dimension-select-trigger');
      t.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    }""")
    for delay in (100, 500):
        page.wait_for_timeout(delay)
        state = page.evaluate("""() => {
          const panels = document.querySelectorAll('.ds-panel');
          return { panelCount: panels.length,
            panelVisible: panels.length > 0 ? getComputedStyle(panels[0]).display : null,
            panelText: panels.length > 0 ? panels[0].innerText.slice(0, 80) : null };
        }""")
        print(f'after JSclick {delay}ms:', json.dumps(state, ensure_ascii=False))
    ctx.close()
    browser.close()
