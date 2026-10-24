# -*- coding: utf-8 -*-
"""INT-1478 探针2：诊断 15173 白屏原因（JS 错误 / 资源加载 / 路由）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15173')
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
        os.environ.get('TEMP', r'C:\Windows\Temp'), 'int1478_profile'))
    o.add_argument('--remote-debugging-port=0')
    o.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    drv_path = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver',
                            'win64', '155.0.8059.84', 'chromedriver.exe')
    return webdriver.Chrome(service=Service(drv_path), options=o)


def main():
    drv = driver()
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': """
            window.__errs = [];
            window.addEventListener('error', function(e){ window.__errs.push(String(e.message)+' @ '+String(e.filename)+':'+e.lineno); });
            window.addEventListener('unhandledrejection', function(e){ window.__errs.push('rejection: '+String(e.reason)); });
        """})
        drv.get(BASE + '/tasks/daily')
        time.sleep(8)
        print('errs:', drv.execute_script('return window.__errs'))
        print('rootHTML:', drv.execute_script("return document.getElementById('root').innerHTML.length"))
        print('bodyText:', repr(drv.execute_script('return document.body.innerText')[:300]))
        print('scripts:', drv.execute_script(
            "return Array.from(document.scripts).map(s=>s.src+'|'+(s.readyState||''))"))
        print('localStorage:', drv.execute_script(
            "return JSON.stringify(Object.fromEntries(Object.entries(localStorage)))")[:600])
        print('browser logs:')
        for l in drv.get_log('browser'):
            print('  ', l['level'], l['message'][:300])
        print('failed resources:')
        for m in drv.get_log('performance'):
            try:
                msg = json.loads(m['message'])['message']
            except Exception:
                continue
            if msg.get('method') == 'Network.loadingFailed':
                print('  FAIL', msg['params'].get('requestId'), msg['params'].get('errorText'))
            if msg.get('method') == 'Network.responseReceived':
                r = msg['params']['response']
                if r['status'] >= 400:
                    print('  HTTP', r['status'], r['url'][:120])
        print('requests:')
        seen = []
        for m in drv.get_log('performance'):
            try:
                msg = json.loads(m['message'])['message']
            except Exception:
                continue
            if msg.get('method') == 'Network.requestWillBeSent':
                u = msg['params']['request']['url']
                if u.startswith(BASE):
                    seen.append(u.replace(BASE, ''))
        for s in dict.fromkeys(seen):
            print('  ', s[:140])
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
