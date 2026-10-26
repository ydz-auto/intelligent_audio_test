# -*- coding: utf-8 -*-
"""INT-1316 残留扫描：登录后经页内 fetch 拉算法列表，确认本卡测试前缀记录已删净。"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://127.0.0.1:5316'


def _driver():
    options = Options()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
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
                except ValueError:
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    return webdriver.Chrome(options=options, service=service)


def main():
    drv = _driver()
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 15).until(lambda d: d.find_elements(By.ID, 'username'))
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
        time.sleep(2.0)
        script = """
            const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
            return fetch('/api/v1/algorithm/definitions', {
              method: 'GET',
              headers: { 'Authorization': 'Bearer ' + token, 'Accept': 'application/json' },
            }).then(async (r) => {
              let body = '';
              try { body = await r.text(); } catch (e) { body = ''; }
              return JSON.stringify({ status: r.status, body: body.slice(0, 200000) });
            });
        """
        res = json.loads(drv.execute_script(script))
        print('status', res['status'])
        body = res['body']
        if res['status'] != 200:
            print('body', body[:500])
            return 1
        data = json.loads(body)
        items = data.get('items') or data.get('data') or data.get('result') or []
        if isinstance(items, dict):
            items = items.get('items') or items.get('data') or []
        leftovers = []
        for it in items:
            t = str(it.get('type', ''))
            n = str(it.get('name', ''))
            if ('jxcs_bulk_int1316' in t or 'jxcs_recheck' in t
                    or '接线测试_INT1316' in n or 'INT1316复核' in n):
                leftovers.append((t, n))
        print('total definitions:', len(items))
        print('leftover test records:', len(leftovers))
        for t, n in leftovers:
            print('  LEFTOVER:', t, '|', n)
        return 1 if leftovers else 0
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
