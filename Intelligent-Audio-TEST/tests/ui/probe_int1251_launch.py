# -*- coding: utf-8 -*-
"""INT-1251 probe: launch app, check login experience and device page load under AUTH_MODE=off."""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5307')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
    drv.set_page_load_timeout(60)
    return drv


def main():
    drv = _driver()
    try:
        # go straight to /login
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        print('URL after /login:', drv.current_url)
        body = drv.execute_script('return document.body.textContent || ""')
        print('BODY contains 开放模式:', '开放模式' in body)
        print('BODY contains 进入工作台:', '进入工作台' in body)
        # go to dashboard directly (off mode auto-auth)
        drv.get(BASE + '/dashboard')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(4)
        print('URL after /dashboard:', drv.current_url)
        body2 = drv.execute_script('return document.body.textContent || ""')
        print('BODY has 工作台 nav:', '工作台' in body2)
        # devices page
        drv.get(BASE + '/devices/test')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(5)
        print('URL after /devices/test:', drv.current_url)
        body3 = drv.execute_script('return document.body.textContent || ""')
        print('BODY has 设备管理:', '设备管理' in body3)
        print('BODY has 添加设备:', '添加' in body3)
        print('BODY sample:', body3[:300])
        os.makedirs('tests/ui/artifacts/int1251', exist_ok=True)
        drv.save_screenshot('tests/ui/artifacts/int1251/probe-devices.png')
        # network summary
        net = []
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])
                inner = msg.get('message', {})
                if inner.get('method') == 'Network.responseReceived':
                    url = inner.get('params', {}).get('response', {}).get('url', '')
                    status = inner.get('params', {}).get('response', {}).get('status')
                    net.append((url, status))
            except Exception:
                pass
        api_calls = [(u, s) for u, s in net if '/api/' in u and 'socket.io' not in u]
        print('API calls:', len(api_calls))
        for u, s in api_calls[:20]:
            print(' ', s, u)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
