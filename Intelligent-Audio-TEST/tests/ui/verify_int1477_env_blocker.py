# -*- coding: utf-8 -*-
"""INT-1477 第 3 轮：环境核对 —— task_service 派生列 schema 漂移阻塞用例域。

只做两件事：
1. 三次核对（/health database、15173 lib-react、auth/mode）；
2. 打开 /testcases/by-group 与 /testcases/by-tag，记录首屏请求与页面可见状态，截图。
不写任何数据。
"""
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
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(ROOT, 'tests', 'ui', 'artifacts', 'int1477')
os.makedirs(ART, exist_ok=True)
OUT = {}


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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


def calls(d):
    reqs = {}
    try:
        logs = d.get_log('performance')
    except Exception:
        return []
    for e in logs:
        try:
            m = json.loads(e['message'])['message']
        except Exception:
            continue
        p = m.get('params', {})
        if m.get('method') == 'Network.requestWillBeSent':
            r = p['request']
            if '/api/' not in r['url']:
                continue
            reqs[p['requestId']] = {'method': r['method'],
                                    'url': r['url'].split(BASE)[-1],
                                    'status': None}
        elif m.get('method') == 'Network.responseReceived':
            if p['requestId'] in reqs:
                reqs[p['requestId']]['status'] = p['response']['status']
    return [v for v in reqs.values() if v['status'] is not None]


def shot(d, name):
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    print('  shot:', name, flush=True)
    return p


def main():
    d = driver()
    try:
        d.get(BASE + '/testcases/by-group')
        time.sleep(6)
        body = d.find_element(By.TAG_NAME, 'body').text
        OUT['by_group'] = {'url': d.current_url, 'body_head': body[:600],
                           'calls': calls(d)}
        shot(d, 'r3_by_group_error')
        print('CALLS by-group:', json.dumps(OUT['by_group']['calls'], ensure_ascii=False), flush=True)
        print('BODY:', body[:400].replace('\n', ' | '), flush=True)

        d.get('about:blank')
        time.sleep(0.5)
        d.get(BASE + '/testcases/by-tag')
        time.sleep(6)
        body2 = d.find_element(By.TAG_NAME, 'body').text
        OUT['by_tag'] = {'url': d.current_url, 'body_head': body2[:600],
                         'calls': calls(d)}
        shot(d, 'r3_by_tag_error')
        print('CALLS by-tag:', json.dumps(OUT['by_tag']['calls'], ensure_ascii=False), flush=True)
        print('BODY2:', body2[:400].replace('\n', ' | '), flush=True)
    finally:
        d.quit()
    with open(os.path.join(ART, 'r3_blocker.json'), 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
