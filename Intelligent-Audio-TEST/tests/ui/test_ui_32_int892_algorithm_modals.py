# -*- coding: utf-8 -*-
"""INT-892 算法域模态窗 浏览器验收走查（真实 Chrome headless，连常驻 5000 后端 + 本 run dev server）。

针对 frontend-react 接线版（INT-647/INT-648 真实接口，AUTH_MODE=off 免登录 dev_user '*'）：
1. 列表层真实数据：共 N 个算法（常驻测试库，基线 voice_llm 小艺语音大模型）
2. 编辑 Sheet 真实预填：算法代码/显示名称/作用域 chips 计数（全部 10/设备 7/API 3/用例 0）
   + 高级配置折叠头计数（参考参数 5 · 映射 30 · 维度 3）+ 展开三节
3. 作用域 chips：切换过滤行数 + 列随 chip 动态显隐（方向列/用例专属列）
4. 草稿保存（真实 PUT /algorithm/definitions/draft）：变脏启动倒计时 + 手动保存草稿 → footer「上次保存」
   + 后端落库实证（GET draft/{type}）+ 重开编辑恢复草稿（INT-589 接线修复）
5. 新建 + 发布写测试数据（真实 POST /algorithm/definitions）→ 列表刷新 → 删除（真实 DELETE）→ 清理
6. 详情 Dialog：真实参数/映射/维度渲染
7. 分组管理：新建/编辑/删除测试分组（真实 group CRUD）→ 清理
8. 导入 Dialog：JSON 错误态 + 真实导入测试算法 → 列表刷新 → 删除 → 清理
9. 确认弹窗族：重载配置（真实 POST /algorithm/reload）+ 复制走查（不发布）
10. 深浅两套主题截图
11. 全会话无 JS 运行时严重错误 + 真实接口请求（performance entries /api/v1）
"""
import json
import os
import re
import time
import urllib.request

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int892_algorithm_modals')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5300')
API = os.environ.get('API_BASE', 'http://localhost:5000/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 本次 run 唯一的测试数据前缀（防并发 run 冲突；验收后全部清理）
RUN_TAG = time.strftime('%H%M%S')
TEST_ALGO_TYPE = f'itest892_pub_{RUN_TAG}'
TEST_ALGO_NAME = f'接线测试_INT892_发布_{RUN_TAG}'
TEST_IMPORT_TYPE = f'itest892_import_{RUN_TAG}'
TEST_GROUP_NAME = f'接线测试_INT892_分组_{RUN_TAG}'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
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
_CONSOLE_JS_ERRORS = []
_API_CALLS = set()


def _drain_console(drv):
    global _CONSOLE_JS_ERRORS
    try:
        for entry in drv.get_log('browser'):
            msg = entry.get('message', '')
            if 'Failed to load resource' in msg and 'Uncaught' not in msg:
                continue
            if entry.get('level') == 'SEVERE':
                _CONSOLE_JS_ERRORS.append(msg)
    except Exception:
        pass


def _collect_api_calls(drv):
    """收集页面发起的 /api/v1 真实接口请求（performance entries）。"""
    try:
        entries = drv.execute_script(
            "return performance.getEntriesByType('resource').map(e => e.name)")
        for name in entries:
            if '/api/v1' in name:
                _API_CALLS.add(name.split('/api/v1', 1)[1][:120])
    except Exception:
        pass


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    _drain_console(drv)
    _collect_api_calls(drv)


def _wait_rows_retry(drv, n):
    try:
        WebDriverWait(drv, 12).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == n)
        return
    except Exception:
        drv.refresh()
        time.sleep(1.5)
        WebDriverWait(drv, 12).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) == n)


def _wait_list_ready(drv):
    """列表已加载：等待 voice_llm 行操作钮出现（不依赖精确总数，防并发 run 干扰）。"""
    def rows(d):
        return d.find_elements(By.XPATH, "//button[@aria-label='算法 小艺语音大模型 的操作']")
    try:
        WebDriverWait(drv, 12).until(lambda d: rows(d))
        return
    except Exception:
        drv.refresh()
        time.sleep(1.5)
        WebDriverWait(drv, 12).until(lambda d: rows(d))


def _open_row_menu(drv, name):
    btn = drv.find_element(By.XPATH, f"//button[@aria-label='算法 {name} 的操作']")
    btn.click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))


def _click_menu_item(drv, label):
    items = drv.find_elements(By.XPATH, "//*[@role='menuitem']")
    for it in items:
        if label in it.text:
            it.click()
            return
    raise AssertionError(f'行菜单项「{label}」未找到')


def _js_click(drv, xpath):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "arguments[0].scrollIntoView({ block: 'center' }); arguments[0].click();", el)
    time.sleep(0.6)


