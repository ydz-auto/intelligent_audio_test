# -*- coding: utf-8 -*-
"""INT-1477 探针：用例页真实栈（docker 前端 15173 / 网关 15000）结构与 Network 概览。"""
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
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    keeps = []
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
    d.set_page_load_timeout(60)
    return d


def drain(d):
    d.get_log('performance')


def net(d):
    out = []
    for e in d.get_log('performance'):
        m = e['message']
        try:
            msg = json.loads(m)['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            u = r['url']
            if '/api/' in u:
                out.append((r['status'], msg['params']['type'], u.split('15173')[-1]))
    return out


d = driver()
try:
    d.get(BASE + '/testcases/by-group')
    time.sleep(7)
    print('URL:', d.current_url)
    print('TITLE:', d.title)
    txt = d.find_element(By.TAG_NAME, 'body').text
    print('BODY[:1200]:', txt[:1200].replace('\n', ' | '))
    print('--- buttons ---')
    for b in d.find_elements(By.TAG_NAME, 'button'):
        t = (b.text or '').strip()
        a = b.get_attribute('aria-label')
        if t or a:
            print(repr(t), '| aria=', a, '| vis=', b.is_displayed())
    print('--- api responses ---')
    for r in net(d):
        print(r)
finally:
    d.quit()
