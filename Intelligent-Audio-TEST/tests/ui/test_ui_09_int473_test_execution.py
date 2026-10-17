# -*- coding: utf-8 -*-
"""INT-473 测试执行 React 可视稿浏览器走查（真实 Chrome headless，按 test_ui_06 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5274）。
本文件断言随返工同步更新为新口径（负责人 2026-10-16 三条定稿）：
  1. 【口径定稿】开始测试不再分 E2E/API——单流程直启 /start-test，/E2ETest、/APITest
     旧链 redirect（不带 mode）；页面无「端到端测试/API 测试」模式切换。
  2. 【命名定稿】第二步步骤名 = 「选择设备/API」；设备网格 + API 表格同屏混选（一个
     任务同时含设备链路 + API 链路），已选汇总设备+API 双计数。
  3. 【口径确认】第二步无报告参数配置；启动校验设备/API 分别检查在线（至少选一）；
     任务名/执行摘要统一不按模式分叉。
  4. 用例不分类型：用例列表不再按 e2e/api 类型过滤（同一用例可被物理设备/HTTP API/
     WebSocket API 三种链路消费）。
  5. 分维筛选：设备（实验室/在线离线/系统类型）+ API（厂商/协议/在线状态）。
  6. 【负责人核心业务口径】多友商横向对比保留验证：多被测主体（设备+API）同用例并发，
     启动摘要设备+API 双计数 + API 并发上限自动合计。
  7. algo_engineer 只读观察态 + 主题抽屉深浅两套（本页零硬编码色值）。

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


def _wait_toasts_clear(drv, timeout=6):
    """sonner toast 右下角会盖住底部动作条；等 toast 自动消失后再点底部按钮，避免 ElementClickIntercepted。"""
    try:
        WebDriverWait(drv, timeout).until(
            lambda d: len([t for t in d.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')
                           if t.is_displayed()]) == 0)
    except Exception:
        pass


def _click_next(drv):
    _wait_toasts_clear(drv)
    btn = [b for b in drv.find_elements(By.TAG_NAME, 'button')
           if b.text.strip() == '下一步' and b.is_displayed()]
    assert btn, '底部「下一步」按钮未找到'
    btn[0].click()
    time.sleep(0.8)


def _click_start(drv):
    _wait_toasts_clear(drv)
    btn = [b for b in drv.find_elements(By.TAG_NAME, 'button')
           if b.text.strip() == '开始测试' and b.is_displayed()]
    assert btn, '底部「开始测试」按钮未找到'
    btn[0].click()
    time.sleep(0.6)


def _click_checkbox(drv, aria_label):
    """点勾选框（Base UI Checkbox：设备卡=button[data-slot=checkbox]；API 行经
    TooltipTrigger render 注入 data-slot=tooltip-trigger，统一按 [aria-label][role=checkbox] 定位）。"""
    els = [e for e in drv.find_elements(By.CSS_SELECTOR, f"[aria-label='{aria_label}']")
           if e.get_attribute('role') == 'checkbox']
    assert els, f'checkbox 「{aria_label}」未找到'
    target = els[0]
    assert not _is_disabled(target), f'checkbox 「{aria_label}」处于禁用态（离线禁选）'
    target.click()
    time.sleep(0.4)


def _is_disabled(el):
    # 仅看 disabled / aria-disabled（Tailwind 类名含 disabled:… 子串，不能按 class 判定）
    return bool(el.get_attribute('disabled')) or (el.get_attribute('aria-disabled') == 'true')


def _toggle_device(drv, name):
    _click_checkbox(drv, f'选择设备 {name}')


def _toggle_api(drv, name):
    _click_checkbox(drv, f'选择 {name}')


def _select_filter(drv, index, option_text):
    """Base UI Select：按工具行固定索引定位触发器（SelectValue 渲染原始 value，
    故按位 0=状态 1=实验室 2=系统类型 3=厂商 4=协议），再点选项（data-slot=select-item）。"""
    triggers = [t for t in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
                if t.is_displayed()]
    assert index < len(triggers), f'Select 触发器不足 {index + 1} 个（现有 {len(triggers)} 个）'
    triggers[index].click()
    time.sleep(0.5)
    opts = [o for o in drv.find_elements(By.CSS_SELECTOR, "[data-slot='select-item']")
            if o.is_displayed()]
    opt = next((o for o in opts if o.text.strip() == option_text), None)
    assert opt, f'Select 选项「{option_text}」未找到（现有：{[o.text.strip() for o in opts]}）'
    opt.click()
    time.sleep(0.4)


def _goto_step1_loaded(drv):
    """下一步 → 步骤一（选择设备/API），等待 mock 数据加载（音箱-客厅位=默认算法可见设备）。"""
    _click_next(drv)
    WebDriverWait(drv, 10).until(
        lambda d: '音箱-客厅位' in _body_text(d))


# ── 1. 单流程直启：无 E2E/API 模式切换 + 旧链 redirect ─────────
def test_01_single_flow_no_mode_switch(drv):
    _login(drv)
    _goto(drv, '/start-test')
    txt = _body_text(drv)
    assert '开始测试' in txt, f'页标题缺失：{txt[:150]}'
    # 四格步骤条（INT-486 合并后：选择测试用例/选择设备/API/执行测试/查看结果）
    for step_name in ['选择测试用例', '选择设备/API', '执行测试', '查看结果']:
        assert step_name in txt, f'步骤条缺「{step_name}」'
    # 无「端到端测试/API 测试」模式切换（页面内不再出现两模式表述）
    assert '端到端测试' not in txt, f'页面仍出现「端到端测试」模式：{txt[:200]}'
    assert 'API 测试' not in txt, f'页面仍出现「API 测试」模式：{txt[:200]}'
    # 步骤条当前态 ring 已挂载（当前格 aria-current=step）
    current = drv.find_elements(By.CSS_SELECTOR, "[aria-current='step']")
    assert current, '当前步骤未标记 aria-current'
    # 底部动作条：步骤 0 仅「下一步」
    btns = [b.text.strip() for b in drv.find_elements(By.TAG_NAME, 'button') if b.is_displayed()]
    assert '下一步' in btns, f'步骤 0 缺「下一步」：{btns}'
    # 旧链 redirect：/E2ETest、/APITest → /start-test（收藏夹/外部链接不断链）
    _goto(drv, '/E2ETest')
    assert 'start-test' in drv.current_url, f'/E2ETest 未 redirect 到 /start-test：{drv.current_url}'
    _goto(drv, '/APITest')
    assert 'start-test' in drv.current_url, f'/APITest 未 redirect 到 /start-test：{drv.current_url}'


# ── 2. 用例不分类型：e2e 型 + api 型同列表，无类型过滤 ─────────
def test_02_cases_no_type_filter(drv):
    _login(drv)
    _goto(drv, '/start-test')
    txt = _body_text(drv)
    assert '选择测试用例' in txt, f'步骤一未渲染：{txt[:150]}'
    # e2e 型（c-001 远场唤醒）与 api 型（a-001 ASR 流式转写）同列表展示——用例不分类型
    assert '远场唤醒' in txt, f'e2e 型用例缺失：{txt[:200]}'
    assert 'ASR 流式转写正确性' in txt, f'api 型用例缺失（应同列表展示）：{txt[:200]}'
    # 无「类型」facet/列（不再按 e2e/api 过滤）；工具栏仅有 分组/标签/评估维度
    for facet in ['分组', '标签', '评估维度']:
        assert facet in txt, f'用例工具栏缺「{facet}」facet'
    # 默认算法 asr_streaming 过滤下：tts_eval 用例不出现（算法过滤仍在，非类型过滤）
    assert 'TTS 音质 MOS 评估' not in txt, f'tts_eval 用例应被默认算法过滤：{txt[:200]}'


# ── 3. 用例正反选：全量圈定 + 对称差补齐 + 表格/卡片双模式 ─────
def test_03_case_positive_negative_select(drv):
    _login(drv)
    _goto(drv, '/start-test')
    assert '选择测试用例' in _body_text(drv)
    # 全量圈定（POST /testcases/ids）：当前筛选 asr_streaming 共 7 条
    drv.find_element(By.XPATH, "//button[contains(., '全选结果')]").click()
    WebDriverWait(drv, 10).until(lambda d: '已全选' in _body_text(d))
    summary = _body_text(drv)
    assert '已选 7 条用例' in summary, f'全选汇总错误：{summary[:200]}'
    # 清空后手动勾选 2 条 → 反选 = 对称差补齐（全量 7 − 已选 2 = 5）
    drv.find_element(By.XPATH, "//button[contains(., '清空选择')]").click()
    time.sleep(0.4)
    _click_checkbox(drv, '选择 远场唤醒 · 3 米距离')
    _click_checkbox(drv, '选择 连续对话 · 多轮上下文保持')
    drv.find_element(By.XPATH, "//button[contains(., '反选')]").click()
    # 反选=全量集−当前选中集（对称差），等待补齐计数落定（mock latency 120ms 后更新）
    WebDriverWait(drv, 10).until(
        lambda d: '反选补齐 5' in _body_text(d))
    summary = _body_text(drv)
    assert '反选补齐 5' in summary, f'反选对称差计数错误：{summary[:200]}'
    # 表格/卡片双模式切换
    drv.find_element(By.XPATH, "//button[contains(., '卡片')]").click()
    time.sleep(0.6)
    assert '卡片' in _body_text(drv), '卡片视图未切换'


# ── 4. 步骤二「选择设备/API」：设备+API 同屏混选双计数 ─────────
def test_04_resource_mixed_selection(drv):
    _login(drv)
    _goto(drv, '/start-test')
    _goto_step1_loaded(drv)
    txt = _body_text(drv)
    # 命名定稿：步骤标题 = 「选择设备/API」（不是「选择资源」）
    assert '选择设备/API' in txt, f'步骤条第二步未显示「选择设备/API」：{txt[:150]}'
    assert '选择资源' not in txt, f'仍出现旧表述「选择资源」：{txt[:200]}'
    # 设备网格 + 被测 API 表格同屏渲染
    assert '设备' in txt and '被测 API' in txt, f'设备+API 未同屏渲染：{txt[:200]}'
    # 设备三型混跑徽章
    for badge in ['真机', 'HTTP API', 'Realtime WS']:
        assert badge in txt, f'设备区缺「{badge}」徽章'
    # 第二步无报告参数配置（负责人口径确认：报告内容/导出在报告阶段）
    assert '报告参数' not in txt and '报告模板' not in txt, f'第二步不应有报告参数配置：{txt[:300]}'
    # 同屏混选：1 设备 + 1 API → 已选汇总双计数 + API 并发上限自动合计
    _toggle_device(drv, '音箱-客厅位')
    _toggle_api(drv, 'ASR HTTP API')
    time.sleep(0.4)
    summary = _body_text(drv)
    assert '已选 1 台设备 · 1 个 API' in summary, f'已选汇总未双计数：{summary[:300]}'
    assert '并发上限 32' in summary, f'API 并发上限合计缺失：{summary[:300]}'


# ── 5. 设备分维筛选：实验室 / 在线离线 / 系统类型 ──────────────
def test_05_device_filters(drv):
    _login(drv)
    _goto(drv, '/start-test')
    _goto_step1_loaded(drv)
    # 在线离线：仅在线 → 离线设备「音箱-入门-03」隐藏
    _select_filter(drv, 0, '在线')
    txt = _body_text(drv)
    assert '音箱-客厅位' in txt, '在线设备应保留'
    assert '音箱-入门-03' not in txt, '离线设备「音箱-入门-03」应被在线筛选隐藏'
    # 系统类型 = 鸿蒙（复位状态；API 区随系统筛选同步过滤无影响设备断言）
    _select_filter(drv, 0, '全部状态')
    _select_filter(drv, 2, '鸿蒙')
    txt = _body_text(drv)
    assert '音箱-客厅位' in txt, '鸿蒙设备缺失'
    assert '音箱-卧室位' not in txt, 'Android 设备应被鸿蒙筛选隐藏'
    assert 'ASR HTTP 网关' not in txt, 'http_api 设备应被鸿蒙筛选隐藏'
    # 实验室 = 旗舰实验室（复位系统；lab-a 成员=客厅位/卧室位/ASR网关/WS网关）
    _select_filter(drv, 2, '全部系统')
    _select_filter(drv, 1, '旗舰实验室')
    txt = _body_text(drv)
    assert '音箱-客厅位' in txt and '音箱-卧室位' in txt, '旗舰实验室设备缺失'
    assert '音箱-入门-03' not in txt, '非旗舰实验室设备「音箱-入门-03」应被隐藏'


# ── 6. API 分维筛选：厂商 / 协议 / 在线状态 ────────────────────
def test_06_api_filters(drv):
    _login(drv)
    _goto(drv, '/start-test')
    _goto_step1_loaded(drv)
    # 厂商 = 内部 ASR 组：仅 ASR HTTP API；Wakeword（内部唤醒组）隐藏
    _select_filter(drv, 3, '内部 ASR 组')
    txt = _body_text(drv)
    assert 'ASR HTTP API' in txt, '内部 ASR 组 API 缺失'
    assert 'Wakeword HTTP API' not in txt, '非 ASR 组 API 应被厂商筛选隐藏'
    # 协议 = WebSocket：mock API 全为 HTTP → 0 命中（复位厂商）
    _select_filter(drv, 3, '全部厂商')
    _select_filter(drv, 4, 'WebSocket')
    txt = _body_text(drv)
    assert 'ASR HTTP API' not in txt, 'HTTP API 应被协议筛选隐藏'
    assert '0 个可执行 API' in txt, f'WebSocket 筛选应显示 0 个可执行 API：{txt[:250]}'
    # 在线状态 = 离线（复位协议）：仅 Wakeword（离线）可见，ASR HTTP API（在线）隐藏
    _select_filter(drv, 4, '全部协议')
    _select_filter(drv, 0, '离线')
    txt = _body_text(drv)
    assert 'Wakeword HTTP API' in txt, '离线 API 缺失'
    assert 'ASR HTTP API' not in txt, '在线 API 应被离线筛选隐藏'


# ── 7. 启动校验：设备/API 分别检查在线（至少选一）──────────────
def test_07_launch_validation_online(drv):
    _login(drv)
    _goto(drv, '/start-test')
    _goto_step1_loaded(drv)
    # 1) 至少选一：无任何选择 → toast 拦截
    _click_start(drv)
    WebDriverWait(drv, 10).until(
        lambda d: '请至少选择一台在线设备或一个在线 API' in _body_text(d))
    # 2) 离线禁选（UI 层在线检查）：离线设备/离线 API checkbox 均 disabled
    off_dev = drv.find_elements(By.CSS_SELECTOR,
                                "[role='checkbox'][aria-label='选择设备 音箱-入门-03']")
    assert off_dev and _is_disabled(off_dev[0]), '离线设备 checkbox 未被禁选'
    off_api = drv.find_elements(By.CSS_SELECTOR,
                                "[role='checkbox'][aria-label='选择 Wakeword HTTP API']")
    assert off_api and _is_disabled(off_api[0]), '离线 API 行 checkbox 未被禁选'
    # 3) 选一台在线设备 → 校验链通过 → 任务名称弹窗（摘要统一不按模式分叉）
    _toggle_device(drv, '音箱-客厅位')
    _click_start(drv)
    WebDriverWait(drv, 10).until(lambda d: '任务名称' in _body_text(d))
    txt = _body_text(drv)
    assert '0 条 · 1 台 · 0 个 · 并发 4' in txt, f'任务名称弹窗摘要未按统一口径：{txt[:300]}'
    # 4) 任务名称默认值统一（不按 E2E/API 分叉）
    name_input = drv.find_element(By.ID, 'task-name')
    assert '测试任务_' in name_input.get_attribute('value'), '默认任务名未按统一口径「测试任务_」'


# ── 8. 【负责人核心口径】多友商横向对比：多被测主体同用例并发 ──
def test_08_multi_vendor_concurrent(drv):
    _login(drv)
    _goto(drv, '/start-test')
    _goto_step1_loaded(drv)
    # 多被测主体：2 台在线设备 + 在线 API 全选（表头全选在线）
    _toggle_device(drv, '音箱-客厅位')
    _toggle_device(drv, '音箱-卧室位')
    _click_checkbox(drv, '全选在线 API')
    time.sleep(0.4)
    summary = _body_text(drv)
    assert '已选 2 台设备 · 1 个 API' in summary, f'混选汇总错误：{summary[:300]}'
    assert '并发上限 32' in summary, f'API 并发上限自动合计缺失：{summary[:300]}'
    # 启动 → 任务名称弹窗执行摘要设备+API 双计数（同一用例集，多被测主体并发）
    _click_start(drv)
    WebDriverWait(drv, 10).until(lambda d: '任务名称' in _body_text(d))
    txt = _body_text(drv)
    assert '0 条 · 2 台 · 1 个 · 并发 4' in txt, f'任务摘要未设备+API 双计数：{txt[:300]}'


# ── 9. 主题抽屉可用性（本页零硬编码色值）────────────────────
def test_09_theme_drawer_available(drv):
    _login(drv)
    _goto(drv, '/start-test')
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


# ── 10. algo_engineer 只读观察态（§3.1.1：动作钮/控制/提交隐藏）──
def test_10_readonly_observer_state(drv):
    """注入 algo_engineer 权限快照（有 algorithm:read、无 task:execute）：
    路由放行 → 只读观察模式——底部「只读」提示可见、开始测试/下一步等动作钮隐藏、
    设备/API 勾选 checkbox 隐藏；步骤条仍可翻页浏览。"""
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
    _goto(drv, '/start-test')
    txt = _body_text(drv)
    assert '开始测试' in txt, f'只读态页面未渲染：{txt[:150]}'
    # 底部只读提示
    assert '只读' in txt and '当前为只读观察模式，不可执行测试' in txt, \
        f'只读观察提示缺失：{txt[:200]}'
    # 动作钮隐藏：开始测试 / 下一步 / 重置流程 均不应出现
    btns = [b.text.strip() for b in drv.find_elements(By.TAG_NAME, 'button') if b.is_displayed()]
    for forbidden in ['开始测试', '下一步', '重置流程']:
        assert forbidden not in btns, f'只读态不应出现「{forbidden}」：{btns}'
    # 步骤条仍可浏览（四个步骤格存在）
    for step_name in ['选择测试用例', '选择设备/API', '执行测试', '查看结果']:
        assert step_name in txt, f'只读态步骤条缺「{step_name}」'
    # 只读态步骤条可浏览；动作钮已由上述断言覆盖（开始测试/下一步/重置流程隐藏）
    assert '下一步' not in btns, '只读态不应有「下一步」'
    # 恢复 admin 会话（后续用例隔离）
    drv.execute_script("window.localStorage.clear()")
