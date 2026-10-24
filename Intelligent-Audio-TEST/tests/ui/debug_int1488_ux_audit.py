# -*- coding: utf-8 -*-
"""INT-1488 审计调试：诊断 15173 登录/首页加载。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1488_ux_audit')


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    for ver in os.listdir(cache):
        exe = os.path.join(cache, ver, 'chromedriver.exe')
        if os.path.isfile(exe) and ver.startswith('155'):
            path = exe
    return webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())


d = driver()
try:
    d.get(BASE + '/login')
    time.sleep(6)
    print('URL', d.current_url)
    print('TITLE', d.title)
    print('BODY', d.find_element(By.TAG_NAME, 'body').text[:400].encode('ascii', 'replace').decode())
    print('INPUTS', [(e.get_attribute('id'), e.get_attribute('type')) for e in d.find_elements(By.TAG_NAME, 'input')])
    print('LS', d.execute_script("return JSON.stringify(Object.keys(localStorage).map(k=>[k,(localStorage.getItem(k)||'').slice(0,20)]))"))
    print('HTML_LEN', len(d.page_source))
    d.save_screenshot(os.path.join(ART, 'dbg_login.png'))
    d.get(BASE + '/logs')
    time.sleep(6)
    print('URL2', d.current_url)
    print('BODY2', d.find_element(By.TAG_NAME, 'body').text[:400].encode('ascii', 'replace').decode())
    d.save_screenshot(os.path.join(ART, 'dbg_logs.png'))
    print('CONSOLE')
    for e in d.get_log('browser'):
        if e.get('level') in ('SEVERE', 'WARNING'):
            print(' ', e['level'], e['message'][:300].encode('ascii', 'replace').decode())
finally:
    d.quit()
print('DBG_DONE')
