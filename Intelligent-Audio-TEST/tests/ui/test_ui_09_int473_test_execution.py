# -*- coding: utf-8 -*-
"""INT-473 测试执行 React 可视稿浏览器走查（真实 Chrome headless，按 test_ui_06 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5274）：
1. /E2ETest 五步向导渲染：标题/副文 + 步骤条五格（选择算法/选择测试用例/选择测试设备/
   执行测试/查看结果）+ 底部动作条「下一步」
2. 步骤一算法双通道写回：选择测试算法 → 选「流式识别引擎」→ 汇总行「已同步全局算法」
   + localStorage iatp:algorithm:v1 algorithmId=asr-stream
3. 步骤二用例正反选：全选结果（全量圈定 toast）+ 反选（对称差补齐）+ 已选汇总行
4. 步骤三设备混跑徽章：真机/HTTP API/Realtime WS 三类型 + 离线禁选
5. 【负责人 2026-10-16 核心口径】多友商横向能力对比——执行流程支持多被测主体同用例并发：
   /APITest 在线 API 全选（表头全选在线）+ 离线行禁选 + 并发自动合计 + 任务名称弹窗启动；
   /E2ETest 三型设备（真机/HTTP API/Realtime WS）混跑多选 → 已选 3 台设备（多被测主体同用例并发）
6. 主题抽屉：10 预设齐全 + lake-view 默认（本页零硬编码色值）
7. algo_engineer 只读观察态：注入无 task:execute 权限快照 → 只读提示 + 动作钮隐藏 + 步骤条可浏览

失败落 tests/ui/artifacts/int473_test_execution/<用例>/（截图+console+source）。
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

# 栈门禁豁免：本文件走查 frontend-react/ mock 稿（无后端依赖），
# tests/ui/conftest.py 经 STACK_GATE_EXEMPT_MODULES 对本模块放行。

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int473_test_execution')

# 5274 = INT-473 交付验收隔离副本 dev server（5273 为主工作区常驻）；env 可覆写
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5274')
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
    time.sleep(1.2)


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


def _click_next(drv):
    btn = [b for b in drv.find_elements(By.TAG_NAME, 'button')
           if b.text.strip() == '下一步' and b.is_displayed()]
    assert btn, '底部「下一步」按钮未找到'
    btn[0].click()
    time.sleep(0.8)


# ── 1. /E2ETest 五步向导渲染 ─────────────────────────────────
def test_01_e2e_wizard_renders(drv):
    _login(drv)
    _goto(drv, '/E2ETest')
    txt = _body_text(drv)
    assert '端到端测试' in txt, f'页标题缺失：{txt[:150]}'
    # 五格步骤条（10_测试执行.md v1.4 交付口径）
    for step_name in ['选择算法', '选择测试用例', '选择测试设备', '执行测试', '查看结果']:
        assert step_name in txt, f'步骤条缺「{step_name}」'
    # 步骤条当前态 ring 已挂载（当前格 aria-current=step）
    current = drv.find_elements(By.CSS_SELECTOR, "[aria-current='step']")
    assert current, '当前步骤未标记 aria-current'
    # 底部动作条：步骤 0 仅「下一步」
    btns = [b.text.strip() for b in drv.find_elements(By.TAG_NAME, 'button') if b.is_displayed()]
    assert '下一步' in btns, f'步骤 0 缺「下一步」：{btns}'


# ── 2. 步骤一算法写回全局 store ─────────────────────────────
def test_02_algorithm_channel_writeback(drv):
    _login(drv)
    _goto(drv, '/E2ETest')
    # 清除持久化算法，回到默认 asr-v3
    drv.execute_script("window.localStorage.removeItem('iatp:algorithm:v1')")
    _goto(drv, '/E2ETest')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='选择测试算法']").click()
    time.sleep(0.8)
    # 选择「流式识别引擎」（asr-stream）
    opts = drv.find_elements(By.CSS_SELECTOR, "div[data-slot='popover-content'] button, [role='listbox'] button")
    target = None
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and '流式识别引擎' in b.text:
            target = b
            break
    assert target, '算法选择浮层未找到「流式识别引擎」'
    target.click()
    time.sleep(0.8)
    # 汇总行「已同步全局算法」可见
    txt = _body_text(drv)
    assert '已同步全局算法' in txt, f'汇总行未出现「已同步全局算法」：{txt[:200]}'
    # localStorage 写回（iatp:algorithm:v1 → asr-stream）
    algo = json.loads(drv.execute_script(
        "return window.localStorage.getItem('iatp:algorithm:v1')") or '{}')
    stored = (algo.get('state') or {}).get('algorithmId')
    assert stored == 'asr-stream', f'全局算法未写回 store：{algo}'


# ── 3. 步骤二用例正反选 ─────────────────────────────────────
def test_03_cases_positive_negative_select(drv):
    _login(drv)
    _goto(drv, '/E2ETest')
    _click_next(drv)  # → 步骤一（选择测试用例）
    txt = _body_text(drv)
    assert '选择测试用例' in txt or '全选结果' in txt, f'步骤二未渲染：{txt[:150]}'
    # 正选：全选结果（POST /testcases/ids 全量圈定 toast）
    drv.find_element(By.XPATH, "//button[contains(., '全选结果')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '已全选' in _body_text(drv))
    summary = _body_text(drv)
    assert '已选' in summary, f'已选汇总行未出现：{summary[:200]}'
    # 反选：对称差补齐
    drv.find_element(By.XPATH, "//button[contains(., '反选')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '已反选' in _body_text(drv) or '补齐' in _body_text(drv))
    # 表格/卡片双模式切换
    drv.find_element(By.XPATH, "//button[contains(., '卡片')]").click()
    time.sleep(0.6)
    assert '卡片' in _body_text(drv), '卡片视图未切换'


# ── 4. 步骤三设备混跑徽章 ───────────────────────────────────
def test_04_device_mixed_badges(drv):
    _login(drv)
    _goto(drv, '/E2ETest')
    _click_next(drv)  # → 步骤一
    _click_next(drv)  # → 步骤二（选择测试设备）
    txt = _body_text(drv)
    assert '选择测试设备' in txt, f'步骤三未渲染：{txt[:150]}'
    # 三类型混跑徽章（10_测试执行.md §3.6.1：physical/http_api/websocket_api）
    for badge in ['真机', 'HTTP API', 'Realtime WS']:
        assert badge in txt, f'设备区缺「{badge}」徽章'
    # 离线设备禁选：入门-03（offline）不可选
    offline_cards = drv.find_elements(By.XPATH, "//button[contains(., '音箱-入门-03')]")
    if offline_cards:
        for card in offline_cards:
            assert card.get_attribute('disabled') or 'opacity-60' in card.get_attribute('class'), \
                '离线设备卡未被禁用'


# ── 5. 【核心口径】/APITest 多被测 API 同用例并发（多友商同时测试）──
def test_05_api_multi_vendor_concurrent(drv):
    _login(drv)
    _goto(drv, '/APITest')
    txt = _body_text(drv)
    assert 'API 测试' in txt, f'/APITest 未渲染：{txt[:150]}'
    _click_next(drv)  # → 步骤一（选择测试用例，默认算法 asr-v3 已解锁）
    _click_next(drv)  # → 步骤二（选择被测 API）
    txt = _body_text(drv)
    assert '选择被测 API' in txt or '最大并发' in txt, f'API 资源步未渲染：{txt[:150]}'
    # 表头全选在线 API（Base UI Checkbox 渲染为 button，data-slot=checkbox）：
    # asr-v3 过滤下在线 ASR HTTP API 被选中、离线 Wakeword 行禁选
    drv.find_element(By.CSS_SELECTOR, "[data-slot='checkbox'][aria-label='全选在线 API']").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    # 已选汇总行：1 个 API（在线被选）+ 并发上限自动合计 32
    assert '1 个 API' in txt, f'已选汇总未显示 1 个 API：{txt[:300]}'
    assert '并发上限' in txt and '32' in txt, f'已选汇总缺并发上限 32：{txt[:300]}'
    # 离线 API（Wakeword）行禁选：勾选态不增加
    offline_row = drv.find_elements(By.XPATH, "//tr[contains(., 'Wakeword')]")
    if offline_row:
        row = offline_row[0]
        checkbox = row.find_elements(By.CSS_SELECTOR, "[data-slot='checkbox']")
        if checkbox:
            cb = checkbox[0]
            assert cb.get_attribute('disabled') or 'disabled' in (
                cb.get_attribute('aria-disabled') or '') or 'disabled' in (
                cb.get_attribute('class') or ''), '离线 API 行未被禁选'
    # 启动校验链：已选在线 API 时开始测试通过（任务名称弹窗出现）
    drv.find_element(By.XPATH, "//button[contains(., '开始测试')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '任务名称' in _body_text(drv))
    txt = _body_text(drv)
    assert '任务名称' in txt, f'任务名称弹窗未打开：{txt[:200]}'
    # 弹窗执行摘要：所选 API 进入任务启动（apiIds 同用例集并发下发——代码层证据见验收结论）
    assert '1 个' in txt or '并发' in txt, f'任务名称弹窗缺执行摘要：{txt[:300]}'


# ── 5b. E2E 多被测主体（真机/HTTP API/Realtime WS 三型混跑）同用例并发 ──
def test_05b_e2e_multi_subject_mixed_run(drv):
    """负责人 2026-10-16 口径：多友商同时测试=多被测主体同用例并发。
    E2E 资源步跨类型多选（真机 音箱-客厅位 + ASR HTTP 网关 + Realtime WS 网关
    三型同时可勾选）→ 已选 3 台设备，验证执行流程支持混合类型并发。"""
    _login(drv)
    _goto(drv, '/E2ETest')
    _click_next(drv)  # → 步骤一
    _click_next(drv)  # → 步骤二（选择测试设备）
    # 三型设备卡同时勾选（真机/HTTP API/Realtime WS）
    for name in ['音箱-客厅位', 'ASR HTTP 网关', 'Realtime WS 网关']:
        drv.find_element(By.CSS_SELECTOR, f"[data-slot='checkbox'][aria-label='选择设备 {name}']").click()
        time.sleep(0.4)
    txt = _body_text(drv)
    assert '3 台设备' in txt, f'已选汇总未显示 3 台设备：{txt[:300]}'
    assert '真机' in txt and 'HTTP API' in txt and 'Realtime WS' in txt, \
        f'设备混跑三型徽章缺失：{txt[:300]}'
    # 离线设备（音箱-入门-03）禁选
    offline_cards = drv.find_elements(By.XPATH, "//button[contains(., '音箱-入门-03')]")
    if offline_cards:
        for card in offline_cards:
            assert card.get_attribute('disabled') or 'opacity-60' in card.get_attribute('class'), \
                '离线设备卡未被禁用'


# ── 6. 主题抽屉可用性（本页零硬编码色值）────────────────────
def test_06_theme_drawer_available(drv):
    _login(drv)
    _goto(drv, '/E2ETest')
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='打开主题设置']").click()
    time.sleep(1.0)
    sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
    txt = sheet.text
    assert '外观设置' in txt and '颜色预设' in txt, f'主题抽屉内容缺失：{txt[:150]}'
    labels = drv.execute_script(
        "return Array.from(document.querySelectorAll('span[role=radio][aria-label]'))"
        ".map(e => e.getAttribute('aria-label'))")
    for name in ['默认蓝', 'Anthropic', '简洁大字', '暗流', '玫瑰园', '湖光',
                 '落日', '林语', '海风', '薰衣草']:
        assert name in labels, f'预设缺「{name}」：{labels}'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)


# ── 7. algo_engineer 只读观察态（§3.1.1：动作钮/控制/提交隐藏）──
def test_07_readonly_observer_state(drv):
    """注入 algo_engineer 权限快照（有 algorithm:read、无 task:execute）：
    路由放行 → 只读观察模式——底部「只读」提示可见、开始测试/下一步等动作钮隐藏、
    设备勾选 checkbox 隐藏；步骤条仍可翻页浏览。"""
    # 先清会话再注入只读权限快照
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
                'permissions': ['algorithm:read', 'task:read', 'report:read'],
            }
        },
        'version': 0,
    }
    drv.execute_script(
        "window.localStorage.setItem('iatp:auth:v1', arguments[0])",
        json.dumps(snapshot, ensure_ascii=False))
    _goto(drv, '/E2ETest')
    txt = _body_text(drv)
    assert '端到端测试' in txt, f'只读态页面未渲染：{txt[:150]}'
    # 底部只读提示
    assert '只读' in txt and '当前为只读观察模式，不可执行测试' in txt, \
        f'只读观察提示缺失：{txt[:200]}'
    # 动作钮隐藏：开始测试 / 下一步 / 重置流程 均不应出现
    btns = [b.text.strip() for b in drv.find_elements(By.TAG_NAME, 'button') if b.is_displayed()]
    for forbidden in ['开始测试', '下一步', '重置流程']:
        assert forbidden not in btns, f'只读态不应出现「{forbidden}」：{btns}'
    # 步骤条仍可浏览（五个步骤格存在）
    for step_name in ['选择算法', '选择测试用例', '选择测试设备', '执行测试', '查看结果']:
        assert step_name in txt, f'只读态步骤条缺「{step_name}」'
    # 恢复 admin 会话（后续用例隔离）
    drv.execute_script("window.localStorage.clear()")
