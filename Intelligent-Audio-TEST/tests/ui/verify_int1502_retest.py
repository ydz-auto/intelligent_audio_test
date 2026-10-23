# -*- coding: utf-8 -*-
"""INT-1502 复测：增益映射表单「播放测试音」接真实 /spl/test-tone（测试工程师独立复核）。

两轮：
- --mode real：前端 dev server 直连 5700 真实库栈（audio_service 带 INT-95 影子夹具，
  POST /spl/test-tone 必回 4xx「没有找到可用的播放设备」）→ 验证请求形态 + 失败态处理。
- --mode stub：前端 dev server 指向 tests/ui/mock_int1502_test_tone.py（只替换两个端点，
  其余透传 5700）→ 验证 200 播放态、停止、关窗兜底停止。

用法：python tests/ui/verify_int1502_retest.py --base http://127.0.0.1:5360 --mode real --out real.json
"""
import argparse
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1502_retest')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')
MAPPING_NAME = '接线测试_INT1502复测_增益映射'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--force-prefers-reduced-motion')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
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


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
    time.sleep(0.2)
    drv.execute_script('arguments[0].click();', el)


def drain_perf(drv):
    try:
        drv.get_log('performance')
    except Exception:
        pass


def collect_network(drv):
    entries = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
        except Exception:
            continue
        payload = msg.get('message') or {}
        method = payload.get('method') or ''
        params = payload.get('params') or {}
        if method == 'Network.requestWillBeSent':
            req = params.get('request') or {}
            entries.append({
                'requestId': params.get('requestId'),
                'method': req.get('method'),
                'url': req.get('url'),
                'postData': req.get('postData'),
                'status': None,
            })
        elif method == 'Network.responseReceived':
            rid = params.get('requestId')
            for item in entries:
                if item['requestId'] == rid:
                    item['status'] = (params.get('response') or {}).get('status')
                    break
    return entries


def response_body(drv, request_id):
    try:
        return drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id}).get('body', '')
    except Exception as exc:  # noqa: BLE001
        return f'<unavailable: {exc}>'


def brief(drv, net):
    return [
        {
            'method': n['method'],
            'url': n['url'],
            'status': n['status'],
            'postData': n['postData'],
            'body': response_body(drv, n['requestId']) if n['status'] else None,
        }
        for n in net
    ]


def toasts(drv):
    out = []
    for el in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]'):
        try:
            text = (el.text or '').strip()
        except Exception:
            continue
        if text:
            out.append(text)
    return out


def wait_toast(drv, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        items = toasts(drv)
        if items:
            return items
        time.sleep(0.2)
    return []


def shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    path = os.path.join(ARTIFACTS, name)
    for attempt in range(3):
        try:
            drv.save_screenshot(path)
            print('screenshot ->', path)
            return path
        except Exception as exc:  # noqa: BLE001
            print('screenshot retry', attempt + 1, exc)
            time.sleep(1.5)
    import base64
    try:
        data = drv.execute_cdp_cmd('Page.captureScreenshot', {'format': 'png'})['data']
        with open(path, 'wb') as f:
            f.write(base64.b64decode(data))
        print('screenshot(cdp) ->', path)
    except Exception as exc:  # noqa: BLE001
        print('screenshot FAILED ->', path, exc)
    return path


def set_theme(drv, base, mode):
    drv.get(base + '/SPLMapping')
    time.sleep(1.0)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', %r)" % mode)
    drv.get('about:blank')
    drv.get(base + '/SPLMapping')
    time.sleep(2.5)


def login(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 25).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "input[placeholder='请输入用户名或邮箱']"))
    drv.find_element(By.CSS_SELECTOR, "input[placeholder='请输入用户名或邮箱']").send_keys(LOGIN_USER)
    drv.find_element(By.CSS_SELECTOR, "input[placeholder='请输入密码']").send_keys(LOGIN_PASS)
    js_click(drv, drv.find_element(By.CSS_SELECTOR, "button[type='submit']"))
    WebDriverWait(drv, 40).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def goto_page(drv, base):
    drv.get(base + '/SPLMapping')
    WebDriverWait(drv, 40).until(
        lambda d: '声压级映射管理' in d.find_element(By.TAG_NAME, 'body').text)
    time.sleep(4.0)


def open_create(drv):
    btns = drv.find_elements(By.XPATH, "//button[normalize-space(.)='添加增益映射']")
    assert btns, '未找到「添加增益映射」按钮'
    js_click(drv, btns[0])
    WebDriverWait(drv, 15).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
    time.sleep(0.8)


def play_button(drv, index=1):
    return drv.find_element(By.XPATH, f"//button[@aria-label='第 {index} 行播放测试音']")


def pick_device(drv, index=0):
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    trigger = dialog.find_element(
        By.CSS_SELECTOR, "[data-slot='select-trigger'][aria-label='关联播放设备']")
    options = []
    for _ in range(8):
        if trigger.get_attribute('aria-expanded') != 'true':
            js_click(drv, trigger)
        end = time.time() + 4.0
        while time.time() < end:
            options = drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
            if options:
                break
            time.sleep(0.2)
        if options:
            break
        try:
            trigger.send_keys('')
        except Exception:
            pass
        drv.execute_script('document.activeElement && document.activeElement.blur && document.activeElement.blur()')
        time.sleep(1.0)
    assert options, '关联播放设备下拉无选项'
    label = options[index].text
    js_click(drv, options[index])
    time.sleep(0.6)
    return label


