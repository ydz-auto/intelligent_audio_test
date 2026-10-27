# -*- coding: utf-8 -*-
"""INT-2090 explore: login to dev server (proxy->docker 15000) and find reports whose
case audios / result audio fields have long audio names."""
import json
import os
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5388')
ART = r'D:\00_user_data\multica_workspaces\intelligent-95ba6a12369f\int-2090-93d04ec988e4\worktree\_int2090'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
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
    drv.set_page_load_timeout(45)
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="username"], input[type="text"]'))
    )
    inputs = drv.find_elements(By.CSS_SELECTOR, 'input')
    # fill username + password
    user = None
    pwd = None
    for inp in inputs:
        t = inp.get_attribute('type') or ''
        name = inp.get_attribute('name') or ''
        if 'password' in t:
            pwd = inp
        elif user is None and 'user' in name or (user is None and t in ('text', 'email', 'string')):
            user = inp
    if user is None and len(inputs) > 0:
        user = inputs[0]
    user.send_keys('admin')
    pwd.send_keys('admin123')
    btns = drv.find_elements(By.CSS_SELECTOR, 'button[type="submit"], button')
    clicked = False
    for b in btns:
        if '登录' in (b.text or '').replace(' ', ''):
            b.click()
            clicked = True
            break
    if not clicked and btns:
        btns[-1].click()
    time.sleep(3)
    token = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1') || ''")
    return token


def fetch_json(drv, path):
    """In-page fetch through dev proxy (same-origin /api), with Bearer token."""
    return drv.execute_script(
        "const t = localStorage.getItem('iatp:auth:token:v1') || '';"
        "return window.fetch(arguments[0], {headers: {'Accept':'application/json', 'Authorization':'Bearer ' + t}})"
        ".then(r => r.ok ? r.json() : Promise.reject(r.status)).catch(e => ({__err: String(e)}))",
        path,
    )


def main():
    drv = _driver()
    try:
        token = login(drv)
        print('TOKEN len:', len(token))
        if not token:
            drv.save_screenshot(os.path.join(ART, 'login_fail.png'))
            return
        # reports list
        data = fetch_json(drv, '/api/v1/reports?page=1&page_size=50&status=published')
        if isinstance(data, dict) and '__err' in data:
            print('REPORTS ERR', data)
        else:
            items = data.get('items') or data.get('data') or []
            print('reports count:', len(items))
            for r in items[:20]:
                print(r.get('id'), '|', (r.get('name') or '')[:40], '|', r.get('status'), '| task', r.get('task_id'))
        # task detail for a recent task to see result_audios names length
        for tid in (701, 702, 677, 670):
            d = fetch_json(drv, f'/api/v1/tasks/{tid}/detail')
            if isinstance(d, dict) and '__err' not in d:
                cases = d.get('cases') or []
                print(f'TASK {tid}: name={d.get("name")} cases={len(cases)}')
                for c in cases[:5]:
                    print('   case', c.get('case_id'), (c.get('name') or '')[:40])
                break
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
