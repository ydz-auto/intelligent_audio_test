# -*- coding: utf-8 -*-
"""INT-1251 walkthrough part 1: device list + add-drawer inspection.

Verifies:
- list total/online counts vs API
- supported algorithm column (INT-1215 claim: Chinese label)
- add drawer: algorithm options (INT-1213 claim: from /algorithm/options)
- offline device edit (INT-1217 claim: not disabled)
"""
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


def api_get(path):
    r = urllib.request.urlopen('http://127.0.0.1:15000' + path)
    return json.loads(r.read().decode())


def main():
    os.makedirs(ART, exist_ok=True)
    # anti-cross-db check
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))
    td = api_get('/api/v1/test-devices?page=1&per_page=1000')['data']
    print('API test-devices total:', td['total'])
    algo = api_get('/api/v1/algorithm/options')['data']['algorithms']
    print('API algorithm options:', algo)

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        body = drv.execute_script('return document.body.textContent || ""')
        print('URL:', drv.current_url)
        print('has 设备管理:', '设备管理' in body)
        # stats row
        print('BODY stats sample:', [s for s in body.split('\n') if '设备' in s][:6])

        # supported algorithm column check: find 'voice_llm' in table (INT-1215)
        cells = drv.find_elements(By.XPATH, "//tbody//td")
        algo_cells = [c.text.strip() for c in cells]
        print('raw voice_llm present in table:', 'voice_llm' in algo_cells)
        print('小艺语音大模型 present in table:', '小艺语音大模型' in algo_cells)
        drv.save_screenshot(os.path.join(ART, 'list-light.png'))

        # open add drawer
        add_btn = drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]")
        drv.execute_script('arguments[0].click()', add_btn)
        time.sleep(2.5)
        drawer = drv.find_element(By.XPATH, "//div[@role='dialog']")
        dbody = drawer.text
        print('=== DRAWER TITLE ===')
        print([l for l in dbody.split('\n') if '添加' in l or '设备' in l][:4])
        # algorithm chips
        print('=== ALGO CHIP AREA ===')
        for kw in ('asr_streaming', 'wakeword_detect', 'tts_eval', '小艺语音大模型', 'voice_llm'):
            print(kw, 'in drawer:', kw in dbody)
        drv.save_screenshot(os.path.join(ART, 'add-drawer-light.png'))

        # close drawer (cancel)
        cancel_btn = drv.find_element(By.XPATH, "//button[contains(., '取消')]")
        drv.execute_script('arguments[0].click()', cancel_btn)
        time.sleep(1)
        print('drawer closed:', drv.find_elements(By.XPATH, "//div[@role='dialog']") == [])

        # offline device edit check (INT-1217): open row actions on first row
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        if rows:
            first_ops = rows[0].find_elements(By.XPATH, ".//button[starts-with(@aria-label, '操作')]")
            if first_ops:
                drv.execute_script('arguments[0].click()', first_ops[0])
                time.sleep(1.5)
                menu = drv.find_element(By.XPATH, "//div[@role='menu']")
                items = [m.text.strip() for m in menu.find_elements(By.XPATH, ".//*[contains(@class,'item')]")]
                print('=== ROW MENU ===')
                print(items)
                edit_item = menu.find_elements(By.XPATH, ".//*[contains(.,'编辑')]")
                print('edit item disabled attr:', edit_item[0].get_attribute('aria-disabled') if edit_item else 'NOT FOUND')
                drv.save_screenshot(os.path.join(ART, 'rowmenu-light.png'))
                # close menu
                drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00f')  # ESC
                time.sleep(1)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()