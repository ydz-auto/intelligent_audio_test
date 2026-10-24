# -*- coding: utf-8 -*-
"""INT-1488 探针：登录后 /logs 页面 Network（performance log）+ 控制台 + 文案。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1488_ux_audit')

o = Options()
o.binary_location = CHROME
o.add_argument('--headless=new')
o.add_argument('--window-size=1680,1050')
o.add_argument('--no-sandbox')
o.page_load_strategy = 'eager'
o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
p = ''
for v in os.listdir(cache):
    e = os.path.join(cache, v, 'chromedriver.exe')
    if os.path.isfile(e) and v.startswith('155'):
        p = e
d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
try:
    d.get(BASE + '/login')
    time.sleep(2)
    if '/login' not in d.current_url:
        d.get(BASE + '/login')
        time.sleep(2)
    WebDriverWait(d, 45).until(lambda x: x.find_elements(By.ID, 'username'))
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(5)
    d.get_log('performance')
    d.get(BASE + '/logs')
    time.sleep(15)
    rows = d.find_elements(By.CSS_SELECTOR, 'table tbody tr')
    print('ROWS', len(rows), flush=True)
    body = d.find_element(By.TAG_NAME, 'body').text
    print('BODY_TAIL', body[-600:].encode('ascii', 'replace').decode(), flush=True)
    reqs = {}
    for e in d.get_log('performance'):
        m = json.loads(e['message']).get('message', {})
        if m.get('method') == 'Network.requestWillBeSent':
            u = m['params']['request']['url']
            if '/api/' in u:
                reqs[m['params']['requestId']] = {'url': u, 'method': m['params']['request']['method'], 'status': None}
        elif m.get('method') == 'Network.responseReceived':
            rid = m['params']['requestId']
            if rid in reqs:
                reqs[rid]['status'] = m['params']['response']['status']
        elif m.get('method') == 'Network.loadingFailed':
            rid = m['params']['requestId']
            if rid in reqs:
                reqs[rid]['failed'] = m['params'].get('errorText')
    for r in reqs.values():
        if 'log' in r['url']:
            print('NET', json.dumps(r, ensure_ascii=False)[:300], flush=True)
    print('--- console ---', flush=True)
    for e in d.get_log('browser'):
        if e.get('level') in ('SEVERE', 'WARNING'):
            print(e['level'], e['message'][:400].encode('ascii', 'replace').decode(), flush=True)
    d.save_screenshot(os.path.join(ART, 'probe_logs2.png'))
finally:
    d.quit()
print('PROBE3_DONE', flush=True)
