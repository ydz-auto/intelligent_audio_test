# -*- coding: utf-8 -*-
"""INT-1701 登录流调试探针。"""
import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = 'http://localhost:15173'


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    opts = Options()
    opts.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    drv = webdriver.Chrome(options=opts, service=Service())
    try:
        drv.get(BASE + '/login')
        time.sleep(4)
        print('URL after load:', drv.current_url)
        print('inputs:', [i.get_attribute('id') for i in drv.find_elements(By.TAG_NAME, 'input')])
        print('buttons:', [(b.get_attribute('type'), b.text.strip()) for b in drv.find_elements(By.TAG_NAME, 'button')][:8])
        u = drv.find_element(By.ID, 'username')
        p = drv.find_element(By.ID, 'password')
        u.clear(); u.send_keys('接线测试_admin')
        p.clear(); p.send_keys('JieXianTest@2026')
        print('submit candidates:', len(drv.find_elements(By.CSS_SELECTOR, "button[type='submit']")))
        drv.execute_script('arguments[0].click()', drv.find_element(By.CSS_SELECTOR, "button[type='submit']"))
        for i in range(12):
            time.sleep(1)
            body = drv.execute_script('return document.body.innerText') or ''
            print(i + 1, 'url=', drv.current_url, '| text=', body[:140].replace('\n', ' | '))
            if '/login' not in drv.current_url:
                break
        print('console:', [e.get('message', '')[:200] for e in drv.get_log('browser')][:10])
        perf = []
        for e in drv.get_log('performance'):
            try:
                m = json.loads(e['message'])['message']
                if m.get('method') == 'Network.responseReceived':
                    r = m['params']['response']
                    if '/api/' in r.get('url', ''):
                        perf.append((r.get('status'), r.get('url')))
            except Exception:
                pass
        print('api:', perf)
        drv.save_screenshot('tests/ui/artifacts/int1701/debug_login.png')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
