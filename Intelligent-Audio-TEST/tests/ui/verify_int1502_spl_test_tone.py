# -*- coding: utf-8 -*-
"""INT-1502 浏览器实测：增益映射表单「播放测试音」接真实 POST /spl/test-tone。

真实库（主库 intelligent_audio_test，本轮经 5700 网关；docker 15173 栈被其它 run
维护停摆）。headless Chrome + CDP performance log 取证。

覆盖（卡内验收三条）：
1) 未选关联设备点播放 → toast「请先选择关联设备」，**无** POST /spl/test-tone
2) 选设备后点播放 → GET /playback-devices/{id} 取 unique_id + POST /spl/test-tone
   （body gain_value/gain_offset/target_spl/unique_id），播放态以响应结果为准
3) 播放中点停止 → POST /spl/test-tone/stop；关闭弹窗同样 stop

顺带闭环：新建「接线测试_INT1502_」映射 → 列表回读 → 编辑回显 → 删除清理。

用法：
  python tests/ui/verify_int1502_spl_test_tone.py [--base http://127.0.0.1:5352]
输出：tests/ui/artifacts/int1502_spl_test_tone/ 下截图 + evidence.json
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1502_spl_test_tone')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
LOGIN_USER = os.environ.get('IAT_LOGIN_USER', '接线测试_admin')
LOGIN_PASS = os.environ.get('IAT_LOGIN_PASS', 'JieXianTest@2026')
MAPPING_NAME = '接线测试_INT1502_增益映射'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    # 弹窗动画在 headless 下偶尔卡住合成器导致截图超时 → 强制减弱动效
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
            return
        except Exception as exc:  # noqa: BLE001
            print('screenshot retry', attempt + 1, exc)
            time.sleep(1.5)
    # 兜底：CDP 直取（绕过 WebDriver 的渲染 ack 等待）
    import base64
    try:
        data = drv.execute_cdp_cmd('Page.captureScreenshot', {'format': 'png'})['data']
        with open(path, 'wb') as f:
            f.write(base64.b64decode(data))
        print('screenshot(cdp) ->', path)
    except Exception as exc:  # noqa: BLE001
        print('screenshot FAILED ->', path, exc)


def set_theme(drv, base, mode, path='/SPLMapping'):
    drv.get(base + path)
    time.sleep(1.0)
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', %r)" % mode)
    drv.get('about:blank')
    drv.get(base + path)
    time.sleep(2.5)


def login(drv, base):
    drv.get(base + '/login')
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "input[placeholder='请输入用户名或邮箱']"))
    drv.find_element(By.CSS_SELECTOR, "input[placeholder='请输入用户名或邮箱']").send_keys(LOGIN_USER)
    drv.find_element(By.CSS_SELECTOR, "input[placeholder='请输入密码']").send_keys(LOGIN_PASS)
    js_click(drv, drv.find_element(By.CSS_SELECTOR, "button[type='submit']"))
    WebDriverWait(drv, 30).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)
    print('logged in ->', drv.current_url)


def goto_page(drv, base):
    drv.get(base + '/SPLMapping')
    WebDriverWait(drv, 40).until(
        lambda d: '声压级映射管理' in d.find_element(By.TAG_NAME, 'body').text)
    # 等页面级 GET /playback-devices 返回（下拉选项来源），避免空下拉
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
    # 弹窗内的关联播放设备 Select（页面图片筛选等其它 Select 无此 aria-label）
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    trigger = dialog.find_element(
        By.CSS_SELECTOR, "[data-slot='select-trigger'][aria-label='关联播放设备']")
    options = []
    for _ in range(6):
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
        # 下拉已展开但无选项（页面播放设备查询尚未返回）：收起后重试
        try:
            trigger.send_keys('')  # ESC
        except Exception:
            pass
        drv.execute_script('document.activeElement && document.activeElement.blur && document.activeElement.blur()')
        time.sleep(1.0)
    assert options, '关联播放设备下拉无选项'
    label = options[index].text
    js_click(drv, options[index])
    time.sleep(0.6)
    return label


def primary_button(drv, text):
    els = drv.find_elements(By.XPATH, f"//button[normalize-space(.)='{text}']")
    return els[-1] if els else None


def tone_summary(drv, net):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5352'))
    ap.add_argument('--out', default='evidence.json', help='证据文件名（区分真实栈 / 契约桩两轮）')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    evidence_path = os.path.join(ARTIFACTS, args.out)
    os.makedirs(ARTIFACTS, exist_ok=True)

    evidence = {'base': base, 'login_user': LOGIN_USER, 'mapping_name': MAPPING_NAME, 'steps': []}
    drv = _driver()
    try:
        drv.set_page_load_timeout(45)
        login(drv, base)
        goto_page(drv, base)

        # ========== A. 新建：未选设备点播放 → 提示且无请求 ==========
        open_create(drv)
        drain_perf(drv)
        js_click(drv, play_button(drv))
        msgs = wait_toast(drv)
        net = collect_network(drv)
        tone_reqs = [n for n in net if '/spl/test-tone' in (n['url'] or '')]
        evidence['steps'].append({
            'step': 'A 未选设备点播放',
            'toasts': msgs,
            'test_tone_requests': tone_summary(drv, tone_reqs),
        })
        assert any('请先选择关联设备' in m for m in msgs), f'未出现「请先选择关联设备」提示: {msgs}'
        assert not tone_reqs, f'未选设备仍下发了测试音请求: {tone_reqs}'
        shot(drv, '01_no_device_light.png')

        # ========== B. 选设备 → 保存（建立可编辑映射） ==========
        device_label = pick_device(drv, 0)
        name_input = drv.find_element(By.CSS_SELECTOR, "input[aria-label='映射名称']")
        name_input.clear()
        name_input.send_keys(MAPPING_NAME)
        drain_perf(drv)
        save = primary_button(drv, '保存')
        js_click(drv, save)
        WebDriverWait(drv, 20).until_not(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        time.sleep(2.0)
        net = collect_network(drv)
        created = [n for n in net if (n['url'] or '').endswith('/api/v1/spl') and n['method'] == 'POST']
        body = drv.find_element(By.TAG_NAME, 'body').text
        evidence['steps'].append({
            'step': 'B 新建映射（含关联设备）',
            'device_label': device_label,
            'create_request': tone_summary(drv, created),
            'toasts': toasts(drv),
            'row_visible': MAPPING_NAME in body,
        })
        assert created, '新建映射未捕获 POST /spl'
        assert MAPPING_NAME in body, '新建后列表未出现该映射'

        # ========== C. 编辑回显 → 播放（真实 test-tone） ==========
        menu = drv.find_element(By.CSS_SELECTOR, f"button[aria-label='映射 {MAPPING_NAME} 的操作']")
        js_click(drv, menu)
        time.sleep(0.8)
        edit = drv.find_elements(By.XPATH, "//*[@role='menuitem'][normalize-space(.)='编辑']")
        assert edit, '行操作菜单无「编辑」'
        js_click(drv, edit[0])
        WebDriverWait(drv, 15).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
        time.sleep(1.2)
        selected_device = drv.find_element(
            By.CSS_SELECTOR, "[data-slot='select-trigger'][aria-label='关联播放设备']").text
        shot(drv, '02_edit_form_light.png')

        drain_perf(drv)
        js_click(drv, play_button(drv))
        play_toasts = wait_toast(drv, 8.0)
        time.sleep(2.0)
        net = collect_network(drv)
        play_toasts += [t for t in toasts(drv) if t not in play_toasts]
        tone = [n for n in net if '/spl/test-tone' in (n['url'] or '') and not (n['url'] or '').endswith('/stop')]
        device_get = [n for n in net if '/playback-devices/' in (n['url'] or '')]
        playing = play_button(drv).get_attribute('aria-pressed')
        evidence['steps'].append({
            'step': 'C 编辑弹窗选设备后点播放',
            'device_echo': selected_device,
            'device_get': tone_summary(drv, device_get),
            'test_tone': tone_summary(drv, tone),
            'toasts': play_toasts,
            'aria_pressed_after_play': playing,
        })
        assert tone, '选设备后未捕获 POST /spl/test-tone'
        shot(drv, '03_after_play_light.png')

        # ========== D. 停止（仅播放态成立时） ==========
        if playing == 'true':
            drain_perf(drv)
            js_click(drv, play_button(drv))
            time.sleep(3.0)
            net = collect_network(drv)
            stop_reqs = [n for n in net if '/spl/test-tone/stop' in (n['url'] or '')]
            evidence['steps'].append({
                'step': 'D 播放中点停止',
                'stop_requests': tone_summary(drv, stop_reqs),
                'toasts': toasts(drv),
                'aria_pressed_after_stop': play_button(drv).get_attribute('aria-pressed'),
            })
            assert stop_reqs, '播放态点停止未捕获 POST /spl/test-tone/stop'
            shot(drv, '04_stopped_light.png')
        else:
            evidence['steps'].append({
                'step': 'D 播放中点停止',
                'skipped': '后端未返回播放态（见 C 的 test_tone 响应），停止链路待有音频输出设备的环境复验',
            })

        # ========== E. 关闭弹窗 ==========
        cancel = primary_button(drv, '取消')
        if cancel:
            drain_perf(drv)
            js_click(drv, cancel)
            WebDriverWait(drv, 10).until_not(
                lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
            time.sleep(1.5)
            net = collect_network(drv)
            close_stops = [n for n in net if '/spl/test-tone/stop' in (n['url'] or '')]
            evidence['steps'].append({
                'step': 'E 关闭弹窗',
                'stop_requests': tone_summary(drv, close_stops),
            })

        # ========== F. 深色截图 + 关闭弹窗兜底停止 ==========
        set_theme(drv, base, 'dark')
        open_create(drv)
        pick_device(drv, 0)
        time.sleep(0.6)
        js_click(drv, play_button(drv))
        dark_toasts = wait_toast(drv, 6.0)
        time.sleep(2.0)
        shot(drv, '05_form_dark.png')
        playing_dark = play_button(drv).get_attribute('aria-pressed')
        drain_perf(drv)
        cancel = primary_button(drv, '取消')
        if cancel:
            js_click(drv, cancel)
            WebDriverWait(drv, 10).until_not(
                lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
            time.sleep(2.0)
            net = collect_network(drv)
            close_stops = [n for n in net if '/spl/test-tone/stop' in (n['url'] or '')]
            evidence['steps'].append({
                'step': 'F 深色弹窗播放后关闭（停止兜底）',
                'toasts': dark_toasts,
                'aria_pressed_before_close': playing_dark,
                'stop_requests': tone_summary(drv, close_stops),
            })
            if playing_dark == 'true':
                assert close_stops, '关闭弹窗未捕获 POST /spl/test-tone/stop'
        else:
            evidence['steps'].append({'step': 'F 深色弹窗', 'toasts': dark_toasts})

        # ========== G. 清理：删除本 run 自建映射 ==========
        goto_page(drv, base)
        removed_all = True
        for _ in range(6):
            menu = drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='映射 {MAPPING_NAME} 的操作']")
            if not menu:
                break
            js_click(drv, menu[0])
            time.sleep(0.8)
            delete = drv.find_elements(By.XPATH, "//*[@role='menuitem'][normalize-space(.)='删除']")
            if not delete:
                removed_all = False
                break
            js_click(drv, delete[0])
            time.sleep(1.0)
            confirm = drv.find_elements(
                By.XPATH, "//button[normalize-space(.)='删除' and not(@role='menuitem')]")
            if confirm:
                js_click(drv, confirm[-1])
            time.sleep(2.5)
        body = drv.find_element(By.TAG_NAME, 'body').text
        evidence['steps'].append({
            'step': 'G 删除自建映射',
            'removed': MAPPING_NAME not in body and removed_all,
            'toasts': toasts(drv),
        })

        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        print('INT-1502 验证脚本完成')
    finally:
        try:
            with open(evidence_path, 'w', encoding='utf-8') as f:
                json.dump(evidence, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        drv.quit()


if __name__ == '__main__':
    main()
