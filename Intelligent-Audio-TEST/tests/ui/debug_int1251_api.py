# -*- coding: utf-8 -*-
"""INT-1251 debug2: API create submit + switch markup."""
import json
import os
import time

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
        drv.get(BASE + '/devices/test')
        time.sleep(5)
        # dump switch markup
        switches = drv.find_elements(By.XPATH, "//*[@data-slot='switch']")
        print('switch count:', len(switches))
        for s in switches[:3]:
            print('SWITCH:', s.tag_name, 'role=', s.get_attribute('role'),
                  'aria-label=', s.get_attribute('aria-label'), 'aria-checked=', s.get_attribute('aria-checked'))
        # find by text label
        sw2 = drv.find_elements(By.XPATH, "//*[contains(text(),'批量操作模式')]/following-sibling::*[@data-slot='switch']")
        print('switch after label:', len(sw2))
        if sw2:
            print('  tag/role/aria:', sw2[0].tag_name, sw2[0].get_attribute('role'), sw2[0].get_attribute('aria-checked'))
            drv.execute_script('arguments[0].click()', sw2[0])
            time.sleep(1.5)
            print('  after click aria-checked:', sw2[0].get_attribute('aria-checked'))
            cb = drv.find_elements(By.XPATH, "//button[starts-with(@aria-label,'选择设备')]")
            print('  checkbox count after batchMode:', len(cb))
        # open add API and dump button state after save attempt
        drv.get(BASE + '/devices/api')
        time.sleep(5)
        add_btn = drv.find_element(By.XPATH, "//button[normalize-space(.)='添加测试API']")
        drv.execute_script('arguments[0].click()', add_btn)
        time.sleep(2.5)
        # fill minimal fields
        def fill_input(label, value):
            xp = f"//label[contains(normalize-space(.),'{label}')]/following-sibling::input[1]"
            el = drv.find_element(By.XPATH, xp)
            el.clear()
            el.send_keys(value)
        fill_input('名称', '接线测试_INT1251_dbgAPI')
        fill_input('API 端点', 'https://api.walk.test/v1/asr')
        # dump save button
        sbtns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='保存']")
        print('save btn count:', len(sbtns))
        if sbtns:
            print('save disabled:', sbtns[-1].get_attribute('disabled'))
        # validation state before submit
        drv.save_screenshot(os.path.join(ART, 'api-drawer-min.png'))
        # click save
        drv.execute_script('arguments[0].click()', sbtns[-1])
        time.sleep(3)
        dlg = drv.find_elements(By.XPATH, "//div[@role='dialog']")
        print('dialog still open after save:', len(dlg))
        if dlg:
            print('drawer after save text (errors?):', [l for l in dlg[0].text.split('\n') if '请填写' in l or '错误' in l])
        # network log for /apis
        net = []
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])
                inner = msg.get('message', {})
                if inner.get('method') == 'Network.requestWillBeSent':
                    url = inner['params']['request']['url']
                    if '/apis' in url and '/v1/' in url:
                        net.append((inner['params']['request'].get('method'), url))
            except Exception:
                pass
        print('apis network:', net)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()