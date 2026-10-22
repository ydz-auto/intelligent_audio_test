# -*- coding: utf-8 -*-
"""INT-1251 part 5: batch delete retest (clean waits) + confirm dialog handling."""
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


def main():
    os.makedirs(ART, exist_ok=True)
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))

    drv = _driver()
    ids = []
    try:
        for i in range(2):
            body = json.dumps({'name': f'{PREFIX}批量Y{i}', 'model': 'B', 'type': 'physical',
                               'system': 'Android', 'system_version': '9', 'app_name': 'B',
                               'app_version': '1', 'connection_type': 'usb',
                               'serial_number': f'BYS-{i}'}, ensure_ascii=False).encode()
            req = urllib.request.Request('http://127.0.0.1:15000/api/v1/test-devices', data=body,
                                         headers={'Content-Type': 'application/json'})
            r = urllib.request.urlopen(req)
            ids.append(json.loads(r.read().decode())['data']['id'])
        print('created:', ids)

        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        sw = drv.find_element(By.XPATH, "//*[@data-slot='switch'][@aria-label='批量操作模式']")
        drv.execute_script('arguments[0].click()', sw)
        time.sleep(2)
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        for r in rows:
            if PREFIX + '批量Y' in r.text:
                cb = r.find_elements(By.XPATH, ".//*[@data-slot='checkbox'][starts-with(@aria-label,'选择设备')]")
                if cb:
                    drv.execute_script('arguments[0].click()', cb[0])
                    time.sleep(0.4)
        time.sleep(1)
        # bulk bar
        bulk = [b.text for b in drv.find_elements(By.XPATH, "//*[contains(text(),'个已选择')]")]
        print('bulk bar:', bulk)
        # delete
        del_btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除']")
        drv.execute_script('arguments[0].click()', del_btns[-1])
        time.sleep(3)  # wait for confirm dialog fully open
        cdel = drv.find_elements(By.XPATH, "//button[normalize-space(.)='批量删除']")
        print('confirm 批量删除 found:', len(cdel))
        if cdel:
            NETWORK.clear()
            drv.execute_script('arguments[0].click()', cdel[-1])
            # wait long for serial deletes
            for _ in range(6):
                time.sleep(2)
                NETWORK.extend(drain(drv))
            dels = [p for p in NETWORK if p[0] == 'REQ' and p[1] == 'DELETE' and 'test-devices/' in p[2]]
            print('DELETE reqs:', dels)
            toasts = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
            print('TOASTS:', toasts)
        time.sleep(2)
        td = api_get('/api/v1/test-devices?page=1&per_page=1000')['data']['items']
        remain = [d for d in td if d['name'].startswith(PREFIX + '批量Y')]
        print('remaining via API:', [(d['id'], d['name']) for d in remain])
        drv.save_screenshot(os.path.join(ART, 'batchY-after.png'))
    finally:
        for did in ids:
            print('CLEANUP', did, api_del(f'/api/v1/test-devices/{did}'))
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()