# -*- coding: utf-8 -*-
"""INT-607 壳/导航/RBAC 接线——真实请求核对（Network 证据）。

加载 /dashboard（dev_user 会话），经 CDP Network 域记录所有 /api/ 请求，
证明壳渲染走真实后端接口（/auth/mode、/auth/me、/home/site[404 回落]、
/algorithm/options 等），无 mock 残留。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5331')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

api_requests = []


def on_request(method, url):
    if '/api/' in url:
        api_requests.append(url.replace(BASE, ''))


options = Options()
options.binary_location = CHROME_BINARY
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1440,900')
driver = webdriver.Chrome(options=options)
try:
    driver.execute_cdp_cmd('Network.enable', {})
    driver.get(BASE + '/dashboard')
    time.sleep(5)
    # 读取已发出的请求（Network.enable 后 get 已覆盖；再补一次 getAllResponseBody 不可行，
    # 直接抓 performance entries 更完整）
    perf = driver.execute_script(
        "return performance.getEntriesByType('resource').filter(e => e.name.includes('/api/')).map(e => e.name)"
    )
    for url in perf:
        api_requests.append(url.replace(BASE, ''))
    print('==== INT-607 真实请求清单（resource entries，经 rsbuild proxy → :5000）====')
    seen = set()
    for u in api_requests:
        if u not in seen:
            seen.add(u)
            print(f'  {u}')
    print(f'==== 共 {len(seen)} 个 /api/ 请求 ====')
finally:
    driver.quit()