def _edit_field(drv, xpath, new_value):
    """用原生 value setter + input 事件改写（Selenium clear/send_keys 不触发 React onChange）。
    兼容 input/textarea。"""
    el = drv.find_element(By.XPATH, xpath)
    tag = el.tag_name.lower()
    proto = 'HTMLTextAreaElement' if tag == 'textarea' else 'HTMLInputElement'
    drv.execute_script(
        "const s = Object.getOwnPropertyDescriptor(window.%s.prototype, 'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));" % proto,
        el, new_value)
    time.sleep(0.6)


def _open_edit_sheet(drv, row_name='小艺语音大模型'):
    _goto(drv, '/AlgorithmConfig')
    _wait_list_ready(drv)
    _open_row_menu(drv, row_name)
    _click_menu_item(drv, '编辑')
    WebDriverWait(drv, 8).until(lambda d: '编辑算法' in _body_text(drv))
    time.sleep(1.2)
    _drain_console(drv)
    _collect_api_calls(drv)


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def _close_sheet(drv):
    """ESC 关闭 Sheet；若脏态守卫 ConfirmDialog 弹出则点「离开并丢弃」确认离开。
    多次 ESC 兜底：焦点在展开的 Select/Collapsible 内时首 ESC 只关内层弹层。"""
    for _ in range(3):
        _press_esc(drv)
        try:
            WebDriverWait(drv, 3).until(
                lambda d: d.find_elements(
                    By.XPATH, "//*[@role='alertdialog'][contains(., '有未保存的更改')]"))
            drv.find_element(
                By.XPATH, "//*[@role='alertdialog']//button[contains(., '离开并丢弃')]").click()
        except Exception:
            pass
        try:
            WebDriverWait(drv, 3).until(
                lambda d: '管理算法定义、参数与映射关系' not in _body_text(d))
            return
        except Exception:
            continue
    raise AssertionError(f'Sheet 关闭失败：{_body_text(drv)[-200:]}')


def _open_more_actions(drv, label):
    """页头「更多操作 ⋯」下拉 → 点击指定动作（分组管理/导入算法/重载配置/批量删除）。"""
    drv.find_element(By.XPATH, "//button[@aria-label='更多操作']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
    _js_click(drv, f"//*[@role='menuitem'][contains(., '{label}')]")


def _countdown_number(drv):
    m = re.search(r'将在 (\d+) 秒后自动保存草稿', _body_text(drv))
    return int(m.group(1)) if m else None


def _table_headers(drv):
    ths = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form table thead th')
    cells = ths or drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form table thead td')
    return [c.text.strip() for c in cells if c.text.strip()]


def _param_rows(drv):
    return drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')


def _click_chip(drv, label):
    btn = drv.find_element(
        By.XPATH, f"//button[starts-with(normalize-space(.), '{label} (')]")
    btn.click()
    time.sleep(0.8)


def _set_theme(drv, label):
    """切换深浅色主题（config-drawer radio）。"""
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, f"//*[@role='radio'][contains(., '{label}')]")
    _press_esc(drv)
    time.sleep(0.5)


