# -*- coding: utf-8 -*-
"""INT-1486 探针 v2：登录 15173 → /start-test → 等列表加载完成 → 页面状态 + 计数（token 直连 15000）"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = 'http://127.0.0.1:15000'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1486'
os.makedirs(ART, exist_ok=True)

import urllib.request


def api_get(path, token):
    req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read().decode('utf-8'))


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in ver.split('.') if x.isdigit()][0]) == chrome_major:
                        drv_path = exe
                except (ValueError, IndexError):
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    try:
        uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        if '/login' not in drv.current_url:
            return drv.current_url
        raise
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(
        lambda d: '/login' not in d.current_url or '欢迎' in (d.execute_script('return document.body.textContent || ""') or ''))
    time.sleep(2)
    return drv.current_url


def main():
    drv = _driver()
    try:
        print('LOGIN URL:', login(drv))
        token = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        print('token?', bool(token))
        drv.get(BASE + '/start-test')
        # 等列表加载（skeleton 消失）
        for i in range(40):
            time.sleep(3)
            sk = drv.find_elements(By.CSS_SELECTOR, '[data-slot="skeleton"], .animate-pulse')
            txt = drv.execute_script('return document.body.innerText') or ''
            if '加载更多' in txt or '暂无' in txt or len(sk) == 0:
                print('loaded after', (i + 1) * 3, 's; skeleton=', len(sk))
                break
        body = drv.execute_script('return document.body.innerText')
        print('=== BODY (first 3000) ===')
        print(body[:3000])
        with open(os.path.join(ART, 'probe_body.txt'), 'w', encoding='utf-8') as f:
            f.write(body)
        drv.save_screenshot(os.path.join(ART, 'probe_starttest.png'))
        for path in [
            '/api/v1/groups?page=1&per_page=200',
            '/api/v1/testcases?page=1&per_page=200',
            '/api/v1/test-devices?per_page=1000',
            '/api/v1/apis?per_page=1000',
            '/api/v1/laboratories',
        ]:
            try:
                st, data = api_get(path, token)
                d = data.get('data') if isinstance(data, dict) and isinstance(data.get('data'), dict) else data
                items = d.get('items') or []
                print('API', path, st, 'items=', len(items) if isinstance(items, list) else type(items),
                      'total=', d.get('total'))
            except Exception as e:
                print('API', path, 'ERR', e)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
