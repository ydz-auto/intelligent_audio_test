# -*- coding: utf-8 -*-
"""INT-1251 part 8: group manager dialog + API row expanded + test device detail verify."""
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


def api_get(path):
    r = urllib.request.urlopen('http://127.0.0.1:15000' + path)
    return json.loads(r.read().decode())


def main():
    os.makedirs(ART, exist_ok=True)
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))

    # API groups count
    groups = api_get('/api/v1/test-devices/device-groups?page=1&per_page=1000')['data']
    print('API device-groups total:', groups['total'])

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        # open 更多操作 → 分组管理
        more = drv.find_element(By.XPATH, "//button[@aria-label='更多操作']")
        drv.execute_script('arguments[0].click()', more)
        time.sleep(1.2)
        menu = drv.find_element(By.XPATH, "//div[@role='menu']")
        group_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='分组管理']")
        print('分组管理 menu item:', len(group_item))
        if group_item:
            drv.execute_script('arguments[0].click()', group_item[0])
            time.sleep(2.5)
            dlg = drv.find_elements(By.XPATH, "//div[@role='dialog']")
            if dlg:
                print('GROUP MANAGER dialog text:', dlg[0].text[:500])
                drv.save_screenshot(os.path.join(ART, 'group-manager-dialog.png'))
            # close
            drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00f')
            time.sleep(1)

        # API row expanded view
        drv.get(BASE + '/devices/api')
        time.sleep(6)
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        if rows:
            row = rows[0]
            print('API row 0 text:', row.text.replace('\n', ' | ')[:300])
            chev = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'展开')]")
            if not chev:
                chev = row.find_elements(By.XPATH, ".//button")
            for c in chev:
                try:
                    c.click()
                    time.sleep(1.5)
                    break
                except Exception:
                    continue
            drv.save_screenshot(os.path.join(ART, 'api-row-expanded.png'))
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()