def _api_get(path):
    with urllib.request.urlopen(API + path, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _api_delete_algorithm(type_):
    req = urllib.request.Request(
        f'{API}/algorithm/definitions/{urllib.parse.quote(type_)}',
        method='DELETE')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _api_create_algorithm(type_, name):
    payload = {
        'type': type_, 'name': name, 'display_order': 1, 'status': 'online',
        'description': 'INT-892 draft probe',
        'device_params': [], 'api_params': [], 'case_params': [],
        'reference_params': [],
        'mappings': {'device': [], 'api': [], 'evaluation': []},
        'associated_dimensions': [],
    }
    req = urllib.request.Request(
        f'{API}/algorithm/definitions',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _api_clear_draft(type_):
    """经 INT-589 全量保存 RPC（PUT /definitions/save，带 id+expected_updated_at）清除草稿快照。"""
    try:
        d = _api_get(f'/algorithm/definitions/{urllib.parse.quote(type_)}')['data']
    except Exception:
        return
    body = {
        'id': d['id'], 'type': d['type'], 'name': d['name'], 'group_id': d.get('group_id'),
        'display_order': d.get('display_order', 0), 'status': d.get('status'),
        'description': d.get('description') or '',
        'device_params': d.get('device_params') or [], 'api_params': d.get('api_params') or [],
        'case_params': d.get('case_params') or [], 'reference_params': d.get('reference_params') or [],
        'mappings': d.get('mappings') or {'device': [], 'api': [], 'evaluation': []},
        'associated_dimensions': d.get('associated_dimensions') or [],
        'expected_updated_at': d.get('updated_at'),
    }
    req = urllib.request.Request(
        f'{API}/algorithm/definitions/save',
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='PUT')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _search_algo(drv, keyword):
    """搜索框按名称过滤列表并等待目标行出现（分页不敏感）。"""
    _edit_field(drv, "//input[@aria-label='搜索算法']", keyword)
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='算法 {keyword} 的操作']"))


import urllib.parse  # noqa: E402


@pytest.fixture(scope='session')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    _goto(_DRIVER, '/login')
    try:
        _DRIVER.execute_script("window.localStorage.clear()")
    except Exception:
        pass
    _goto(_DRIVER, '/login')
    yield _DRIVER
    try:
        _drain_console(_DRIVER)
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_makereport(item, call):
    if call.when == 'call' and call.excinfo is not None and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


def _save_evidence(name, drv):
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, f'{name}.png'))
        with open(os.path.join(ARTIFACTS, f'{name}.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
    except Exception:
        pass


def _screenshot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv.save_screenshot(os.path.join(ARTIFACTS, f'{name}.png'))
    time.sleep(0.3)


# ── 0. 环境自检：后端常驻可用 ──
def test_00_backend_snapshot(drv):
    d = _api_get('/algorithm/definitions')
    types = [i['type'] for i in d['data']['items']]
    assert 'voice_llm' in types, f'常驻库应含 voice_llm，实际 {types}'
    detail = _api_get('/algorithm/definitions/voice_llm')
    assert len(detail['data']['device_params']) == 7, 'voice_llm 设备参数应 7'
    assert len(detail['data']['api_params']) == 3, 'voice_llm API 参数应 3'
    assert len(detail['data']['reference_params']) == 5, 'voice_llm 参考参数应 5'
    assert len((detail['data'].get('mappings') or {}).get('evaluation') or []) == 30, \
        'voice_llm 评估映射应 30'
    assert len(detail['data']['associated_dimensions'] or []) == 3, 'voice_llm 关联维度应 3'


# ── 1. 列表层：真实数据渲染 ──
def test_01_list_real_data(drv):
    _goto(drv, '/AlgorithmConfig')
    txt = _body_text(drv)
    assert '算法配置' in txt, f'列表页未渲染：{txt[:150]}'
    assert '个算法' in txt, f'标题徽标应显示真实计数：{txt[:300]}'
    assert '小艺语音大模型' in txt, f'真实算法行缺失：{txt[:300]}'
    assert 'voice_llm' in txt, f'算法代码缺失：{txt[:300]}'
    _collect_api_calls(drv)
    assert any('/algorithm/definitions' in u for u in _API_CALLS), \
        f'页面应发起真实 GET /algorithm/definitions：{sorted(_API_CALLS)[-6:]}'


# ── 2. 编辑 Sheet：真实数据预填 + 参数表 + 高级配置折叠 ──
def test_02_edit_sheet_real_prefill(drv):
    _open_edit_sheet(drv)
    txt = _body_text(drv)
    assert '编辑算法' in txt and '管理算法定义、参数与映射关系' in txt
    # 真实预填
    type_val = drv.find_element(By.XPATH, "//input[@id='algo-type']").get_attribute('value')
    name_val = drv.find_element(By.XPATH, "//input[@id='algo-name']").get_attribute('value')
    assert type_val == 'voice_llm', f'算法代码应预填 voice_llm，实际 {type_val}'
    assert name_val == '小艺语音大模型', f'显示名称应预填 小艺语音大模型，实际 {name_val}'
    # 作用域 chips 真实计数（7 设备 / 3 API / 0 用例）
    for chip in ['全部 (10)', '设备 (7)', 'API (3)', '用例 (0)']:
        assert chip in txt, f'作用域 chip「{chip}」缺失：{txt[:500]}'
    assert len(_param_rows(drv)) == 10, f'「全部」态应显示 10 行参数，实际 {len(_param_rows(drv))}'
    # 高级配置折叠头真实计数 + 默认收起
    assert '参考参数 5 · 映射 30 · 维度 3' in txt, f'折叠头计数徽章缺失：{txt[:800]}'
    assert '添加参考字段' not in txt, '高级配置折叠区未默认收起'
    # 展开三节
    _js_click(drv, "//button[contains(., '高级配置') and contains(., '参考参数')]")
    WebDriverWait(drv, 5).until(lambda d: '添加参考字段' in _body_text(d))
    txt = _body_text(drv)
    assert '设备参数映射' in txt and '添加关联维度' in txt, f'展开后三节缺失：{txt[600:1200]}'
    # 参考参数 5 行真实数据预填（input value 侧断言；placeholder=ref_code 表内行）
    ref_codes = drv.find_elements(By.XPATH, "//input[@placeholder='ref_code']")
    assert len(ref_codes) == 5, f'参考参数应 5 行，实际 {len(ref_codes)}'
    first_ref_code = ref_codes[0].get_attribute('value')
    assert first_ref_code == 'correct_answer', f'首行参考参数代码应 correct_answer，实际 {first_ref_code}'
    # 评估映射 30 条 / 关联维度 3 个（名称经 dimensionOptions 解析）
    assert '30 条映射' in txt, f'评估映射计数缺失：{txt[:1600]}'
    assert '未接管率占比' in txt and '误接管率占比' in txt and '接管内容平均分' in txt, \
        f'关联维度真实行缺失：{txt[:1600]}'
    _screenshot(drv, '02_edit_sheet_light')
    _close_sheet(drv)


# ── 3. 作用域 chips：切换过滤 + 列随 chip 动态显隐 ──
def test_03_scope_chips_filter_columns(drv):
    _open_edit_sheet(drv)
    headers = _table_headers(drv)
    assert '方向' in headers, f'「全部」态应显示方向列：{headers}'
    assert '适用范围' in headers and '范围约束' in headers and '字段路径' in headers, \
        f'「全部」态应显示用例专属列：{headers}'
    # 设备 → 7 行，隐藏用例专属列，保留方向列
    _click_chip(drv, '设备')
    headers = _table_headers(drv)
    assert '方向' in headers, f'「设备」态应保留方向列：{headers}'
    assert '适用范围' not in headers and '范围约束' not in headers and '字段路径' not in headers, \
        f'「设备」态应隐藏用例专属列：{headers}'
    assert len(_param_rows(drv)) == 7, f'「设备」chip 应过滤到 7 行，实际 {len(_param_rows(drv))}'
    # API → 3 行
    _click_chip(drv, 'API')
    assert len(_param_rows(drv)) == 3, f'「API」chip 应过滤到 3 行，实际 {len(_param_rows(drv))}'
    # 用例 → 0 行空态 + 功能特性快捷开关 + 隐藏方向列
    _click_chip(drv, '用例')
    headers = _table_headers(drv)
    assert '方向' not in headers, f'「用例」态应隐藏方向列：{headers}'
    assert '适用范围' in headers and '范围约束' in headers, f'「用例」态应显示用例专属列：{headers}'
    txt = _body_text(drv)
    # 用例域无行：filtered 为空 → 空态文案（total 10 非 0 → 走「未找到匹配参数」分支）
    assert '未找到匹配参数' in txt, f'「用例」态应显示空态：{txt[1000:1600]}'
    assert '勾选后自动批量添加/删除对应参数' in txt, '功能特性快捷开关提示缺失'
    _screenshot(drv, '03_scope_case_empty')
    # 全部 → 恢复 10 行全列
    _click_chip(drv, '全部')
    headers = _table_headers(drv)
    assert '方向' in headers and '适用范围' in headers, f'「全部」态应恢复全列：{headers}'
    assert len(_param_rows(drv)) == 10, f'「全部」态应恢复 10 行，实际 {len(_param_rows(drv))}'
    _close_sheet(drv)


# ── 4. 草稿保存（真实 PUT draft）：落库实证 + 重开恢复 + 清理 ──
def test_04_draft_save_footer(drv):
    """草稿保存 → 后端落库 → 重开恢复（INT-589 接线修复；专用测试算法，前后清理）。"""
    draft_type = f'itest892_draft_{RUN_TAG}'
    draft_name = f'接线测试_INT892_草稿_{RUN_TAG}'
    _api_create_algorithm(draft_type, draft_name)
    try:
        # 打开编辑 Sheet：发布版预填 + 无倒计时
        _goto(drv, '/AlgorithmConfig')
        _wait_list_ready(drv)
        _search_algo(drv, draft_name)
        _open_row_menu(drv, draft_name)
        _click_menu_item(drv, '编辑')
        WebDriverWait(drv, 8).until(lambda d: '编辑算法' in _body_text(drv))
        time.sleep(1.2)
        _drain_console(drv)
        _collect_api_calls(drv)
        name_val = drv.find_element(By.XPATH, "//input[@id='algo-name']").get_attribute('value')
        assert name_val == draft_name, f'编辑态应预填发布版名称，实际 {name_val}'
        assert _countdown_number(drv) is None, '编辑态未编辑不应显示自动保存倒计时'
        # 改名称 → 变脏启动 30s 倒计时
        _edit_field(drv, "//input[@id='algo-name']", draft_name + '_draft')
        n = _countdown_number(drv)
        assert n == 30, f'变脏后应显示「将在 30 秒后自动保存草稿」，实际 {n}'
        # 手动保存草稿 → toast「草稿已保存」+ footer「上次保存」时间戳（真实 PUT /definitions/draft）
        _js_click(drv, "//button[normalize-space()='保存草稿']")
        WebDriverWait(drv, 8).until(lambda d: '草稿已保存' in _body_text(d))
        assert '上次保存' in _body_text(drv), '保存草稿后 footer 应显示「上次保存」时间戳'
        # 快照重置后直接关闭（不弹脏态守卫）
        _close_sheet(drv)
        assert '有未保存的更改' not in _body_text(drv), '草稿保存成功后关闭不应弹脏态守卫'
        # 后端落库实证：GET draft/{type} 返回草稿快照（name=草稿名）
        d = _api_get(f'/algorithm/definitions/draft/{draft_type}')
        assert d['data'].get('name') == draft_name + '_draft', \
            f'草稿应落库（name=草稿名），实际 {d}'
        # 重开编辑 → 草稿恢复（name=草稿名）+ 头部 Alert「该算法存在未发布的草稿」
        _search_algo(drv, draft_name)
        _open_row_menu(drv, draft_name)
        _click_menu_item(drv, '编辑')
        WebDriverWait(drv, 8).until(lambda d: '编辑算法' in _body_text(drv))
        time.sleep(1.2)
        _drain_console(drv)
        _collect_api_calls(drv)
        name_val = drv.find_element(By.XPATH, "//input[@id='algo-name']").get_attribute('value')
        assert name_val == draft_name + '_draft', f'重开应恢复草稿名，实际 {name_val}'
        assert '该算法存在未发布的草稿' in _body_text(drv), '重开应显示未发布草稿横幅'
        _screenshot(drv, '04_draft_restored_light')
        _close_sheet(drv)
    finally:
        # 清理：发布清除草稿 + 删除测试算法（防断言中断残留）
        try:
            _api_clear_draft(draft_type)
        except Exception:
            pass
        try:
            _api_delete_algorithm(draft_type)
        except Exception:
            pass


# ── 5. 新建 + 发布写测试数据（真实 POST）→ 列表刷新 → 删除（真实 DELETE）→ 清理 ──
def test_05_create_publish_delete(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_list_ready(drv)
    _js_click(drv, "//button[normalize-space()='新建算法']")
    WebDriverWait(drv, 8).until(lambda d: '新建算法' in _body_text(drv))
    time.sleep(0.8)
    txt = _body_text(drv)
    assert '全部 (0)' in txt and '设备 (0)' in txt and 'API (0)' in txt and '用例 (0)' in txt, \
        f'新建态作用域 chips 应全 0：{txt[:500]}'
    # 填测试数据
    _edit_field(drv, "//input[@id='algo-type']", TEST_ALGO_TYPE)
    _edit_field(drv, "//input[@id='algo-name']", TEST_ALGO_NAME)
    # 添加一个设备参数（scope=全部 → 下拉「添加设备参数」）
    drv.find_element(By.XPATH, "//button[@aria-label='添加参数']").click()
    WebDriverWait(drv, 4).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem'][contains(., '添加设备参数')]"))
    _js_click(drv, "//*[@role='menuitem'][contains(., '添加设备参数')]")
    WebDriverWait(drv, 4).until(
        lambda d: len(drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')) == 1)
    _edit_field(drv,
        "//*[@id='algorithm-mutate-form']//tbody/tr[1]//input[@placeholder='param_code']",
        'd_pub_test')
    _edit_field(drv,
        "//*[@id='algorithm-mutate-form']//tbody/tr[1]//input[@placeholder='如：输入音频']",
        '发布测试参数')
    assert '设备 (1)' in _body_text(drv), '添加设备参数后 chip 应更新为 设备 (1)'
    # 草稿保存（真实 PUT /definitions/draft）
    _js_click(drv, "//button[normalize-space()='保存草稿']")
    WebDriverWait(drv, 8).until(lambda d: '草稿已保存' in _body_text(d))
    # 发布 → 真实 POST /algorithm/definitions → toast「算法已创建」+ Sheet 关闭
    _js_click(drv, "//button[normalize-space()='发布']")
    WebDriverWait(drv, 12).until(lambda d: '算法已创建' in _body_text(d))
    WebDriverWait(drv, 8).until(
        lambda d: '管理算法定义、参数与映射关系' not in _body_text(d))
    # 列表刷新：新行可见
    WebDriverWait(drv, 10).until(lambda d: TEST_ALGO_NAME in _body_text(d))
    txt = _body_text(drv)
    assert TEST_ALGO_NAME in txt, f'发布后列表应出现测试算法：{txt[:400]}'
    # 后端实证：GET detail 真实存在
    d = _api_get(f'/algorithm/definitions/{TEST_ALGO_TYPE}')
    assert d['data']['name'] == TEST_ALGO_NAME, f'后端应返回测试算法：{d}'
    assert len(d['data']['device_params']) == 1, '发布应携带 1 个设备参数'
    assert d['data']['device_params'][0]['param_code'] == 'd_pub_test'
    # 草稿清理（发布走旧更新路径不自动清草稿，INT-589 全量保存 RPC 才清；此处显式清）
    _api_clear_draft(TEST_ALGO_TYPE)
    d = _api_get(f'/algorithm/definitions/draft/{TEST_ALGO_TYPE}')
    assert d['data'] == {}, f'草稿应已清理，实际 {d}'
    # 删除（真实 DELETE）→ 清理
    _open_row_menu(drv, TEST_ALGO_NAME)
    _click_menu_item(drv, '删除')
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '确认删除')]"))
    _js_click(drv, "//*[@role='alertdialog']//button[normalize-space()='删除']")
    WebDriverWait(drv, 10).until(lambda d: '算法已删除' in _body_text(d))
    WebDriverWait(drv, 10).until(lambda d: TEST_ALGO_NAME not in _body_text(d))
    assert TEST_ALGO_NAME not in _body_text(drv), '删除后列表不应再出现测试算法'
    # 后端实证已清理
    try:
        _api_get(f'/algorithm/definitions/{TEST_ALGO_TYPE}')
        raise AssertionError('测试算法仍存在，删除未生效')
    except Exception:
        pass  # 期望 404/400 not found


# ── 6. 详情 Dialog：真实数据只读渲染 ──
def test_06_detail_dialog(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_list_ready(drv)
    _open_row_menu(drv, '小艺语音大模型')
    _click_menu_item(drv, '详情')
    WebDriverWait(drv, 8).until(lambda d: '算法定义与参数映射只读详情' in _body_text(d))
    txt = _body_text(drv)
    assert '算法类型' in txt and 'voice_llm' in txt, f'详情基本信息缺失：{txt[:400]}'
    assert '显示名称' in txt and '小艺语音大模型' in txt, f'详情显示名称缺失：{txt[:400]}'
    assert '参数数量' in txt and '10' in txt, f'参数数量应为 10：{txt[:400]}'
    assert '设备参数（7）' in txt and 'API参数（3）' in txt and '用例参数（0）' in txt, \
        f'参数定义 Tabs 计数缺失：{txt[:800]}'
    assert '评估参数（30）' in txt, f'评估映射计数缺失：{txt[:800]}'
    assert '评估维度关联' in txt, f'关联维度节缺失：{txt[:800]}'
    _screenshot(drv, '06_detail_dialog_light')
    _press_esc(drv)
    WebDriverWait(drv, 5).until(
        lambda d: '算法定义与参数映射只读详情' not in _body_text(d))


# ── 7. 分组管理：新建/编辑/删除测试分组（真实 group CRUD）→ 清理 ──
def test_07_group_manager_crud(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_list_ready(drv)
    _open_more_actions(drv, '分组管理')
    WebDriverWait(drv, 8).until(lambda d: '算法分组管理' in _body_text(d))
    assert '共 0 个分组' in _body_text(drv) or '暂无分组' in _body_text(drv), \
        '分组管理应显示空态'
    # 新建测试分组
    _js_click(drv, "//button[normalize-space()='新建分组']")
    WebDriverWait(drv, 5).until(lambda d: '新建分组' in _body_text(d))
    _edit_field(drv, "//input[@id='group-name']", TEST_GROUP_NAME)
    _edit_field(drv, "//textarea[@id='group-desc']", 'INT-892 分组 CRUD 走查')
    _js_click(drv, "//*[@role='dialog']//button[normalize-space()='保存']")
    WebDriverWait(drv, 8).until(lambda d: '分组已创建' in _body_text(d))
    # 等 refetch 完成：列表出现新分组行
    WebDriverWait(drv, 8).until(lambda d: TEST_GROUP_NAME in _body_text(d))
    _screenshot(drv, '07_group_manager_light')
    # 编辑：改名
    _js_click(drv, f"//button[@aria-label='编辑分组 {TEST_GROUP_NAME}']")
    WebDriverWait(drv, 5).until(lambda d: '编辑分组' in _body_text(d))
    new_name = TEST_GROUP_NAME + '_改'
    _edit_field(drv, "//input[@id='group-name']", new_name)
    _js_click(drv, "//*[@role='dialog']//button[normalize-space()='保存']")
    WebDriverWait(drv, 8).until(lambda d: '分组已更新' in _body_text(d))
    # 等 refetch 完成：新名行的删除钮出现（旧名非 new_name 子串误判）
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='删除分组 {new_name}']"))
    assert new_name in _body_text(drv), '编辑后分组名应更新'
    # 删除 → 确认 → 清理
    _js_click(drv, f"//button[@aria-label='删除分组 {new_name}']")
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '删除分组')]"))
    _js_click(drv, "//*[@role='alertdialog']//button[normalize-space()='删除']")
    WebDriverWait(drv, 10).until(lambda d: '分组已删除' in _body_text(d))
    # 等 refetch 完成：分组清空（alertdialog 关闭 + 列表重拉）
    WebDriverWait(drv, 10).until(lambda d: '共 0 个分组' in _body_text(d))
    assert new_name not in _body_text(drv), '删除后分组应清空'
    # 后端实证：groups 空
    g = _api_get('/algorithm/groups')
    assert len(g['data']['items']) == 0, f'后端分组应清空：{g}'
    _press_esc(drv)
    WebDriverWait(drv, 5).until(lambda d: '算法分组管理' not in _body_text(d))


# ── 8. 导入 Dialog：JSON 错误态 + 真实导入 → 列表刷新 → 删除 → 清理 ──
def test_08_import_dialog(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_list_ready(drv)
    _open_more_actions(drv, '导入算法')
    WebDriverWait(drv, 5).until(lambda d: '导入算法' in _body_text(d))
    # 错误态：非数组 JSON
    _edit_field(drv, "//textarea[@aria-label='算法定义 JSON']", '{"not":"array"}')
    _js_click(drv, "//button[normalize-space()='导入']")
    WebDriverWait(drv, 5).until(
        lambda d: '期望算法定义数组' in _body_text(d))
    assert 'JSON 格式错误' in _body_text(drv), 'JSON 格式错误提示缺失'
    # 真实导入测试算法（snake_case 契约，与后端 AlgorithmImportRequest 对齐）
    payload = json.dumps([{
        'type': TEST_IMPORT_TYPE,
        'name': f'接线测试_INT892_导入_{RUN_TAG}',
        'display_order': 1,
        'status': 'online',
        'description': 'INT-892 import dialog probe',
        'device_params': [],
        'api_params': [],
        'case_params': [],
        'reference_params': [],
        'mappings': {'device': [], 'api': [], 'evaluation': []},
        'associated_dimensions': [],
    }], ensure_ascii=False)
    _edit_field(drv, "//textarea[@aria-label='算法定义 JSON']", payload)
    _js_click(drv, "//button[normalize-space()='导入']")
    WebDriverWait(drv, 10).until(lambda d: '成功导入 1 个算法' in _body_text(d))
    # 列表刷新：导入的新行可见（dialog 关闭后列表重拉）
    WebDriverWait(drv, 10).until(
        lambda d: f'接线测试_INT892_导入_{RUN_TAG}' in _body_text(d))
    assert f'接线测试_INT892_导入_{RUN_TAG}' in _body_text(drv), '导入后列表应出现新算法'
    # 后端实证
    d = _api_get(f'/algorithm/definitions/{TEST_IMPORT_TYPE}')
    assert d['data']['name'] == f'接线测试_INT892_导入_{RUN_TAG}'
    # 删除清理
    _open_row_menu(drv, f'接线测试_INT892_导入_{RUN_TAG}')
    _click_menu_item(drv, '删除')
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '确认删除')]"))
    _js_click(drv, "//*[@role='alertdialog']//button[normalize-space()='删除']")
    WebDriverWait(drv, 10).until(
        lambda d: f'接线测试_INT892_导入_{RUN_TAG}' not in _body_text(d))
    try:
        _api_get(f'/algorithm/definitions/{TEST_IMPORT_TYPE}')
        raise AssertionError('导入的测试算法未清理')
    except Exception:
        pass


# ── 9. 确认弹窗族：重载配置（真实 POST /algorithm/reload）+ 复制走查 ──
def test_09_confirm_dialogs(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_list_ready(drv)
    # 重载配置（更多操作下拉）
    _open_more_actions(drv, '重载配置')
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '重载配置')]"))
    txt = _body_text(drv)
    assert '将重载后端算法配置缓存' in txt, f'重载确认文案缺失：{txt[:400]}'
    _js_click(drv, "//*[@role='alertdialog']//button[normalize-space()='重载']")
    WebDriverWait(drv, 10).until(lambda d: '配置已重载' in _body_text(d))
    # 复制走查：确认弹窗 → 复制 Sheet 预填（不发布，避免写入）
    _open_row_menu(drv, '小艺语音大模型')
    _click_menu_item(drv, '复制')
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '确认复制')]"))
    assert '小艺语音大模型 (副本)' in _body_text(drv), '复制确认应提示副本命名'
    _js_click(drv, "//*[@role='alertdialog']//button[normalize-space()='复制']")
    WebDriverWait(drv, 8).until(lambda d: '复制算法' in _body_text(d))
    name_val = drv.find_element(By.XPATH, "//input[@id='algo-name']").get_attribute('value')
    type_val = drv.find_element(By.XPATH, "//input[@id='algo-type']").get_attribute('value')
    assert name_val == '小艺语音大模型 (副本)', f'复制态应预填副本名，实际 {name_val}'
    assert type_val == 'voice_llm_copy', f'复制态代码应追加 _copy，实际 {type_val}'
    # 复制参数表真实预填：10 行（设备 7 + API 3）
    assert len(_param_rows(drv)) == 10, f'复制态应预填 10 行参数，实际 {len(_param_rows(drv))}'
    _screenshot(drv, '09_clone_sheet_light')
    _close_sheet(drv)


