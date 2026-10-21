# -*- coding: utf-8 -*-
"""INT-1105 探针 2：hash 路由 /#/devices 页可达性与模态窗结构。"""
import time

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5525'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto(BASE + '/#/devices', wait_until='networkidle', timeout=30000)
    time.sleep(3)
    print('URL:', page.url)
    body = page.evaluate("document.body ? document.body.innerText : 'NO BODY'")
    print('BODY:', body.replace('\n', ' | ')[:600])
    html = page.content()
    print('HAS device-view:', 'device-view' in html)
    print('HAS tab-btn:', 'tab-btn' in html)
    browser.close()
