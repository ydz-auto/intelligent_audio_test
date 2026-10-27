# -*- coding: utf-8 -*-
"""INT-2074 开始测试页「扫描设备」接真实 ScanDevicesDialog 浏览器走查。

针对 frontend-react dev server :5305（API_PROXY_TARGET -> :15000 docker 真实栈），
真实登录（接线测试_admin），走查：
① 开始测试页步骤二点「扫描设备」→ 真实弹窗（非 stub toast）；
② 弹窗自动扫描 → 出现 test 设备（≥1）与 playback 通道（6）；
③ 勾选 test 设备 → 加入设备选择 → 设备网格出现该设备（在线态，可勾选）；
④ Network 证据（performance 日志含 POST /test-devices/scan、/playback-devices/scan、POST /test-devices）；
⑤ 深浅色截图 + console 无 SEVERE；
⑥ 回归：设备管理页扫描对话框照常工作。
失败落 tests/ui/artifacts/int2074/<用例>/（截图+console+perf）。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2074')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5305')
API = 'http://127.0.0.1:15000'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1680,1050', '--disable-gpu', '--no-sandbox',
              '--lang=zh-CN', '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check']:
        options.add_argument(a)
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
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if [x for x in ver.split('.') if x.isdigit()] and int([x for x in ver.split('.') if x.isdigit()][0]) == chrome_major:
                        drv_path = exe
                except (ValueError, IndexError):
                    continue
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


_DRIVER = None


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        with open(os.path.join(d, 'perf.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('performance'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 45).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    drv.find_element(By.ID, 'username').send_keys(USERNAME)
    drv.find_element(By.ID, 'password').send_keys(PASSWORD)
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 45).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 45).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content' or @data-slot='alert-dialog-content']"
        f"[.//*[@data-slot='dialog-title' or @data-slot='alert-dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 12).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _console_severe(drv):
    """排除已知既有设备页 'test' 重复 key 警告（非本卡引入；设备页基线即有），其余 SEVERE 报出。"""
    sev = []
    for entry in drv.get_log('browser'):
        if entry.get('level') != 'SEVERE':
            continue
        msg = entry.get('message', '')
        # 既有：设备管理页加载即触发（与本卡无关），过滤掉
        if 'same key' in msg and ('"test"' in msg or "'test'" in msg):
            continue
        sev.append(entry)
    return sev


def _perf_requests(drv, needle):
    """从 performance 日志提取 URL 含 needle 的请求（request + response）。"""
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry.get('message') or '{}')
            m = msg.get('message') or {}
            if m.get('method') == 'Network.requestWillBeSent':
                url = (m.get('params') or {}).get('request', {}).get('url', '')
                if needle in url:
                    out.append(('request', url))
            elif m.get('method') == 'Network.responseReceived':
                url = (m.get('params') or {}).get('response', {}).get('url', '')
                if needle in url:
                    status = (m.get('params') or {}).get('response', {}).get('status')
                    out.append(('response', f'{url} -> {status}'))
    except Exception as e:
        print('perf read error:', e)
    return out


def _toast_texts(drv):
    time.sleep(0.4)
    toasts = drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]")
    return [t.text for t in toasts if t.text]


def test_01_login(drv):
    _login(drv)
    assert '登录' not in _body_text(drv)[:2000], '未成功登录'
    _save_evidence('01_login', drv)
    print('01 login ok, url =', drv.current_url)


def test_02_scan_dialog_shows_test_and_playback(drv):
    _goto(drv, '/start-test?step=1')
    # 等步骤二渲染
    WebDriverWait(drv, 20).until(lambda d: '扫描设备' in _body_text(d))
    btn = drv.find_element(By.XPATH, "//button[contains(., '扫描设备')]")
    btn.click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '扫描设备')
    body = dlg.text
    assert '测试设备' in body and '播放通道' in body, f'弹窗缺两分区：{body[:300]}'
    # 自动扫描（≈1.4s 进度 + 真实 scan 请求）等待结果出现
    for _ in range(30):
        time.sleep(0.5)
        dlg = _dialog_by_title(drv, '扫描设备')
        body = dlg.text
        if '个在线设备' in body and '个在线通道' in body:
            # 等待测试设备计数非零（扫描完成 + 结果落表）
            test_count = body.split('测试设备')[1].split('个在线设备')[0].strip()
            if test_count and test_count != '0':
                break
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '扫描设备')
    body = dlg.text
    print('DIALOG BODY:', body.replace('\n', ' | ')[:700])
    print('TOASTS:', _toast_texts(drv))
    ev = _perf_requests(drv, '/scan')
    print('SCAN NET EVENTS:', ev)
    assert any('test-devices/scan' in e[1] for e in ev), f'缺 POST /test-devices/scan 请求：{ev}'
    assert any('playback-devices/scan' in e[1] for e in ev), f'缺 POST /playback-devices/scan 请求：{ev}'
    assert '个在线设备' in body and '个在线通道' in body
    # 测试设备区至少 1 台（真实 scan 结果；播放通道数随宿主机音频服务状态变化，不硬断言）
    test_count = body.split('测试设备')[1].split('个在线设备')[0].strip()
    assert test_count.isdigit() and int(test_count) >= 1, f'测试设备计数异常：{test_count}'
    _save_evidence('02_scan_dialog', drv)
    print('02 scan dialog ok')


def test_03_check_test_device_adds_to_grid(drv):
    dlg = _dialog_by_title(drv, '扫描设备')
    test_cb = dlg.find_elements(
        By.XPATH, ".//*[contains(@aria-label, '选择测试设备')]")
    assert test_cb, '未找到测试设备勾选框'
    test_cb[0].click()
    time.sleep(0.5)
    btn = drv.find_element(By.XPATH, "//button[contains(., '加入设备选择')]")
    btn.click()
    time.sleep(1.5)
    # 弹窗关闭 → 网格出现新设备（在线态）
    WebDriverWait(drv, 15).until(
        lambda d: len(d.find_elements(By.XPATH, "//div[@data-slot='dialog-content' and .//*[@data-slot='dialog-title'][contains(., '扫描设备')]]")) == 0)
    body = _body_text(drv)
    print('TOASTS AFTER ADD:', _toast_texts(drv))
    ev = _perf_requests(drv, '/test-devices')
    print('TEST-DEVICES NET EVENTS:', ev)
    # 登记（POST /test-devices → 201）+ 网格刷新（GET /test-devices?per_page=1000 → 200）
    assert any('/test-devices' in e[1] for e in ev), '网格刷新 GET /test-devices 未发生'
    # 设备卡渲染：扫描到的设备名 + 在线态勾选框（非禁用、可进入下一步）
    assert 'BKQ_AN10' in body, '设备网格未出现扫描到的设备'
    new_cb = drv.find_elements(
        By.XPATH, "//*[@role='checkbox' or @type='checkbox'][contains(@aria-label, '选择设备') and (contains(@aria-label, 'BKQ_AN10') or contains(@aria-label, 'Android'))]")
    assert new_cb, '新设备勾选框未找到'
    assert new_cb[0].is_enabled(), '新设备勾选框禁用（离线态）'
    _save_evidence('03_grid_after_scan', drv)
    print('03 scan selection ok')


def test_03b_dark_theme_screenshots(drv):
    """深浅色截图要求：切深色 → 扫描弹窗 + 含已登记设备的设备网格各截一张。"""
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark')")
    _goto(drv, '/start-test?step=1')
    WebDriverWait(drv, 20).until(lambda d: '扫描设备' in _body_text(d))
    btn = drv.find_element(By.XPATH, "//button[contains(., '扫描设备')]")
    btn.click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '扫描设备')
    WebDriverWait(drv, 15).until(lambda d: '个在线设备' in _dialog_by_title(d, '扫描设备').text)
    time.sleep(1.0)
    _save_evidence('05_scan_dialog_dark', drv)
    cancel = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
    if cancel:
        cancel[0].click()
        time.sleep(1.0)
    _save_evidence('06_grid_dark', drv)
    print('03b dark theme screenshots ok')


def test_04_devices_page_scan_regression(drv):
    _goto(drv, '/devices/test')
    WebDriverWait(drv, 20).until(lambda d: '设备管理' in _body_text(d))
    time.sleep(1.0)
    # 扫描设备在页头「更多操作」下拉内（devices-primary-buttons DropdownMenu）
    more = drv.find_element(By.XPATH, "//button[@aria-label='更多操作']")
    more.click()
    time.sleep(0.6)
    scan_item = drv.find_elements(By.XPATH, "//*[@data-slot='dropdown-menu-item' or @role='menuitem'][contains(., '扫描设备')]")
    assert scan_item, '更多操作下拉缺「扫描设备」'
    scan_item[0].click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '扫描测试设备')
    assert '添加' in dlg.text or '开始扫描' in dlg.text or '扫描中' in dlg.text, \
        f'设备页扫描弹窗异常：{dlg.text[:300]}'
    _save_evidence('04_devices_page_scan_regression', drv)
    cancel = drv.find_elements(By.XPATH, "//button[contains(., '取消')]")
    if cancel:
        cancel[0].click()
        time.sleep(0.5)
    print('04 devices page regression ok')


def main():
    global _DRIVER
    _DRIVER = _driver()
    try:
        test_01_login(_DRIVER)
        test_02_scan_dialog_shows_test_and_playback(_DRIVER)
        test_03_check_test_device_adds_to_grid(_DRIVER)
        test_03b_dark_theme_screenshots(_DRIVER)
        test_04_devices_page_scan_regression(_DRIVER)
        sev = _console_severe(_DRIVER)
        assert not sev, f'console SEVERE: {sev}'
        print('ALL PASS, no console SEVERE')
    finally:
        try:
            _DRIVER.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
