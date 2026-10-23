# -*- coding: utf-8 -*-
"""INT-1251 part 7: API create row display check + device detail dialog + screenshots."""
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


def fill_input(drv, label, value):
    xp = f"//label[contains(normalize-space(.),'{label}')]/following-sibling::input[1]"
    el = drv.find_element(By.XPATH, xp)
    el.clear()
    el.send_keys(value)
    time.sleep(0.2)


def pick_select(drv, label, value):
    sel = drv.find_element(By.XPATH, f"//label[contains(normalize-space(.),'{label}')]/following-sibling::button[1]")
    drv.execute_script('arguments[0].click()', sel)
    time.sleep(1)
    opt = drv.find_element(By.XPATH, f"//*[@role='option' and normalize-space(.)='{value}']")
    drv.execute_script('arguments[0].click()', opt)
    time.sleep(0.6)


def click_btn(drv, text):
    els = drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{text}']")
    for el in els:
        try:
            drv.execute_script('arguments[0].click()', el)
            return True
        except Exception:
            continue
    return False


def main():
    os.makedirs(ART, exist_ok=True)
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))

    drv = _driver()
    api_id = None
    try:
        # create an API device via UI with proxy config
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/api')
        time.sleep(6)
        click_btn(drv, '添加测试API')
        time.sleep(2.5)
        aname = PREFIX + 'API列表显示'
        fill_input(drv, '名称', aname)
        fill_input(drv, '供应商', 'VendorShow')
        fill_input(drv, 'API 端点', 'https://show.test/v1/asr')
        pick_select(drv, '代理类型', 'HTTP')
        fill_input(drv, '代理地址', 'u:p@9.9.9.9:9999')
        click_btn(drv, '保存')
        time.sleep(4)
        apis = api_get('/api/v1/apis?page=1&per_page=1000')['data']['items']
        mine = [a for a in apis if a['name'] == aname]
        if mine:
            api_id = mine[0]['id']
            print('API created:', api_id)
            # how does the list row display it?
            drv.get(BASE + '/devices/api')
            time.sleep(5)
            rows = drv.find_elements(By.XPATH, "//tbody/tr")
            row = None
            for r in rows:
                if aname in r.text:
                    row = r
                    break
            if row:
                print('API ROW text:', row.text.replace('\n', ' | ')[:400])
                drv.save_screenshot(os.path.join(ART, 'api-row-display.png'))
            # expand row to see endpoint detail
            if row:
                chev = row.find_elements(By.XPATH, ".//button")
                for c in chev:
                    try:
                        c.click()
                        break
                    except Exception:
                        continue
                time.sleep(1.5)
                drv.save_screenshot(os.path.join(ART, 'api-row-expanded.png'))

        # device detail dialog on a real device
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        if rows:
            ops = rows[0].find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
            drv.execute_script('arguments[0].click()', ops[0])
            time.sleep(1.5)
            menu = drv.find_element(By.XPATH, "//div[@role='menu']")
            detail_item = menu.find_elements(By.XPATH, ".//*[@data-slot='dropdown-menu-item' and normalize-space(.)='详情']")
            if detail_item:
                drv.execute_script('arguments[0].click()', detail_item[0])
                time.sleep(2)
                dlg = drv.find_elements(By.XPATH, "//div[@role='dialog']")
                if dlg:
                    print('DETAIL DIALOG text sample:', dlg[0].text[:400])
                    drv.save_screenshot(os.path.join(ART, 'device-detail-dialog.png'))
            # close
            drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00f')
            time.sleep(1)
        # light + dark full page screenshots for the conclusion
        drv.save_screenshot(os.path.join(ART, 'devices-test-light.png'))
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', JSON.stringify('dark'))")
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        drv.save_screenshot(os.path.join(ART, 'devices-test-dark.png'))
        drv.get(BASE + '/devices/api')
        time.sleep(6)
        drv.save_screenshot(os.path.join(ART, 'devices-api-dark.png'))
    finally:
        if api_id:
            print('CLEANUP api', api_id, api_del(f'/api/v1/apis/{api_id}'))
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()