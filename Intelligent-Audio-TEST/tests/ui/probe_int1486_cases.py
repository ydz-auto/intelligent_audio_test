# -*- coding: utf-8 -*-
"""INT-1486 探针 v3：抓 /testcases 实际请求与响应（patch 前置登记 + 响应体文本）。"""
import json, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_BASE', 'http://localhost:15173')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1486'
os.makedirs(ART, exist_ok=True)

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = function(input, init) {
  let url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = (init && init.method) || (input && input.method) || 'GET';
  const entry = { url: String(url), method: method, status: null, reqBody: init && init.body ? String(init.body).slice(0,2000) : null };
  window.__fetchLog.push(entry);
  return __origFetch.apply(this, arguments).then(async function(res) {
    entry.status = res.status;
    if (entry.url.indexOf('/testcases') !== -1) {
      try { entry.resBody = (await res.clone().text()).slice(0, 1500); } catch (e) {}
    }
    return res;
  }).catch(function(e) { entry.status = 'ERR ' + e; throw e; });
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
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-extensions')
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
                    if int([x for x in ver.split('.') if x.isdigit()][0]) == chrome_major:
                        drv_path = exe
                except (ValueError, IndexError):
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    try:
        uname = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        if '/login' not in drv.current_url:
            return drv.current_url
        raise
    uname.send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(
        lambda d: '/login' not in d.current_url or '欢迎' in (d.execute_script('return document.body.textContent || ""') or ''))
    time.sleep(2)
    return drv.current_url


def main():
    drv = _driver()
    try:
        print('LOGIN URL:', login(drv))
        print('algorithm storage:', drv.execute_script("return localStorage.getItem('iatp:algorithm:v1')"))
        drv.get(BASE + '/start-test')
        time.sleep(30)
        log = drv.execute_script('return window.__fetchLog || []')
        for it in log:
            if '/testcases' in it['url'] or '/groups' in it['url']:
                print('REQ', it['method'], it['status'], it['url'])
                if it.get('resBody'):
                    print('  RESP:', it['resBody'][:800])
        body = drv.execute_script('return document.body.innerText')
        print('empty-state?', '没有找到符合条件的测试用例' in body)
        with open(os.path.join(ART, 'probe3_body.txt'), 'w', encoding='utf-8') as f:
            f.write(body)
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
