# -*- coding: utf-8 -*-
"""INT-644 设备页 infra mock→api 浏览器验收（devicesApi 经 client.ts 切真实后端）。

针对 frontend-react/ 的 pnpm build 产物（dist 直出），静态服务 :5301 代理 /api → 本 run
隔离后端网关 :8500（V9.7.31 主仓库 parallel_stack +3500，AUTH_MODE=off 免认证，隔离库
intelligent_audio_test_test）。真实 Chrome headless。

覆盖验收标准：
① 测试设备页签：真实后端设备列表渲染（badge「在线 x/共 y」与后端 total 一致、行数据与
   GET /test-devices 一致）、无 mock 名残留（音箱-客厅位/手机-小米12 等不得出现）；
② 监控告警面板：真实 stats（本库为空 → 待处理 0 + 空态「暂无告警」）与历史监控空态；
③ 设备详情弹窗：真实字段渲染；
④ 新增测试设备（真实 POST）→ 批量删除（真实 DELETE，前端串行 §11-7）往返；
⑤ 播放设备页签空态、测试 API 页签真实列表（无 mock 名残留）；
⑥ 深浅色截图 + console 无 SEVERE。
失败落 tests/ui/artifacts/int644_devices/<用例>/（截图+console+source）。
"""
import json
import os
import time

