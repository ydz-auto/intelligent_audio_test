# -*- coding: utf-8 -*-
"""INT-1477 探针：用例页首屏加载态/空态时间线 + 列表请求最终状态（真实栈）。"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   'tests', 'ui', 'artifacts', 'int1477')
os.makedirs(ART, exist_ok=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        cands = []
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [e for v, e in cands if v and v[0] == major]
        if same:
            path = max(same)
    d = webdriver.Chrome(options=o, service=Service(path) if path else Service())
    d.set_page_load_timeout(120)
    return d


def snap(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    print('  shot:', name, flush=True)


d = driver()
try:
    d.get(BASE + '/')
    time.sleep(1.5)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    t0 = time.time()
    seen = {}
    first_empty = None
    rendered = None
    for i in range(40):
        try:
            b = d.find_element(By.TAG_NAME, 'body').text
        except Exception:
            b = ''
        if '没有找到符合条件的测试用例' in b and first_empty is None:
            first_empty = time.time() - t0
            snap(d, 'probe_loading_empty_state')
        if '预览音频' in b or '条用例' in b or '共' in b and '个用例' in b:
            if rendered is None and '没有找到符合条件的测试用例' not in b:
                rendered = time.time() - t0
                snap(d, 'probe_list_rendered')
                break
        time.sleep(2)
    print('first_empty at', first_empty, '| rendered at', rendered)
    body = d.find_element(By.TAG_NAME, 'body').text
    print('BODY[:300]:', body[:300].replace('\n', ' | '))
    reqs = {}
    for e in d.get_log('performance'):
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        meth = m.get('method')
        p = m.get('params', {})
        if meth == 'Network.requestWillBeSent':
            r = p['request']
            if 'testcases?' in r['url']:
                reqs[p['requestId']] = {'m': r['method'], 'u': r['url'].split('15173')[-1],
                                        'ts': r.get('timestamp'), 'status': None, 'end': None}
        elif meth == 'Network.responseReceived':
            rid = p['requestId']
            if rid in reqs:
                reqs[rid]['status'] = p['response']['status']
                reqs[rid]['end'] = p['timestamp']
        elif meth == 'Network.loadingFailed':
            rid = p['requestId']
            if rid in reqs:
                reqs[rid]['status'] = 'FAILED:' + str(p.get('errorText'))
                reqs[rid]['end'] = p['timestamp']
    for v in reqs.values():
        dur = (v['end'] - v['ts']) if v['end'] and v['ts'] else None
        print(v['m'], v['u'][:100], '->', v['status'], ('%.1fs' % dur) if dur else 'PENDING')
finally:
    d.quit()