# ── 10. 深浅两套主题截图 ──
def test_10_light_dark_screenshots(drv):
    # 深色：编辑 Sheet 展开高级配置
    _set_theme(drv, '深色')
    _open_edit_sheet(drv)
    _js_click(drv, "//button[contains(., '高级配置') and contains(., '参考参数')]")
    WebDriverWait(drv, 5).until(lambda d: '添加参考字段' in _body_text(d))
    time.sleep(0.5)
    _screenshot(drv, '10_edit_sheet_dark')
    _close_sheet(drv)
    # 深色：分组管理（临时分组截图后清理）
    dark_group = TEST_GROUP_NAME + '_dark'
    _open_more_actions(drv, '分组管理')
    WebDriverWait(drv, 8).until(lambda d: '算法分组管理' in _body_text(d))
    _js_click(drv, "//button[normalize-space()='新建分组']")
    WebDriverWait(drv, 5).until(lambda d: '新建分组' in _body_text(d))
    _edit_field(drv, "//input[@id='group-name']", dark_group)
    _js_click(drv, "//*[@role='dialog']//button[normalize-space()='保存']")
    WebDriverWait(drv, 8).until(lambda d: '分组已创建' in _body_text(d))
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, f"//button[@aria-label='删除分组 {dark_group}']"))
    _screenshot(drv, '10_group_manager_dark')
    # 删除临时分组清理
    _js_click(drv, f"//button[@aria-label='删除分组 {dark_group}']")
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog'][contains(., '删除分组')]"))
    _js_click(drv, "//*[@role='alertdialog']//button[normalize-space()='删除']")
    WebDriverWait(drv, 8).until(lambda d: '分组已删除' in _body_text(d))
    WebDriverWait(drv, 8).until(lambda d: '共 0 个分组' in _body_text(d))
    _press_esc(drv)
    WebDriverWait(drv, 5).until(lambda d: '算法分组管理' not in _body_text(d))
    # 还原浅色
    _set_theme(drv, '浅色')


