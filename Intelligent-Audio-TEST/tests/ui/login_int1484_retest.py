# -*- coding: utf-8 -*-
"""INT-1484 retest：登录取 token（写 artifacts/int1484/token.txt），供 API 探针复用。"""
import os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://localhost:15318')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1484')
os.makedirs(ART, exist_ok=True)


def main():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1000')
    o.add_argument('--no-sandbox')
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    exe = ''
    for ver in sorted(os.listdir(cache)) if os.path.isdir(cache) else []:
        p = os.path.join(cache, ver, 'chromedriver.exe')
        if os.path.isfile(p):
            exe = p
    drv = webdriver.Chrome(options=o, service=Service(executable_path=exe) if exe else Service())
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1.5)
        u = WebDriverWait(drv, 15).until(
            lambda d: d.find_element(By.ID, 'username') if d.find_elements(By.ID, 'username') else False)
        u.send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
        time.sleep(2)
        tok = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        with open(os.path.join(ART, 'token.txt'), 'w', encoding='utf-8') as f:
            f.write(tok or '')
        print('URL', drv.current_url, 'TOKEN_LEN', len(tok or ''))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
