# -*- coding: utf-8 -*-
"""INT-601 算法配置页重做 浏览器验收走查（真实 Chrome headless，照 test_ui_21 先例）。

针对 frontend-react/ mock 稿（算法配置数据走 mock API，无后端依赖；认证会话用
localStorage 'iatp:auth:v1' 注入 admin 权限快照，绕开对后端 /auth/login 的依赖）：
1. 列表层：标题徽标「共 7 个算法」+ 分页「共 7 个算法 · 1/1 页」+ has_draft「有草稿」Badge
2. 编辑 Sheet 结构降维：单页滚动三区块（基本信息 → 参数表 → 高级配置折叠默认收起）、无五 Tab
3. 作用域 chips：全部 (10)/设备 (3)/API (2)/用例 (5) 计数 + 切换过滤 + 列随 chip 动态显隐
4. 30s 自动保存：变脏启动「将在 30 秒后自动保存草稿」+ 递减 + 变更重置
5. 归零自动保存：静默写草稿（时间戳更新、Sheet 不关、倒计时消失、无打扰 toast）
6. 参数行失焦 1.5s 防抖草稿保存（旧习惯保留；toast「草稿已保存」+ 时间戳更新）
7. 草稿乐观锁冲突：footer inline Alert「草稿已过期：该算法已被他人修改」+ [继续编辑][立即刷新]
8. 发布乐观锁冲突：AlertDialog「发布冲突：该算法已被他人修改。」+ [刷新并丢弃我的更改][继续编辑]
9. 发布成功：toast「算法已发布」+ Sheet 关闭
10. 脏态离开守卫：未保存关闭 → ConfirmDialog「有未保存的更改」+ [离开并丢弃]
11. 深浅两套主题下倒计时/Alert 可读
12. 全会话无 JS 运行时严重错误（网络 504 属后端环境噪音，不算）
"""
import json
import os
import re
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int601_algorithm_config_redo')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
AUTH_KEY = 'iatp:auth:v1'


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


def _drain_console(drv):
    """把浏览器 console 累积的「JS 运行时错误」归入会话级列表（忽略 504 等网络资源失败）。"""
    global _CONSOLE_JS_ERRORS
    try:
        for entry in drv.get_log('browser'):
            msg = entry.get('message', '')
            # 网络资源加载失败（504 Gateway Timeout 等）属后端环境噪音，不算 JS 运行时错误
            if 'Failed to load resource' in msg and 'Uncaught' not in msg:
                continue
            if entry.get('level') == 'SEVERE':
                _CONSOLE_JS_ERRORS.append(msg)
    except Exception:
        pass


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _seed_admin_auth(drv):
    """注入 admin 权限快照（permissions ['*']），绕开后端登录依赖（§9 全放行口径）。"""
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
        "window.localStorage.setItem(arguments[0], arguments[1])",
        AUTH_KEY, json.dumps(snapshot, ensure_ascii=False))


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    _drain_console(drv)


def _open_edit_sheet(drv, row_name='通用识别引擎'):
    """行菜单 → 编辑，等 Sheet 出现（§6.1）。"""
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    _open_row_menu(drv, row_name)
    _click_menu_item(drv, '编辑')
    WebDriverWait(drv, 8).until(lambda d: '编辑算法' in _body_text(drv))
    time.sleep(1.2)
    _drain_console(drv)


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


def _edit_field(drv, xpath, new_value):
    """用原生 value setter + input 事件改写（Selenium clear/send_keys 不触发 React onChange）。"""
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
        el, new_value)
    time.sleep(0.6)


def _edit_name(drv, new_name):
    _edit_field(drv, "//input[@id='algo-name']", new_name)


def _countdown_number(drv):
    """从 body 文本提取「将在 {n} 秒后自动保存草稿」的 n；无倒计时返回 None。"""
    m = re.search(r'将在 (\d+) 秒后自动保存草稿', _body_text(drv))
    return int(m.group(1)) if m else None


def _press_esc(drv):
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)


def _js_click(drv, xpath):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script(
        "arguments[0].scrollIntoView({ block: 'center' }); arguments[0].click();", el)
    time.sleep(0.6)


