# -*- coding: utf-8 -*-
"""INT-1106 返工 P1 复核：DimensionSelect 面板须浮于模态遮罩之上可点击选择。

- 截「算法配置模态窗内 关联维度 / 参数映射」DimensionSelect 面板打开态（浅色 + 深色）。
- 证据：elementsFromPoint 面板中心首元素 ∈ 面板（非 modal-overlay）+ 面板/遮罩计算 z-index
  + 真实鼠标点击选项后触发器值改变（选择成功；写接口经 route 拦截，不改库）。
"""
import json
import os

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5511'
WORKTREE = r'D:\00_user_data\multica_workspaces_desktop-api.multica.ai\intelligent-95ba6a12369f\int-1106-67442b9dc5e6\worktree'
OUT = os.path.join(WORKTREE, '_int1106_shots')
os.makedirs(OUT, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

evidence = {'light': {}, 'dark': {}}
blocked_writes = []


def block_writes(route):
    req = route.request
    if req.method in ('POST', 'PUT', 'DELETE') and (
        '/algorithm/dimension-relations' in req.url or '/algorithm/mappings' in req.url
    ):
        blocked_writes.append(f'{req.method} {req.url}')
        # 以成功响应截断写请求：既不改库，也不让前端进错误分支（无 console.error）
        route.fulfill(status=200, content_type='application/json', body='{}')
    else:
        route.continue_()


def probe_panel(page, name, theme, shot_file):
    """对当前打开的 .ds-panel 做三点证据 + 截图。name=light/dark 场景名。"""
    # 等面板可见
    panel = page.locator('.ds-panel:visible')
    panel.wait_for(state='visible', timeout=8000)
    # 1) 元素拾取：面板中心命中首元素必须在面板内
    probe = page.evaluate("""() => {
      const panel = document.querySelector('.ds-panel');
      if (!panel) return { ok: false, err: 'no panel' };
      const r = panel.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const hit = document.elementsFromPoint(cx, cy);
      const overlay = document.querySelector('.modal-overlay');
      const inPanel = hit.length > 0 && panel.contains(hit[0]);
      return {
        ok: inPanel,
        panelZ: getComputedStyle(panel).zIndex,
        overlayZ: overlay ? getComputedStyle(overlay).zIndex : null,
        topElClass: hit[0] ? hit[0].className : null,
        center: { x: Math.round(cx), y: Math.round(cy) },
      };
    }""")
    evidence[theme][name] = {'probe': probe}
    # 2) 截图（面板打开态）
    page.screenshot(path=shot_file)
    return probe


def open_first_dimension_panel(page, scope_selector):
    """在 scope_selector 内打开第一个 dimension-select-trigger（先滚入视口再点）。"""
    triggers = page.locator(f'{scope_selector} .dimension-select-trigger:visible')
    triggers.first.wait_for(state='visible', timeout=8000)
    triggers.first.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    triggers.first.click()
    page.locator('.ds-panel:visible').wait_for(state='visible', timeout=8000)


def click_and_verify_selection(page, scope_selector):
    """在面板内点击一个与当前值不同的选项，断言面板关闭且触发器值改变（写接口被成功响应截断，不改库）。
    用元素 handle 锚定被点击的触发器本身（映射表点击后会重渲染/重排，.first 再查可能落到别的行）。"""
    panel = page.locator('.ds-panel:visible')
    trigger_loc = page.locator(f'{scope_selector} .dimension-select-trigger:visible').first
    before_line = trigger_loc.inner_text().strip().split('\n')[0]
    handle = trigger_loc.element_handle()
    options = panel.locator('.ds-option:not(.ds-option-clear)')
    chosen = None
    for i in range(options.count()):
        txt = options.nth(i).inner_text().strip().split('\n')[0]
        if txt != before_line:
            chosen = options.nth(i)
            break
    if chosen is None:
        chosen = options.last
    chosen.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    chosen_text = chosen.inner_text().strip().split('\n')[0]
    chosen.click()
    # 面板应关闭
    page.wait_for_timeout(400)
    closed = page.locator('.ds-panel:visible').count() == 0
    try:
        after_line = handle.inner_text().strip().split('\n')[0]
    except Exception:
        after_line = trigger_loc.inner_text().strip().split('\n')[0]
    return {
        'closed': closed,
        'clicked': chosen_text,
        'before': before_line,
        'after': after_line,
        'changed': after_line != before_line,
    }


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=False)
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = ctx.new_page()
        page.route('**/*', block_writes)

        console_errors = []
        page.on('console', lambda m: console_errors.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: console_errors.append(str(e)))

        page.goto(BASE + '/#/AlgorithmConfig', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        # 登录（若出现登录卡）
        if page.locator('.login-card').count() > 0:
            page.locator('.login-card input[type="text"]').fill('admin')
            page.locator('.login-card input[type="password"]').fill('admin123')
            page.locator('.login-btn').click()
            page.wait_for_timeout(2500)
        # 等待算法表格出现真实数据
        page.wait_for_selector('tr:has-text("voice_llm") button:has-text("编辑")', timeout=15000)
        page.locator('tr:has-text("voice_llm") button:has-text("编辑")').first.click()
        page.wait_for_selector('.tab-btn:has-text("关联维度")', timeout=10000)
        page.wait_for_selector('.modal-overlay', timeout=10000)

        # ===== 关联维度 =====
        page.locator('.tab-btn:has-text("关联维度")').click()
        page.wait_for_timeout(600)
        open_first_dimension_panel(page, '.tab-content')
        light_probe = probe_panel(
            page, 'dimensions', 'light',
            os.path.join(OUT, 'int1106_fix_dimensions_light.png'))
        # 真实点击选择（选与当前值不同的选项）
        click_res = click_and_verify_selection(page, '.tab-content')
        evidence['light']['dimensions']['click'] = click_res

        # ===== 参数映射（评估） =====
        page.locator('.tab-btn:has-text("参数映射")').click()
        page.wait_for_timeout(800)
        # 展开评估映射节
        eval_header = page.locator('.mapping-header:has-text("评估参数映射")')
        if eval_header.count() > 0:
            body = page.locator('.mapping-section:has-text("评估参数映射") .mapping-body')
            if body.count() > 0 and not body.is_visible():
                eval_header.first.click()
                page.wait_for_timeout(500)
        # 诊断：映射节触发器数量
        scope = '.mapping-section:has-text("评估参数映射")'
        scope_loc = page.locator('.mapping-section', has_text='评估参数映射')
        body = scope_loc.locator('.mapping-body')
        triggers = scope_loc.locator('.dimension-select-trigger')
        rows = scope_loc.locator('tbody tr')
        diag = {
            'sectionCount': scope_loc.count(),
            'bodyVisible': body.count() > 0 and body.first.is_visible(),
            'triggerCount': triggers.count(),
            'rowCount': rows.count(),
            'textSnippet': scope_loc.first.inner_text()[:300] if scope_loc.count() > 0 else None,
        }
        print('[diag mappings]', json.dumps(diag, ensure_ascii=False))
        page.screenshot(path=os.path.join(OUT, '_diag_mappings_light.png'))
        # 在评估映射节内打开第一个目标维度 DimensionSelect
        open_first_dimension_panel(page, scope)
        light_probe_map = probe_panel(
            page, 'mappings', 'light',
            os.path.join(OUT, 'int1106_fix_mappings_light.png'))
        click_res = click_and_verify_selection(page, scope)
        evidence['light']['mappings']['click'] = click_res

        # ===== 深色 =====
        page.evaluate("document.documentElement.classList.add('dark')")
        page.wait_for_timeout(400)
        page.locator('.tab-btn:has-text("关联维度")').click()
        page.wait_for_timeout(600)
        open_first_dimension_panel(page, '.tab-content')
        probe_panel(page, 'dimensions', 'dark', os.path.join(OUT, 'int1106_fix_dimensions_dark.png'))
        evidence['dark']['dimensions']['click'] = click_and_verify_selection(page, '.tab-content')

        page.locator('.tab-btn:has-text("参数映射")').click()
        page.wait_for_timeout(600)
        eval_header = page.locator('.mapping-header:has-text("评估参数映射")')
        if eval_header.count() > 0:
            body = page.locator('.mapping-section:has-text("评估参数映射") .mapping-body')
            if body.count() > 0 and not body.is_visible():
                eval_header.first.click()
                page.wait_for_timeout(500)
        open_first_dimension_panel(page, scope)
        probe_panel(page, 'mappings', 'dark', os.path.join(OUT, 'int1106_fix_mappings_dark.png'))
        evidence['dark']['mappings']['click'] = click_and_verify_selection(page, scope)

        evidence['console_errors'] = console_errors
        evidence['blocked_writes'] = blocked_writes

        ctx.close()
        browser.close()

    with open(os.path.join(OUT, 'evidence.json'), 'w', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
