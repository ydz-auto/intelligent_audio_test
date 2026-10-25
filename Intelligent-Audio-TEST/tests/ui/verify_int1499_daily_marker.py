# -*- coding: utf-8 -*-
"""INT-1499 尾段取证（Chrome 在上一轮 daily 页签崩了）：日常任务页签「挑选合并」标识 + 收尾。

浏览器：打开 /tasks?tab=daily，定位本 run 容器行，取行文本 + 浅/深截图；
接口：软删 + purge 本 run 容器、清空购物车。
用法：python tests/ui/verify_int1499_daily_marker.py <task_id> <task_name>
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: BLE001
    pass

BASE = 'http://127.0.0.1:15173'
API = 'http://127.0.0.1:15000'
USER = '接线测试_int1499b'
PASS = 'JieXianTest@2026'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1499_15173')
os.makedirs(ART, exist_ok=True)
TASK_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 0
TASK_NAME = sys.argv[2] if len(sys.argv) > 2 else '接线测试_INT1499_全链路_15173'

LOGIN_JS = r"""
return (async () => {
  const keyResp = await fetch('/api/v1/auth/login/encryption-key').then(r=>r.json());
  const d = keyResp.data || keyResp;
  const pem = d.public_key.replace(/-----[^-]+-----/g,'').replace(/\s+/g,'');
  const bin = Uint8Array.from(atob(pem), c=>c.charCodeAt(0));
  const key = await crypto.subtle.importKey('spki', bin, {name:'RSA-OAEP', hash:'SHA-256'}, false, ['encrypt']);
  const enc = await crypto.subtle.encrypt({name:'RSA-OAEP'}, key, new TextEncoder().encode(arguments[0]));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(enc)));
  const body = new URLSearchParams({username: arguments[1], password_encrypted: b64, encryption_key_id: d.kid});
  const r = await fetch('/api/v1/auth/login', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  const j = await r.json();
  if (j.access_token) localStorage.setItem('iatp:auth:token:v1', j.access_token);
  return {status: r.status, token: j.access_token || null};
})()
"""


def driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    for a in ('--headless=new', '--window-size=1560,1080', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage'):
        o.add_argument(a)
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:  # noqa: BLE001
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe) and ver.split('.')[0].isdigit() and int(ver.split('.')[0]) == major:
                path = exe
    return webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())


def api(method, path, token, body=None):
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(API + path, data=data, method=method)
    r.add_header('Authorization', 'Bearer ' + token)
    if body is not None:
        r.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(r, timeout=120) as x:
            raw = x.read()
            return x.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b'{}')
        except ValueError:
            return e.code, raw[:200]


def main():
    out = {}
    d = driver()
    try:
        d.get(BASE + '/login')
        time.sleep(4)
        res = d.execute_script(LOGIN_JS, PASS, USER)
        tok = res.get('token')
        out['login'] = bool(tok)
        if not tok:
            raise RuntimeError('login failed')
        d.get(BASE + '/tasks?tab=daily')
        time.sleep(8)
        row = d.execute_script('''
          var rows=Array.from(document.querySelectorAll('tr')).filter(function(r){
            return (r.innerText||'').indexOf(arguments[0])>=0;});
          return rows.length ? (rows[0].innerText||'').replace(/\\n/g,' | ').slice(0,300) : null;''',
                               TASK_NAME)
        out['daily_row'] = row
        out['daily_has_marker'] = bool(row) and '挑选合并' in row and '结果挑选' in row
        body = d.execute_script('return document.body.innerText||"";')
        out['tabs'] = d.execute_script(
            "return Array.from(document.querySelectorAll(\"[role='tab']\"))"
            ".map(function(t){return (t.innerText||'').trim();}).filter(Boolean);")
        out['row_count_text'] = [ln.strip() for ln in body.splitlines() if '来源' in ln][:4]
        print('DAILY_MARKER', json.dumps(out, ensure_ascii=False)[:600])
        p = os.path.join(ART, 'p14_daily_marker_light.png')
        d.save_screenshot(p)
        print('SHOT', p)

        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark');")
        d.refresh()
        time.sleep(6)
        p2 = os.path.join(ART, 'p14_daily_marker_dark.png')
        d.save_screenshot(p2)
        print('SHOT', p2)

        # 容器详情（本 run 新容器）浅/深
        if TASK_ID:
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
            d.get(BASE + '/tasks/%d' % TASK_ID)
            time.sleep(6)
            dtxt = d.execute_script('return document.body.innerText||"";')
            out['detail_lines'] = [ln.strip() for ln in dtxt.splitlines()
                                   if '结果' in ln or '用例清单' in ln][:6]
            print('DETAIL', json.dumps(out['detail_lines'], ensure_ascii=False)[:400])
            p3 = os.path.join(ART, 'p15_container_detail_light.png')
            d.save_screenshot(p3)
            print('SHOT', p3)
    finally:
        try:
            d.quit()
        except Exception:  # noqa: BLE001
            pass
        # 收尾：软删 + purge 容器，清空购物车
        if TASK_ID:
            print('CLEANUP delete', api('DELETE', '/api/v1/tasks/%d' % TASK_ID, tok))
            print('CLEANUP purge', api('DELETE', '/api/v1/tasks/%d/purge' % TASK_ID, tok))
        print('CLEANUP cart', api('DELETE', '/api/v1/tasks/cherry-picks/cart/items', tok))
    with open(os.path.join(ART, 'result_daily.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
