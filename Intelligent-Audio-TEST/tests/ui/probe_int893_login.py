# -*- coding: utf-8 -*-
"""INT-893 probe: what does the login flow actually do under current gateway state."""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5312')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
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


def main():
    drv = _driver()
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 15).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1.5)
        drv.find_element(By.ID, 'username').send_keys('admin')
        drv.find_element(By.ID, 'password').send_keys('admin123')
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        time.sleep(6)
        print('URL:', drv.current_url)
        body = drv.execute_script('return document.body.textContent || ""')
        # toasts
        toasts = [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('TOASTS:', json.dumps(toasts, ensure_ascii=False))
        # find snippets around 登录失败/欢迎/网络/失败
        for key in ('欢迎回来', '登录失败', '网络异常', '加密校验失败', '服务器错误', 'Internal Server Error', '工作台', '登录'):
            if key in body:
                idx = body.find(key)
                print(f'BODY[{key}]: ...{body[max(0,idx-60):idx+80]!r}...')
        # network to /auth/login
        net = []
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])
                inner = msg.get('message', {})
                if inner.get('method') == 'Network.responseReceived':
                    url = inner.get('params', {}).get('response', {}).get('url', '')
                    if '/auth/login' in url or '/auth/encryption-key' in url or '/auth/me' in url:
                        net.append({
                            'url': url,
                            'status': inner.get('params', {}).get('response', {}).get('status'),
                        })
            except Exception:
                pass
        print('NETWORK:', json.dumps(net, ensure_ascii=False, indent=1))
        os.makedirs('tests/ui/artifacts/int893_probe', exist_ok=True)
        drv.save_screenshot('tests/ui/artifacts/int893_probe/login-failed.png')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
