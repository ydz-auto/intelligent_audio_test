# -*- coding: utf-8 -*-
"""INT-887 Benchmark 页真实数据走查（wiring/react 接线验收，连常驻 5000 段后端栈）。

前端 dev server 5330（/api 代理 → localhost:5000），AUTH_MODE=off：未登录访客全员放行，
公开路由 /rankings 首屏即真实排行数据（GET /api/v1/benchmarks/ranking 返回 INT844 单行）。

验证点（对应卡验收清单）：
1. 真实数据渲染：组卡标题「{metric_name} · {scenario_key}」、方向徽章、主值、来源/主体类型徽章、
   名次、计算于角标，全部与后端 GET /benchmarks/ranking 返回一致；无 mock 残留
   （旧 mock 算法卡「通用识别引擎」、旧 mock 组卡「字错率 · 通用」不出现）。
2. 筛选行真实数据源：测试集 Select 含数据去重 suite（general）、指标 Select 来自
   /benchmarks/metric-mappings 真实映射、主体联想来自 /ranking/subjects。
3. 主链路可操作：类别页签写 URL、列表/表格视图切换、立即计算 ConfirmDialog → POST compute → toast。
4. 空态：语音合成类别（后端无数据）→「暂无排行数据」。
5. 错误态：CDP 阻断 /benchmarks/ranking →「排行加载失败」+ 重试；解除后重试恢复数据。
6. 浅色/深色截图 + Network 性能日志（真实 /benchmarks/* 请求，snake_case 返回）。

失败落 tests/ui/artifacts/int887_benchmark/<用例>/（截图+console+source+network）。
"""
import json
import os
import time
from urllib.parse import unquote

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int887_benchmark')

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5330')
API = os.environ.get('REACT_API_BASE', 'http://localhost:5330/api/v1')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 后端排行主查询（走 dev server 代理 → 常驻 5000 网关），断言页面渲染与 API 一致
RANKING_URL = API + '/benchmarks/ranking'


def _api_ranking():
    r = requests.get(RANKING_URL, timeout=20)
    r.raise_for_status()
    return r.json()['data']['items']


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {
        'browser': 'ALL',
        'performance': 'ALL',
    })
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
    drv.set_page_load_timeout(60)
    return drv


_DRIVER = None
_CONSOLE_SEVERE = []


