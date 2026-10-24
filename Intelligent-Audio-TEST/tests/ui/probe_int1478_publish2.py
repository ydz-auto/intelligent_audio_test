# -*- coding: utf-8 -*-
"""INT-1478 发布弹窗提交探针 v2：显式选择来源任务后提交。"""
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
                                                 'int1478_pub_probe2'))
o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
d = webdriver.Chrome(service=Service(DRIVER), options=o)
d.set_page_load_timeout(120)
d.set_script_timeout(60)
try:
    d.get(BASE + '/tasks/daily')
    time.sleep(8)
    box = d.find_elements(By.CSS_SELECTOR, 'input[placeholder*="搜索任务名称"]')[0]
    d.execute_script('arguments[0].click()', box)
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
    time.sleep(3)
    st = d.find_elements(By.CSS_SELECTOR, '[role=dialog] [aria-label="选择来源任务"]')
    print('select trigger:', len(st))
    if st:
        d.execute_script('arguments[0].click()', st[0])
        time.sleep(1.5)
        opts = [o for o in d.find_elements(By.CSS_SELECTOR, '*[role=option]') if o.is_displayed()]
        print('options:', len(opts), [x.text.strip()[:30] for x in opts[:3]])
        if opts:
            d.execute_script('arguments[0].click()', opts[0])
            time.sleep(1.5)
    inp = d.find_elements(By.CSS_SELECTOR, '[role=dialog] input[placeholder*="发布后展示"]')
    print('name inputs:', len(inp))
    if inp:
        d.execute_script('arguments[0].click()', inp[0])
        inp[0].send_keys(Keys.CONTROL, 'a')
        inp[0].send_keys(Keys.DELETE)
        inp[0].send_keys(name)
        time.sleep(0.8)
    btn = None
    for b in d.find_elements(By.CSS_SELECTOR, '[role=dialog] button'):
        if b.text.strip() == '发布':
            btn = b
    print('btn enabled:', btn.is_enabled() if btn else None,
          'disabled attr:', btn.get_attribute('disabled') if btn else None)
    d.save_screenshot(os.path.join(ART, '05d_publish_selected.png'))
    mark = len(d.get_log('performance'))
    if btn is not None:
        d.execute_script('arguments[0].click()', btn)
    time.sleep(8)
    reqs = []
    for m in d.get_log('performance')[mark:]:
        msg = json.loads(m['message'])['message']
        if msg.get('method') == 'Network.requestWillBeSent':
            r = msg['params']['request']
            if '/api/' in r['url']:
                reqs.append('%s %s %s' % (r['method'], r['url'].replace(BASE, ''), (r.get('postData') or '')[:250]))
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            if '/api/' in r['url']:
                reqs.append('RESP %s %s' % (r['status'], r['url'].replace(BASE, '')))
    print('\n'.join(reqs))
    print('toasts:', [t.text for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')])
    hits = [p for p in api('/api/v1/published-tasks?page=1&per_page=50&keyword=' + urllib.parse.quote('INT1478_发布'))['data']['items'] if name in p['name']]
    print('published hits:', hits)
finally:
    d.quit()
