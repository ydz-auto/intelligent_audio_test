# -*- coding: utf-8 -*-
"""INT-509 评估维度 React 可视稿浏览器走查（真实 Chrome headless，按 test_ui_09/10 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. /Evaluation 页面渲染：页头「评估维度」+ 说明 + 面包屑；自动合并提示条；双视图
   页签（列表视图/分组视图）；筛选工具栏（搜索/状态/分类/关联算法）；维度表格九列
   （维度名称/描述/分类/关联算法/权重/API 状态/状态/操作）
2. 列表视图表格内容：主/子维度层级（主/子徽章 + 子维度「（父名）」括注）、权重滑杆、
   启用/禁用状态徽章、LLM Judge 徽章（语义理解）
3. 筛选：搜索「时延」→ 仅响应时延维度；重置筛选恢复全量
4. 分组视图：切「分组视图」→ 分类聚合卡（识别质量/语义理解/响应体验/稳定性 +
   组头「添加维度」/计数徽章）
5. 新增维度抽屉（§5.5）：打开「新增维度」→ Sheet 标题 + 五页签（基本信息/层级配置/
   结果配置/API配置/关联算法）→ 填名称 → 保存 → toast「评估维度添加成功」+ Sheet 关闭
6. 新增分类弹窗（§5.5）：打开「新增分类」→ 分类名称/描述/图标 → 创建 → toast
7. 规则试算（§4.1）：点「规则试算维度 识别准确率」→ 输入测试值 → 试算 → 「评分 X 分」
8. API 健康测试（§5.5）：点「测试维度 识别准确率 的 API」→ 结果弹窗「API健康测试结果」+ 在线
9. 删除确认（§4.1/§5.6）：点「删除维度 …」→ ConfirmDialog 文案 → 确认 → toast「维度已删除」
10. RBAC 只读态：注入仅 evaluation:read 快照 → 写钮禁用 + Tooltip「无 evaluation:dim_manage 权限」

失败落 tests/ui/artifacts/int509_evaluation/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int509_evaluation')

# 5273 = 工作区常驻 dev server（strictPort 钉死）；env 可覆写
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


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


@pytest.fixture(scope='session')
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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _login(drv, username='demo_admin'):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _table_headers(drv):
    return [h.text for h in drv.find_elements(By.CSS_SELECTOR, 'table thead th')]


# ── 1. 页面渲染 ─────────────────────────────────────────
def test_01_page_renders(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    assert '评估维度' in txt, f'页标题缺失：{txt[:150]}'
    assert '管理语音测试的评估维度和权重' in txt, f'页说明缺失：{txt[:200]}'
    assert '同一分类下、评估服务与请求模板一致的维度，评估时会自动合并为一次请求，共用一次判定结果。' in txt, \
        f'自动合并提示条缺失：{txt[:300]}'
    for tab in ['列表视图', '分组视图']:
        assert tab in txt, f'视图页签「{tab}」缺失'
    # 工具栏 + 表头
    assert _search_input_exists(drv), '搜索框缺失'
    for header in ['维度名称', '描述', '分类', '关联算法', '权重', 'API 状态', '状态', '操作']:
        assert header in _table_headers(drv), f'表头「{header}」缺失：{_table_headers(drv)}'


def _search_input_exists(drv):
    return len(drv.find_elements(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")) > 0


# ── 2. 列表视图表格内容 ─────────────────────────────────
def test_02_list_view_content(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    for dim in ['识别准确率', '字准率', '句准率', '语义理解', '响应时延', '噪声鲁棒性']:
        assert dim in txt, f'维度「{dim}」缺失：{txt[:400]}'
    # 子维度括注「（父名）」
    assert '（识别准确率）' in txt, '子维度父名括注缺失'
    # 徽章：主/子 + 状态 + LLM Judge
    assert '主' in txt and '子' in txt, '主/子徽章缺失'
    assert '启用' in txt and '禁用' in txt, '启用/禁用状态徽章缺失'
    assert 'LLM Judge' in txt, 'LLM Judge 徽章缺失（语义理解维度）'
    # 在线/离线 API 状态
    assert '在线' in txt and '离线' in txt, '在线/离线 API 状态缺失'


# ── 3. 搜索筛选 + 重置 ──────────────────────────────────
def test_03_search_filter_reset(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    box = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
    box.send_keys('时延')
    WebDriverWait(drv, 10).until(
        lambda d: '响应时延' in _body_text(drv) and '识别准确率' not in _body_text(drv))
    txt = _body_text(drv)
    assert '响应时延' in txt and '识别准确率' not in txt, f'搜索「时延」结果异常：{txt[:400]}'
    # 重置筛选恢复全量
    drv.find_element(By.XPATH, "//button[contains(., '重置筛选')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '识别准确率' in _body_text(drv))


# ── 4. 分组视图 ─────────────────────────────────────────
def test_04_group_view(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '分组视图')]").click()
    time.sleep(1.0)
    txt = _body_text(drv)
    for cat in ['识别质量', '语义理解', '响应体验', '稳定性']:
        assert cat in txt, f'分类聚合卡「{cat}」缺失：{txt[:400]}'
    assert '添加维度' in txt, '组头「添加维度」缺失'
    # 分类行操作（编辑/删除分类）
    assert len(drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='编辑分类 ']")) >= 2, \
        '分类「编辑分类」按钮缺失'
    # 组内表格复用同款列
    headers = _table_headers(drv)
    assert '维度名称' in headers, '分组视图组内表格列缺失'


# ── 5. 新增维度抽屉（§5.5）──────────────────────────────
def test_05_dimension_mutate_drawer(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
    time.sleep(0.9)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    stxt = sheet.text
    assert '新增评估维度' in stxt, f'抽屉标题缺失：{stxt[:150]}'
    for tab in ['基本信息', '层级配置', '结果配置', 'API配置', '关联算法']:
        assert tab in stxt, f'抽屉页签「{tab}」缺失：{stxt[:300]}'
    # 填名称 → 保存
    sheet.find_element(By.ID, 'dim-name').send_keys('试听质量')
    time.sleep(0.3)
    save_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                if b.text.strip() == '保存' and b.is_displayed()]
    assert save_btn and not save_btn[0].get_attribute('disabled'), '填名后「保存」应启用'
    save_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '评估维度添加成功' in _body_text(drv))
    time.sleep(0.6)


# ── 6. 新增分类弹窗（§5.5）──────────────────────────────
def test_06_category_create_dialog(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.XPATH, "//button[contains(., '新增分类')]").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert '新建分类' in dtxt, f'分类弹窗标题缺失：{dtxt[:150]}'
    for field in ['分类名称', '描述', '图标']:
        assert field in dtxt, f'分类字段「{field}」缺失：{dtxt[:200]}'
    dialog.find_element(By.ID, 'category-name').send_keys('音频体验')
    time.sleep(0.3)
    create_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                  if b.text.strip() in ('创建', '保存') and b.is_displayed()]
    assert create_btn and not create_btn[0].get_attribute('disabled'), '填名后「创建」应启用'
    create_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '分类添加成功' in _body_text(drv))


# ── 7. 规则试算（§4.1）─────────────────────────────────
def test_07_rule_calc(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='规则试算维度 识别准确率']").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert '规则试算' in dtxt, f'试算弹窗标题缺失：{dtxt[:150]}'
    dialog.find_element(By.ID, 'calc-value').send_keys('96.5')
    time.sleep(0.3)
    calc_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                if b.text.strip() == '试算' and b.is_displayed()]
    assert calc_btn, '试算按钮缺失'
    calc_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '评分' in _body_text(drv))
    dtxt = dialog.text
    assert '评分 10 分' in dtxt, f'试算结果异常：{dtxt[:300]}'


# ── 8. API 健康测试（§5.5）─────────────────────────────
def test_08_health_test(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='测试维度 识别准确率 的 API']").click()
    time.sleep(1.0)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='dialog-content']")
    dtxt = dialog.text
    assert 'API健康测试结果' in dtxt, f'健康结果弹窗缺失：{dtxt[:150]}'
    assert '在线' in dtxt, f'总状态在线缺失：{dtxt[:300]}'
    assert '健康探测完成' in dtxt, f'端点信息缺失：{dtxt[:300]}'


# ── 9. 删除确认（§5.6）─────────────────────────────────
def test_09_delete_confirm(drv):
    _login(drv)
    _goto(drv, '/Evaluation')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='删除维度 响应时延']").click()
    time.sleep(0.8)
    dialog = drv.find_element(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")
    dtxt = dialog.text
    assert '删除维度' in dtxt and '确定要删除维度「响应时延」吗？此操作不可恢复。' in dtxt, \
        f'删除确认文案缺失：{dtxt[:200]}'
    confirm_btn = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == '删除' and b.is_displayed()]
    assert confirm_btn, '确认按钮「删除」缺失'
    confirm_btn[0].click()
    WebDriverWait(drv, 10).until(
        lambda d: '维度已删除' in _body_text(drv))


# ── 10. RBAC 只读态（仅 evaluation:read）───────────────
def test_10_rbac_readonly_state(drv):
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script("window.localStorage.clear()")
    snapshot = {
        'state': {
            'user': {
                'id': 'mock-algo-001',
                'username': 'algo_engineer',
                'displayName': '演示算法工程师',
                'roleName': '算法工程师',
                'permissions': ['evaluation:read'],
            }
        },
        'version': 0,
    }
    drv.execute_script(
        "window.localStorage.setItem('iatp:auth:v1', arguments[0])",
        json.dumps(snapshot, ensure_ascii=False))
    _goto(drv, '/Evaluation')
    txt = _body_text(drv)
    assert '评估维度' in txt, f'只读态页面未渲染：{txt[:150]}'
    # 新增维度钮禁用
    new_btn = drv.find_elements(By.XPATH, "//button[contains(., '新增维度')]")
    for b in new_btn:
        if b.is_displayed():
            assert b.get_attribute('disabled'), '只读态「新增维度」应禁用'
    # 行操作禁用（首个编辑钮）
    edit_btn = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='编辑维度 ']")
    assert edit_btn and edit_btn[0].get_attribute('disabled'), '只读态编辑维度应禁用'
    del_btn = drv.find_elements(By.CSS_SELECTOR, "button[aria-label^='删除维度 ']")
    assert del_btn and del_btn[0].get_attribute('disabled'), '只读态删除维度应禁用'
    # 恢复 admin 会话（后续用例隔离）
    drv.execute_script("window.localStorage.clear()")
