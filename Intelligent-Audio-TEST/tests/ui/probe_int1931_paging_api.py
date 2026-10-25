# -*- coding: utf-8 -*-
"""INT-1931 纯接口取证：日志合并视图分页是否重叠/乱序（用浏览器登录拿 token，再用 urllib 直连 15000）。"""
import json
import os
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
API = 'http://127.0.0.1:15000'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1931', 'probe_paging_api.json')
PARAMS = {'start_time': '2026-10-24T00:00', 'end_time': '2026-10-25T20:00', 'per_page': 20}


def get_token():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.page_load_strategy = 'eager'
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    p = ''
    for v in os.listdir(cache):
        e = os.path.join(cache, v, 'chromedriver.exe')
        if os.path.isfile(e) and v.startswith('155'):
            p = e
    d = webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())
    try:
        d.get(BASE + '/login')
        WebDriverWait(d, 40).until(lambda x: x.find_elements(By.ID, 'username'))
        d.find_element(By.ID, 'username').send_keys('接线测试_admin')
        d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
        tok = d.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        return tok
    finally:
        d.quit()


def api(path, tok, params=None):
    url = API + '/api/v1' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + tok})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


tok = get_token()
res = {'token': bool(tok), 'params': PARAMS}
pages = {}
for n in (1, 2, 3):
    d = api('/logs', tok, dict(PARAMS, page=n))
    data = d['data']
    pages[n] = {'page': data.get('page'), 'per_page': data.get('per_page'), 'total': data.get('total'),
                'ids': [i['id'] for i in data['items']],
                'times': [i['time'] for i in data['items']]}
    time.sleep(0.5)
res['pages'] = pages
s1, s2, s3 = (set(pages[n]['ids']) for n in (1, 2, 3))
res['overlap_1_2'] = sorted(s1 & s2)
res['overlap_1_3'] = sorted(s1 & s3)
res['overlap_2_3'] = sorted(s2 & s3)
res['sorted_desc'] = {n: all(pages[n]['times'][i] >= pages[n]['times'][i + 1] for i in range(len(pages[n]['times']) - 1))
                      for n in (1, 2, 3)}
res['all_ids_unique_within'] = {n: len(set(pages[n]['ids'])) == len(pages[n]['ids']) for n in (1, 2, 3)}
# 同一请求连发两次（排除并发漂移）
again = api('/logs', tok, dict(PARAMS, page=2))['data']
res['page2_repeat_ids_equal'] = [i['id'] for i in again['items']] == pages[2]['ids']
# 不同 per_page 的偏移
big = api('/logs', tok, dict(PARAMS, page=1, per_page=40))['data']
res['per_page40_first40_vs_page1'] = {'per_page40_head': [i['id'] for i in big['items']][:20] == pages[1]['ids'],
                                      'per_page40_tail20': [i['id'] for i in big['items']][20:40]}
res['first_last_times'] = {n: (pages[n]['times'][0], pages[n]['times'][-1]) for n in (1, 2, 3)}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print('WROTE', OUT)
print(json.dumps({k: res[k] for k in ('overlap_1_2', 'overlap_1_3', 'overlap_2_3', 'sorted_desc',
                                      'all_ids_unique_within', 'page2_repeat_ids_equal',
                                      'first_last_times', 'per_page40_first40_vs_page1')}, ensure_ascii=True)[:2500])
