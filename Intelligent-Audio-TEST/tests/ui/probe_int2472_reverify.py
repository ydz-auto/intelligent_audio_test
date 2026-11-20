# -*- coding: utf-8 -*-
"""INT-2472 返修复验探针：P1（DESTRUCTIVE 决策带 confirm）+ P2（>20 对象强制逐项核对）。

真实栈：React dev server（交付分支 89db359c9）→ 网关 http://localhost:15000。
审批单为本次 run 种入的真实库记录（种子含 21 对象 / DESTRUCTIVE / DESTRUCTIVE 拒绝三张单），
页面所有读请求与决策请求都走真实后端，不做任何响应拦截。

跑法：<python> tests/ui/probe_int2472_reverify.py --base http://localhost:5312
"""
import argparse
import asyncio
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from playwright.async_api import async_playwright  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts',
                   'int2472_reverify')

SESSION_KEY = 'iatp:ai-chat:v1:agent-session'
THEME_KEY = 'iatp:theme:v1:mode'

S1 = ('2472a000-0000-4000-8000-000000000001',
      '2472b000-0000-4000-8000-000000000001')
S2 = ('2472a000-0000-4000-8000-000000000002',
      '2472b000-0000-4000-8000-000000000002')
S3 = ('2472a000-0000-4000-8000-000000000003',
      '2472b000-0000-4000-8000-000000000003')

A1 = '2472c000-0000-4000-8000-000000000001'
A2 = '2472c000-0000-4000-8000-000000000002'
A3 = '2472c000-0000-4000-8000-000000000003'


async def login(page, base):
    await page.goto(base + '/login', wait_until='domcontentloaded')
    await page.wait_for_selector('input[type=password]', timeout=60000)
    await page.fill("input[placeholder*='用户名']", 'dev_user')
    await page.fill('input[type=password]', 'dev_password')
    await page.keyboard.press('Enter')
    await page.wait_for_function(
        "() => !location.pathname.startsWith('/login')", timeout=60000)
    await page.wait_for_timeout(1500)


async def open_session(page, base, session_id, run_id, dark=None):
    """把 Agent 会话存档写到 localStorage 后刷新，等 restore() 恢复待审批卡。"""
    async def apply():
        await page.evaluate(
            """([key, sid, rid, themeKey, theme]) => {
                localStorage.setItem(key, JSON.stringify(
                    {version: 1, data: {sessionId: sid, runId: rid}}))
                if (theme) localStorage.setItem(themeKey, theme)
            }""",
            [SESSION_KEY, session_id, run_id, THEME_KEY, dark])
    if page.url.endswith('/login') or '/login' in page.url:
        await page.wait_for_timeout(500)
    await apply()
    await page.goto(base + '/ai-chat', wait_until='domcontentloaded')
    await page.wait_for_timeout(3500)


async def wait_card(page, approval_id):
    card = page.locator(f'[data-approval-id="{approval_id}"]')
    await card.wait_for(state='visible', timeout=30000)
    return card


async def card_status(page, approval_id):
    """已决卡会落进折叠的「已处理」区（未展开时卸载），先展开再读状态。"""
    card = page.locator(f'[data-approval-id="{approval_id}"]')
    try:
        return await card.get_attribute('data-approval-status', timeout=3000)
    except Exception:
        pass
    try:
        await page.get_by_text(re.compile(r'^已处理（')).click(timeout=5000)
        await page.wait_for_timeout(600)
        return await card.get_attribute('data-approval-status', timeout=5000)
    except Exception:
        return None


async def shot_card(page, card, path):
    """把卡片滚进视口后整页截图（证据里要看得见卡面内容）。

    用 JS scrollIntoView 而不是 Playwright 的 scroll_into_view_if_needed：
    审批面板在会话滚动容器里，决策后频繁重渲染会让 actionable 等待超时。
    """
    try:
        handle = await card.first.element_handle(timeout=5000)
        if handle is not None:
            await page.evaluate(
                "el => el && el.scrollIntoView({block: 'center'})", handle)
            await page.wait_for_timeout(500)
    except Exception:
        pass
    await page.screenshot(path=path)


def decision_calls(log):
    return [item for item in log if '/decision' in item['url']]


