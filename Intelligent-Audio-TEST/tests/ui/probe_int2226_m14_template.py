# -*- coding: utf-8 -*-
"""INT-2226 M14：从 React 导入弹窗下载 Excel 模板，供本 run 造导入夹具。"""
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2226')
os.makedirs(ART, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.goto('http://localhost:15173/login', wait_until='domcontentloaded')
    time.sleep(3)
    pg.locator('input[type=password]').first.fill('dev_password')
    pg.locator('input[type=text], input:not([type])').first.fill('dev_user')
    pg.get_by_role('button', name=re.compile('登\\s*录')).first.click()
    pg.wait_for_function("() => !/login/i.test(location.href)", timeout=45000)
    time.sleep(3)
    pg.goto('http://localhost:15173/testcases', wait_until='domcontentloaded')
    time.sleep(5)
    pg.get_by_role('button', name=re.compile('导入用例')).first.click()
    time.sleep(2)
    with pg.expect_download(timeout=30000) as dl:
        pg.get_by_role('button', name=re.compile('下载 ?Excel 模板')).first.click()
    path = os.path.join(ART, 'template.xlsx')
    dl.value.save_as(path)
    print('saved', path, os.path.getsize(path), flush=True)
    b.close()
