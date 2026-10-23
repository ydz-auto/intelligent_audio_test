# -*- coding: utf-8 -*-
"""INT-1255 环境探针：确认 dev server 5311 + docker 后端 15000 链路 + AUTH_MODE=off 自动放行。"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
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
    drv.set_page_load_timeout(45)
    return drv


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2.0)


def _body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def run():
    drv = _driver()
    try:
        _goto(drv, '/')
        print('URL:', drv.current_url)
        print('TITLE:', drv.title)
        body = _body(drv)
        print('BODY (first 500):', body[:500].replace('\n', ' '))
        # 检查 dev_user 放行
        if 'dev_user' in body:
            print('DEV_USER: auto-authenticated as dev_user (AUTH_MODE=off)')
        # Network 检查 /auth/me
        try:
            for entry in drv.get_log('performance'):
                msg = json.loads(entry['message'])
                inner = msg.get('message', {})
                if inner.get('method') == 'Network.requestWillBeSent':
                    url = inner.get('params', {}).get('request', {}).get('url', '')
                    if '/api/' in url and 'localhost:15000' not in url:
                        print('API CALL:', inner.get('params', {}).get('request', {}).get('method'), url[:120])
        except Exception as e:
            print('perf log err:', e)

        # 尝试登录页
        _goto(drv, '/login')
        print('LOGIN URL:', drv.current_url)
        body = _body(drv)
        print('LOGIN BODY contains 登录:', '登录' in body)
        print('LOGIN BODY (first 300):', body[:300].replace('\n', ' '))
    except Exception as e:
        import traceback
        traceback.print_exc()
        drv.save_screenshot(os.path.join(os.path.dirname(__file__), 'artifacts', 'probe_int1255_fail.png'))
        return 1
    finally:
        try:
            drv.quit()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(run())
