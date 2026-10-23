# -*- coding: utf-8 -*-
"""INT-1251 debug: delete confirm dialog structure."""
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
PREFIX = '接线测试_INT1251_'


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


def api_del(path):
    req = urllib.request.Request('http://127.0.0.1:15000' + path, method='DELETE')
    try:
        r = urllib.request.urlopen(req)
        return ('OK', r.status, r.read().decode()[:100])
    except urllib.error.HTTPError as e:
        return ('ERR', e.code, e.read().decode()[:150])


def api_post(path, payload):
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request('http://127.0.0.1:15000' + path, data=body,
                                 headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req)
    return json.loads(r.read().decode())


def main():
    os.makedirs(ART, exist_ok=True)
    drv = _driver()
    tid = None
    try:
        tid = api_post('/api/v1/test-devices', {'name': PREFIX + 'deldbg', 'model': 'M', 'type': 'physical',
                       'system': 'Android', 'system_version': '10', 'app_name': 'A',
                       'app_version': '1', 'connection_type': 'usb', 'serial_number': 'DD-1'})['data']['id']
        print('created', tid)
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        row = None
        for r in rows:
            if PREFIX + 'deldbg' in r.text:
                row = r
                break
        if row:
            ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
            drv.execute_script('arguments[0].click()', ops[0])
            time.sleep(1.5)
            menu = drv.find_element(By.XPATH, "//div[@role='menu']")
            del_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='删除']")
            # click the actual menu item element (data-slot), fallback to matched
            target = None
            for el in del_item:
                if el.get_attribute('data-slot') == 'dropdown-menu-item':
                    target = el
                    break
            if not target and del_item:
                target = del_item[0]
            print('delete target tag:', target.tag_name, 'slot:', target.get_attribute('data-slot'))
            print('delete disabled attr:', target.get_attribute('aria-disabled'), '| data-disabled:', target.get_attribute('data-disabled'))
            print('all menu items:', [ (m.get_attribute('data-slot'), m.text, m.get_attribute('aria-disabled')) for m in menu.find_elements(By.XPATH, ".//*[@data-slot='dropdown-menu-item']") ])
            try:
                target.click()
            except Exception as e:
                print('native click err:', e)
            time.sleep(3)
            # dump dialogs and buttons
            dlg = drv.find_elements(By.XPATH, "//div[@role='dialog']")
            print('dialog count:', len(dlg))
            if dlg:
                print('dialog text:', dlg[-1].text[:400])
                btns = dlg[-1].find_elements(By.XPATH, ".//button")
                print('dialog buttons:', [b.text for b in btns])
                drv.save_screenshot(os.path.join(ART, 'delete-confirm-debug.png'))
    finally:
        if tid:
            print('CLEANUP', tid, api_del(f'/api/v1/test-devices/{tid}'))
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()