# -*- coding: utf-8 -*-
"""INT-1333 编辑闭环重走（INT-1251 阻塞项解除后）—— React 测试设备编辑闭环。

覆盖：
- 新建（UI 提交全部字段）
- 编辑抽屉回显：逐个字段读 input value / select 文本，与 GET /test-devices/{id} 核对
- 改字段保存：改 名称/描述/型号/系统版本/应用名称/应用版本/序列号/连接方式 + 算法 chip，PUT 后 GET 核对
- 删除清理：删除自建记录，库内零残留
数据源：docker 真实库 :15000（intelligent_audio_test），防串库三次检查。
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
API = os.environ.get('API_BASE', 'http://127.0.0.1:15000')
ART = os.path.join('tests', 'ui', 'artifacts', 'int1333')
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
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def api_get(path):
    with urllib.request.urlopen(API + path) as r:
        return json.loads(r.read().decode())


def api_del(path):
    req = urllib.request.Request(API + path, method='DELETE')
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def drain_network(drv):
    """performance log 双层解包：外层 {method:'Network...', params:{requestId, ...}}。"""
    pairs = []
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry['message'])
                method = msg['message']['method']
                inner = msg['message']['params']
                if method == 'Network.requestWillBeSent':
                    req = inner['request']
                    url = req.get('url', '')
                    if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                        pairs.append({'kind': 'req', 'method': req.get('method'),
                                      'url': url, 'post': req.get('postData', '')[:400],
                                      'ts': inner.get('timestamp')})
                elif method == 'Network.responseReceived':
                    resp = inner['response']
                    url = resp.get('url', '')
                    if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                        pairs.append({'kind': 'resp', 'status': resp.get('status'),
                                      'url': url, 'ts': inner.get('timestamp')})
            except Exception:
                pass
    except Exception:
        pass
    return pairs


def show_net(label):
    print(f'--- NET [{label}] ---')
    for p in NETWORK[-40:]:
        if p['kind'] == 'req':
            print(f"  REQ {p['method']} {p['url']}")
            if p.get('post'):
                print(f"    body: {p['post']}")
        else:
            print(f"  RESP {p['status']} {p['url']}")


def fill_input(drv, label, value):
    xp = f"//label[contains(text(),'{label}')]/following-sibling::input[1]"
    el = drv.find_element(By.XPATH, xp)
    el.clear()
    el.send_keys(value)
    return el


def read_input(drv, label):
    xp = f"//label[contains(text(),'{label}')]/following-sibling::input[1]"
    el = drv.find_element(By.XPATH, xp)
    return el.get_attribute('value')


def read_select(drv, label):
    """base-ui SelectTrigger 是 button，取闭合态文本。"""
    xp = f"//label[contains(text(),'{label}')]/following-sibling::button[1]"
    el = drv.find_element(By.XPATH, xp)
    return el.text.strip()


def pick_select(drv, label, value):
    sel = drv.find_element(By.XPATH, f"//label[contains(text(),'{label}')]/following-sibling::button[1]")
    drv.execute_script('arguments[0].click()', sel)
    time.sleep(1)
    opt = drv.find_element(By.XPATH, f"//*[@role='option' and contains(.,'{value}')]")
    drv.execute_script('arguments[0].click()', opt)
    time.sleep(0.6)


def open_row_menu_edit(drv, row):
    ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
    drv.execute_script('arguments[0].click()', ops[0])
    time.sleep(1.2)
    menu = drv.find_element(By.XPATH, "//div[@role='menu']")
    edit_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='编辑']")
    if not edit_item:
        print('EDIT item NOT FOUND in menu')
        return False
    disabled = edit_item[0].get_attribute('aria-disabled') or edit_item[0].get_attribute('data-disabled')
    print('EDIT item disabled:', disabled)
    if disabled:
        return False
    drv.execute_script('arguments[0].click()', edit_item[0])
    time.sleep(2)
    return True


def find_row(drv, name):
    rows = drv.find_elements(By.XPATH, "//tbody/tr")
    for r in rows:
        if name in (r.text or ''):
            return r
    return None


def main():
    os.makedirs(ART, exist_ok=True)
    # 防串库 ① run 开始
    health = json.loads(urllib.request.urlopen(API + '/health').read().decode())
    print('HEALTH db:', health.get('database'))
    assert health.get('database') == 'intelligent_audio_test', 'DB WRONG'

    name = PREFIX + '编辑闭环A'
    name2 = name + '_改名'

    drv = _driver()
    created_id = None
    try:
        # ========== 新建（UI）==========
        drv.get(BASE + '/devices/test')
        time.sleep(6)
        NETWORK.extend(drain_network(drv))
        add_btn = drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]")
        drv.execute_script('arguments[0].click()', add_btn)
        time.sleep(2.5)
        fill_input(drv, '名称', name)
        fill_input(drv, '描述', '编辑闭环走查描述')
        fill_input(drv, '型号', 'Echo S1')
        fill_input(drv, '系统版本', '14')
        fill_input(drv, '应用名称', 'EchoApp')
        fill_input(drv, '应用版本', '3.1.0')
        fill_input(drv, '设备序列号', 'ECHO-SN-0001')
        pick_select(drv, '设备类型', '真机')
        pick_select(drv, '设备系统', 'Android')
        pick_select(drv, '连接方式', 'USB连接')
        drv.save_screenshot(os.path.join(ART, 'create-filled.png'))
        save_btn = drv.find_element(By.XPATH, "//button[contains(., '保存')]")
        NETWORK.clear()
        drv.execute_script('arguments[0].click()', save_btn)
        time.sleep(4)
        NETWORK.extend(drain_network(drv))
        show_net('create')
        toasts = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('CREATE TOASTS:', toasts)
        drv.save_screenshot(os.path.join(ART, 'create-result.png'))

        td = api_get('/api/v1/test-devices?page=1&per_page=1000')['data']['items']
        mine = [d for d in td if d['name'] == name]
        if not mine:
            print('FATAL: created device not found via API')
            return
        created_id = mine[0]['id']
        print('CREATED id:', created_id)

        # 防串库 ② 每批截图前
        health2 = json.loads(urllib.request.urlopen(API + '/health').read().decode())
        print('HEALTH db (before edit):', health2.get('database'))
        assert health2.get('database') == 'intelligent_audio_test'

        # ========== 编辑回显核对 ==========
        drv.get(BASE + '/devices/test')
        time.sleep(5)
        row = find_row(drv, name)
        assert row is not None, 'row not found for edit'
        ok = open_row_menu_edit(drv, row)
        print('EDIT drawer opened:', ok)
        if not ok:
            return
        drv.save_screenshot(os.path.join(ART, 'edit-drawer.png'))

        det = api_get(f'/api/v1/test-devices/{created_id}')['data']
        echo = {
            '名称': det.get('name'),
            '描述': det.get('description') or '',
            '型号': det.get('model'),
            '系统版本': det.get('system_version'),
            '应用名称': det.get('app_name'),
            '应用版本': det.get('app_version'),
            '设备序列号': det.get('serial_number'),
        }
        print('=== EDIT ECHO CHECK (input value vs GET) ===')
        all_ok = True
        for field, expected in echo.items():
            actual = read_input(drv, field)
            ok_ = (actual or '') == (expected or '')
            if not ok_:
                all_ok = False
            print(f'  {field}: drawer={actual!r} get={expected!r} {"✅" if ok_ else "❌"}')
        # selects
        sel_expect = {
            '设备类型': '真机',
            '设备系统': 'Android',
            '连接方式': 'USB连接',
        }
        for field, expected in sel_expect.items():
            actual = read_select(drv, field)
            ok_ = expected in (actual or '')
            if not ok_:
                all_ok = False
            print(f'  {field}[select]: drawer={actual!r} expect={expected!r} {"✅" if ok_ else "❌"}')
        print('ECHO ALL OK:', all_ok)

        # ========== 改字段保存 ==========
        fill_input(drv, '名称', name2)
        fill_input(drv, '型号', 'Echo S2')
        fill_input(drv, '系统版本', '15')
        fill_input(drv, '应用名称', 'EchoApp2')
        fill_input(drv, '应用版本', '4.0.0')
        fill_input(drv, '设备序列号', 'ECHO-SN-0002')
        pick_select(drv, '连接方式', '远程连接')
        # 算法 chip：真实选项「小艺语音大模型」（INT-1213）——点击选中后 PUT 带 supported_algorithms
        try:
            chip = drv.find_element(By.XPATH, "//label[contains(text(),'算法类型')]/following-sibling::div[1]//button[contains(.,'小艺语音大模型')]")
            drv.execute_script('arguments[0].click()', chip)
            time.sleep(0.5)
            print('algorithm chip 小艺语音大模型 toggled: selected', chip.get_attribute('class'))
        except Exception as e:
            print('algorithm chip click failed:', e)
        drv.save_screenshot(os.path.join(ART, 'edit-modified.png'))
        save_btn2 = drv.find_element(By.XPATH, "//button[contains(., '保存')]")
        NETWORK.clear()
        drv.execute_script('arguments[0].click()', save_btn2)
        time.sleep(4)
        NETWORK.extend(drain_network(drv))
        show_net('edit save')
        toasts2 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('EDIT TOASTS:', toasts2)
        drv.save_screenshot(os.path.join(ART, 'edit-saved.png'))

        # ========== GET 核对 ==========
        det2 = api_get(f'/api/v1/test-devices/{created_id}')['data']
        expect2 = {
            'name': name2, 'model': 'Echo S2', 'system_version': '15',
            'app_name': 'EchoApp2', 'app_version': '4.0.0',
            'serial_number': 'ECHO-SN-0002', 'connection_type': 'remote',
        }
        print('=== GET AFTER EDIT ===')
        all_ok2 = True
        for k, exp in expect2.items():
            act = det2.get(k)
            ok_ = act == exp
            if not ok_:
                all_ok2 = False
            print(f'  {k}: get={act!r} expect={exp!r} {"✅" if ok_ else "❌"}')
        print('  supported_algorithms:', det2.get('supported_algorithms'))
        print('AFTER EDIT ALL OK:', all_ok2)

        # 防串库 ③ 交付前
        health3 = json.loads(urllib.request.urlopen(API + '/health').read().decode())
        print('HEALTH db (delivery):', health3.get('database'))
        assert health3.get('database') == 'intelligent_audio_test'
    finally:
        # ========== 删除清理 ==========
        if created_id:
            st, body = api_del(f'/api/v1/test-devices/{created_id}')
            print('CLEANUP delete:', st, body[:120])
            # 确认库内无残留（软删后列表不可见；purge 前仅确认列表无自建数据）
            td = api_get('/api/v1/test-devices?page=1&per_page=1000')['data']['items']
            leftover = [d for d in td if d['name'].startswith(PREFIX)]
            print('LEFT OVER test devices with prefix:', leftover)
            if leftover:
                for d in leftover:
                    api_del(f"/api/v1/test-devices/{d['id']}")
                    print('  force deleted leftover', d['id'])
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
