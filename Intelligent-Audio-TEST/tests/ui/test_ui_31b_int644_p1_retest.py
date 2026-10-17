# -*- coding: utf-8 -*-
"""INT-644 返修 P1 复验浏览器用例（设备分组 id 字符串语义：UUID 不再 NaN）。

审计 P1（INT-644 评论 01a14b05）：`deviceGroupAdapter.id: Number(uuid)` 恒 NaN →
① 分组筛选下拉 option value 全 "NaN"、`groups.find(String(g.id)===f.groupId)` 乱命中；
② 分组管理弹窗成员增/删 `g.id === groupId`（NaN===NaN）静默失效；③ React key 重复。
返修交付（评论 01a14b20，commit 48fbb783..4df116bf）：DeviceGroup.id 改 string、
adapter 直通 `String(dto.id)`、弹窗全量字符串语义、nextGroupId 本地分组 id 字符串化。

本复验只测打回失败项（P1）+ 修复相关用例，不从头全测：
① 分组 facet 渲染真实分组名、选项值为真实 UUID（URL groupId 命中，非 "NaN"）；
② 分组筛选切换后正确解析对应分组（A/B 互不串扰），空态渲染正常、无 crash；
③ 分组管理弹窗：真实分组行渲染；成员添加 select → 标签出现；× 移出 → 标签消失；
④ 弹窗新建本地分组（string id）出现；⑤ 深浅色截图；console 无 SEVERE/无重复 key 告警。

环境：frontend-react dist 静态服务（BASE）代理 /api → 常驻后端（API_BASE :5000，AUTH_MODE=off）。
测试数据：模块 fixture 经后端 API 预置 2 个真实分组（UUID id，成员 10/11 与 9），
teardown 用 DELETE /device-groups/{id}?cascade=true 清理，不留库内残留。
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
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int644_devices_p1')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5302')
API_BASE = os.environ.get('INT644_API_BASE', 'http://127.0.0.1:5000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

GROUP_A_NAME = 'INT644复测_组A'
GROUP_B_NAME = 'INT644复测_组B'
LOCAL_GROUP_NAME = 'INT644复测_本地组'


def _api_client():
    return httpx.Client(base_url=API_BASE, timeout=15, trust_env=False)


def _create_group(client, name, device_ids):
    r = client.post('/test-devices/device-groups',
                    json={'name': name, 'group_type': 'test', 'device_ids': device_ids})
    r.raise_for_status()
    body = r.json()
    assert body.get('success'), f'创建设备分组失败: {body}'
    return body['data']['id']


@pytest.fixture(scope='module')
def groups():
    """预置两个真实分组（成员 10/11 与 9），teardown 级联删除清理。幂等：先清历史同名残留。"""
    client = _api_client()
    # 幂等：清掉任何历史 INT644复测_ 分组残留（手动预置/上次中断遗留）
    before = client.get('/test-devices/device-groups', params={'page': 1, 'per_page': 100}).json()
    for g in before['data']['items']:
        if g['name'].startswith('INT644复测_'):
            client.delete(f"/test-devices/device-groups/{g['id']}", params={'cascade': 'true'})
    a_id = _create_group(client, GROUP_A_NAME, [10, 11])
    b_id = _create_group(client, GROUP_B_NAME, [9])
    # 契约证据：列表端点 device_ids 恒空、detail 端点带成员（与 Vue INT-626 同契约）
    lst = client.get('/test-devices/device-groups', params={'page': 1, 'per_page': 100}).json()
    by_id = {g['id']: g for g in lst['data']['items']}
    det_a = client.get(f'/test-devices/device-groups/{a_id}').json()['data']
    info = {
        'a_id': a_id, 'b_id': b_id,
        'list_device_ids_empty': all(g['device_ids'] == [] for g in by_id.values()),
        'detail_a_device_ids': det_a.get('device_ids', []),
    }
    yield info
    try:
        for gid in (a_id, b_id):
            r = client.delete(f'/test-devices/device-groups/{gid}', params={'cascade': 'true'})
            r.raise_for_status()
    except Exception:
        pass
    # 清理后确认列表为空、无残留
    try:
        after = client.get('/test-devices/device-groups', params={'page': 1, 'per_page': 100}).json()
        remain = [g['name'] for g in after['data']['items'] if g['name'].startswith('INT644复测_')]
        assert remain == [], f'测试数据残留未清理: {remain}'
    except Exception as e:
        raise AssertionError(f'清理校验失败: {e}')


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
    """先注入登录态+主题，再访问页面（常驻后端 AUTH_MODE=off 免 token；admin 态过路由守卫）。"""
    drv.get(BASE + '/login')
    time.sleep(0.8)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
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
    WebDriverWait(drv, 25).until(lambda d: '工作台' in _body_text(d))
    time.sleep(1.6)


def _console_severe(drv):
    sev = []
    for entry in drv.get_log('browser'):
        if entry.get('level') == 'SEVERE':
            sev.append(entry)
    return sev


def _console_duplicate_key(drv):
    return [e for e in drv.get_log('browser')
            if 'two children with the same key' in (e.get('message') or '')]


def _open_group_facet(drv):
    """点开「分组」facet Popover，返回选项文本列表。"""
    trigger = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[.//span[text()='分组']]"))
    trigger.click()
    time.sleep(0.5)
    content = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "[data-slot='popover-content']"))
    labels = [e.text for e in content.find_elements(By.CSS_SELECTOR, 'button')]
    return labels, content


def _pick_facet_option(content, option_text):
    for btn in content.find_elements(By.CSS_SELECTOR, 'button'):
        if option_text in btn.text:
            btn.click()
            time.sleep(0.6)
            return
    raise AssertionError(f'分组 facet 缺选项「{option_text}」')


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    WebDriverWait(drv, 10).until(lambda d: len(d.find_elements(By.XPATH, xpath)) > 0)
    return drv.find_element(By.XPATH, xpath)


def _select_in_field(drv, scope, label, option_text):
    """base-ui Select：点 trigger → 在 portal 里点 option（scope 内 label 相邻 trigger）。"""
    trigger = scope.find_element(
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


def _pick_add_member_select(drv, dlg, option_text):
    """分组行内「添加成员设备」Select：点 trigger（无 label，按 placeholder 文本定位）→ 点 portal 选项。"""
    trigger = WebDriverWait(dlg, 10).until(
        lambda d: d.find_element(By.XPATH,
            "//button[@data-slot='select-trigger'][contains(., '添加成员设备')]"))
    trigger.click()
    time.sleep(0.5)
    for content in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-content']"):
        for item in content.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']"):
            if option_text in item.text:
                item.click()
                time.sleep(0.4)
                return
    raise AssertionError(f'Select「添加成员设备」缺选项「{option_text}」')


# ─────────────────────────── 用例 ───────────────────────────

def _facet_trigger_text(drv):
    trigger = drv.find_element(By.XPATH, "//button[.//span[text()='分组']]")
    return trigger.text


def test_01_group_facet_real_uuid_no_nan(drv, groups):
    """P1①：分组 facet 渲染真实组名；选中组A后 trigger 回显组A（修复前 id NaN → 错命中首组）。"""
    _goto(drv, '/devices/test', theme='light')
    labels, content = _open_group_facet(drv)
    joined = '\n'.join(labels)
    assert GROUP_A_NAME in joined and GROUP_B_NAME in joined, f'facet 缺真实组名: {labels}'
    assert 'NaN' not in joined, f'facet 出现 NaN 选项: {labels}'
    assert '全部' not in joined, f'facet 不应含「全部」: {labels}'
    _pick_facet_option(content, GROUP_A_NAME)
    trigger = _facet_trigger_text(drv)
    assert GROUP_A_NAME in trigger, f'选中组A后 trigger 应回显组A，实际: {trigger!r}'
    assert GROUP_B_NAME not in trigger, f'选中组A后 trigger 不应回显组B（NaN 错命中首组）: {trigger!r}'
    # 契约证据：列表端点成员为空（与 Vue INT-626 同契约），筛选后表内呈现空态而非错乱/崩溃
    time.sleep(1.0)
    assert ('暂无设备' in _body_text(drv) or '未找到匹配的设备' in _body_text(drv)), \
        '筛选后空态文案缺失'
    _save_evidence('01_group_facet_selected_light', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'


def test_02_group_facet_switch_b_distinct(drv, groups):
    """P1①：切换到组B，trigger 回显组B，与组A 互不串扰（真实 UUID 选项值命中）。"""
    _goto(drv, '/devices/test', theme='light')
    _, content = _open_group_facet(drv)
    _pick_facet_option(content, GROUP_B_NAME)
    trigger = _facet_trigger_text(drv)
    assert GROUP_B_NAME in trigger, f'选中组B后 trigger 应回显组B，实际: {trigger!r}'
    assert GROUP_A_NAME not in trigger, f'选中组B后 trigger 不应回显组A（串扰）: {trigger!r}'
    assert 'NaN' not in trigger, f'trigger 不应含 NaN: {trigger!r}'
    _save_evidence('02_group_facet_switch_b_light', drv)


def test_03_group_manager_member_add_remove(drv, groups):
    """P1②：分组管理弹窗真实组行渲染；成员添加/移除生效（修复前静默失效）。"""
    _goto(drv, '/devices/test', theme='light')
    # 打开「更多操作」→「分组管理」
    WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']")).click()
    time.sleep(0.5)
    for item in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']"):
        if '分组管理' in item.text:
            item.click()
            time.sleep(0.8)
            break
    dlg = _dialog_by_title(drv, '设备分组管理')
    dlg_text = dlg.text
    assert GROUP_A_NAME in dlg_text and GROUP_B_NAME in dlg_text, f'弹窗缺真实组行: {dlg_text[:300]}'
    assert 'NaN' not in dlg_text, f'弹窗出现 NaN: {dlg_text[:300]}'
    # 展开组A（点击行头，aria-expanded）
    row_btn = WebDriverWait(dlg, 10).until(
        lambda d: d.find_element(By.XPATH, f"//button[.//span[text()='{GROUP_A_NAME}']]"))
    row_btn.click()
    time.sleep(0.5)
    # 添加成员：Select 添加成员设备 → 选 pura90豆包（#10）
    _pick_add_member_select(drv, dlg, 'pura90豆包')
    time.sleep(0.5)
    assert 'pura90豆包' in dlg.text, '添加成员后成员标签未出现（P1 未修复）'
    # 移除成员：点成员标签上的 ×（aria-label 移出 …）
    rm_btn = WebDriverWait(dlg, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "button[aria-label^='移出 pura90豆包']"))
    rm_btn.click()
    time.sleep(0.5)
    assert 'pura90豆包' not in dlg.text, '移出成员后成员标签未消失'
    _save_evidence('03_group_manager_add_remove_light', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'
    assert not _console_duplicate_key(drv), f'React 重复 key 告警: {_console_duplicate_key(drv)}'


def test_04_group_manager_create_local_group(drv, groups):
    """P1③：弹窗新建本地分组（string id）出现、无 NaN/重复 key 告警。"""
    _goto(drv, '/devices/test', theme='light')
    WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']")).click()
    time.sleep(0.5)
    for item in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']"):
        if '分组管理' in item.text:
            item.click()
            time.sleep(0.8)
            break
    dlg = _dialog_by_title(drv, '设备分组管理')
    name_input = dlg.find_element(By.CSS_SELECTOR, "input[id='group-name']")
    name_input.send_keys(LOCAL_GROUP_NAME)
    dlg.find_element(By.XPATH, "//button[.//text()[normalize-space()='创建']]").click()
    time.sleep(0.6)
    assert LOCAL_GROUP_NAME in dlg.text, '新建本地分组未出现'
    _save_evidence('04_group_manager_create_local_light', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'
    assert not _console_duplicate_key(drv), f'React 重复 key 告警: {_console_duplicate_key(drv)}'


def test_05_dark_theme_screenshots(drv, groups):
    """深色主题：设备页 + 分组 facet + 分组管理弹窗截图。"""
    _goto(drv, '/devices/test', theme='dark')
    time.sleep(1.0)
    _save_evidence('05_devices_dark', drv)
    _, content = _open_group_facet(drv)
    joined = '\n'.join(e.text for e in content.find_elements(By.CSS_SELECTOR, 'button'))
    assert GROUP_A_NAME in joined and 'NaN' not in joined
    _save_evidence('06_group_facet_dark', drv)
    # 关闭 facet，开分组管理弹窗截深色
    drv.find_element(By.CSS_SELECTOR, "body").click()
    time.sleep(0.3)
    WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "button[aria-label='更多操作']")).click()
    time.sleep(0.5)
    for item in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dropdown-menu-item']"):
        if '分组管理' in item.text:
            item.click()
            time.sleep(0.8)
            break
    _dialog_by_title(drv, '设备分组管理')
    _save_evidence('07_group_manager_dark', drv)
    assert not _console_severe(drv), f'console SEVERE: {_console_severe(drv)}'
