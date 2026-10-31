# -*- coding: utf-8 -*-
"""INT-2176 补证：登录取 token（浏览器 localStorage iatp:auth:token:v1）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = 'http://localhost:15173'
USER, PWD = '接线测试_admin', 'JieXianTest@2026'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))


def driver():
    o = Options()
    o.binary_location = CHROME
    for a in ['--headless=new', '--window-size=1680,1050', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run',
              '--no-default-browser-check', '--force-device-scale-factor=1']:
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(60)
    return d


def main():
    d = driver()
    try:
        d.get(BASE + '/login')
        WebDriverWait(d, 40).until(lambda x: x.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        d.find_element(By.ID, 'username').send_keys(USER)
        d.find_element(By.ID, 'password').send_keys(PWD)
        d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(d, 40).until(lambda x: '/login' not in x.current_url)
        time.sleep(2)
        token = d.execute_script("return window.localStorage.getItem('iatp:auth:token:v1')")
        art = os.path.join(HERE, 'artifacts', 'int2176')
        os.makedirs(art, exist_ok=True)
        with open(os.path.join(art, 'token.txt'), 'w', encoding='utf-8') as f:
            f.write(token or '')
        print('token_len', len(token or ''), 'url', d.current_url)
    finally:
        d.quit()


if __name__ == '__main__':
    main()