def _drain_console(drv):
    global _CONSOLE_SEVERE
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                _CONSOLE_SEVERE.append(entry.get('message', ''))
    except Exception:
        pass


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
        network = []
        try:
            for entry in drv.get_log('performance'):
                msg = entry.get('message', '')
                if '/benchmarks/' in msg or '/algorithm/' in msg:
                    network.append(msg)
        except Exception:
            pass
        with open(os.path.join(d, 'network.log'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(network))
    except Exception:
        pass


@pytest.fixture(scope='session')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    yield _DRIVER
    try:
        _drain_console(_DRIVER)
        _DRIVER.quit()
    except Exception:
        pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


def _goto(drv, path, wait_ready=True):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _wait_text_gone(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text not in _body_text(drv))


def _reset_page_state(drv):
    """清空排行页算法/视图本地态，确保用例从默认「全部算法 + 列表视图」开始。"""
    # 先落到站内页（初始 data:/about:blank 上 localStorage 不可读）
    if not drv.current_url.startswith(BASE):
        drv.get(BASE + '/')
        time.sleep(0.5)
    drv.execute_script(
        'localStorage.removeItem("iatp:rankings:v1:algorithm");'
        'localStorage.removeItem("iatp:rankings:v1:view");'
        'localStorage.removeItem("theme");')
    time.sleep(0.3)


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_realdata_render_no_mock_residual(drv):
    """真实数据渲染：组卡标题/方向/主值/来源徽章/名次/计算于与后端 API 一致，无 mock 残留。"""
    _reset_page_state(drv)
    items = _api_ranking()
    assert items, '后端 /benchmarks/ranking 无数据，无法走查真实数据渲染'
    row = items[0]
    _goto(drv, '/rankings')
    _wait_text(drv, row['subject_name'])
    _wait_text(drv, f"{row['metric_name']} · {row['scenario_key']}")
    text = _body_text(drv)
    # 组卡角标与方向徽章
    direction = '越低越好' if row['direction'] == 'lower_is_better' else '越高越好'
    assert direction in text, f'方向徽章「{direction}」缺失'
    assert '个主体 · 计算于' in text, '「个主体 · 计算于」角标缺失'
    # 主值（compact 格式：值+单位）
    val = str(row['metric_value']).rstrip('0').rstrip('.') if '.' in str(row['metric_value']) else str(row['metric_value'])
    assert f'{val}{row["unit"]}' in text, f'主值「{val}{row["unit"]}」未渲染'
    # 来源徽章与主体类型徽章
    source_label = '平台实测' if row['source'] == 'platform_test' else '外部基线'
    assert source_label in text, f'来源徽章「{source_label}」缺失'
    type_label = '开源' if row['subject_type'] == 'open_source' else '闭源'
    assert type_label in text, f'主体类型徽章「{type_label}」缺失'
    # 名次（列表视图左列 rank.）
    assert f"{row['rank']}." in text, f'名次「{row["rank"]}」缺失'
    # 无 mock 残留：旧 mock 算法卡/组卡不应出现
    assert '通用识别引擎' not in text, '旧 mock 算法卡「通用识别引擎」残留'
    assert '字错率 · 通用' not in text, '旧 mock 组卡「字错率 · 通用」残留'
    # 算法网格降级条（/algorithm/definitions 在常驻栈走 400 时优雅降级，INT-875 观测）
    if '算法详情暂不可用' in text:
        print('[env] 算法详情暂不可用：常驻栈 algorithm gRPC 50067 未监听，页面优雅降级（env 缺口，非接线缺陷）')
    _save_evidence('test_realdata_render_no_mock_residual', drv)


def test_filters_real_sources(drv):
    """筛选行真实数据源：测试集 Select 含数据 suite、指标 Select 来自真实映射、来源 Select 三态。"""
    _reset_page_state(drv)
    items = _api_ranking()
    suite = items[0]['benchmark_suite']
    _goto(drv, '/rankings')
    _wait_text(drv, items[0]['subject_name'])
    # 测试集 Select：打开 → 验证选项 → 点「全部测试集」选中并关闭
    drv.find_element(By.XPATH, "//button[@aria-label='测试集']").click()
    time.sleep(0.5)
    suite_text = _body_text(drv)
    assert '全部测试集' in suite_text
    assert suite in suite_text, f'测试集选项「{suite}」缺失'
    drv.find_element(By.XPATH, "//*[@role='option' and contains(., '全部测试集')]").click()
    time.sleep(0.4)
    # 指标 Select（真实映射：Word Error Rate 来自 /metric-mappings）
    drv.find_element(By.XPATH, "//button[@aria-label='指标']").click()
    time.sleep(0.5)
    metric_text = _body_text(drv)
    assert '全部指标' in metric_text
    assert 'Word Error Rate' in metric_text, '指标下拉未含真实映射「Word Error Rate」'
    assert 'TTLW 末字延迟' in metric_text, '指标下拉未含真实映射「TTLW 末字延迟」'
    drv.find_element(By.XPATH, "//*[@role='option' and contains(., '全部指标')]").click()
    time.sleep(0.4)
    # 来源 Select 三态
    drv.find_element(By.XPATH, "//button[@aria-label='数据来源']").click()
    time.sleep(0.5)
    source_text = _body_text(drv)
    for label in ('全部来源', '平台实测', '外部基线'):
        assert label in source_text, f'来源选项「{label}」缺失'
    drv.find_element(By.XPATH, "//*[@role='option' and contains(., '全部来源')]").click()


def test_category_tab_writes_url_and_empty_state(drv):
    """类别页签主链路 + 空态：语音识别写 category=asr；语音合成（后端无数据）→ 空态「暂无排行数据」。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '排行榜')
    # 默认全部 → 数据态
    asr_tab = drv.find_element(By.XPATH, "//div[@role='tablist']//button[contains(., '语音识别')]")
    asr_tab.click()
    time.sleep(0.8)
    assert 'category=asr' in drv.current_url, 'URL 未写入 category=asr'
    # 语音合成 → 空态（后端无 tts 排行数据）
    tts_tab = drv.find_element(By.XPATH, "//div[@role='tablist']//button[contains(., '语音合成')]")
    tts_tab.click()
    time.sleep(0.8)
    assert 'category=tts' in drv.current_url, 'URL 未写入 category=tts'
    _wait_text(drv, '暂无排行数据')
    text = _body_text(drv)
    assert '尚未计算排行' in text, '空态描述缺失'
    assert '立即计算' in text, '空态「立即计算」按钮缺失（AUTH_MODE=off 全员放行）'
    _save_evidence('test_category_tab_writes_url_and_empty_state', drv)
    # 切回语音识别恢复数据态
    asr_tab = drv.find_element(By.XPATH, "//div[@role='tablist']//button[contains(., '语音识别')]")
    asr_tab.click()
    time.sleep(0.8)
    items = _api_ranking()
    _wait_text(drv, items[0]['subject_name'])


def test_error_state_retry_recovers(drv):
    """错误态：CDP 阻断 /benchmarks/ranking → 「排行加载失败」+ 重试；解除后重试恢复数据。"""
    _reset_page_state(drv)
    items = _api_ranking()
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.setBlockedURLs', {
        'urls': ['*benchmarks/ranking*', '*benchmarks/ranking?*']})
    try:
        _goto(drv, '/rankings')
        _wait_text(drv, '排行加载失败')
        text = _body_text(drv)
        assert '查询排行失败，请稍后重试' in text or '无法连接到服务器' in text or '排行加载失败' in text
        assert '重试' in text, '错误态「重试」按钮缺失'
        _save_evidence('test_error_state_retry_recovers', drv)
    finally:
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    # 解除阻断 → 点「重试」恢复数据
    drv.find_element(By.XPATH, "//button[contains(., '重试')]").click()
    _wait_text(drv, items[0]['subject_name'])


def test_view_switch_and_table_columns(drv):
    """列表/表格视图切换：表格列（名次/主体类型/来源/版本/score100/百分位/与最佳差/与中位差/计算于）。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '排行榜')
    _wait_text(drv, '榜单')
    table_tab = drv.find_element(By.XPATH, "//button[contains(., '表格')]")
    table_tab.click()
    time.sleep(0.8)
    text = _body_text(drv)
    for col in ('名次', '主体类型', '来源', '版本', 'score100', '百分位', '与最佳差', '与中位差', '计算于'):
        assert col in text, f'表格列「{col}」缺失'
    drv.find_element(By.XPATH, "//button[contains(., '列表')]").click()
    time.sleep(0.8)
    assert '与中位差' not in _body_text(drv), '切回列表后表格列不应保留'