def _click_chip(drv, label):
    """点击作用域 chip（全部/设备/API/用例）。ToggleGroupItem 是 button，文案带计数「{label} (n)」。"""
    btn = drv.find_element(
        By.XPATH, f"//button[starts-with(normalize-space(.), '{label} (')]")
    btn.click()
    time.sleep(0.8)


def _table_headers(drv):
    """Sheet 内参数表当前可见的列头文本（小写对比用）。"""
    ths = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form table thead th')
    cells = ths or drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form table thead td')
    return [c.text.strip() for c in cells if c.text.strip()]


def _close_sheet(drv):
    """ESC 关闭 Sheet；若脏态守卫 ConfirmDialog 弹出则点「离开并丢弃」确认离开。"""
    _press_esc(drv)
    try:
        WebDriverWait(drv, 3).until(
            lambda d: d.find_elements(
                By.XPATH, "//*[@role='alertdialog'][contains(., '有未保存的更改')]"))
        drv.find_element(
            By.XPATH, "//*[@role='alertdialog']//button[contains(., '离开并丢弃')]").click()
    except Exception:
        pass
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(drv))


@pytest.fixture(scope='session')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    _goto(_DRIVER, '/login')
    try:
        _DRIVER.execute_script("window.localStorage.clear()")
    except Exception:
        pass
    # 会话级注入 admin 权限快照（权限 '*'），单跑任意用例也能通过路由守卫（§9 全放行口径）
    _seed_admin_auth(_DRIVER)
    yield _DRIVER
    try:
        _drain_console(_DRIVER)
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_makereport(item, call):
    if call.when == 'call' and call.excinfo is not None and _DRIVER is not None:
        import sys
        _save_evidence(item.name, _DRIVER)


