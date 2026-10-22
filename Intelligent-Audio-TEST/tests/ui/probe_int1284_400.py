# -*- coding: utf-8 -*-
"""INT-1284 probe: capture /testcases 400 response body on /start-test."""
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
    options.add_argument('--window-size=1200,900')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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
        drv.get_log('performance')  # drain
        drv.get(BASE + '/start-test?step=0&view=table')
        time.sleep(12)
        found = []
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                params = (msg.get('message') or {}).get('params') or {}
                method = (msg.get('message') or {}).get('method') or ''
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                r = params.get('request') or {}
                url = r.get('url', '')
                if '/testcases' in url and 'api/v1' in url:
                    found.append({'rid': params.get('requestId'), 'url': url, 'status': None, 'body': None})
            elif method == 'Network.responseReceived':
                for f in found:
                    if f['rid'] == params.get('requestId'):
                        f['status'] = (params.get('response') or {}).get('status')
        for f in found:
            try:
                resp = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': f['rid']})
                f['body'] = resp.get('body', '')[:600]
            except Exception:
                pass
        with open(os.path.join(OUT, 'probe-400.txt'), 'w', encoding='utf-8') as fo:
            fo.write(json.dumps(found, ensure_ascii=False, indent=1))
        print(json.dumps(found, ensure_ascii=False, indent=1)[:2500])
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
