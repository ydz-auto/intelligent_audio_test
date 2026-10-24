# -*- coding: utf-8 -*-
"""INT-1478 探针：docker 真实栈前端 15173 是否可用、任务域页面真实数据渲染。"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1478_probe')
os.makedirs(ART, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def driver():
    o = Options()
    o.binary_location = CHROME
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1680,1050')
    o.add_argument('--no-sandbox')
    o.add_argument('--disable-gpu')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--user-data-dir=' + os.path.join(
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_probe_profile'))
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    drv_path = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                            'win64', '155.0.8059.84', 'chromedriver.exe')
    return webdriver.Chrome(service=Service(drv_path), options=o)


def api_calls(drv):
    out = []
    for m in drv.get_log('performance'):
        try:
            msg = json.loads(m['message'])['message']
        except Exception:
            continue
        if msg.get('method') == 'Network.requestWillBeSent':
            url = msg['params']['request']['url']
            if '/api/' in url:
                out.append(msg['params']['request']['method'] + ' ' + url)
    return out


def main():
    drv = driver()
    try:
        drv.get(BASE + '/tasks/daily')
        WebDriverWait(drv, 30).until(
            lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(6)
        print('URL:', drv.current_url)
        print('TITLE:', drv.title)
        drv.save_screenshot(os.path.join(ART, '01_tasks_daily.png'))
        body = drv.find_element(By.TAG_NAME, 'body').text
        print('BODY(len=%d):' % len(body))
        print(body[:1500])
        tabs = drv.find_elements(By.CSS_SELECTOR, '[role=tab]')
        print('TABS:', [t.text for t in tabs])
        print('API CALLS:')
        for c in dict.fromkeys(api_calls(drv)):
            print('  ', c)
        logs = [l for l in drv.get_log('browser') if l['level'] in ('SEVERE', 'WARNING')]
        print('BROWSER LOGS:', json.dumps(logs[:10], ensure_ascii=False))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
