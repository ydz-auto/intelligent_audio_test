# -*- coding: utf-8 -*-
"""INT-1931 补帧：日志维护归档小节深色帧（等设置页真正加载完再截）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15241')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1931')

o = Options()
o.binary_location = CHROME
o.add_argument('--headless=new')
o.add_argument('--window-size=1680,1200')
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
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
    d.get(BASE + '/system-settings/operations/log-maintenance')
    WebDriverWait(d, 60).until(lambda x: '归档管理' in (x.find_element(By.TAG_NAME, 'body').text or ''))
    WebDriverWait(d, 40).until(lambda x: '归档状态' in (x.find_element(By.TAG_NAME, 'body').text or ''))
    time.sleep(2.5)
    t = d.find_element(By.TAG_NAME, 'body').text or ''
    info = {'has_archive': '归档管理' in t, 'has_status': '归档状态' in t,
            'has_list': '归档列表' in t, 'cls': d.execute_script('return document.documentElement.className'),
            'bundle': d.execute_script("return Array.from(document.querySelectorAll('script[src]')).map(s=>s.getAttribute('src')).join(',')"),
            'snippet': t[t.find('归档管理'):t.find('归档管理') + 200]}
    path = os.path.join(ART, 'shots', 'i4_archive_dark.png')
    d.save_screenshot(path)
    info['size'] = os.path.getsize(path)
    print(json.dumps(info, ensure_ascii=True))
finally:
    d.quit()
