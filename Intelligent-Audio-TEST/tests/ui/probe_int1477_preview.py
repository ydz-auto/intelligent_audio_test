# -*- coding: utf-8 -*-
"""INT-1477 探针：分组展开与「预览音频」入口现状（真实栈 15173）。"""
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
    d.set_page_load_timeout(60)
    return d


def jsclick(d, el):
    d.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)


d = driver()
try:
    d.get(BASE + '/')
    time.sleep(2)
    d.get(BASE + '/testcases/by-group?rw=%d' % int(time.time()))
    end = time.time() + 60
    while time.time() < end:
        b = d.find_element(By.TAG_NAME, 'body').text
        if '用例管理' in b and '导出' in b:
            break
        time.sleep(1)
    time.sleep(2)
    for i in range(5):
        els = [e for e in d.find_elements(By.XPATH, "//button[contains(normalize-space(.),'加载更多')]") if e.is_displayed()]
        if not els:
            break
        jsclick(d, els[0])
        time.sleep(1.5)
    body = d.find_element(By.TAG_NAME, 'body').text
    print('PAGE TEXT[:800]:', body[:800].replace('\n', ' | '))
    print('--- group spans ---')
    for e in d.find_elements(By.TAG_NAME, 'span'):
        t = (e.text or '').strip()
        if t == '音频上传生成':
            print('SPAN', e.get_attribute('class'))
            par = e
            for _ in range(5):
                par = par.find_element(By.XPATH, '..')
                print('  PARENT tag=', par.tag_name, 'role=', par.get_attribute('role'),
                      'cls=', (par.get_attribute('class') or '')[:80])
    print('--- click span ---')
    el = None
    for e in d.find_elements(By.XPATH, "//span[normalize-space(.)='音频上传生成']"):
        if e.is_displayed():
            el = e
            break
    if el is None:
        print('NO SPAN')
    else:
        jsclick(d, el)
        time.sleep(3)
        print('after click, body has 预览音频:', '预览音频' in d.find_element(By.TAG_NAME, 'body').text)
        for b in d.find_elements(By.TAG_NAME, 'button'):
            a = b.get_attribute('aria-label')
            t = (b.text or '').strip()
            if a or t:
                print('BTN', repr(t), 'aria=', a, 'vis=', b.is_displayed(), 'disabled=', b.get_attribute('disabled'))
    print('--- aria buttons count ---')
    print('预览音频 total', len(d.find_elements(By.XPATH, "//button[@aria-label='预览音频']")))
finally:
    d.quit()
