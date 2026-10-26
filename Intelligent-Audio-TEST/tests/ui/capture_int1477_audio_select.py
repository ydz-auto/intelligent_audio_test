# -*- coding: utf-8 -*-
"""INT-1477 补拍：音频库选择弹窗（等到真实音频列表渲染后再截图）。

用例行 → 新增用例 → 音频列表 → 从音频库选择 → 等真实列表/分页 → 截图（浅/深）。
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
ART = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   'tests', 'ui', 'artifacts', 'int1477')
os.makedirs(ART, exist_ok=True)


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


def find(d, t, tag='*', exact=True):
    cond = f"normalize-space(.)='{t}'" if exact else f"contains(normalize-space(.),'{t}')"
    for e in d.find_elements(By.XPATH, f"//{tag}[{cond}]"):
        if e.is_displayed():
            return e
    return None


def click_text(d, t, tag='*', exact=True, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        e = find(d, t, tag, exact)
        if e:
            jsclick(d, e)
            return e
        time.sleep(0.4)
    raise AssertionError(f'未找到可点击元素: {t}')


def api_calls(d, needle='audios'):
    out = []
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
            if p['requestId'] in reqs:
                reqs[p['requestId']]['status'] = p['response']['status']
                reqs[p['requestId']]['end'] = p['timestamp']
    for v in reqs.values():
        if needle in v['u']:
            dur = (v['end'] - v['ts']) if v['end'] and v['ts'] else None
            out.append(f"{v['m']} {v['u'][:90]} -> {v['status']} {('%.1fs' % dur) if dur else ''}")
    return out


d = driver()
try:
    for theme in ('light', 'dark'):
        d.get(BASE + '/')
        time.sleep(1.2)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
        d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
        end = time.time() + 120
        while time.time() < end:
            b = d.find_element(By.TAG_NAME, 'body').text
            if '用例管理' in b and '没有找到符合条件的测试用例' not in b and '条' in b:
                break
            time.sleep(2)
        time.sleep(1.5)
        click_text(d, '新增用例', 'button')
        time.sleep(2.5)
        click_text(d, '音频列表', 'button')
        time.sleep(1.0)
        for label in ('+ 添加音频', '从音频库选择'):
            try:
                click_text(d, label, 'button', timeout=3)
                break
            except AssertionError:
                continue
        # 等真实音频列表：底部计数出现非 0 或出现分页/行
        t0 = time.time()
        rows = 0
        while time.time() - t0 < 90:
            b = d.find_element(By.TAG_NAME, 'body').text
            if '暂无可用的音频' in b or '暂无音频' in b:
                break
            if '当前页' in b and '个音频' in b:
                seg = b.split('当前页')[-1][:40]
                if not seg.startswith(' 0 '):
                    rows = 1
                    break
            time.sleep(1.5)
        time.sleep(1.5)
        p = os.path.join(ART, f'02_audio_select_{theme}.png')
        d.save_screenshot(p)
        print(theme, 'waited %.1fs' % (time.time() - t0), 'rows_seen=', rows, 'shot=', p, flush=True)
        for line in api_calls(d):
            print('   ', line)
        body = d.find_element(By.TAG_NAME, 'body').text
        print('   tail[:300]=', body[-300:].replace('\n', ' | '))
finally:
    d.quit()
