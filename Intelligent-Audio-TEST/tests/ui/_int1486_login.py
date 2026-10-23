# -*- coding: utf-8 -*-
"""INT-1486 helper: UI login on 15173 -> dump token + verify business endpoints."""
import json, os, time, urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1486'
TOKEN_FILE = os.path.join(ART, 'token.txt')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
os.makedirs(ART, exist_ok=True)


def driver():
    o = Options(); o.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
              '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check']:
        o.add_argument(a)
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
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    return webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())


def get(path, token):
    r = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:300]


def main():
    d = driver()
    try:
        d.get(BASE + '/login')
        WebDriverWait(d, 30).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        d.find_element(By.ID, 'username').send_keys('接线测试_admin')
        d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(d, 30).until(lambda x: '/login' not in x.current_url)
        time.sleep(2)
        token = d.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        print('URL', d.current_url, 'token?', bool(token))
        open(TOKEN_FILE, 'w').write(token or '')
        for p in ['/api/v1/groups?page=1&per_page=200',
                  '/api/v1/testcases?page=1&per_page=5',
                  '/api/v1/tasks?page=1&per_page=5',
                  '/api/v1/apis?per_page=1000',
                  '/api/v1/test-devices?per_page=1000',
                  '/api/v1/laboratories']:
            st, body = get(p, token)
            try:
                j = json.loads(body)
                dd = j.get('data', j)
                n = len(dd.get('items', [])) if isinstance(dd, dict) else '?'
                tot = dd.get('total') if isinstance(dd, dict) else '?'
                print('GET', p, '->', st, 'items', n, 'total', tot)
            except Exception:
                print('GET', p, '->', st, body[:200])
    finally:
        d.quit()


if __name__ == '__main__':
    main()
