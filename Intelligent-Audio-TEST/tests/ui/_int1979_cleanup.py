# -*- coding: utf-8 -*-
"""INT-1979 走查数据清理：删掉本卡导入的音频与生成的用例（真实库 :15000 经 dev 代理 5362）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = 'http://localhost:5362'
DRIVER = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
NAMES = ['甲1.wav', '乙1.wav', '单独.wav']
KEYWORDS = ['甲1', '乙1', '单独']
OUT = os.path.join(HERE, 'artifacts', 'int1979', 'cleanup.json')


def make_driver():
    o = Options()
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1440,900')
    o.page_load_strategy = 'eager'
    d = webdriver.Chrome(service=Service(DRIVER), options=o)
    d.set_script_timeout(240)
    return d


def api(d, method, path, body=None):
    return d.execute_async_script("""
    const cb = arguments[arguments.length - 1];
    const token = localStorage.getItem('iatp:auth:token:v1') || '';
    const init = {method: %s, headers: token ? {Authorization: 'Bearer ' + token} : {}};
    if (%s) { init.headers['Content-Type'] = 'application/json'; init.body = %s; }
    fetch(%s, init).then(r => r.text().then(t => cb({status: r.status, body: t})))
      .catch(e => cb({status: 0, body: String(e)}));
    """ % (json.dumps(method), json.dumps(body is not None),
           json.dumps(json.dumps(body, ensure_ascii=False)) if body is not None else 'null',
           json.dumps(path)))


def wait(d, fn, t=90):
    end = time.time() + t
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def items_of(resp):
    try:
        body = json.loads(resp['body'])
    except Exception:
        return []
    data = body.get('data') if isinstance(body.get('data'), dict) else body
    return data.get('items') or []


d = make_driver()
report = {'audio_ids': [], 'testcase_ids': [], 'steps': []}
try:
    d.get(BASE + '/login')
    wait(d, lambda: len(d.find_elements(By.ID, 'username')) > 0, 60)
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.CSS_SELECTOR, 'button[type=submit]').click()
    wait(d, lambda: '/login' not in d.current_url, 90)
    d.get(BASE + '/audio-import')
    wait(d, lambda: '音频管理' in d.execute_script('return document.body.innerText'), 120)

    for name, kw_raw in zip(NAMES, KEYWORDS):
        got = [i.get('id') for i in items_of(
            api(d, 'GET', '/api/v1/audios?page=1&per_page=100&keyword=%s'
                % d.execute_script('return encodeURIComponent(arguments[0])', kw_raw)))
               if i.get('name') == name]
        report['audio_ids'].extend(got)
        report['steps'].append({'audio': name, 'ids': got})

    tc_ids = set()
    for name in NAMES:
        kw = d.execute_script('return encodeURIComponent(arguments[0])', '测试用例_%s' % name)
        for i in items_of(api(d, 'GET', '/api/v1/testcases?page=1&per_page=100&keyword=%s' % kw)):
            if (i.get('name') or '').startswith('测试用例_%s_' % name):
                tc_ids.add(i.get('id'))
    report['testcase_ids'] = sorted(tc_ids)

    for tid in report['testcase_ids']:
        rr = api(d, 'DELETE', '/api/v1/testcases/%s' % tid)
        report['steps'].append({'delete_testcase': tid, 'status': rr['status']})

    ids = sorted(set(report['audio_ids']))
    if ids:
        rr = api(d, 'POST', '/api/v1/audios/batch-action',
                 {'action': 'delete', 'audio_ids': ids})
        report['steps'].append({'delete_audios': ids, 'status': rr['status'],
                                'body': rr['body'][:400]})
finally:
    d.quit()
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=1)[:3000])
