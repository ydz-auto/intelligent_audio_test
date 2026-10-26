# -*- coding: utf-8 -*-
"""INT-1477 探针：用例列表在浏览器内的真实请求状态与耗时（真实栈 15173 → 15000）。"""
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


d = driver()
try:
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    t0 = time.time()
    last_body = ''
    while time.time() - t0 < 150:
        try:
            last_body = d.find_element(By.TAG_NAME, 'body').text
        except Exception:
            pass
        if '没有找到符合条件的测试用例' in last_body:
            print('EMPTY STATE at %.1fs' % (time.time() - t0))
            break
        if '预览音频' in last_body or '新增用例' in last_body and '/ 100' in last_body:
            print('LIST RENDERED at %.1fs' % (time.time() - t0))
            break
        time.sleep(2)
    print('BODY[:400]:', last_body[:400].replace('\n', ' | '))
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
            if '/api/' not in r['url']:
                continue
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
    print('--- api calls ---')
    for v in reqs.values():
        dur = (v['end'] - v['ts']) if v['end'] and v['ts'] else None
        print(v['m'], v['u'][:110], '->', v['status'], ('%.1fs' % dur) if dur else '')
    print('--- console ---')
    for e in d.get_log('browser'):
        print(e['level'], e['message'][:200])
finally:
    d.quit()