import httpx
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int644_devices')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5301')
API_BASE = os.environ.get('INT644_API_BASE', 'http://127.0.0.1:8500/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 旧 mock 名（INT-644 前 devices-mock.ts 常量化设备名）——验收「无 mock 残留」
OLD_MOCK_NAMES = ['音箱-客厅位', '音箱-卧室位', '音箱-入门-03', '手机-小米12', '手机-华为P60', '音柱-会议室']
# 新增测试数据前缀（测试数据卫生：创建后即删除）
TEST_PREFIX = '接线测试_INT644_'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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
    drv.set_page_load_timeout(45)
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
    except Exception:
        pass


@pytest.fixture(scope='module')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    yield _DRIVER
    try:
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _goto(drv, path, theme='light'):
    """先注入登录态+主题，再访问页面（真实后端 AUTH_MODE=off 免 token；admin 态过路由守卫）。"""
    drv.get(BASE + '/login')
    time.sleep(0.8)
    drv.execute_script(
        "try { window.localStorage.clear() } catch (e) {}")
    snapshot = {
        'state': {
            'user': {
                'id': 'mock-admin-001',
                'username': 'admin',
                'displayName': '演示管理员',
                'roleName': '超级管理员',
                'permissions': ['*'],
            }
        },
        'version': 0,
    }
    drv.execute_script(
        "window.localStorage.setItem('iatp:auth:v1', arguments[0])",
        json.dumps(snapshot, ensure_ascii=False))
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.get(BASE + path)
    WebDriverWait(drv, 35).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    # 应用壳渲染（侧栏「工作台」）确认 SPA bootstrap 完成
    WebDriverWait(drv, 25).until(lambda d: '工作台' in _body_text(d))
    time.sleep(1.6)


def _api(path):
    r = httpx.get(API_BASE + path, timeout=15, trust_env=False)
    r.raise_for_status()
    return r.json()


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content' or @data-slot='alert-dialog-content']"
        f"[.//*[@data-slot='dialog-title' or @data-slot='alert-dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 10).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _drawer(drv):
    el = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']"))
    return el


def _select_in_field(drv, sheet, label, option_text):
    """Sheet 内某 label 字段的 base-ui Select：点 trigger → 在 portal 里点 option。"""
    trigger = sheet.find_element(
        By.XPATH, f"//label[contains(., '{label}')]/following-sibling::button[@data-slot='select-trigger']")
    trigger.click()
    time.sleep(0.5)
    for content in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content']"):
        for item in content.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']"):
            if option_text in item.text:
                item.click()
                time.sleep(0.4)
                return
    raise AssertionError(f'Select「{label}」缺选项「{option_text}」')


def _fill_test_device_form(drv, sheet, name, model):
    """填写测试设备创建表单（§6.2 必填：名称/型号/设备类型/设备系统/系统版本/应用名称/应用版本/连接方式/序列号）。"""
    sheet.find_element(By.XPATH, ".//input[@placeholder='如：音箱-客厅位']").send_keys(name)
    sheet.find_element(By.XPATH, ".//input[@placeholder='如：旗舰 S1']").send_keys(model)
    _select_in_field(drv, sheet, '设备类型', '真机')
    _select_in_field(drv, sheet, '设备系统', 'HarmonyOS')
    sheet.find_element(By.XPATH, ".//input[@placeholder='如：12']").send_keys('12')
    sheet.find_element(
        By.XPATH, "//label[contains(., '应用名称')]/following-sibling::input").send_keys('测试应用')
    sheet.find_element(
        By.XPATH, "//label[contains(., '应用版本')]/following-sibling::input").send_keys('1.0.0')
    _select_in_field(drv, sheet, '连接方式', 'USB连接')
    sheet.find_element(By.XPATH, ".//input[@placeholder='连接后自动填充']").send_keys('SN-' + name[-8:])


def _toast_text(drv):
    time.sleep(0.4)
    toasts = drv.find_elements(By.CSS_SELECTOR, "li[data-sonner-toast]")
    if not toasts:
        return ''
    return '\n'.join(t.text for t in toasts)


def _console_severe(drv):
    sev = []
    for entry in drv.get_log('browser'):
        if entry.get('level') == 'SEVERE':
            sev.append(entry)
    return sev


def _assert_no_mock(drv, label=''):
    body = _body_text(drv)
    for name in OLD_MOCK_NAMES:
        assert name not in body, f'{label} mock 名残留「{name}」'


def _api_first_test_device_name():
    data = _api('/test-devices?page=1&per_page=1000')
    items = (data.get('data') or {}).get('items') or []
    return items[0]['name'] if items else None


def _api_first_api_name():
    data = _api('/apis?page=1&per_page=1000')
    items = (data.get('data') or {}).get('items') or []
    return items[0]['name'] if items else None


def _api_test_total():
    data = _api('/test-devices?page=1&per_page=1000')
    return (data.get('data') or {}).get('total') or 0


def _api_find_test_device(name):
    """全量拉取后前端侧按名过滤（与页面前端筛选同口径；不依赖后端 keyword 语义）。"""
    data = _api('/test-devices?page=1&per_page=1000')
    items = (data.get('data') or {}).get('items') or []
    return [i for i in items if i.get('name') == name]


# ── ① 测试设备页签：真实列表 + 无 mock 残留 + 深浅色 ──
def test_01_test_devices_real_list_light_dark(drv):
    _goto(drv, '/devices/test', theme='light')
    WebDriverWait(drv, 15).until(
        lambda d: '设备管理' in _body_text(d))
    body = _body_text(drv)
    total = _api_test_total()
    assert f'在线 ' in body and f'共 {total}' in body, \
        f'badge「在线 x/共 {total}」缺失：{body[:400]}'
    # 统计徽章行（§9 四枚）
    for label in ['总设备数', '在线设备', '离线设备', '异常设备']:
        assert label in body, f'统计徽章缺「{label}」'
    # 后端首设备名出现在页面（真实请求 ↔ 渲染一致）
    first = _api_first_test_device_name()
    if first:
        assert first in body, f'后端设备「{first}」未渲染'
    _assert_no_mock(drv, '[light]')
    _save_evidence('01_test_devices_light', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'

    # 深色
    _goto(drv, '/devices/test', theme='dark')
    WebDriverWait(drv, 15).until(
        lambda d: '设备管理' in _body_text(d))
    _save_evidence('02_test_devices_dark', drv)
    assert not _console_severe(drv), f'dark console SEVERE: {_console_severe(drv)}'


# ── ② 监控告警面板：真实 stats（本库空 → 待处理 0 + 空态）──
def test_02_alarm_panel_stats_and_empty(drv):
    _goto(drv, '/devices/test', theme='light')
    WebDriverWait(drv, 15).until(lambda d: '设备管理' in _body_text(d))
    # 开关②「监控告警面板」（base-ui Switch 渲染为 span[role=switch]，点 label 不会切换）
    sw = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//span[@role='switch'][@aria-label='监控告警面板']"))
    sw.click()
    time.sleep(1.2)
    body = _body_text(drv)
    assert '待处理' in body and '已确认' in body and '已恢复' in body, \
        f'告警统计徽章缺失：{body[:500]}'
    assert '告警列表' in body and '暂无告警' in body, '告警空态缺失'
    # 历史监控空态
    hist_tab = drv.find_element(By.XPATH, "//button[@role='tab'][contains(., '历史监控')]")
    hist_tab.click()
    time.sleep(1.0)
    assert '暂无历史记录' in _body_text(drv), '历史监控空态缺失'
    _save_evidence('03_alarm_panel_empty', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'


# ── ③ 设备详情弹窗：真实字段 ──
def test_03_device_detail_dialog(drv):
    _goto(drv, '/devices/test', theme='light')
    WebDriverWait(drv, 15).until(lambda d: '设备管理' in _body_text(d))
    first = _api_first_test_device_name()
    assert first, '后端无测试设备可开详情'
    row = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, f"//*[contains(., '{first}')]"))
    # 行操作 → 详情
    op = drv.find_element(By.XPATH, f"//button[@aria-label='操作 {first}']")
    op.click()
    time.sleep(0.8)
    drv.find_element(By.XPATH, "//div[@role='menu']//*[contains(., '详情')]").click()
    time.sleep(1.0)
    dlg = _dialog_by_title(drv, '测试设备详情')
    assert first in dlg.text, '详情弹窗未含设备名'
    _save_evidence('04_device_detail_light', drv)
    dlg.find_element(By.XPATH, ".//button[contains(., '关闭')]").click()
    time.sleep(0.5)


# ── ④ 新增测试设备（真实 POST）→ 批量删除（真实 DELETE）──
def test_04_create_and_batch_delete_device(drv):
    name = TEST_PREFIX + str(int(time.time()))
    _goto(drv, '/devices/test', theme='light')
    WebDriverWait(drv, 15).until(lambda d: '设备管理' in _body_text(d))
    # 新增按钮 → 抽屉
    drv.find_element(By.XPATH, "//button[contains(., '添加测试设备')]").click()
    time.sleep(1.0)
    sheet = _drawer(drv)
    _fill_test_device_form(drv, sheet, name, '旗舰 S1')
    _save_evidence('05_create_device_drawer_filled', drv)
    sheet.find_element(By.XPATH, ".//button[@type='submit'][contains(., '保存')]").click()
    WebDriverWait(drv, 15).until(lambda d: '测试设备已保存' in _toast_text(d))
    # 后端确认（真实 POST）
    time.sleep(1.2)
    assert _api_find_test_device(name), 'POST 后后端未见新设备'
    _save_evidence('06_after_create', drv)

    # 页面出现新行 → 开启批量操作模式 → 勾选 → 批量删除（删除钮在底部悬浮批量条内）
    WebDriverWait(drv, 12).until(
        lambda d: name in _body_text(d))
    bm_switch = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//span[@role='switch'][@aria-label='批量操作模式']"))
    bm_switch.click()
    time.sleep(0.8)
    _save_evidence('06b_batch_mode_on', drv)
    # 批量模式开启后行勾选 checkbox 才渲染
    cbs = drv.find_elements(By.XPATH, "//*[@role='checkbox']")
    assert any(cb.get_attribute('aria-label') == f'选择设备 {name}' for cb in cbs), \
        f'批量模式下行勾选缺失：{[(cb.get_attribute("aria-label") or "") for cb in cbs][:8]}'
    cb = next(cb for cb in cbs if cb.get_attribute('aria-label') == f'选择设备 {name}')
    drv.execute_script('arguments[0].click();', cb)
    time.sleep(0.9)
    _save_evidence('06c_device_selected', drv)
    bulk_bar = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个已选择')]]"))
    bulk_bar.find_element(By.XPATH, ".//button[contains(., '删除')]").click()
    time.sleep(0.8)
    dlg = _dialog_by_title(drv, '批量操作')
    assert '批量删除' in dlg.text, f'批量确认弹窗缺文案：{dlg.text[:200]}'
    dlg.find_element(By.XPATH, ".//button[contains(., '批量删除')]").click()
    WebDriverWait(drv, 15).until(
        lambda d: '批量删除完成' in _toast_text(d))
    # 后端确认已删（真实 DELETE）
    time.sleep(1.2)
    assert not _api_find_test_device(name), f'DELETE 后后端仍存在：{name}'
    _save_evidence('07_after_batch_delete', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'


# ── ⑤ 播放设备空态 + 测试 API 真实列表 ──
def test_05_playback_empty_and_api_real_list(drv):
    # 播放设备：本库无未删播放设备 → 空态
    _goto(drv, '/devices/playback', theme='light')
    WebDriverWait(drv, 15).until(
        lambda d: '设备管理' in _body_text(d))
    body = _body_text(drv)
    assert '播放设备' in body
    # 本库无未删除播放设备 → 空态（§表格空文案：暂无播放设备）
    assert '暂无播放设备' in body, f'播放设备空态缺失：{body[:400]}'
    assert '在线 0/共 0' in body, f'播放设备 badge 应为 0/0：{body[:200]}'
    _assert_no_mock(drv, '[playback]')
    _save_evidence('08_playback_empty_light', drv)

    # 测试 API：真实列表
    _goto(drv, '/devices/api', theme='light')
    WebDriverWait(drv, 15).until(lambda d: '设备管理' in _body_text(d))
    body = _body_text(drv)
    api_first = _api_first_api_name()
    if api_first:
        assert api_first in body, f'后端 API「{api_first}」未渲染'
    for label in ['总测试API数', '可用API', '不可用API', '测试中API']:
        assert label in body, f'API 统计徽章缺「{label}」'
    _assert_no_mock(drv, '[api]')
    _save_evidence('09_api_real_list_light', drv)

    # 深色 API 页
    _goto(drv, '/devices/api', theme='dark')
    WebDriverWait(drv, 15).until(lambda d: '设备管理' in _body_text(d))
    _save_evidence('10_api_real_list_dark', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'
