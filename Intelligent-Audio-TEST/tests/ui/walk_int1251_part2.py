# -*- coding: utf-8 -*-
"""INT-1251 walkthrough part 2: full CRUD closed loop on test devices (§3.5).

1. 新建: fill ALL fields (接线测试_ prefix) → submit → verify list + GET /test-devices/{id} each field
2. 编辑: reopen edit drawer, verify echo; try changing each editable field, save, re-verify
3. 删除: list disappears + API soft-delete
4. 批量操作: on 2-3 self-created records
5. 校验与状态: required empty, invalid values, cancel/close reopen form state
6. 选项与计数: dropdown option counts vs API
Network evidence: capture request/response for each step.
"""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5307')
ART = os.path.join('tests', 'ui', 'artifacts', 'int1251')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PREFIX = '接线测试_INT1251_'

NETWORK = []  # (method, url, status, requestBody)


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


def api_delete(path):
    req = urllib.request.Request('http://127.0.0.1:15000' + path, method='DELETE')
    try:
        r = urllib.request.urlopen(req)
        return ('OK', r.status, r.read().decode()[:150])
    except urllib.error.HTTPError as e:
        return ('ERR', e.code, e.read().decode()[:200])


def drain_network(drv):
    """Collect request/response pairs since last drain."""
    pairs = []
    entries = drv.get_log('performance')
    for entry in entries:
        try:
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            method = inner.get('method', '')
            if method == 'Network.requestWillBeSent':
                req = inner['params']['request']
                url = req['url']
                if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                    pairs.append({
                        'kind': 'req',
                        'url': url,
                        'method': req.get('method'),
                        'post': req.get('postData', '')[:400],
                        'ts': inner['params'].get('timestamp'),
                    })
            elif method == 'Network.responseReceived':
                resp = inner['params']['response']
                url = resp['url']
                if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                    pairs.append({
                        'kind': 'resp',
                        'url': url,
                        'status': resp.get('status'),
                        'ts': inner['params'].get('timestamp'),
                    })
        except Exception:
            pass
    return pairs


def show_net(label):
    print(f'--- NET [{label}] ---')
    for p in NETWORK[-60:]:
        if p['kind'] == 'req':
            print(f"  REQ {p['method']} {p['url']}")
            if p.get('post'):
                print(f"    body: {p['post']}")
        else:
            print(f"  RESP {p['status']} {p['url']}")


def fill_input(drv, label, value):
    """Fill an input by its preceding Label text."""
    xp = f"//label[contains(text(),'{label}')]/following-sibling::input[1]"
    el = drv.find_element(By.XPATH, xp)
    el.clear()
    el.send_keys(value)
    return el


