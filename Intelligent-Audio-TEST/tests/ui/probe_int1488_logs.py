# -*- coding: utf-8 -*-
"""INT-1488 快速探针：登录后 /logs 是否出数（含接口状态）。"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:15173'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def drv():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.page_load_strategy = 'eager'
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    p = ''
    for v in os.listdir(cache):
        e = os.path.join(cache, v, 'chromedriver.exe')
        if os.path.isfile(e) and v.startswith('155'):
            p = e
    return webdriver.Chrome(options=o, service=Service(executable_path=p) if p else Service())


d = drv()
try:
    d.get(BASE + '/login')
    time.sleep(2)
    if '/login' not in d.current_url:
        d.get(BASE + '/login')
        time.sleep(2)
    WebDriverWait(d, 45).until(lambda x: x.find_elements(By.ID, 'username'))
    d.find_element(By.ID, 'username').send_keys('接线测试_admin')
    d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(5)
    print('TOKEN', bool(d.execute_script("return localStorage.getItem('iatp:auth:token:v1')")), flush=True)
    d.get(BASE + '/logs')
    time.sleep(12)
    body = d.find_element(By.TAG_NAME, 'body').text
    print('ROWS', len(d.find_elements(By.CSS_SELECTOR, 'table tbody tr')), flush=True)
    print('FOOTER', [l for l in body.split('\n') if '条日志' in l], flush=True)
    out = d.execute_async_script(
        "const cb=arguments[arguments.length-1];"
        "const t=localStorage.getItem('iatp:auth:token:v1');"
        "fetch('http://127.0.0.1:15000/api/v1/logs?page=1&per_page=20',{headers:{Authorization:'Bearer '+t}})"
        ".then(r=>r.text().then(x=>cb({s:r.status,b:x.slice(0,300)}))).catch(e=>cb({s:-1,b:String(e)}));")
    print('API', out, flush=True)
    d.save_screenshot(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1488_ux_audit', 'probe_logs.png'))
finally:
    d.quit()
print('PROBE_DONE', flush=True)
