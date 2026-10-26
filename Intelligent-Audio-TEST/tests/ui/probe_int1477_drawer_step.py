# -*- coding: utf-8 -*-
"""INT-1477 探针：抽屉「音频列表」步的步骤切换与「+ 添加音频」按钮定位。"""
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


d = driver()
try:
    d.get(BASE + '/')
    time.sleep(1.5)
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light');")
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    end = time.time() + 120
    while time.time() < end:
        b = d.find_element(By.TAG_NAME, 'body').text
        if '用例管理' in b and '没有找到符合条件的测试用例' not in b and '条' in b:
            break
        time.sleep(2)
    time.sleep(2)
    btn = find(d, '新增用例', 'button')
    jsclick(d, btn)
    time.sleep(3)
    print('--- dialog after open ---')
    for e in d.find_elements(By.XPATH, "//*[@role='dialog']"):
        if e.is_displayed():
            print('DIALOG cls=', (e.get_attribute('class') or '')[:80])
            print('  text[:300]=', e.text[:300].replace('\n', ' | '))
    print('--- step candidates (text 含 音频列表) ---')
    for e in d.find_elements(By.XPATH, "//*[contains(normalize-space(.),'音频列表')]"):
        if e.is_displayed() and (e.text or '').strip() == '音频列表':
            print('EL tag=', e.tag_name, 'role=', e.get_attribute('role'),
                  'cls=', (e.get_attribute('class') or '')[:60])
    el = find(d, '音频列表')
    print('clickable step:', el.tag_name if el is not None else None)
    if el is not None:
        jsclick(d, el)
        time.sleep(2)
    d.save_screenshot(os.path.join(ART, 'probe_audio_step.png'))
    print('--- buttons after step click ---')
    for b in d.find_elements(By.TAG_NAME, 'button'):
        t = (b.text or '').strip()
        a = b.get_attribute('aria-label')
        if (t or a) and b.is_displayed():
            print('BTN', repr(t), 'aria=', a, 'disabled=', b.get_attribute('disabled'))
finally:
    d.quit()
