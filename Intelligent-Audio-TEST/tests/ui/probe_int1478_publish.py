# -*- coding: utf-8 -*-
"""INT-1478 发布弹窗提交探针：定位「发布」钮为何无请求（JS click vs 原生 click）。"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

BASE = 'http://127.0.0.1:15173'
BACK = 'http://127.0.0.1:15000'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1478_modals_a')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
name = '接线测试_INT1478_发布_%s' % time.strftime('%H%M%S')


def api(p):
    return json.loads(urllib.request.urlopen(BACK + p, timeout=120).read().decode())


o = Options()
o.binary_location = CHROME
o.add_argument('--headless=new')
o.add_argument('--window-size=1680,1050')
o.add_argument('--no-sandbox')
o.add_argument('--disable-gpu')
o.add_argument('--lang=zh-CN')
o.add_argument('--user-data-dir=' + os.path.join(os.environ.get('TEMP', r'C:\Windows\Temp'),
                                                 'int1478_pub_probe'))
o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
d = webdriver.Chrome(service=Service(DRIVER), options=o)
try:
    d.get(BASE + '/tasks/daily')
    time.sleep(8)
    box = d.find_elements(By.CSS_SELECTOR, 'input[placeholder*="搜索任务名称"]')[0]
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys('接线测试_INT1478')
    time.sleep(2.5)
    trig = d.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]')[0]
    d.execute_script('arguments[0].click()', trig)
    time.sleep(0.6)
    for it in d.find_elements(By.CSS_SELECTOR, '*[role=menuitem]'):
        if it.text.strip() == '发布':
            d.execute_script('arguments[0].click()', it)
            break
    time.sleep(2.5)
    inp = d.find_elements(By.CSS_SELECTOR, '[role=dialog] input[placeholder*="发布后展示"]')[0]
    d.execute_script('arguments[0].click()', inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(name)
    time.sleep(0.8)
    btn = None
    for b in d.find_elements(By.CSS_SELECTOR, '[role=dialog] button'):
        if b.text.strip() == '发布':
            btn = b
    print('btn found:', btn is not None, 'enabled:', btn.is_enabled() if btn else None,
          'rect:', btn.rect if btn else None)
    print('outer:', btn.get_attribute('outerHTML')[:400] if btn else '')
    mark = len(d.get_log('performance'))
    try:
        btn.click()
        print('native click ok')
    except Exception as exc:
        print('native click failed:', exc)
        ActionChains(d).move_to_element(btn).click().perform()
        print('actionchains click ok')
    time.sleep(8)
    reqs = []
    for m in d.get_log('performance')[mark:]:
        msg = json.loads(m['message'])['message']
        if msg.get('method') == 'Network.requestWillBeSent':
            r = msg['params']['request']
            if '/api/' in r['url']:
                reqs.append((r['method'], r['url'].replace(BASE, ''), (r.get('postData') or '')[:300]))
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            if '/api/' in r['url']:
                reqs.append(('RESP', r['status'], r['url'].replace(BASE, '')))
    for x in reqs:
        print('  ', x)
    toasts = [t.text for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    print('toasts:', toasts)
    print('dialog:', [e.text[:120] for e in d.find_elements(By.CSS_SELECTOR, '[role=dialog]') if e.is_displayed()])
    hits = [p for p in api('/api/v1/published-tasks?page=1&per_page=50&keyword=' + urllib.parse.quote('INT1478_发布'))['data']['items'] if name in p['name']]
    print('published hits:', hits)
    d.save_screenshot(os.path.join(ART, '05c_publish_probe.png'))
finally:
    d.quit()
