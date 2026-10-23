# -*- coding: utf-8 -*-
"""INT-1251 part 9: driver keyword select options + playback edit confirm + option counts."""
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
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))
    dk = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/api/v1/test-devices/driver-keywords').read().decode())['data']
    print('API driver keywords:', len(dk))
    for k in dk[:5]:
        print(' ', k['name'], k['keywords'], k['system'])

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        add = drv.find_element(By.XPATH, "//button[normalize-space(.)='添加测试设备']")
        drv.execute_script('arguments[0].click()', add)
        time.sleep(2.5)
        # open 驱动关键字 select
        sel = drv.find_element(By.XPATH, "//label[contains(normalize-space(.),'驱动关键字')]/following-sibling::button[1]")
        drv.execute_script('arguments[0].click()', sel)
        time.sleep(1.5)
        opts = drv.find_elements(By.XPATH, "//*[@role='option']")
        opt_texts = [o.text.strip() for o in opts if o.text.strip()]
        print('driver keyword options in drawer:', len(opt_texts))
        for t in opt_texts[:6]:
            print(' ', t)
        drv.save_screenshot(os.path.join(ART, 'driver-keywords-drawer.png'))
        # close select + drawer
        drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00f')
        time.sleep(1)
        drv.find_element(By.XPATH, "//button[normalize-space(.)='取消']").click()
        time.sleep(1)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()