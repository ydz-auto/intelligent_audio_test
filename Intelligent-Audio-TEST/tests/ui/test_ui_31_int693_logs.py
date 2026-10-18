# -*- coding: utf-8 -*-
"""INT-693 日志页接线浏览器验收（真实 Chrome headless，按 test_ui_28 先例）。

覆盖验收标准：
1. 登录→/logs 真实链路走通（真实后端 api_gateway :5000 + 本 run dev server :5312；
   rsbuild proxy /api → localhost:5000）；日志列表真实数据渲染（GET /logs）+ 统计
   徽章行（GET /logs/stats）真实接口。
2. 筛选工具栏/搜索/级别 tag 渲染；导出日志弹窗（含格式选择）/ 清除日志确认弹窗 /
   实时监控配置弹窗（轮询间隔/自动滚动/新日志计数 toast）逐项呈现。
3. 实时开关开启 → 实时监控指示器出现（POST /logs/refresh 轮询兜底）。
4. Network 证据：performance entries 含 /api/v1/logs、/api/v1/logs/stats、
   /api/v1/logs/refresh。
前置：5312 dev server 已在跑（本 worktree）；:5000 常驻后端（AUTH_MODE=off 全放行，
dev_user permissions=['*']）。本用例不做写操作（不清除/不标记真实日志），仅走查弹窗。
"""
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5312')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
# 与整站 tests/ui 其余用例同口径（PROJECT_ROOT = 仓库根；tests/ui/artifacts/...）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int693_logs')
THEME_KEY = 'iatp:theme:v1:mode'


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
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
        d = os.path.join(ARTIFACTS, item.name)
        os.makedirs(d, exist_ok=True)
        try:
            _DRIVER.save_screenshot(os.path.join(d, 'screenshot.png'))
            with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
                f.write(_DRIVER.page_source)
        except Exception:
            pass


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=20):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _set_theme(drv, mode):
    drv.execute_script(
        'try { localStorage.setItem(%r, %r) } catch (e) {}' % (THEME_KEY, mode))
    _goto(drv, '/logs')


def _resource_urls(drv, needle):
    return drv.execute_script(
        'return performance.getEntriesByType("resource").map(e => e.name)'
        '.filter(n => n.includes(%r))' % needle)


def test_01_logs_page_real_data(drv):
    os.makedirs(ARTIFACTS, exist_ok=True)
    # AUTH_MODE=off：先落会话引导（dev_user '*'），再进 /logs
    _goto(drv, '/')
    _goto(drv, '/logs')

    _wait_text(drv, '日志查看')
    # 统计徽章行（GET /logs/stats 真实数据）
    _wait_text(drv, '总日志条数')
    _wait_text(drv, '信息日志')
    # 日志表格真实数据渲染（tbody 至少 1 行）
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)

    light = os.path.join(ARTIFACTS, 'logs-light.png')
    drv.save_screenshot(light)
    assert os.path.getsize(light) > 10_000, '浅色截图过小'

    urls = _resource_urls(drv, '/api/v1/logs')
    assert any(u.endswith('/api/v1/logs') or '/api/v1/logs?' in u for u in urls), \
        '未请求 GET /logs：%s' % urls
    assert any('stats' in u for u in _resource_urls(drv, '/api/v1/logs/stats')), \
        '未请求 GET /logs/stats'


def test_02_dark_theme(drv):
    _set_theme(drv, 'dark')
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.5)
    dark = os.path.join(ARTIFACTS, 'logs-dark.png')
    drv.save_screenshot(dark)
    assert os.path.getsize(dark) > 10_000, '深色截图过小'
    theme_mode = drv.execute_script('return document.documentElement.className')
    assert 'dark' in theme_mode, '深色主题未生效：%s' % theme_mode


def test_03_export_dialog(drv):
    _set_theme(drv, 'light')
    _wait_text(drv, '日志查看')
    btn = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '导出日志')]"))
    btn.click()
    _wait_text(drv, '当前筛选条件')
    _wait_text(drv, '格式')
    _wait_text(drv, '导出')
    shot = os.path.join(ARTIFACTS, 'export-dialog.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '导出弹窗截图过小'
    # 关闭弹窗（ESC / 取消）
    cancel = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '取消')]"))
    cancel.click()
    time.sleep(0.5)


