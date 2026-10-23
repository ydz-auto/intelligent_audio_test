# -*- coding: utf-8 -*-
"""INT-1436 测试工程师验收截图（浅色 + 深色 + 移动端 + 关于页入口），dev server 5273。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1436_test_accept')


def _driver(width=1680, height=1050):
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument(f'--window-size={width},{height}')
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    ver_t = tuple(int(x) for x in ver.split('.') if x.isdigit())
                except ValueError:
                    continue
                if ver_t and ver_t[0] == chrome_major:
                    drv_path = exe
    return webdriver.Chrome(options=options, service=Service(executable_path=drv_path) if drv_path else Service())


def _shot(drv, name):
    os.makedirs(ART, exist_ok=True)
    drv.save_screenshot(os.path.join(ART, name))
    print('saved', name)


def main():
    drv = _driver()
    try:
        # 浅色
        drv.get(BASE + '/user-guide-integration')
        time.sleep(3.0)
        _shot(drv, 'light_top.png')
        h = drv.execute_script('return document.body.scrollHeight')
        drv.set_window_size(1680, min(h, 4200))
        time.sleep(0.5)
        _shot(drv, 'light_full.png')

        # 深色
        drv.set_window_size(1680, 1050)
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'dark')")
        drv.get('about:blank')
        drv.get(BASE + '/user-guide-integration')
        time.sleep(2.5)
        _shot(drv, 'dark_top.png')
        h = drv.execute_script('return document.body.scrollHeight')
        drv.set_window_size(1680, min(h, 4200))
        time.sleep(0.5)
        _shot(drv, 'dark_full.png')

        # 移动端浅色
        drv.set_window_size(390, 844)
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', 'light')")
        drv.get('about:blank')
        drv.get(BASE + '/user-guide-integration')
        time.sleep(2.0)
        _shot(drv, 'mobile_390.png')

        # 关于页入口
        drv.set_window_size(1680, 1050)
        drv.get('about:blank')
        drv.get(BASE + '/about')
        time.sleep(2.5)
        _shot(drv, 'about_links.png')
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
