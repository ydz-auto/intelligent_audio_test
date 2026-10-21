# -*- coding: utf-8 -*-
"""INT-1105 探针：检查 /devices 页可达性与模态窗结构（Playwright）。"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5525'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto(BASE + '/devices', wait_until='networkidle', timeout=30000)
    time.sleep(3)
    print('URL:', page.url)
    print('TITLE:', page.title())
    body = page.evaluate("document.body ? document.body.innerText.slice(0, 800) : 'NO BODY'")
    print('BODY:', body.replace('\n', ' | ')[:800])
    # 检查设备页关键元素
    html = page.content()
    print('HAS device-view:', 'device-view' in html)
    print('HAS login form:', 'login' in page.url or '登录' in body[:500])
    browser.close()
