# -*- coding: utf-8 -*-
"""INT-1251 part 6: single delete via UI + playback edit echo + dark mode screenshots."""
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
NETWORK = []


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
    try:
        r = urllib.request.urlopen(req)
        return ('OK', r.status, json.loads(r.read().decode()))
    except urllib.error.HTTPError as e:
        return ('ERR', e.code, e.read().decode()[:200])


def drain(drv):
    pairs = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            method = inner.get('method', '')
            if method == 'Network.requestWillBeSent':
                req = inner['params']['request']
                url = req['url']
                if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                    pairs.append(('REQ', req.get('method'), url, req.get('postData', '')[:300]))
            elif method == 'Network.responseReceived':
                resp = inner['params']['response']
                url = resp['url']
                if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                    pairs.append(('RESP', str(resp.get('status')), url, ''))
        except Exception:
            pass
    return pairs


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
    test_id = None
    pb_id = None
    try:
        # create a test device via API
        res = api_post('/api/v1/test-devices', {'name': PREFIX + '单删', 'model': 'M', 'type': 'physical',
                       'system': 'Android', 'system_version': '10', 'app_name': 'A',
                       'app_version': '1', 'connection_type': 'usb', 'serial_number': 'DEL-SN-1'})
        test_id = res[2]['data']['id']
        print('test device created:', test_id)

        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        # find row
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        row = None
        for r in rows:
            if PREFIX + '单删' in r.text:
                row = r
                break
        print('row found:', row is not None)
        if row:
            ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
            drv.execute_script('arguments[0].click()', ops[0])
            time.sleep(1.5)
            menu = drv.find_element(By.XPATH, "//div[@role='menu']")
            del_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='删除']")
            print('delete menu item found:', len(del_item))
            if del_item:
                NETWORK.clear()
                drv.execute_script('arguments[0].click()', del_item[0])
                time.sleep(2.5)
                cbtn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除']")
                print('confirm delete btn:', len(cbtn))
                if cbtn:
                    drv.execute_script('arguments[0].click()', cbtn[-1])
                    time.sleep(5)
                    NETWORK.extend(drain(drv))
                    delreqs = [p for p in NETWORK if p[0] == 'REQ' and p[1] == 'DELETE' and 'test-devices/' in p[2]]
                    print('single DELETE reqs:', delreqs)
                    toasts = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                    print('SINGLE DELETE TOASTS:', toasts)
                # verify gone
                time.sleep(1)
                rows2 = drv.find_elements(By.XPATH, "//tbody/tr")
                still = [r for r in rows2 if PREFIX + '单删' in r.text]
                print('row still in list after delete:', len(still))
                drv.save_screenshot(os.path.join(ART, 'single-delete-result.png'))

        # ===== playback edit echo =====
        pb_res = api_post('/api/v1/playback-devices', {'name': PREFIX + '播放编辑', 'model': 'PBM',
                       'device_type': 'dry', 'sample_rate': 44100, 'channel_index': 1,
                       'device_unique_id': 'PB-EDIT-001', 'description': 'desc', 'status': 'offline'})
        pb_id = pb_res[2]['data']['id']
        print('playback created:', pb_id)
        drv.get(BASE + '/devices/playback')
        time.sleep(6)
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        row = None
        for r in rows:
            if PREFIX + '播放编辑' in r.text:
                row = r
                break
        print('playback row found:', row is not None)
        if row:
            ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
            drv.execute_script('arguments[0].click()', ops[0])
            time.sleep(1.5)
            menu = drv.find_element(By.XPATH, "//div[@role='menu']")
            edit_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='编辑']")
            disabled = edit_item[0].get_attribute('aria-disabled') if edit_item else 'NOT FOUND'
            print('playback EDIT disabled:', disabled)
            if edit_item and not disabled:
                drv.execute_script('arguments[0].click()', edit_item[0])
                time.sleep(2.5)
                drawer = drv.find_element(By.XPATH, "//div[@role='dialog']")
                dtext = drawer.text
                print('playback edit echo name:', PREFIX + '播放编辑' in dtext)
                print('playback edit echo model:', 'PBM' in dtext)
                print('playback edit echo sampleRate:', '44100' in dtext)
                print('playback edit echo uniqueId:', 'PB-EDIT-001' in dtext)
                drv.save_screenshot(os.path.join(ART, 'playback-edit-echo.png'))
                # change name
                fill_input(drv, '名称', PREFIX + '播放编辑_改')
                NETWORK.clear()
                click_btn(drv, '保存')
                time.sleep(4)
                NETWORK.extend(drain(drv))
                toasts2 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                print('PLAYBACK EDIT TOASTS:', toasts2)
                det = api_get(f'/api/v1/playback-devices/{pb_id}')['data']
                print('AFTER PLAYBACK EDIT name:', det.get('name'))

        # ===== dark mode screenshots =====
        drv.get(BASE + '/devices/test')
        time.sleep(4)
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', JSON.stringify('dark'))")
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        drv.save_screenshot(os.path.join(ART, 'list-dark.png'))
        # dark add drawer
        click_btn(drv, '添加测试设备')
        time.sleep(2.5)
        drv.save_screenshot(os.path.join(ART, 'add-drawer-dark.png'))
        click_btn(drv, '取消')
        time.sleep(1)

    finally:
        if test_id:
            print('CLEANUP test', test_id, api_del(f'/api/v1/test-devices/{test_id}'))
        if pb_id:
            print('CLEANUP playback', pb_id, api_del(f'/api/v1/playback-devices/{pb_id}'))
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()