# -*- coding: utf-8 -*-
"""INT-1251 inspect: dump device page DOM structure for selector planning."""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5307')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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
    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        print('URL:', drv.current_url)
        # buttons
        btns = drv.find_elements(By.XPATH, "//button")
        print('=== BUTTONS ===')
        for b in btns[:30]:
            txt = (b.text or '').strip().replace('\n', ' | ')
            if txt:
                print(repr(txt))
        print('=== TABS ===')
        for el in drv.find_elements(By.XPATH, "//*[@role='tab']"):
            print(repr(el.text.strip()))
        # table headers
        print('=== THEAD ===')
        for el in drv.find_elements(By.XPATH, "//thead//th"):
            print(repr(el.text.strip()))
        # first data rows
        print('=== FIRST ROWs (text) ===')
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        print('row count:', len(rows))
        for r in rows[:3]:
            print(repr(r.text[:220]))
        drv.save_screenshot('tests/ui/artifacts/int1251/inspect-devices.png')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()