def test_04_clear_dialog(drv):
    _wait_text(drv, '日志查看')
    btn = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '清除日志')]"))
    btn.click()
    _wait_text(drv, '清除此时间之前的日志')
    _wait_text(drv, '保留已标记日志')
    _wait_text(drv, '清除操作不可恢复')
    shot = os.path.join(ARTIFACTS, 'clear-dialog.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '清除弹窗截图过小'
    cancel = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '取消')]"))
    cancel.click()
    time.sleep(0.5)


def test_05_realtime_toggle_and_config(drv):
    _wait_text(drv, '日志查看')
    # 开启实时日志开关 → 实时监控指示器出现（POST /logs/refresh 轮询兜底）
    sw = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="switch"][aria-label="实时日志开关"]'))
    sw.click()
    _wait_text(drv, '实时监控中')
    _wait_text(drv, '速率')
    _wait_text(drv, '延迟')
    # 打开实时监控配置弹窗
    cfg_btn = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '配置')]"))
    cfg_btn.click()
    _wait_text(drv, '实时监控配置')
    _wait_text(drv, '轮询间隔')
    _wait_text(drv, '自动滚动')
    _wait_text(drv, '新日志计数 toast')
    shot = os.path.join(ARTIFACTS, 'realtime-config.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '实时配置弹窗截图过小'
    # 关闭配置弹窗 + 关闭实时（回干净态）
    done = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '完成')]"))
    done.click()
    time.sleep(0.5)
    # 验证 refresh 轮询真实请求（开环后至少触发一次）
    WebDriverWait(drv, 20).until(
        lambda d: any('logs/refresh' in u for u in _resource_urls(drv, '/api/v1/logs/refresh')))


def test_06_column_sort(drv):
    """P2 返修：§4.4 排序列——时间列头可点击排序（客户端 sortLogs，第三次回原序）。"""
    _set_theme(drv, 'light')
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)

    def first_two_times():
        cells = drv.find_elements(By.CSS_SELECTOR, 'tbody tr td:nth-child(3)')
        return [c.text for c in cells[:2]]

    sort_btn = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(@aria-label, '按时间排序')]"))
    sort_btn.click()  # 第 1 击：desc（与后端默认倒序一致）
    time.sleep(0.3)
    d1 = first_two_times()
    sort_btn.click()  # 第 2 击：asc（旧在前）
    time.sleep(0.3)
    a1 = first_two_times()
    # 两次点击后时间列应升序（ISO 时间串逐字典序 = 时间序）
    assert a1[0] <= a1[1], f'时间升序排序未生效：{a1[0]} > {a1[1]}'
    sort_btn.click()  # 第 3 击：回服务端原序（回 desc 默认展示）
    time.sleep(0.3)
    r1 = first_two_times()
    assert r1[0] >= r1[1], f'第三次点击应回服务端倒序：{r1[0]} < {r1[1]}'
    shot = os.path.join(ARTIFACTS, 'logs-sorted.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '排序截图过小'


def test_07_error_state_not_empty(drv):
    """P2 返修：首载失败渲染 ErrorState（日志列表加载失败 + 重试），不得误显示空态「暂无日志」。

    用 CDP 拦截 /api/v1/logs* 列表请求制造加载失败，断言错误态出现且空态文案不出现；
    解除拦截点击重试后恢复真实数据（INT-607 错误态区分先例）。
    """
    _set_theme(drv, 'light')
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)

    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api/v1/logs*']})
    _goto(drv, '/logs')
    WebDriverWait(drv, 15).until(lambda d: '日志列表加载失败' in _body_text(drv))
    txt = _body_text(drv)
    assert '获取日志列表失败，请重试' in txt, '错误态描述缺失'
    assert '暂无日志' not in txt, '加载失败被误渲染成空态（P2-2 复发）'
    retry = [b for b in drv.find_elements(By.TAG_NAME, 'button') if '重试' in b.text]
    assert retry, '重试按钮未出现'
    shot = os.path.join(ARTIFACTS, 'error-state.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '错误态截图过小'

    # 解除拦截 + 点击重试 → 恢复真实数据
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    retry[0].click()
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    assert '日志列表加载失败' not in _body_text(drv), '重试后错误态未消失'
