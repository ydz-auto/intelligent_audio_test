# -*- coding: utf-8 -*-
"""INT-1333 probe: verify base-ui Select trigger display in create vs edit (label vs raw value)."""
import json
import os
import time
import urllib.request

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


def trigger_text(drv, label):
    try:
        el = drv.find_element(By.XPATH, f"//label[contains(text(),'{label}')]/following-sibling::button[1]")
        return el.text.strip()
    except Exception as e:
        return f'ERR {e}'


def main():
    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)

        # ---- CREATE drawer: default + after pick ----
        add_btn = drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]")
        drv.execute_script('arguments[0].click()', add_btn)
        time.sleep(2.5)
        print('CREATE default 设备类型:', trigger_text(drv, '设备类型'))
        print('CREATE default 设备系统:', trigger_text(drv, '设备系统'))
        print('CREATE default 连接方式:', trigger_text(drv, '连接方式'))
        # pick 真机
        sel = drv.find_element(By.XPATH, "//label[contains(text(),'设备类型')]/following-sibling::button[1]")
        drv.execute_script('arguments[0].click()', sel)
        time.sleep(1)
        opt = drv.find_element(By.XPATH, "//*[@role='option' and contains(.,'真机')]")
        drv.execute_script('arguments[0].click()', opt)
        time.sleep(0.8)
        print('CREATE after pick 真机 设备类型:', trigger_text(drv, '设备类型'))
        # cancel
        cancel_btn = drv.find_element(By.XPATH, "//button[contains(., '取消')]")
        drv.execute_script('arguments[0].click()', cancel_btn)
        time.sleep(1)

        # ---- EDIT drawer on existing offline device row (id 9 pura90小艺) ----
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        row = None
        for r in rows:
            if 'pura90小艺' in r.text:
                row = r
                break
        if not row:
            print('EDIT row pura90小艺 NOT FOUND')
            return
        ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
        drv.execute_script('arguments[0].click()', ops[0])
        time.sleep(1.2)
        menu = drv.find_element(By.XPATH, "//div[@role='menu']")
        edit_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='编辑']")
        print('EDIT item disabled:', edit_item[0].get_attribute('aria-disabled') if edit_item else 'NOT FOUND')
        if edit_item:
            drv.execute_script('arguments[0].click()', edit_item[0])
            time.sleep(2)
            print('EDIT 设备类型:', trigger_text(drv, '设备类型'))
            print('EDIT 设备系统:', trigger_text(drv, '设备系统'))
            print('EDIT 连接方式:', trigger_text(drv, '连接方式'))
            # dump the SelectTrigger buttons' full inner text
            for lbl in ('设备类型', '设备系统', '连接方式'):
                try:
                    btns = drv.find_elements(By.XPATH, f"//label[contains(text(),'{lbl}')]/following-sibling::button[1]")
                    for b in btns:
                        print(f'  {lbl} trigger innerHTML:', b.get_attribute('innerHTML')[:120].replace(chr(10), ' '))
                except Exception as e:
                    print(f'  {lbl} trigger innerHTML ERR:', e)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
