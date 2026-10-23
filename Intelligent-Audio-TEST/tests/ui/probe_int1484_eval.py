# -*- coding: utf-8 -*-
"""INT-1484 探针：登录真实库栈前端(15173) → 取 token → 直读评估域接口，落 JSON。"""
import json, os, time, urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
os.makedirs(ART, exist_ok=True)


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
                    if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major:
                        drv_path = exe
                except ValueError:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    uname = WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, 'username')))
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)


def api_get(token, path):
    req = urllib.request.Request(API + '/api/v1' + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def main():
    drv = _driver()
    try:
        login(drv)
        token = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        print('token:', (token or '')[:30], 'len', len(token or ''))
        out = {}
        dims = api_get(token, '/evaluation/dimensions?per_page=1000')
        cats = api_get(token, '/evaluation/categories?per_page=100')
        algos = api_get(token, '/algorithm/options')
        out['dimensions'] = dims
        out['categories'] = cats
        out['algorithm_options'] = algos
        with open(os.path.join(ART, 'api_baseline.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        items = (dims.get('data') or {}).get('items') or dims.get('items') or []
        print('dimensions:', len(items), 'categories:', len((cats.get('data') or {}).get('items') or cats.get('items') or []))
        print('top keys:', list(dims.keys()))
        for it in items[:5]:
            print(' dim', it.get('id'), it.get('name'), 'type=', it.get('dimension_type'), 'cat=', it.get('category_id'), 'status=', it.get('status'))
        with open(os.path.join(ART, 'token.txt'), 'w', encoding='utf-8') as f:
            f.write(token or '')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