def _save_evidence(name, drv):
    try:
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, f'{name}.png'))
        with open(os.path.join(ARTIFACTS, f'{name}.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
    except Exception:
        pass


# ── 1. 列表层：徽标/分页/草稿 Badge ──
def test_01_list_page_badges_and_pagination(drv):
    _seed_admin_auth(drv)
    _goto(drv, '/AlgorithmConfig')
    txt = _body_text(drv)
    assert '算法配置' in txt, f'列表页未渲染：{txt[:150]}'
    # 标题徽标「共 {n} 个算法」+ 分页「共 {n} 个算法 · {page}/{pageCount} 页」（§3.4/§3.7/§10）
    assert '共 7 个算法' in txt, f'标题徽标「共 7 个算法」缺失：{txt[:300]}'
    assert '共 7 个算法 · 1/1 页' in txt, f'分页文案缺失：{txt[:300]}'
    # has_draft「有草稿」Badge（asr-v3 mock 返回 hasDraft=true，§3.4 注）
    assert '有草稿' in txt, f'「有草稿」Badge 缺失：{txt[:300]}'
    # 主按钮
    assert '新建算法' in txt, f'「新建算法」按钮缺失：{txt[:300]}'
    # 关联用例计数列消费 case_count
    assert '50' in txt, f'关联用例计数缺失：{txt[:500]}'
    _drain_console(drv)


# ── 2. 编辑 Sheet 结构降维：单页滚动三区块 + 无五 Tab + 高级配置默认收起 ──
def test_02_edit_sheet_structure_no_tabs(drv):
    _open_edit_sheet(drv)
    txt = _body_text(drv)
    # 单页滚动布局标题
    assert '编辑算法' in txt and '管理算法定义、参数与映射关系' in txt, f'Sheet 标题缺失：{txt[:200]}'
    # 无五 Tab 顶层切换（旧 829 行 AlgorithmConfigModal 五 Tab 已去除）
    tab_els = drv.find_elements(
        By.XPATH, "//*[@id='algorithm-mutate-form']//*[@role='tab']")
    assert not tab_els, f'五 Tab 结构残留：Sheet 表单区仍存在页签元素'
    # 编辑态草稿提示 Alert（§6.1 编辑态）
    assert '该算法存在未发布的草稿' in txt, '编辑态「该算法存在未发布的草稿」Alert 缺失'
    # 基本信息区
    assert '算法代码' in txt and '显示名称' in txt and '所属分组' in txt, '基本信息区缺失'
    # 作用域 chips 计数（§6.4）
    for chip_text in ['全部 (10)', '设备 (3)', 'API (2)', '用例 (5)']:
        assert chip_text in txt, f'作用域 chip「{chip_text}」缺失：{txt[:500]}'
    # 折叠区默认收起：折叠头计数徽章可见，展开内容不可见
    assert '参考参数 2 · 映射 4 · 维度 2' in txt, \
        f'高级配置折叠头计数徽章缺失：{txt[:800]}'
    assert '添加参考字段' not in txt, '高级配置折叠区未默认收起（展开内容不应可见）'
    # 展开 → 三节内容可见（§6.5 ①参考参数 ②参数映射 ③评估维度）
    _js_click(drv, "//button[contains(., '高级配置') and contains(., '参考参数')]")
    WebDriverWait(drv, 5).until(lambda d: '添加参考字段' in _body_text(d))
    txt = _body_text(drv)
    assert '设备参数映射' in txt and '添加关联维度' in txt, f'展开后三节缺失：{txt[600:1200]}'
    # 折叠回默认态
    _js_click(drv, "//button[contains(., '高级配置') and contains(., '参考参数')]")
    time.sleep(0.5)
    # footer 双态保存按钮（§6.2）
    txt = _body_text(drv)
    assert '取消' in txt and '保存草稿' in txt and '发布' in txt, 'footer 按钮缺失'
    _close_sheet(drv)


# ── 3. 作用域 chips：切换过滤 + 列随 chip 动态显隐 ──
def test_03_scope_chips_filter_columns(drv):
    _open_edit_sheet(drv)
    # 全部态：方向列 + 用例专属列（适用范围/范围约束/标注代码/字段路径）全显
    headers = _table_headers(drv)
    assert '方向' in headers, f'「全部」态应显示方向列：{headers}'
    assert '适用范围' in headers and '范围约束' in headers and '字段路径' in headers, \
        f'「全部」态应显示用例专属列：{headers}'
    # 切「设备」→ 仅设备行 + 隐藏用例专属列，方向列保留（§6.4 showCaseOnly=false）
    _click_chip(drv, '设备')
    headers = _table_headers(drv)
    assert '方向' in headers, f'「设备」态应保留方向列：{headers}'
    assert '适用范围' not in headers and '范围约束' not in headers and '字段路径' not in headers, \
        f'「设备」态应隐藏用例专属列：{headers}'
    assert '标注代码' not in headers, f'「设备」态应隐藏标注代码列：{headers}'
    # 行数 = 设备参数数 3（表内 tbody tr）
    rows = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')
    assert len(rows) == 3, f'「设备」chip 应过滤到 3 行，实际 {len(rows)}'
    # 切「用例」→ 仅用例行 + 方向列隐藏，用例专属列显示；功能特性快捷开关可见
    _click_chip(drv, '用例')
    headers = _table_headers(drv)
    assert '方向' not in headers, f'「用例」态应隐藏方向列：{headers}'
    assert '适用范围' in headers and '范围约束' in headers and '字段路径' in headers, \
        f'「用例」态应显示用例专属列：{headers}'
    rows = drv.find_elements(By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr')
    assert len(rows) == 5, f'「用例」chip 应过滤到 5 行，实际 {len(rows)}'
    # 功能特性快捷开关（用例/全部态显示，§6.4）
    assert '勾选后自动批量添加/删除对应参数' in _body_text(drv), '功能特性快捷开关提示缺失'
    # 切回「全部」恢复全列
    _click_chip(drv, '全部')
    headers = _table_headers(drv)
    assert '方向' in headers and '适用范围' in headers, f'「全部」态应恢复全列：{headers}'
    _close_sheet(drv)


# ── 4. 30s 自动保存倒计时：变脏启动 / 递减 / 变更重置 ──
def test_04_countdown_start_reset(drv):
    _open_edit_sheet(drv)
    assert _countdown_number(drv) is None, '编辑态未编辑不应显示自动保存倒计时'
    _edit_name(drv, 'INT601 自动保存走查')
    n = _countdown_number(drv)
    assert n == 30, f'变脏后应显示「将在 30 秒后自动保存草稿」，实际 {n}'
    time.sleep(5)
    n2 = _countdown_number(drv)
    assert n2 is not None and n2 < n, f'倒计时应递减：{n} → {n2}'
    _edit_name(drv, 'INT601 自动保存走查二')
    n3 = _countdown_number(drv)
    assert n3 == 30, f'再次编辑应重置回 30s，实际 {n3}'
    _close_sheet(drv)


# ── 5. 归零自动保存：静默写草稿 + Sheet 不关 + 快照重置 ──
def test_05_zero_out_auto_save(drv):
    _open_edit_sheet(drv)
    _edit_name(drv, '归零自动保存走查')
    assert _countdown_number(drv) == 30, '编辑后应显示倒计时 30s'
    # 30s 归零 → 静默写草稿（无「草稿已保存」打扰 toast，§6.2）→ 时间戳 + 倒计时消失 + Sheet 不关
    WebDriverWait(drv, 35).until(
        lambda d: _countdown_number(d) is None and '上次保存' in _body_text(d))
    assert '编辑算法' in _body_text(drv), '自动保存成功后 Sheet 不应关闭'
    assert '草稿已保存' not in _body_text(drv), '30s 自动保存应静默（不弹「草稿已保存」toast）'
    # 快照重置：此刻关闭不再弹脏态守卫（§6.1）
    _press_esc(drv)
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(drv))
    assert '有未保存的更改' not in _body_text(drv), '自动保存成功后关闭不应弹脏态守卫'


# ── 6. 参数行失焦 1.5s 防抖草稿保存（旧习惯保留）──
def test_06_blur_debounce_draft_save(drv):
    _open_edit_sheet(drv)
    # 编辑参数表首行「参数代码」（合规：小写+下划线，符合 ^[a-z][a-z0-9_]*$）
    code_input = drv.find_element(
        By.CSS_SELECTOR, '#algorithm-mutate-form tbody tr input[placeholder="param_code"]')
    code_input.click()  # 先聚焦参数行输入，保证后续失焦触发参数表容器 focusout
    _edit_field_via_el(drv, code_input, 'input_audio_x')
    # 焦点移出参数表容器（点击基本信息区「显示名称」，§6.2 参数表容器 focusout）→ 1.5s 防抖草稿保存
    drv.find_element(By.XPATH, "//input[@id='algo-name']").click()
    WebDriverWait(drv, 8).until(lambda d: '草稿已保存' in _body_text(d))
    # 时间戳更新（footer「上次保存」出现）+ 保存后表单与草稿快照一致（倒计时消失）
    assert '上次保存' in _body_text(drv), '失焦防抖保存后应显示「上次保存」时间戳'
    assert _countdown_number(drv) is None, '失焦保存后表单已与草稿快照一致，不应再显示倒计时'
    _close_sheet(drv)


def _edit_field_via_el(drv, el, new_value):
    drv.execute_script(
        "const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
        "s.call(arguments[0], arguments[1]);"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
        el, new_value)
    time.sleep(0.6)


# ── 7. 草稿乐观锁冲突：footer inline Alert「草稿已过期」──
def test_07_draft_conflict_footer_alert(drv):
    _open_edit_sheet(drv)
    # 打开冲突模式 'draft'（走查钩子，接线后删除）
    drv.execute_script("window.__iatpAlgo && window.__iatpAlgo.setConflictMode('draft')")
    _edit_name(drv, '草稿冲突走查')
    # 手动保存草稿触发冲突（mock draft 分支恒冲突）
    _js_click(drv, "//button[normalize-space()='保存草稿']")
    WebDriverWait(drv, 8).until(
        lambda d: '草稿已过期：该算法已被他人修改' in _body_text(d))
    assert '继续编辑' in _body_text(drv) and '立即刷新' in _body_text(drv), \
        '草稿冲突应提供 [继续编辑][立即刷新] 动作'
    # 复位冲突模式 + 继续编辑 → 冲突清除，回到正常 footer
    drv.execute_script("window.__iatpAlgo && window.__iatpAlgo.setConflictMode('none')")
    _js_click(drv, "//button[normalize-space()='继续编辑']")
    WebDriverWait(drv, 5).until(
        lambda d: '草稿已过期：该算法已被他人修改' not in _body_text(d))
    assert '保存草稿' in _body_text(drv), '冲突清除后应恢复「保存草稿」按钮'
    _close_sheet(drv)


# ── 8. 发布乐观锁冲突：AlertDialog「发布冲突」──
def test_08_publish_conflict_dialog(drv):
    _open_edit_sheet(drv)
    drv.execute_script("window.__iatpAlgo && window.__iatpAlgo.setConflictMode('publish')")
    _edit_name(drv, '发布冲突走查')
    _js_click(drv, "//button[normalize-space()='发布']")
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(
            By.XPATH, "//*[@role='alertdialog'][contains(., '发布冲突')]"))
    txt = _body_text(drv)
    assert '发布冲突：该算法已被他人修改。' in txt, '发布冲突 AlertDialog 描述缺失'
    assert '刷新并丢弃我的更改' in txt and '继续编辑' in txt, \
        '发布冲突应提供 [刷新并丢弃我的更改][继续编辑]'
    # 复位 + 继续编辑 → Dialog 关闭、Sheet 不关
    drv.execute_script("window.__iatpAlgo && window.__iatpAlgo.setConflictMode('none')")
    _js_click(drv, "//*[@role='alertdialog']//button[contains(., '继续编辑')]")
    WebDriverWait(drv, 5).until(
        lambda d: not d.find_elements(
            By.XPATH, "//*[@role='alertdialog'][contains(., '发布冲突')]"))
    assert '编辑算法' in _body_text(drv), '继续编辑后 Sheet 应保持打开'
    _close_sheet(drv)


# ── 9. 发布成功：toast「算法已发布」+ Sheet 关闭 ──
def test_09_publish_success(drv):
    _open_edit_sheet(drv)
    _edit_name(drv, '发布成功走查')
    _js_click(drv, "//button[normalize-space()='发布']")
    WebDriverWait(drv, 10).until(lambda d: '算法已发布' in _body_text(d))
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(d))
    txt = _body_text(drv)
    assert '发布冲突' not in txt, '发布成功不应出现冲突 Dialog'


