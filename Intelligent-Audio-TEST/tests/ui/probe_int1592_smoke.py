# -*- coding: utf-8 -*-
"""INT-1592 冒烟：docker React 15173 打开 /tasks/cherry-picks，确认免登录与可选元素。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('INT1592_BASE', 'http://127.0.0.1:15173')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1592')
os.makedirs(ART, exist_ok=True)


def driver():
    o = Options()
    o.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--force-prefers-reduced-motion')
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
        same = [exe for ver, exe in cands if ver and ver[0] == major]
        if same:
            path = max(same)
    return webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())


d = driver()
try:
    d.get(BASE + '/tasks/cherry-picks')
    time.sleep(6)
    print('url:', d.current_url)
    body = d.find_element(By.TAG_NAME, 'body').text
    print('body:', body[:800])
    d.save_screenshot(os.path.join(ART, '00_smoke.png'))
finally:
    d.quit()
