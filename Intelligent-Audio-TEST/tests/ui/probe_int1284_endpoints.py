# -*- coding: utf-8 -*-
"""Probe /testcases endpoint variants from logged-in browser."""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5304'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1284_grouped')
os.makedirs(OUT, exist_ok=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\\Google\\Chrome\\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    cands = []
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    return webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())


def main():
    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1)
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(drv, 20).until(lambda d: '/dashboard' in d.current_url)
        time.sleep(2)
        # 需要带 auth header 才能 fetch —— 从 localStorage 取 token
        probe = drv.execute_script('''
          const results = [];
          const token = localStorage.getItem('iatp:auth:token:v1');
          const h = token ? { 'Authorization': 'Bearer ' + token } : {};
          const urls = [
            '/api/v1/testcases?page=1&per_page=100',
            '/api/v1/testcases?page=1&per_page=100&algorithm_type=',
            '/api/v1/testcases?page=1&per_page=100&algorithm_type=voice_llm',
            '/api/v1/groups?page=1&per_page=200',
          ];
          return Promise.all(urls.map(url =>
            fetch(url, { headers: h }).then(async r => ({
              url, status: r.status,
              body: (await r.text()).slice(0, 300),
            })).catch(e => ({ url, status: 'ERR', body: String(e) }))
          )).then(res => ({ res, token }));
        ''')
        with open(os.path.join(OUT, 'probe-endpoints.txt'), 'w', encoding='utf-8') as f:
            f.write(json.dumps(probe, ensure_ascii=False, indent=1))
        print(json.dumps(probe.get('res', []), ensure_ascii=False, indent=1)[:2000])
        print('token found:', bool(probe.get('token')))
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
