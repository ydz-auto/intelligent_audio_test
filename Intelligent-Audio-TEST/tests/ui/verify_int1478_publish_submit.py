# -*- coding: utf-8 -*-
"""INT-1478 发布弹窗提交（等待来源任务加载 → 显式选择 → 提交 → 回读）。"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse

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
name = '接线测试_INT1478_发布_%s' % time.strftime('%H%M%S')
out = {}


def api(p):
    return json.loads(urllib.request.urlopen(BACK + p, timeout=180).read().decode())


def js(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    d.execute_script('arguments[0].click();', el)


o = Options()
o.binary_location = CHROME
o.add_argument('--headless=new')
o.add_argument('--window-size=1680,1050')
o.add_argument('--no-sandbox')
o.add_argument('--disable-gpu')
o.add_argument('--lang=zh-CN')
o.add_argument('--user-data-dir=' + os.path.join(os.environ.get('TEMP', r'C:\Windows\Temp'),
                                                 'int1478_pub_probe3'))
o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
d = webdriver.Chrome(service=Service(DRIVER), options=o)
d.set_page_load_timeout(120)
d.set_script_timeout(60)
try:
    d.get(BASE + '/tasks/daily')
    time.sleep(8)
    box = d.find_elements(By.CSS_SELECTOR, 'input[placeholder*="搜索任务名称"]')[0]
    d.execute_script('arguments[0].click()', box)
    box.send_keys(Keys.CONTROL, 'a')
    box.send_keys(Keys.DELETE)
    box.send_keys('接线测试_INT1478')
    time.sleep(1.0)
    for b in d.find_elements(By.CSS_SELECTOR, 'button'):
        if b.text.strip() == '查询' and b.is_displayed():
            js(d, b)
            break
    trig = None
    end = time.time() + 60
    while time.time() < end:
        els = [e for e in d.find_elements(By.CSS_SELECTOR, 'button[aria-label="任务操作"]') if e.is_displayed()]
        if els:
            trig = els[0]
            break
        time.sleep(1.5)
    assert trig is not None, '任务行 60s 未出现'
    time.sleep(0.5)
    js(d, trig)
    time.sleep(0.6)
    for it in d.find_elements(By.CSS_SELECTOR, '*[role=menuitem]'):
        if it.text.strip() == '发布':
            js(d, it)
            break
    time.sleep(2)
    st = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=dialog] [aria-label="选择来源任务"]') if e.is_displayed()]
    assert st, '未找到来源任务选择器'
    # 等来源任务列表加载完（加载中… 消失）——后端 /tasks per_page=100 偶发极慢
    opts = []
    end = time.time() + 150
    while time.time() < end:
        js(d, st[0])
        time.sleep(2)
        opts = [o for o in d.find_elements(By.CSS_SELECTOR, '*[role=option]') if o.is_displayed()]
        texts = [x.text.strip() for x in opts]
        if texts and not (len(texts) == 1 and '加载中' in texts[0]):
            shot = os.path.join(ART, '05_publish_options_light.png')
            d.save_screenshot(shot)
            out['option_count'] = len(texts)
            out['option_sample'] = texts[:5]
            break
        # 关下拉再试
        d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(2)
    assert opts, '来源任务列表 150s 未加载'
    target = None
    for x in opts:
        if '接线测试_INT1478' in x.text:
            target = x
            break
    assert target is not None, '选项中没有接线测试任务'
    js(d, target)
    time.sleep(1.5)
    inp = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=dialog] input[placeholder*="发布后展示"]') if e.is_displayed()][0]
    js(d, inp)
    inp.send_keys(Keys.CONTROL, 'a')
    inp.send_keys(Keys.DELETE)
    inp.send_keys(name)
    time.sleep(0.8)
    btn = None
    for b in d.find_elements(By.CSS_SELECTOR, '[role=dialog] button'):
        if b.text.strip() == '发布' and b.is_displayed():
            btn = b
    out['btn_enabled'] = btn.is_enabled() if btn else None
    d.save_screenshot(os.path.join(ART, '05b_publish_filled_light.png'))
    mark = len(d.get_log('performance'))
    js(d, btn)
    time.sleep(8)
    reqs = []
    for m in d.get_log('performance')[mark:]:
        msg = json.loads(m['message'])['message']
        if msg.get('method') == 'Network.requestWillBeSent':
            r = msg['params']['request']
            if '/api/' in r['url'] and r['method'] != 'GET':
                reqs.append({'method': r['method'], 'url': r['url'].replace(BASE, ''),
                             'post': (r.get('postData') or '')[:400]})
        if msg.get('method') == 'Network.responseReceived':
            r = msg['params']['response']
            if '/api/published-tasks' in r['url'] and r['status']:
                reqs.append({'status': r['status'], 'url': r['url'].replace(BASE, '')})
    out['submit_requests'] = reqs
    out['toasts'] = [t.text for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
    hits = [p for p in api('/api/v1/published-tasks?page=1&per_page=50&keyword=' + urllib.parse.quote('INT1478_发布'))['data']['items'] if name in p['name']]
    out['readback'] = [{'id': p['id'], 'name': p['name'], 'version': p.get('version')} for p in hits]
    if hits:
        det = api('/api/v1/published-tasks/%d' % hits[0]['id'])['data']
        out['roundtrip'] = {'name': det.get('name'), 'status': det.get('status'),
                            'source_task_id': det.get('source_task_id'),
                            'snapshot_keys': list((det.get('snapshot_config') or {}).keys())[:8]}
    out['name'] = name
finally:
    with open(os.path.join(ART, 'publish_probe.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    d.quit()