def button(drv, text):
    els = drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{text}']")
    return els[-1] if els else None


def open_edit(drv, name):
    menu = drv.find_element(By.CSS_SELECTOR, f"button[aria-label='映射 {name} 的操作']")
    js_click(drv, menu)
    time.sleep(0.8)
    edit = drv.find_elements(By.XPATH, "//*[@role='menuitem'][normalize-space(.)='编辑']")
    assert edit, '行操作菜单无「编辑」'
    js_click(drv, edit[0])
    WebDriverWait(drv, 15).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
    time.sleep(1.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:5360')
    ap.add_argument('--mode', choices=['real', 'stub'], required=True)
    ap.add_argument('--out', default='evidence.json')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)
    ev = {'base': base, 'mode': args.mode, 'login_user': LOGIN_USER, 'steps': []}

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        login(drv, base)
        goto_page(drv, base)
        ev['api_host_probe'] = 'stub' if args.mode == 'stub' else 'real-5700'
        shot(drv, f'00_page_{args.mode}.png')

        # ---- A. 未选设备 → 提示 + 零请求 ----
        open_create(drv)
        drain_perf(drv)
        js_click(drv, play_button(drv))
        msgs = wait_toast(drv)
        net = collect_network(drv)
        tone_reqs = [n for n in net if '/spl/test-tone' in (n['url'] or '')]
        ev['steps'].append({'step': 'A 未选设备点播放', 'toasts': msgs,
                            'requests': brief(drv, tone_reqs),
                            'count': len(tone_reqs)})
        assert any('请先选择关联设备' in m for m in msgs), f'缺「请先选择关联设备」提示: {msgs}'
        assert not tone_reqs, f'未选设备仍下发请求: {tone_reqs}'
        shot(drv, f'01_no_device_{args.mode}.png')

        # ---- B. 选设备 + 新建映射 ----
        device_label = pick_device(drv, 0)
        ev['selected_device_label'] = device_label
        name_input = drv.find_element(By.CSS_SELECTOR, "input[aria-label='映射名称']")
        name_input.clear()
        name_input.send_keys(MAPPING_NAME)
        drain_perf(drv)
        js_click(drv, button(drv, '保存'))
        WebDriverWait(drv, 25).until_not(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        time.sleep(2.0)
        net = collect_network(drv)
        created = [n for n in net if (n['url'] or '').endswith('/api/v1/spl') and n['method'] == 'POST']
        body_text = drv.find_element(By.TAG_NAME, 'body').text
        ev['steps'].append({'step': 'B 新建映射', 'device_label': device_label,
                            'create': brief(drv, created), 'toasts': toasts(drv),
                            'row_visible': MAPPING_NAME in body_text})
        assert created, '新建未捕获 POST /api/v1/spl'
        assert MAPPING_NAME in body_text, '新建后列表未出现该映射'

        # ---- C. 编辑弹窗：设备回显 + 播放 ----
        open_edit(drv, MAPPING_NAME)
        dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
        echo = dialog.find_element(
            By.CSS_SELECTOR, "[data-slot='select-trigger'][aria-label='关联播放设备']").text
        shot(drv, f'02_edit_form_light_{args.mode}.png')
        drain_perf(drv)
        js_click(drv, play_button(drv))
        play_toasts = wait_toast(drv, 8.0)
        time.sleep(2.0)
        net = collect_network(drv)
        play_toasts += [t for t in toasts(drv) if t not in play_toasts]
        tone = [n for n in net if '/spl/test-tone' in (n['url'] or '') and not (n['url'] or '').endswith('/stop')]
        device_get = [n for n in net if '/playback-devices/' in (n['url'] or '')]
        pressed = play_button(drv).get_attribute('aria-pressed')
        ev['steps'].append({'step': 'C 编辑弹窗播放', 'device_echo': echo,
                            'device_get': brief(drv, device_get),
                            'test_tone': brief(drv, tone),
                            'toasts': play_toasts, 'aria_pressed': pressed})
        assert device_get, '播放前未捕获 GET /playback-devices/{id}'
        assert any(n['status'] == 200 for n in device_get), f'GET 设备非 200: {device_get}'
        assert tone, '播放未捕获 POST /spl/test-tone'
        tone_entry = tone[-1]
        assert '"unique_id"' in (tone_entry['postData'] or ''), f'请求体缺 unique_id: {tone_entry["postData"]}'
        assert '"gain_value"' in (tone_entry['postData'] or ''), f'请求体缺 gain_value: {tone_entry["postData"]}'
        shot(drv, f'03_after_play_{args.mode}.png')

        if args.mode == 'real':
            # 影子夹具下必然失败：断言失败态处理（提示后端 message、不进播放态）
            assert (tone_entry['status'] or 0) >= 400, f'真实栈意外成功: {tone_entry["status"]}'
            assert pressed != 'true', '播放失败后仍进入播放态'
            assert any('没有找到可用的播放设备' in t for t in play_toasts), f'未提示后端 message: {play_toasts}'
            # 关闭弹窗（无播放态 → 不应有 stop）
            drain_perf(drv)
            js_click(drv, button(drv, '取消'))
            WebDriverWait(drv, 10).until_not(
                lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
            time.sleep(1.5)
            net = collect_network(drv)
            stops = [n for n in net if '/spl/test-tone/stop' in (n['url'] or '')]
            ev['steps'].append({'step': 'D 未播放时关闭弹窗', 'stop_requests': brief(drv, stops)})
            assert not stops, '未进入播放态却下发了 stop'
        else:
            # 契约桩 200：进入播放态
            assert tone_entry['status'] == 200, f'桩播放非 200: {tone_entry["status"]}'
            assert pressed == 'true', '播放成功后未进入播放态'
            assert any('测试音已播放' in t for t in play_toasts), f'缺播放成功提示: {play_toasts}'
            unique = json.loads(tone_entry['postData']).get('unique_id')
            assert unique, '请求体 unique_id 为空'

            # ---- D. 播放中点停止 ----
            drain_perf(drv)
            js_click(drv, play_button(drv))
            time.sleep(2.5)
            net = collect_network(drv)
            stops = [n for n in net if '/spl/test-tone/stop' in (n['url'] or '')]
            pressed_after = play_button(drv).get_attribute('aria-pressed')
            ev['steps'].append({'step': 'D 播放中点停止', 'stop_requests': brief(drv, stops),
                                'toasts': toasts(drv), 'aria_pressed_after': pressed_after})
            assert stops, '点停止未捕获 POST /spl/test-tone/stop'
            assert json.loads(stops[-1]['postData'] or '{}').get('unique_id') == unique, '停止请求 unique_id 不一致'
            assert stops[-1]['status'] == 200, f'停止非 200: {stops[-1]["status"]}'
            assert pressed_after != 'true', '停止后仍为播放态'
            shot(drv, '04_stopped_stub.png')

            # ---- E. 再次播放 → 关闭弹窗兜底 stop ----
            drain_perf(drv)
            js_click(drv, play_button(drv))
            time.sleep(2.5)
            playing_again = play_button(drv).get_attribute('aria-pressed')
            drain_perf(drv)
            js_click(drv, button(drv, '取消'))
            WebDriverWait(drv, 10).until_not(
                lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
            time.sleep(2.0)
            net = collect_network(drv)
            close_stops = [n for n in net if '/spl/test-tone/stop' in (n['url'] or '')]
            ev['steps'].append({'step': 'E 播放中关闭弹窗', 'aria_pressed_before_close': playing_again,
                                'stop_requests': brief(drv, close_stops)})
            assert playing_again == 'true', '再次播放未进入播放态'
            assert close_stops, '关闭弹窗未下发 stop'
            assert close_stops[-1]['status'] == 200, f'关窗 stop 非 200: {close_stops[-1]["status"]}'

        # ---- F. 深色主题截图 ----
        set_theme(drv, base, 'dark')
        open_edit(drv, MAPPING_NAME)
        shot(drv, f'05_edit_form_dark_{args.mode}.png')
        drain_perf(drv)
        js_click(drv, play_button(drv))
        wait_toast(drv, 6.0)
        time.sleep(1.5)
        shot(drv, f'06_after_play_dark_{args.mode}.png')
        dark_pressed = play_button(drv).get_attribute('aria-pressed')
        ev['steps'].append({'step': 'F 深色播放', 'aria_pressed': dark_pressed,
                            'toasts': toasts(drv)})
        js_click(drv, button(drv, '取消'))
        WebDriverWait(drv, 10).until_not(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        time.sleep(1.5)

        # ---- G. 清理 ----
        set_theme(drv, base, 'light')
        goto_page(drv, base)
        removed = False
        for _ in range(6):
            menus = drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='映射 {MAPPING_NAME} 的操作']")
            if not menus:
                removed = True
                break
            js_click(drv, menus[0])
            time.sleep(0.8)
            dels = drv.find_elements(By.XPATH, "//*[@role='menuitem'][normalize-space(.)='删除']")
            if not dels:
                break
            js_click(drv, dels[0])
            time.sleep(1.0)
            confirm = drv.find_elements(
                By.XPATH, "//button[normalize-space(.)='删除' and not(@role='menuitem')]")
            if confirm:
                js_click(drv, confirm[-1])
            time.sleep(2.5)
        body_text = drv.find_element(By.TAG_NAME, 'body').text
        removed = removed and MAPPING_NAME not in body_text
        ev['steps'].append({'step': 'G 清理自建映射', 'removed': removed, 'toasts': toasts(drv)})
        assert removed, '自建映射未能删除（测试数据残留）'

        ev['ok'] = True
        print(json.dumps(ev, ensure_ascii=False, indent=2))
    finally:
        ev['ok'] = ev.get('ok', False)
        with open(os.path.join(ARTIFACTS, args.out), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        drv.quit()


if __name__ == '__main__':
    main()