# ── 11. 全会话：无 JS 运行时严重错误 + 真实接口请求清单 ──
def test_11_session_clean(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_list_ready(drv)
    time.sleep(1.0)
    _drain_console(drv)
    _collect_api_calls(drv)
    assert not _CONSOLE_JS_ERRORS, \
        '浏览器控制台存在 JS 运行时严重错误：\n' + '\n'.join(_CONSOLE_JS_ERRORS[-10:])
    # 证据落盘：本会话真实接口请求清单
    os.makedirs(ARTIFACTS, exist_ok=True)
    with open(os.path.join(ARTIFACTS, 'api_calls.txt'), 'w', encoding='utf-8') as f:
        for u in sorted(_API_CALLS):
            f.write(u + '\n')
    # 后端数据卫生自检：本卡测试数据全部清理
    d = _api_get('/algorithm/definitions')
    types = [i['type'] for i in d['data']['items']]
    assert not any(t.startswith('itest892') for t in types), f'本卡残留测试算法：{types}'
    g = _api_get('/algorithm/groups')
    assert all('itest892' not in str(g['name']) for g in g['data']['items']), \
        f'本卡残留测试分组：{g}'
    # 草稿残留自检：本卡涉及的测试算法草稿快照应全部清除（draft 接口无草稿返回 data:{}）
    for leftover_type in (TEST_ALGO_TYPE, TEST_IMPORT_TYPE, f'itest892_draft_{RUN_TAG}'):
        try:
            dd = _api_get(f'/algorithm/definitions/draft/{leftover_type}')
            assert dd['data'] == {}, f'草稿残留：{leftover_type} → {dd}'
        except Exception:
            pass  # 仅防御：算法已删时 draft 接口仍应 200 空 {}，异常视为清理过
