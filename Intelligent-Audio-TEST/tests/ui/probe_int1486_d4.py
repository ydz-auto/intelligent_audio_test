# -*- coding: utf-8 -*-
"""INT-1486 探针：步骤二 API 卡片渲染（调试 D4）。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1486'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
SUF = str(int(time.time()))[-6:]
NAME = '接线测试_INT1486_PROBE_' + SUF

import urllib.request
token = open(os.path.join(ART, 'token.txt')).read().strip()


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:300]


st, hc = req('POST', '/api/v1/apis', {
    'name': NAME, 'description': 'probe', 'algorithm_type': 'voice_llm', 'default_max_process': 5,
    'endpoints': [{'endpoint': 'https://example.test/probe', 'name': None, 'max_process': 1,
                   'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                   'description': None}]})
print('CREATE', st, json.dumps(hc, ensure_ascii=False)[:300])
api_id = (hc.get('data') or {}).get('id') if isinstance(hc, dict) else None
st, one = req('GET', f'/api/v1/apis/{api_id}')
print('GET api', st, json.dumps(one, ensure_ascii=False)[:800])
st, lst = req('GET', '/api/v1/apis?per_page=1000')
items = (lst.get('data', lst) or {}).get('items', [])
print('LIST total', len(items), [(x.get('id'), x.get('name'), x.get('status')) for x in items])

o = Options(); o.binary_location = CHROME
for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox', '--lang=zh-CN']:
    o.add_argument(a)
cache = r'D:\00_user_data\.cache\selenium\chromedriver\win64'
path = ''
for v in os.listdir(cache):
    exe = os.path.join(cache, v, 'chromedriver.exe')
    if os.path.isfile(exe):
        path = exe
d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
d.set_script_timeout(120)
d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': "try{localStorage.setItem('iatp:auth:token:v1', %s)}catch(e){}" % json.dumps(token)})
try:
    d.get(BASE + '/start-test')
    WebDriverWait(d, 60).until(lambda x: '按分组' in (x.execute_script('return document.body.innerText') or ''))
    time.sleep(4)
    # filter-all 直接下一步
    btns = d.find_elements(By.XPATH, "//button[normalize-space(.)='下一步']")
    d.execute_script('arguments[0].click()', btns[0])
    WebDriverWait(d, 60).until(lambda x: '执行参数' in (x.execute_script('return document.body.innerText') or ''))
    time.sleep(4)
    labels = d.execute_script("return Array.from(document.querySelectorAll('[aria-label]')).map(e=>e.getAttribute('aria-label'))")
    print('ARIA sample', [l for l in labels if l and ('API' in l or 'api' in l)][:30])
    print('HAS NAME', [l for l in labels if l and NAME in l][:5])
    t = d.execute_script('return document.body.innerText')
    print('BODY contains NAME', NAME in t)
    print('BODY excerpt', [ln for ln in t.splitlines() if 'API' in ln or '算法' in ln][:20])
    d.save_screenshot(os.path.join(ART, 'probe_d4_step2.png'))
finally:
    d.quit()
    print('CLEAN', req('DELETE', f'/api/v1/apis/{api_id}'))
