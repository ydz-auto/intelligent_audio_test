# -*- coding: utf-8 -*-
import time
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:5522'

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    console_msgs = []
    page.on('console', lambda m: console_msgs.append(f'[{m.type}] {m.text}'))
    page.on('pageerror', lambda e: console_msgs.append(f'[pageerror] {e}'))

    page.goto(f'{BASE}/#/ai-chat', wait_until='networkidle')
    page.wait_for_selector('.ai-chat-page')
    page.wait_for_selector('.ai-chat-empty', timeout=15000)
    print('empty ok')

    page.click('.provider-switcher-trigger')
    page.click('.manage-link')
    page.wait_for_selector('.provider-manager .pm-list')
    print('provider manager open')
    page.click('.pm-list .btn-primary')
    page.wait_for_selector('.pm-form')
    print('form open, input count:', page.locator('.pm-form .pm-input').count())
    inputs = page.locator('.pm-form .pm-input')
    print('inputs:', [inputs.nth(i).get_attribute('placeholder') for i in range(inputs.count())])
    inputs.nth(0).fill('MockChat')
    inputs.nth(1).fill('http://127.0.0.1:7799')
    inputs.nth(2).fill('sk-int1109')
    print('filled, clicking fetch models')
    page.click('.pm-fetch-models')
    time.sleep(3)
    print('after fetch: model rows =', page.locator('.pm-model-row').count())
    print('model row values:', [page.locator('.pm-model-row input').nth(i).input_value() for i in range(page.locator('.pm-model-row').count())])
    page.screenshot(path='_int1109_debug_form.png')
    print('console:', console_msgs[:20])
    browser.close()