def main():
    os.makedirs(ART, exist_ok=True)
    health = json.loads(urllib.request.urlopen('http://127.0.0.1:15000/health').read().decode())
    print('HEALTH db:', health.get('database'))
    assert health.get('database') == 'intelligent_audio_test', 'DB WRONG'

    created_ids = []

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        NETWORK.extend(drain_network(drv))

        # ============ 1. 新建 test device ============
        add_btn = drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]")
        drv.execute_script('arguments[0].click()', add_btn)
        time.sleep(2.5)
        name = PREFIX + '测试设备A'
        fill_input(drv, '名称', name)
        fill_input(drv, '描述', '走查描述')
        fill_input(drv, '型号', 'Walkthrough S1')
        fill_input(drv, '系统版本', '12')
        fill_input(drv, '应用名称', 'WalkApp')
        fill_input(drv, '应用版本', '2.0.0')
        fill_input(drv, '设备序列号', 'WALK-SN-001')
        # device type / system / connection select
        # click 设备类型 select
        def pick_select(label, value):
            sel = drv.find_element(By.XPATH, f"//label[contains(text(),'{label}')]/following-sibling::button[1]")
            drv.execute_script('arguments[0].click()', sel)
            time.sleep(1)
            opt = drv.find_element(By.XPATH, f"//*[@role='option' and contains(.,'{value}')]")
            drv.execute_script('arguments[0].click()', opt)
            time.sleep(0.6)
        pick_select('设备类型', '真机')
        pick_select('设备系统', 'Android')
        pick_select('连接方式', 'USB连接')
        # algorithm chip: none selectable matches real options; leave default
        drv.save_screenshot(os.path.join(ART, 'add-drawer-filled.png'))

        # submit
        save_btn = drv.find_element(By.XPATH, "//button[contains(., '保存')]")
        NETWORK.clear()  # keep only this mutation
        drv.execute_script('arguments[0].click()', save_btn)
        time.sleep(4)
        NETWORK.extend(drain_network(drv))
        show_net('create test device')
        toasts = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('TOASTS:', toasts)
        drv.save_screenshot(os.path.join(ART, 'create-result.png'))

        # find created device id via API
        td = api_get('/api/v1/test-devices?page=1&per_page=1000')['data']['items']
        mine = [d for d in td if d['name'] == name]
        print('CREATED in list via API:', [(d['id'], d['name'], d['serial_number']) for d in mine])
        if mine:
            created_ids.append(mine[0]['id'])
            did = mine[0]['id']
            # verify list shows it
            body = drv.execute_script('return document.body.textContent || ""')
            print('list contains name:', name in body)
            # GET detail
            det = api_get(f'/api/v1/test-devices/{did}')['data']
            print('GET /test-devices/{id}:')
            for k in ('name', 'model', 'system', 'system_version', 'app_name', 'app_version',
                      'connection_type', 'serial_number', 'status'):
                print(f'  {k}: {det.get(k)!r}')

        # ============ 2. 编辑 ============
        if created_ids:
            # reload page, find row, try edit (offline device → INT-1217 check)
            drv.get(BASE + '/devices/test')
            time.sleep(5)
            rows = drv.find_elements(By.XPATH, "//tbody/tr")
            row = None
            for r in rows:
                if name in r.text:
                    row = r
                    break
            if row:
                ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
                drv.execute_script('arguments[0].click()', ops[0])
                time.sleep(1.2)
                menu = drv.find_element(By.XPATH, "//div[@role='menu']")
                edit_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='编辑']")
                if edit_item:
                    disabled = edit_item[0].get_attribute('aria-disabled') or edit_item[0].get_attribute('data-disabled')
                    print('EDIT item disabled:', disabled)
                    if not disabled:
                        drv.execute_script('arguments[0].click()', edit_item[0])
                        time.sleep(2)
                        drawer = drv.find_element(By.XPATH, "//div[@role='dialog']")
                        dtext = drawer.text
                        # echo check
                        print('EDIT drawer echoes name:', name in dtext)
                        print('EDIT drawer echoes model:', 'Walkthrough S1' in dtext)
                        print('EDIT drawer echoes systemVersion:', '12' in dtext)
                        print('EDIT drawer echoes appName:', 'WalkApp' in dtext)
                        print('EDIT drawer echoes serial:', 'WALK-SN-001' in dtext)
                        # change a field
                        nm = fill_input(drv, '名称', name + '_改名')
                        time.sleep(0.3)
                        NETWORK.clear()
                        save_btn2 = drv.find_element(By.XPATH, "//button[contains(., '保存')]")
                        drv.execute_script('arguments[0].click()', save_btn2)
                        time.sleep(4)
                        NETWORK.extend(drain_network(drv))
                        show_net('edit test device')
                        toasts2 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                        print('EDIT TOASTS:', toasts2)
                        det2 = api_get(f'/api/v1/test-devices/{created_ids[0]}')['data']
                        print('AFTER EDIT GET name:', det2.get('name'))
                    else:
                        print('EDIT IS DISABLED — INT-1217 fix absent in wiring/react')
                # close menu
                drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)
            drv.save_screenshot(os.path.join(ART, 'edit-check.png'))

        # ============ 3. 删除 ============
        if created_ids:
            drv.get(BASE + '/devices/test')
            time.sleep(5)
            rows = drv.find_elements(By.XPATH, "//tbody/tr")
            row = None
            for r in rows:
                if name in r.text:
                    row = r
                    break
            if row:
                ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
                drv.execute_script('arguments[0].click()', ops[0])
                time.sleep(1.2)
                menu = drv.find_element(By.XPATH, "//div[@role='menu']")
                del_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='删除']")
                if del_item:
                    NETWORK.clear()
                    drv.execute_script('arguments[0].click()', del_item[0])
                    time.sleep(1.5)
                    # confirm dialog
                    cbtn = drv.find_elements(By.XPATH, "//button[contains(.,'删除')]")
                    if cbtn:
                        drv.execute_script('arguments[0].click()', cbtn[-1])
                        time.sleep(4)
                        NETWORK.extend(drain_network(drv))
                        show_net('delete test device')
                        toasts3 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                        print('DELETE TOASTS:', toasts3)
                        det3 = api_delete(f'/api/v1/test-devices/{created_ids[0]}')
                        print('DELETE API (2nd attempt / verify):', det3)
                        created_ids.pop(0)

        # ============ 5. 校验与状态 ============
        add_btn2 = drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]")
        drv.execute_script('arguments[0].click()', add_btn2)
        time.sleep(2)
        # submit empty name
        NETWORK.clear()
        save_btn3 = drv.find_element(By.XPATH, "//button[contains(., '保存')]")
        drv.execute_script('arguments[0].click()', save_btn3)
        time.sleep(2)
        NETWORK.extend(drain_network(drv))
        drawer3 = drv.find_element(By.XPATH, "//div[@role='dialog']")
        d3 = drawer3.text
        print('empty submit errors present:', '请填写设备名称' in d3, '|', '请填写型号' in d3)
        drv.save_screenshot(os.path.join(ART, 'validation-empty.png'))
        # cancel then reopen — form cleared?
        cancel_btn = drv.find_element(By.XPATH, "//button[contains(., '取消')]")
        drv.execute_script('arguments[0].click()', cancel_btn)
        time.sleep(1)
        add_btn3 = drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]")
        drv.execute_script('arguments[0].click()', add_btn3)
        time.sleep(2)
        drawer4 = drv.find_element(By.XPATH, "//div[@role='dialog']")
        d4 = drawer4.text
        print('reopen: previous values remain?', 'Walkthrough' in d4 or PREFIX in d4)

        # ============ 6. 选项与计数 ============
        algo_opt = api_get('/api/v1/algorithm/options')['data']['algorithms']
        dk = api_get('/api/v1/test-devices/driver-keywords')['data']
        print('API algorithm options:', [(a['value'], a['name']) for a in algo_opt])
        print('API driver keywords count:', len(dk))
        print('drawer shows driver keyword:', dk[0]['name'] if dk else 'N/A', 'in drawer:', dk[0]['name'] in d4 if dk else False)
        # close drawer
        cancel_btn2 = drv.find_element(By.XPATH, "//button[contains(., '取消')]")
        drv.execute_script('arguments[0].click()', cancel_btn2)
        time.sleep(1)
        drv.save_screenshot(os.path.join(ART, 'final-light.png'))
    finally:
        # cleanup any leftover created ids
        for did in created_ids:
            print('CLEANUP id', did, api_delete(f'/api/v1/test-devices/{did}'))
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()