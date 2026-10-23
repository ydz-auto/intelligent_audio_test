# -*- coding: utf-8 -*-
"""INT-1487 收尾：核对/清理「接线测试_INT1487」用例残留。"""
import json
import os
import sys
import time
import winreg

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = 'http://localhost:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def drv():
    o = Options()
    o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1280,800', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-extensions', '--no-proxy-server'):
        o.add_argument(a)
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    p = ''
    if os.path.isdir(cache):
        for v in os.listdir(cache):
            e = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(e) and v.split('.')[0].isdigit() and int(v.split('.')[0]) == major:
                p = max(p, e)
    d = webdriver.Chrome(options=o, service=Service(p) if p else Service())
    d.set_page_load_timeout(120)
    return d


def api(d, method, path, body=None):
    s = """
    const [m,p,b] = arguments; const cb = arguments[arguments.length-1];
    const tk = localStorage.getItem('iatp:auth:token:v1');
    const o = {method:m, headers:{Accept:'application/json'}, credentials:'include'};
    if (tk) o.headers.Authorization = 'Bearer ' + tk;
    if (b) { o.headers['Content-Type']='application/json'; o.body=JSON.stringify(b); }
    fetch('/api/v1'+p, o).then(async r=>cb({status:r.status, body: await r.text()}))
      .catch(e=>cb({status:-1, body:String(e)}));
    """
    d.set_script_timeout(120)
    r = d.execute_async_script(s, method, path, body)
    try:
        r['json'] = json.loads(r['body'])
    except Exception:
        r['json'] = None
    return r


d = drv()
try:
    d.get(BASE + '/login')
    end = time.time() + 60
    while time.time() < end and not d.find_elements(By.ID, 'username'):
        if '/login' not in d.current_url:
            break
        time.sleep(1)
    if d.find_elements(By.ID, 'username'):
        d.find_element(By.ID, 'username').send_keys('接线测试_admin')
        d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '登' in b.text and '录' in b.text:
                d.execute_script('arguments[0].click()', b)
                break
    time.sleep(15)
    print('url', d.current_url)
    r = api(d, 'GET', '/testcases?page=1&per_page=100&keyword=%E6%8E%A5%E7%BA%BF%E6%B5%8B%E8%AF%95_INT1487')
    print('list', r['status'])
    items = ((r.get('json') or {}).get('data') or {}).get('items', [])
    print('残留用例', [(i.get('id'), i.get('name'), i.get('deleted')) for i in items])
    ids = [str(i['id']) for i in items]
    if ids:
        p = api(d, 'POST', '/testcases/purge', {'ids': ids})
        print('purge', p['status'], p['body'][:200])
    r2 = api(d, 'GET', '/testcases?page=1&per_page=100&keyword=%E6%8E%A5%E7%BA%BF%E6%B5%8B%E8%AF%95_INT1487&only_deleted=true')
    print('回收站', r2['status'], [i.get('name') for i in (((r2.get('json') or {}).get('data') or {}).get('items', []))])
    gs = api(d, 'GET', '/groups?page=1&per_page=200')
    print('分组残留', [g['name'] for g in (((gs.get('json') or {}).get('data') or {}).get('items', [])) if 'INT1487' in g['name']])
finally:
    try:
        d.quit()
    except Exception:
        pass
