# -*- coding: utf-8 -*-
"""INT-1483 recon: login docker React frontend 15173 + real stack 15000, dump
algorithm definitions/groups via in-page authenticated fetch."""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1483')
os.makedirs(ART, exist_ok=True)


def driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
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
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    return webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    try:
        u = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        print('NO LOGIN FORM, url=', drv.current_url)
        return
    u.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)


def api(drv, path):
    return drv.execute_async_script(
        """
        const path = arguments[0]; const done = arguments[arguments.length-1];
        const token = localStorage.getItem('iatp:auth:token:v1');
        fetch('/api/v1' + path, {headers: token ? {Authorization: 'Bearer ' + token} : {}})
          .then(r => r.text().then(t => done({status: r.status, body: t})))
          .catch(e => done({status: -1, body: String(e)}));
        """, path)


d = driver()
try:
    login(d)
    print('URL', d.current_url)
    d.get(BASE + '/AlgorithmConfig')
    time.sleep(4)
    print('TITLE', d.title)
    print('TEXT', (d.execute_script('return document.body.textContent||""') or '')[:1200])
    d.save_screenshot(os.path.join(ART, 'recon_list.png'))

    r = api(d, '/algorithm/definitions')
    print('DEFS status', r['status'])
    data = json.loads(r['body'])
    items = data.get('data', data).get('items', data.get('items', [])) if isinstance(data, dict) else []
    print('DEFS count', len(items))
    for it in items[:5]:
        print('  ', json.dumps(it, ensure_ascii=False)[:400])

    g = api(d, '/algorithm/groups')
    print('GROUPS status', g['status'])
    print('GROUPS body', g['body'][:1500])

    dims = api(d, '/evaluation/dimensions')
    print('DIMS status', dims['status'], 'len', len(dims['body']))
    cats = api(d, '/evaluation/categories')
    print('CATS status', cats['status'], 'len', len(cats['body']))
    opts = api(d, '/algorithm/options')
    print('OPTS status', opts['status'], opts['body'][:300])
finally:
    d.quit()
