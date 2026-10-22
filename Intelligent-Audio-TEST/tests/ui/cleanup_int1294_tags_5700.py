# -*- coding: utf-8 -*-
"""清理 INT-1294 复测遗留的临时分类（24/25，来自前两轮失败的 capture 脚本）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5396')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)


def api_call(drv, method, path, payload=None):
    body_js = ('JSON.stringify(%s)' % json.dumps(payload)) if payload is not None else 'undefined'
    return drv.execute_script('''
      const token = localStorage.getItem('iatp:auth:token:v1');
      const body = %s;
      return fetch('%s', {
        method: '%s',
        headers: {'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : ''},
        body: body
      }).then(async r => {
        let d = null;
        try { d = await r.json(); } catch (e) {}
        return {status: r.status, data: d};
      });
    ''' % (body_js, path, method))


def main():
    drv = _driver()
    try:
        login(drv)
        # 只清理本卡（INT-1294）复测自建数据：名称精确含 INT1294 / PROBE，不动其他卡
        cats = api_call(drv, 'GET', '/api/v1/tags/categories?page=1&per_page=100')
        items = ((cats.get('data') or {}).get('data') or {}).get('items', [])
        for c in items:
            name = (c.get('name') or '')
            print('CAT', c.get('id'), name)
            if 'INT1294' in name or 'PROBE' in name:
                r = api_call(drv, 'DELETE', '/api/v1/tags/categories/%s' % c['id'])
                print('  cleanup cat', c['id'], json.dumps(r, ensure_ascii=False)[:120])
        # 标签（cascade 删标签下用例；仅本卡数据）
        tags = api_call(drv, 'GET', '/api/v1/tags?page=1&per_page=100')
        items = ((tags.get('data') or {}).get('data') or {}).get('items', [])
        for t in items:
            name = (t.get('name') or '')
            if 'INT1294' in name or 'PROBE' in name:
                print('TAG', t.get('id'), name)
                r = api_call(drv, 'DELETE', '/api/v1/tags/%s?cascade=true' % t['id'])
                print('  cleanup tag', t.get('id'), json.dumps(r, ensure_ascii=False)[:120])
        # 再查一次
        cats2 = api_call(drv, 'GET', '/api/v1/tags/categories?page=1&per_page=100')
        items2 = ((cats2.get('data') or {}).get('data') or {}).get('items', [])
        print('REMAINING CATS:', [c.get('name') for c in items2])
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