# ── 10. 脏态离开守卫：未保存关闭 → ConfirmDialog ──
def test_10_dirty_leave_guard(drv):
    _open_edit_sheet(drv)
    _edit_name(drv, '脏态离开走查')
    _press_esc(drv)
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(
            By.XPATH, "//*[@role='alertdialog'][contains(., '有未保存的更改')]"))
    # 点「离开并丢弃」→ Sheet 关闭
    _js_click(drv, "//*[@role='alertdialog']//button[contains(., '离开并丢弃')]")
    WebDriverWait(drv, 5).until(lambda d: '编辑算法' not in _body_text(d))
    assert '有未保存的更改' not in _body_text(drv), '离开后守卫不应残留'


# ── 11. 深浅两套主题下倒计时可读 ──
def test_11_light_dark_theme_readable(drv):
    # 浅色（默认）：打开编辑 Sheet → 倒计时可读
    _open_edit_sheet(drv)
    _edit_name(drv, '深浅色走查-浅色')
    assert _countdown_number(drv) == 30, '浅色主题下倒计时应可读'
    _close_sheet(drv)

    # 切深色（主题经 localStorage 持久化，后续整页刷新仍生效）
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, "//*[@role='radio'][contains(., '深色')]")
    _press_esc(drv)
    time.sleep(0.5)

    # 深色：打开编辑 Sheet → 倒计时可读
    _open_edit_sheet(drv)
    _edit_name(drv, '深浅色走查-深色')
    assert _countdown_number(drv) == 30, '深色主题下倒计时应可读'
    _close_sheet(drv)

    # 切回浅色还原
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, "//*[@role='radio'][contains(., '浅色')]")
    _press_esc(drv)
    time.sleep(0.5)


# ── 12. 全会话无 JS 运行时严重错误 ──
def test_12_no_js_runtime_errors(drv):
    _goto(drv, '/AlgorithmConfig')
    _wait_rows_retry(drv, 7)
    time.sleep(1.0)
    _drain_console(drv)
    assert not _CONSOLE_JS_ERRORS, \
        '浏览器控制台存在 JS 运行时严重错误：\n' + '\n'.join(_CONSOLE_JS_ERRORS[-10:])
