# -*- coding: utf-8 -*-
"""INT-2457 截图探针：React 对话通道（平台 Agent 默认 / 自带供应商降级 / 错误态 / 深浅色）。

只读：登录 + GET + 一次发送（后端无 agent 端点 → 404 错误态，不改业务数据）。
跑法：<python> tests/ui/probe_int2457_agent_channel.py --base http://localhost:5337
"""
import argparse
import asyncio
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from playwright.async_api import async_playwright  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2457')


async def login(page, base):
    await page.goto(base + '/login', wait_until='domcontentloaded')
    await page.wait_for_selector('input[type=password]', timeout=30000)
    await page.fill("input[placeholder*='用户名']", 'dev_user')
    await page.fill('input[type=password]', 'dev_password')
    await page.keyboard.press('Enter')
    await page.wait_for_function(
        "() => !location.pathname.startsWith('/login')", timeout=30000)
    await page.wait_for_timeout(1500)


async def main(base):
    os.makedirs(OUT, exist_ok=True)
    net = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={'width': 1680, 'height': 950})
        page = await ctx.new_page()

        def on_response(resp):
            if '/api/v1/agent' in resp.url:
                net.append({'url': resp.url.split('?')[0], 'status': resp.status})

        page.on('response', on_response)

        await login(page, base)
        await page.goto(base + '/ai-chat', wait_until='domcontentloaded')
        await page.wait_for_selector('text=灵犀Agent', timeout=30000)
        await page.wait_for_timeout(2500)
        await page.screenshot(path=os.path.join(OUT, '01-platform-light.png'))

        # 平台 Agent 通道发送 → 后端无 agent 端点 → 语义化错误态（真实请求）
        box = page.locator('textarea')
        await box.fill('帮我把最近的测试任务生成一份报告')
        await page.keyboard.press('Enter')
        await page.wait_for_function(
            "() => (document.body.innerText || '').includes('平台 Agent 暂不可用')"
            " || (document.body.innerText || '').includes('Agent')",
            timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=os.path.join(OUT, '02-platform-error.png'))

        # 切换到自带供应商（降级通道入口）
        await page.get_by_role('radio', name='自带供应商').click()
        await page.wait_for_timeout(1000)
        await page.screenshot(path=os.path.join(OUT, '03-provider-channel.png'))

        # 深色：写主题偏好后重载，回到平台通道
        await page.evaluate("() => localStorage.setItem('iatp:theme:v1:mode', 'dark')")
        await page.reload(wait_until='domcontentloaded')
        await page.wait_for_timeout(2500)
        await page.get_by_role('radio', name='平台 Agent').click()
        await page.wait_for_timeout(1200)
        await page.screenshot(path=os.path.join(OUT, '04-platform-dark.png'))

        html_dark = await page.evaluate(
            "() => document.documentElement.classList.contains('dark')")
        print(json.dumps({'dark_applied': html_dark, 'agent_requests': net},
                         ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5337')
    args = ap.parse_args()
    asyncio.run(main(args.base))
