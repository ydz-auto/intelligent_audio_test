# -*- coding: utf-8 -*-
"""INT-1251 walkthrough part 3 (robust): API devices CRUD + batch ops + playback."""
import json
import os
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

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
                    pairs.append(('REQ', req.get('method'), url, req.get('postData', '')[:500]))
            elif method == 'Network.responseReceived':
                resp = inner['params']['response']
                url = resp['url']
                if '/api/v1/' in url and 'socket.io' not in url and 'sse' not in url:
                    pairs.append(('RESP', str(resp.get('status')), url, ''))
        except Exception:
            pass
    return pairs


def show_net(label):
    print(f'--- NET [{label}] ---')
    for k, m, u, b in NETWORK[-30:]:
        print(f"  {k} {m} {u}")
        if b:
            print(f"     body: {b}")


def fill_input(drv, label, value):
    xp = f"//label[contains(normalize-space(.),'{label}')]/following-sibling::input[1]"
    el = drv.find_element(By.XPATH, xp)
    el.clear()
    el.send_keys(value)
    time.sleep(0.2)
    return el


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
    assert health.get('database') == 'intelligent_audio_test'

    drv = _driver()
    api_id = None
    batch_ids = []
    try:
        drv.set_page_load_timeout(60)

        # ============ API devices tab ============
        drv.get(BASE + '/devices/api')
        time.sleep(6)
        click_btn(drv, '添加测试API')
        time.sleep(2.5)
        aname = PREFIX + 'API设备A'
        fill_input(drv, '名称', aname)
        fill_input(drv, '供应商', 'WalkVendor')
        fill_input(drv, 'API 端点', 'https://api.walk.test/v1/asr')
        # protocol default https; env default testing; algorithm default asr_streaming
        # set proxy: 代理类型 HTTP + 代理地址
        pick_select(drv, '代理类型', 'HTTP')
        fill_input(drv, '代理地址', 'user:pass@127.0.0.1:8080')
        drv.save_screenshot(os.path.join(ART, 'api-add-filled.png'))
        NETWORK.clear()
        click_btn(drv, '保存')
        time.sleep(4)
        NETWORK.extend(drain(drv))
        show_net('create api device')
        # validation errors?
        dlg = drv.find_elements(By.XPATH, "//div[@role='dialog']")
        if dlg:
            errs = [l for l in dlg[0].text.split('\n') if '请填写' in l or '必填' in l or '代理' in l]
            print('API create drawer still open, errors:', errs)
        toasts = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('API CREATE TOASTS:', toasts)

        apis = api_get('/api/v1/apis?page=1&per_page=1000')['data']['items']
        mine = [a for a in apis if a['name'] == aname]
        print('API created:', [(a['id'], a['name']) for a in mine])
        if mine:
            api_id = mine[0]['id']
            det = api_get(f'/api/v1/apis/{api_id}')['data']
            print('GET /apis/{id}:')
            for k in ('name', 'vendor', 'api_url', 'proxy_type', 'proxy_url', 'algorithm_type', 'status', 'meta'):
                print(f'  {k}: {det.get(k)!r}')
        else:
            print('API CREATE FAILED — no record in backend')

        # edit
        if api_id:
            drv.get(BASE + '/devices/api')
            time.sleep(5)
            rows = drv.find_elements(By.XPATH, "//tbody/tr")
            row = None
            for r in rows:
                if aname in r.text:
                    row = r
                    break
            if row:
                ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
                if ops:
                    drv.execute_script('arguments[0].click()', ops[0])
                    time.sleep(1.2)
                    menu = drv.find_element(By.XPATH, "//div[@role='menu']")
                    edit_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='编辑']")
                    if edit_item:
                        disabled = edit_item[0].get_attribute('aria-disabled')
                        print('API EDIT disabled:', disabled)
                        if not disabled:
                            drv.execute_script('arguments[0].click()', edit_item[0])
                            time.sleep(2.5)
                            drawer = drv.find_element(By.XPATH, "//div[@role='dialog']")
                            dtext = drawer.text
                            print('API edit echo name:', aname in dtext)
                            print('API edit echo vendor:', 'WalkVendor' in dtext)
                            print('API edit echo apiUrl:', 'https://api.walk.test/v1/asr' in dtext)
                            print('API edit echo proxyUrl:', 'user:pass@127.0.0.1:8080' in dtext)
                            drv.save_screenshot(os.path.join(ART, 'api-edit-echo.png'))
                            # change proxy url + name
                            fill_input(drv, '代理地址', 'user2:pass2@127.0.0.1:8081')
                            NETWORK.clear()
                            click_btn(drv, '保存')
                            time.sleep(4)
                            NETWORK.extend(drain(drv))
                            show_net('edit api device')
                            toasts2 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                            print('API EDIT TOASTS:', toasts2)
                            det2 = api_get(f'/api/v1/apis/{api_id}')['data']
                            print('AFTER API EDIT proxy_url:', det2.get('proxy_url'))

        # ============ Batch ops on test devices ============
        for i in range(3):
            body = json.dumps({'name': f'{PREFIX}批量{i}', 'model': 'BatchM', 'type': 'physical',
                               'system': 'Android', 'system_version': '11', 'app_name': 'B',
                               'app_version': '1', 'connection_type': 'usb',
                               'serial_number': f'BATCH-SN-{i}'}, ensure_ascii=False).encode()
            req = urllib.request.Request('http://127.0.0.1:15000/api/v1/test-devices', data=body,
                                         headers={'Content-Type': 'application/json'})
            r = urllib.request.urlopen(req)
            new_id = json.loads(r.read().decode())['data']['id']
            batch_ids.append(new_id)
        print('batch created ids:', batch_ids)

        drv.get(BASE + '/devices/test')
        time.sleep(5)
        # enable 批量操作模式 (span role=switch)
        sw = drv.find_element(By.XPATH, "//*[@data-slot='switch'][@aria-label='批量操作模式']")
        drv.execute_script('arguments[0].click()', sw)
        time.sleep(2)
        print('batchMode aria-checked:', sw.get_attribute('aria-checked'))
        # wait for checkboxes to render
        time.sleep(1)
        cbs = drv.find_elements(By.XPATH, "//*[@data-slot='checkbox'][starts-with(@aria-label,'选择设备')]")
        print('checkbox count after batchMode:', len(cbs))
        # select our rows
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        sel = 0
        for r in rows:
            if PREFIX + '批量' in r.text:
                cb = r.find_elements(By.XPATH, ".//*[@data-slot='checkbox'][starts-with(@aria-label,'选择设备')]")
                if cb:
                    drv.execute_script('arguments[0].click()', cb[0])
                    sel += 1
                    time.sleep(0.4)
        print('selected rows:', sel)
        time.sleep(1)
        bulk = drv.find_elements(By.XPATH, "//*[contains(text(),'个已选择')]")
        print('bulk bar:', [b.text for b in bulk] or 'NOT SHOWN')
        drv.save_screenshot(os.path.join(ART, 'bulk-selected.png'))

        # batch health check (connect/reboot may fail on offline; health_check is batch action)
        hbtns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='健康检查']")
        print('health check btn count:', len(hbtns))
        if hbtns:
            NETWORK.clear()
            drv.execute_script('arguments[0].click()', hbtns[-1])
            time.sleep(1.5)
            cbtn = drv.find_elements(By.XPATH, "//button[normalize-space(.)='确认执行']")
            if cbtn:
                drv.execute_script('arguments[0].click()', cbtn[-1])
                time.sleep(4)
                NETWORK.extend(drain(drv))
                show_net('batch health_check')
                toasts3 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                print('BATCH HEALTH TOASTS:', toasts3)
        drv.save_screenshot(os.path.join(ART, 'bulk-health-result.png'))

        # batch delete
        time.sleep(1)
        rows = drv.find_elements(By.XPATH, "//tbody/tr")
        for r in rows:
            if PREFIX + '批量' in r.text:
                cb = r.find_elements(By.XPATH, ".//*[@data-slot='checkbox'][starts-with(@aria-label,'选择设备')]")
                if cb:
                    drv.execute_script('arguments[0].click()', cb[0])
                    time.sleep(0.4)
        time.sleep(1)
        del_btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除']")
        print('bulk delete btn count:', len(del_btns))
        if del_btns:
            NETWORK.clear()
            drv.execute_script('arguments[0].click()', del_btns[-1])
            time.sleep(1.5)
            cdel = drv.find_elements(By.XPATH, "//button[normalize-space(.)='批量删除']")
            if cdel:
                drv.execute_script('arguments[0].click()', cdel[-1])
                time.sleep(4)
                NETWORK.extend(drain(drv))
                show_net('batch delete')
                toasts4 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                print('BATCH DELETE TOASTS:', toasts4)
        td = api_get('/api/v1/test-devices?page=1&per_page=1000')['data']['items']
        remain = [d for d in td if d['name'].startswith(PREFIX + '批量')]
        print('batch records remaining via API:', [(d['id'], d['name']) for d in remain])

        # ============ playback create ============
        drv.get(BASE + '/devices/playback')
        time.sleep(5)
        drv.save_screenshot(os.path.join(ART, 'playback-list-light.png'))
        click_btn(drv, '添加播放设备')
        time.sleep(2.5)
        pname = PREFIX + '播放设备A'
        fill_input(drv, '名称', pname)
        fill_input(drv, '型号', 'PlaybackModel1')
        fill_input(drv, '系统唯一标识', 'PB-UNIQUE-001')
        fill_input(drv, '采样率', '48000')
        NETWORK.clear()
        click_btn(drv, '保存')
        time.sleep(4)
        NETWORK.extend(drain(drv))
        show_net('create playback device')
        toasts5 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
        print('PLAYBACK CREATE TOASTS:', toasts5)
        pbs = api_get('/api/v1/playback-devices?page=1&per_page=1000')['data']['items']
        mine_pb = [p for p in pbs if p['name'] == pname]
        print('playback created:', [(p['id'], p['name']) for p in mine_pb])
        if mine_pb:
            pb_id = mine_pb[0]['id']
            # delete via UI row action
            time.sleep(2)
            rows = drv.find_elements(By.XPATH, "//tbody/tr")
            row = None
            for r in rows:
                if pname in r.text:
                    row = r
                    break
            if row:
                ops = row.find_elements(By.XPATH, ".//button[starts-with(@aria-label,'操作')]")
                if ops:
                    drv.execute_script('arguments[0].click()', ops[0])
                    time.sleep(1.2)
                    menu = drv.find_element(By.XPATH, "//div[@role='menu']")
                    del_item = menu.find_elements(By.XPATH, ".//*[normalize-space(.)='删除']")
                    if del_item:
                        NETWORK.clear()
                        drv.execute_script('arguments[0].click()', del_item[0])
                        time.sleep(1.5)
                        # confirm dialog: destructive button text 删除
                        cdel2 = drv.find_elements(By.XPATH, "//button[normalize-space(.)='删除']")
                        if cdel2:
                            drv.execute_script('arguments[0].click()', cdel2[-1])
                            time.sleep(4)
                            NETWORK.extend(drain(drv))
                            show_net('delete playback device')
                            toasts6 = [t.text for t in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]
                            print('PLAYBACK DELETE TOASTS:', toasts6)
            pbs2 = api_get('/api/v1/playback-devices?page=1&per_page=1000')['data']['items']
            remain_pb = [p for p in pbs2 if p['name'] == pname]
            if remain_pb:
                print('playback still exists — cleanup via API:', api_del(f"/api/v1/playback-devices/{remain_pb[0]['id']}"))
            else:
                print('playback deleted OK')

    finally:
        if api_id:
            print('API CLEANUP:', api_del(f'/api/v1/apis/{api_id}'))
        for bid in batch_ids:
            print('CLEANUP batch', bid, api_del(f'/api/v1/test-devices/{bid}'))
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()