# -*- coding: utf-8 -*-
"""INT-1229 5700 清理：登录提取 token → 删除「接线测试_INT1229_」测试 API（主库）。"""
import json, os, time, urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5310')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

def get_token():
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
    options.add_argument('--disable-background-networking')
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
        cands = []
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
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1.5)
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/dashboard' in d.current_url)
        time.sleep(1)
        token = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        return token
    finally:
        try: drv.quit()
        except Exception: pass

def call(port, path, method='GET', token=None, body=None):
    url = 'http://127.0.0.1:{}{}'.format(port, path)
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')

def main():
    token = get_token()
    print('token len:', len(token) if token else 0)
    if not token:
        print('NO TOKEN')
        return
    status, body = call(5700, '/api/v1/apis?per_page=200', 'GET', token=token)
    print('list status', status)
    try:
        items = json.loads(body).get('data', {}).get('items', [])
    except Exception as e:
        print('parse err', e, body[:200]); return
    mine = [i for i in items if '接线测试_INT1229' in (i.get('name') or '')]
    print('found test APIs:', len(mine))
    for i in mine:
        s, b = call(5700, '/api/v1/apis/{}'.format(i['id']), 'DELETE', token=token)
        print('delete', i['id'], repr(i['name']), '->', s, b[:100])

if __name__ == '__main__':
    main()
