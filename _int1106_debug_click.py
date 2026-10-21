# -*- coding: utf-8 -*-
"""聚焦：映射节内 DimensionSelect 点击选项后，触发器的真实文本变化。"""
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
    def block_writes(route):
        req = route.request
        if req.method in ('POST', 'PUT', 'DELETE') and (
            '/algorithm/dimension-relations' in req.url or '/algorithm/mappings' in req.url
        ):
            route.fulfill(status=200, content_type='application/json', body='{}')
        else:
            route.continue_()
    page.route('**/*', block_writes)

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
    triggers = scope_loc.locator('.dimension-select-trigger:visible')

    # 打开第 2 个触发器（第 1 行），用 handle 锚定
    t = triggers.nth(0)
    t.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    before_text = t.inner_text().strip().split('\n')[0]
    print('before trigger[0] text:', before_text)
    handle = t.element_handle()
    t.click()
    page.locator('.ds-panel:visible').wait_for(state='visible', timeout=8000)
    panel = page.locator('.ds-panel:visible')
    options = panel.locator('.ds-option:not(.ds-option-clear)')
    print('panel option count:', options.count())
    for i in range(min(6, options.count())):
        print(f'  opt[{i}] text={options.nth(i).inner_text()!r}')
    # 选一个与当前值不同的
    chosen = None
    for i in range(options.count()):
        txt = options.nth(i).inner_text().strip().split('\n')[0]
        if txt != before_text:
            chosen = options.nth(i)
            break
    if chosen is None:
        chosen = options.last
    print('clicking option text:', repr(chosen.inner_text()))
    chosen.click()
    page.wait_for_timeout(600)
    print('panel closed:', page.locator('.ds-panel:visible').count() == 0)
    # 读锚定的 handle 文本
    try:
        after_handle = handle.inner_text().strip().split('\n')[0]
        print('handle text after:', after_handle)
    except Exception as e:
        print('handle detached:', e)
    # 重新查询第一行
    after_trigger = scope_loc.locator('.dimension-select-trigger:visible').nth(0).inner_text().strip().split('\n')[0]
    print('re-query trigger[0] after:', after_trigger)
    page.screenshot(path=os.path.join(OUT, '_diag_mapping_click.png'))
    print('console errors:', json.dumps(errs, ensure_ascii=False))
    ctx.close()
    browser.close()
