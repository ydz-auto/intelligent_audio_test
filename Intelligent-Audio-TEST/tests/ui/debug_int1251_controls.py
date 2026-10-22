# -*- coding: utf-8 -*-
"""INT-1251 debug: API drawer + batch checkbox controls."""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5307')
ART = os.path.join('tests', 'ui', 'artifacts', 'int1251')
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
    return webdriver.Chrome(options=options, service=service)


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        # ===== API tab =====
        drv.get(BASE + '/devices/api')
        time.sleep(6)
        print('=== API TAB BUTTONS ===')
        for b in drv.find_elements(By.XPATH, "//button"):
            t = (b.text or '').strip().replace('\n', '|')
            if t:
                print(repr(t))
        # open add API
        add = None
        for b in drv.find_elements(By.XPATH, "//button"):
            if b.text.strip().startswith('添加测试API'):
                add = b
        if add:
            print('click add API btn:', repr(add.text))
            drv.execute_script('arguments[0].click()', add)
            time.sleep(2.5)
            dialogs = drv.find_elements(By.XPATH, "//div[@role='dialog']")
            print('dialogs:', len(dialogs))
            if dialogs:
                print('drawer text sample:', dialogs[0].text[:500])
                # find all labels and inputs
                labels = [l.text for l in drv.find_elements(By.XPATH, "//div[@role='dialog']//label")]
                print('LABELS:', labels)
                # inputs
                inputs = drv.find_elements(By.XPATH, "//div[@role='dialog']//input")
                print('INPUT placeholder:', [i.get_attribute('placeholder') for i in inputs])
                drv.save_screenshot(os.path.join(ART, 'api-drawer-debug.png'))
        # ===== test tab checkbox =====
        drv.get(BASE + '/devices/test')
        time.sleep(5)
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        if rows:
            r0 = rows[0]
            print('=== ROW0 HTML snippet ===')
            print(r0.get_attribute('outerHTML')[:1200])
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()