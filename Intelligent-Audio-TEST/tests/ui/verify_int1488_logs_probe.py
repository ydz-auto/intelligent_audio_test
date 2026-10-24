# -*- coding: utf-8 -*-
"""INT-1488 探针：docker React 15173 + 真实库栈 15000 登录 /logs，看页面与真实请求。"""
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
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
API = os.environ.get('API_BASE', 'http://localhost:15000')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1488')

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || 'GET';
  const entry = { url: url, method: method, reqBody: init && init.body ? String(init.body) : null };
  try {
    const res = await __origFetch.apply(this, arguments);
    entry.status = res.status;
    const ct = res.headers.get('content-type') || '';
    if (ct.indexOf('json') !== -1) {
      try { entry.resBody = (await res.clone().text()).slice(0, 4000) } catch (e) {}
    }
    window.__fetchLog.push(entry);
    return res;
  } catch (e) {
    entry.error = String(e);
    window.__fetchLog.push(entry);
    throw e;
  }
};
"""


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if tuple(int(x) for x in ver.split('.') if x.isdigit())[0] == chrome_major:
                        drv_path = exe
                except Exception:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def body(drv):
    return drv.execute_script('return document.body.textContent || ""')


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    try:
        uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        print('no login form; url=', drv.current_url)
        return
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 30).until(
        lambda d: '/login' not in d.current_url or '欢迎' in body(d))
    time.sleep(2)
    print('login url:', drv.current_url)


def main():
    os.makedirs(ART, exist_ok=True)
    # 环境三次核对 #1
    health = json.loads(urllib.request.urlopen(API + '/health', timeout=10).read().decode())
    html = urllib.request.urlopen(BASE + '/', timeout=10).read().decode()
    print('HEALTH#1:', health)
    print('FRONT lib-react:', 'lib-react' in html)
    drv = _driver()
    try:
        login(drv)
        drv.get(BASE + '/logs')
        WebDriverWait(drv, 30).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
        time.sleep(2)
        rows = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
        print('rows:', len(rows))
        print('BODY:', body(drv)[:1500].replace('\n', ' | '))
        log = drv.execute_script('return window.__fetchLog || []')
        print('FETCH n=', len(log))
        for e in log:
            print(json.dumps(e, ensure_ascii=False)[:500])
        drv.save_screenshot(os.path.join(ART, 'probe_logs.png'))
        print('saved probe screenshot')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
