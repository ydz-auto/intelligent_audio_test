# -*- coding: utf-8 -*-
"""INT-1478 确认钮点击诊断：JS click vs CDP 真实鼠标事件（重新执行范围弹窗）。"""
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

BASE = 'http://127.0.0.1:15173'
BACK = 'http://127.0.0.1:15000'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1478_modals_a')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DRIVER = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                      'win64', '155.0.8059.84', 'chromedriver.exe')
out = {}


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
                                                 'int1478_confirm_probe'))
o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
d = webdriver.Chrome(service=Service(DRIVER), options=o)
d.set_page_load_timeout(120)
try:
    d.get(BASE + '/tasks/552')
    time.sleep(12)
    btns = [b for b in d.find_elements(By.CSS_SELECTOR, 'button') if b.is_displayed() and b.text.strip() == '重新执行']
    out['reexec_btn'] = len(btns)
    if btns:
        d.execute_script('arguments[0].click()', btns[0])
        time.sleep(6)
    d.save_screenshot(os.path.join(ART, '06d_reexec_dialog.png'))
    confirm = [b for b in d.find_elements(By.CSS_SELECTOR, '[role=dialog] button') if b.text.strip().startswith('确认')]
    out['confirm_count'] = len(confirm)
    if confirm:
        c = confirm[0]
        out['rect'] = c.rect
        out['enabled'] = c.is_enabled()
        out['html'] = c.get_attribute('outerHTML')[:300]
        # 1) JS click
        mark = len(d.get_log('performance'))
        d.execute_script('arguments[0].click()', c)
        time.sleep(5)
        js_reqs = [json.loads(m['message'])['message'] for m in d.get_log('performance')[mark:]]
        out['after_js'] = [x['params']['request']['method'] + ' ' + x['params']['request']['url']
                           for x in js_reqs if x.get('method') == 'Network.requestWillBeSent'
                           and '/api/' in x['params']['request']['url']]
        out['toasts_js'] = [t.text for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        out['dialog_after_js'] = len([e for e in d.find_elements(By.CSS_SELECTOR, '[role=dialog]') if e.is_displayed()])
        # 2) CDP 真实鼠标
        re_confirm = [b for b in d.find_elements(By.CSS_SELECTOR, '[role=dialog] button') if b.text.strip().startswith('确认')]
        if re_confirm:
            c2 = re_confirm[0]
            r = c2.rect
            x = r['x'] + r['width'] / 2
            y = r['y'] + r['height'] / 2 + d.execute_script('return window.scrollY') * 0
            mark = len(d.get_log('performance'))
            d.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': x, 'y': y,
                                                           'button': 'left', 'clickCount': 1})
            d.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': x, 'y': y,
                                                           'button': 'left', 'clickCount': 1})
            time.sleep(8)
            cdp_reqs = [json.loads(m['message'])['message'] for m in d.get_log('performance')[mark:]]
            out['after_cdp'] = [x2['params']['request']['method'] + ' ' + x2['params']['request']['url']
                                for x2 in cdp_reqs if x2.get('method') == 'Network.requestWillBeSent'
                                and '/api/' in x2['params']['request']['url']]
            out['toasts_cdp'] = [t.text for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
            out['task_after'] = {k: api('/api/v1/tasks/552')['data'].get(k)
                                 for k in ('execution_status', 'status')}
    out['severe'] = [l['message'][:200] for l in d.get_log('browser') if l['level'] == 'SEVERE'][-8:]
finally:
    print(json.dumps(out, ensure_ascii=False, indent=2))
    d.quit()
