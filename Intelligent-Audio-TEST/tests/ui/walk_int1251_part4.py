# -*- coding: utf-8 -*-
"""INT-1251 walkthrough part 4: batch delete verify + scan dialog + single delete verify."""
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
        return ('OK', r.status, r.read().decode()[:120])
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
                    pairs.append(('REQ', req.get('method'), url, req.get('postData', '')[:400]))
            elif method == 'Network.responseReceived':
                resp = inner['params']['response']
                url = resp['url']
                if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                    pairs.append(('RESP', str(resp.get('status')), url, ''))
        except Exception:
            pass
    return pairs


def main():
    os.makedirs(ART, exist_ok=True)
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))
    assert health.get('database') == 'intelligent_audio_test'

    drv = _driver()
    ids = []
    try:
        # create 3 test devices via API for batch ops
        for i in range(3):
            body = json.dumps({'name': f'{PREFIX}批量X{i}', 'model': 'B', 'type': 'physical',
                               'system': 'Android', 'system_version': '9', 'app_name': 'B',
                               'app_version': '1', 'connection_type': 'usb',
                               'serial_number': f'BXS-{i}'}, ensure_ascii=False).encode()
            req = urllib.request.Request('http://127.0.0.1:15000/api/v1/test-devices', data=body,
                                         headers={'Content-Type': 'application/json'})
            r = urllib.request.urlopen(req)
            ids.append(json.loads(r.read().decode())['data']['id'])
        print('created:', ids)

        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        # enable batch mode
        sw = drv.find_element(By.XPATH, "//*[@data-slot='switch'][@aria-label='批量操作模式']")
        drv.execute_script('arguments[0].click()', sw)
        time.sleep(2)
        # select our rows
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        sel = 0
        for r in rows:
            if PREFIX + '批量X' in r.text:
                cb = r.find_elements(By.XPATH, ".//*[@data-slot='checkbox'][starts-with(@aria-label,'选择设备')]")
                if cb:
                    drv.execute_script('arguments[0].click()', cb[0])
                    sel += 1
                    time.sleep(0.4)
        print('selected:', sel)
        time.sleep(1)
        bulk = drv.find_elements(By.XPATH, "//*[contains(text(),'个已选择')]")
        print('bulk bar:', [b.text for b in bulk])
        drv.save_screenshot(os.path.join(ART, 'bulk2-selected.png'))

        # batch delete
        del_btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除']")
        print('delete btn count:', len(del_btns))
        if del_btns:
            NETWORK.clear()
            drv.execute_script('arguments[0].click()', del_btns[-1])
            time.sleep(2)
            # confirm dialog
            cdel = drv.find_elements(By.XPATH, "//button[normalize-space(.)='批量删除']")
            print('confirm 批量删除 found:', len(cdel))
            if cdel:
                drv.execute_script('arguments[0].click()', cdel[-1])
                time.sleep(8)  # serial deletes take time
                NETWORK.extend(drain(drv))
                show = [p for p in NETWORK if p[0] == 'REQ' and 'test-devices/' in p[2] and p[1] == 'DELETE']
                print('DELETE requests captured:', show)
                toasts = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                print('BATCH DELETE TOASTS:', toasts)
        # verify
        td = api_get('/api/v1/test-devices?page=1&per_page=1000')['data']['items']
        remain = [d for d in td if d['name'].startswith(PREFIX + '批量X')]
        print('remaining via API:', [(d['id'], d['name']) for d in remain])
        drv.save_screenshot(os.path.join(ART, 'bulk2-after-delete.png'))

        # ============ scan dialog ============
        drv.get(BASE + '/devices/test')
        time.sleep(5)
        # open 更多操作 → 扫描设备
        more = drv.find_element(By.XPATH, "//button[@aria-label='更多操作']")
        drv.execute_script('arguments[0].click()', more)
        time.sleep(1.2)
        menu = drv.find_element(By.XPATH, "//div[@role='menu']")
        scan_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='扫描设备']")
        print('scan menu item:', len(scan_item))
        if scan_item:
            NETWORK.clear()
            drv.execute_script('arguments[0].click()', scan_item[0])
            time.sleep(2)
            NETWORK.extend(drain(drv))
            scan_reqs = [p for p in NETWORK if '/scan' in p[2]]
            print('scan requests:', scan_reqs)
            dlg = drv.find_elements(By.XPATH, "//div[@role='dialog']")
            if dlg:
                print('scan dialog text sample:', dlg[0].text[:300])
                drv.save_screenshot(os.path.join(ART, 'scan-dialog.png'))
                # start scan
                start_btn = drv.find_elements(By.XPATH, "//button[contains(.,'开始扫描')]")
                if start_btn:
                    NETWORK.clear()
                    drv.execute_script('arguments[0].click()', start_btn[-1])
                    time.sleep(5)
                    NETWORK.extend(drain(drv))
                    scan_reqs2 = [p for p in NETWORK if '/scan' in p[2]]
                    print('scan start requests:', scan_reqs2)
                    time.sleep(3)
                    dlg2 = drv.find_elements(By.XPATH, "//div[@role='dialog']")
                    if dlg2:
                        print('scan dialog after start:', dlg2[0].text[:400])
                        drv.save_screenshot(os.path.join(ART, 'scan-after-start.png'))
    finally:
        for did in ids:
            print('CLEANUP', did, api_del(f'/api/v1/test-devices/{did}'))
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()