async def main(base):
    os.makedirs(OUT, exist_ok=True)
    net = []
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={'width': 1680, 'height': 950})
        page = await ctx.new_page()

        def on_request(req):
            if '/api/v1/agent' in req.url:
                net.append({
                    'method': req.method,
                    'url': req.url.split('?')[0],
                    'post': req.post_data,
                })

        async def on_response(resp):
            if '/api/v1/agent' in resp.url and '/decision' in resp.url:
                for item in reversed(net):
                    if item['url'] == resp.url.split('?')[0] and 'status' not in item:
                        item['status'] = resp.status
                        try:
                            item['body'] = await resp.text()
                        except Exception:
                            item['body'] = ''
                        break

        page.on('request', on_request)
        page.on('response', lambda r: asyncio.ensure_future(on_response(r)))

        await login(page, base)

        # ---------- S1：WRITE 21 对象（P2） ----------
        await open_session(page, base, *S1)
        card = await wait_card(page, A1)
        text1 = await card.inner_text()
        results['s1_card_has_21'] = '影响对象 21' in text1
        results['s1_has_batch_hint'] = '超过单次审批上限' in text1
        await shot_card(page, card, os.path.join(OUT, '01_s1_21objects_light.png'))

        before = len(decision_calls(net))
        await card.get_by_role('button', name='批准执行').click()
        await page.wait_for_timeout(800)
        results['s1_no_request_on_click'] = len(decision_calls(net)) == before
        confirm_btn = page.get_by_role('button', name='逐项核对后批准')
        await confirm_btn.wait_for(timeout=15000)
        results['s1_confirm_disabled_initially'] = await confirm_btn.is_disabled()
        boxes = page.locator('[data-approval-target-list] [role=checkbox]')
        box_count = await boxes.count()
        if box_count == 0:
            boxes = page.get_by_role('checkbox')
            box_count = await boxes.count()
        results['s1_checkbox_count'] = box_count
        await page.screenshot(path=os.path.join(OUT, '02_s1_dialog_unchecked_light.png'))
        for index in range(box_count):
            await boxes.nth(index).click()
        await page.wait_for_timeout(400)
        results['s1_confirm_enabled_after_check'] = not await confirm_btn.is_disabled()
        await page.screenshot(path=os.path.join(OUT, '03_s1_dialog_checked_light.png'))
        await confirm_btn.click()
        await page.wait_for_timeout(3000)
        calls1 = decision_calls(net)
        results['s1_decision_calls'] = calls1
        results['s1_card_status'] = await card_status(page, A1)
        await shot_card(page, page.locator('[data-agent-approval-panel]'),
                        os.path.join(OUT, '04_s1_approved_light.png'))

        # ---------- S2：DESTRUCTIVE（P1，confirm=true） ----------
        await open_session(page, base, *S2)
        card2 = await wait_card(page, A2)
        text2 = await card2.inner_text()
        results['s2_risk_attr'] = await card2.get_attribute('data-approval-risk')
        results['s2_has_destructive_label'] = '高危操作' in text2
        await shot_card(page, card2, os.path.join(OUT, '05_s2_destructive_light.png'))

        before2 = len(decision_calls(net))
        await card2.get_by_role('button', name='批准执行').click()
        await page.wait_for_timeout(1000)
        results['s2_no_request_before_confirm'] = len(decision_calls(net)) == before2
        dlg_title = page.get_by_text('确认执行高危操作？')
        await dlg_title.wait_for(timeout=15000)
        results['s2_dialog_title'] = await dlg_title.is_visible()
        await page.screenshot(path=os.path.join(OUT, '06_s2_dialog_light.png'))
        await page.get_by_role('button', name='确认批准').click()
        await page.wait_for_timeout(3000)
        results['s2_decision_calls'] = decision_calls(net)[before2:]
        results['s2_card_status'] = await card_status(page, A2)

        # 深色：另起一次会话（同一张单已决策，改看 S3 的待审批卡）
        await open_session(page, base, *S3, dark='dark')
        await page.wait_for_timeout(1200)
        dark_applied = await page.evaluate(
            "() => document.documentElement.classList.contains('dark')")
        results['dark_applied'] = dark_applied
        card3 = await wait_card(page, A3)
        await shot_card(page, card3, os.path.join(OUT, '07_s3_destructive_dark.png'))
        await card3.get_by_role('button', name='批准执行').click()
        await page.get_by_text('确认执行高危操作？').wait_for(timeout=15000)
        await page.screenshot(path=os.path.join(OUT, '08_s3_dialog_dark.png'))
        await page.get_by_role('button', name='取消').click()
        await page.wait_for_timeout(600)

        # ---------- S3：DESTRUCTIVE 拒绝（不带 confirm；连点只发一次） ----------
        before3 = len(decision_calls(net))
        reject = card3.get_by_role('button', name='拒绝')
        box = await reject.bounding_box()
        # 真·连点：同一坐标快速双击，与单次点击走同一事件处理（按钮禁用 + store 决策闸）
        await page.mouse.dblclick(box['x'] + box['width'] / 2,
                                  box['y'] + box['height'] / 2)
        await page.wait_for_timeout(3000)
        results['s3_decision_calls'] = decision_calls(net)[before3:]
        results['s3_card_status'] = await card_status(page, A3)
        await shot_card(page, page.locator('[data-agent-approval-panel]'),
                        os.path.join(OUT, '09_s3_rejected_dark.png'))

        # 深色下的待审批卡（S3 已决策，另看 S2 的已批准卡）——补一张浅色已批准
        await open_session(page, base, *S2, dark='light')
        await page.wait_for_timeout(800)
        panel = page.locator('[data-agent-approval-panel]')
        await shot_card(page, panel, os.path.join(OUT, '10_s2_approved_light.png'))

        await browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))
    with open(os.path.join(OUT, 'network.json'), 'w', encoding='utf-8') as fp:
        json.dump(net, fp, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://localhost:5312')
    args = parser.parse_args()
    asyncio.run(main(args.base.rstrip('/')))