def test_recompute_confirm_dialog(drv):
    """主链路：立即计算 → ConfirmDialog → POST /benchmarks/ranking/compute → toast「排行计算完成」。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '立即计算')
    drv.find_element(By.XPATH, "//button[contains(., '立即计算')]").click()
    time.sleep(0.6)
    dialog = _body_text(drv)
    assert '重新计算排行？' in dialog, '确认弹窗标题缺失'
    assert '将合并平台实测与外部基线全量重算' in dialog, '弹窗描述缺失'
    drv.find_element(By.XPATH, "//button[contains(., '开始计算')]").click()
    _wait_text(drv, '排行计算完成', timeout=25)


def test_dark_theme_renders(drv):
    """深浅色：深色下榜单仍渲染 + 深色截图。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings')
    _wait_text(drv, '排行榜')
    items = _api_ranking()
    _wait_text(drv, items[0]['subject_name'])
    # 经 PublicHeader ConfigDrawer 切「深色」（抽屉开着时点 trigger 会被遮罩拦截，用 Escape 关闭）
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    time.sleep(0.6)
    drv.find_element(By.XPATH, "//*[@aria-label='选择深色']").click()
    time.sleep(0.8)
    ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.6)
    _wait_text(drv, items[0]['subject_name'])
    text = _body_text(drv)
    assert '排行榜' in text and '榜单' in text
    html_class = drv.find_element(By.TAG_NAME, 'html').get_attribute('class')
    print(f'[dark] html class = {html_class}')
    _save_evidence('test_dark_theme_renders', drv)


def test_network_evidence_real_requests(drv):
    """Network 证据：页面加载期间真实请求 /benchmarks/ranking、/ranking/subjects、/metric-mappings。"""
    _reset_page_state(drv)
    _goto(drv, '/rankings?category=asr')
    _wait_text(drv, '排行榜')
    items = _api_ranking()
    _wait_text(drv, items[0]['subject_name'])
    # 触发主体联想（/ranking/subjects）与指标映射（/metric-mappings 已在筛选行加载）
    try:
        inp = drv.find_element(By.XPATH, "//input[@aria-label='搜索主体']")
        inp.click()
        inp.send_keys('INT844')
        time.sleep(1.0)
    except Exception:
        pass
    time.sleep(1.0)
    urls = []
    try:
        for entry in drv.get_log('performance'):
            msg = entry.get('message', '')
            try:
                data = json.loads(msg)
                method = data.get('message', {}).get('method', '')
                if method == 'Network.requestWillBeSent':
                    u = data['message']['params']['request'].get('url', '')
                    if u.startswith('http://localhost:5330/api'):
                        urls.append(u)
            except Exception:
                continue
    except Exception:
        pass
    joined = '\n'.join(sorted(set(urls)))
    print(f'[network] captured {len(set(urls))} api urls:\n{joined}')
    d = os.path.join(ARTIFACTS, 'test_network_evidence_real_requests')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'network.log'), 'w', encoding='utf-8') as f:
        f.write(joined)
    assert any('/benchmarks/ranking' in u for u in urls), f'未见 /benchmarks/ranking 请求\n{joined}'
    assert any('/benchmarks/metric-mappings' in u for u in urls), '未见 /benchmarks/metric-mappings 请求'
    assert any('/benchmarks/ranking/subjects' in u for u in urls), '未见 /benchmarks/ranking/subjects 请求'
