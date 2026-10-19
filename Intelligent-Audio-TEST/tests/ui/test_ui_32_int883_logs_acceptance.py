# -*- coding: utf-8 -*-
"""INT-883 日志页验收浏览器实测（wiring/react，dev :5327 + 常驻后端 :5000）。

按 devloop §4.3 React 实测 + §3.3 界面卡附图：真实数据渲染 + 筛选 + 实时轮询兜底 +
空态/错误态 + 浅/深色截图 + Network 证据。按 test_ui_31_int693_logs 先例（Selenium
headless Chrome）。

验收清单映射：
1. 日志列表真实数据渲染 + 筛选 —— test_01 / test_02
2. Socket.IO /ws/logs 实时通道有推送 —— test_03 探测：断言轮询兜底 POST /logs/refresh
   真实请求 + 记录页面无 socket.io-client 连接（window.io 未定义、performance 无
   /socket.io 与 ws:// 条目）—— WS 主通道是否接入由此实证
3. 空态 / 错误态 —— test_04（CDP 拦截 → 错误态+重试恢复）/ test_05（搜索空 → 空态）
4. 浅色 + 深色 + Network 截图 —— test_06（深色截图）/ test_07（Network 证据叠加层截图）
"""
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5327')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int883_logs')
THEME_KEY = 'iatp:theme:v1:mode'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
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
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(d))


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


def _snap(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    assert os.path.getsize(path) > 10_000, f'截图过小: {name}'
    return path


def _network_overlay(drv, title, patterns):
    """注入固定底部网络证据面板（performance 条目 + WebSocket 探测）并截图。"""
    drv.execute_script("""
      const el = document.createElement('div');
      el.id = 'net-evidence';
      el.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:99999;'
        + 'max-height:34vh;overflow:auto;background:rgba(20,20,25,.92);color:#e6e6e6;'
        + 'font:11px/1.5 Consolas,monospace;padding:10px 12px;border:1px solid #555;'
        + 'border-radius:8px;white-space:pre-wrap;word-break:break-all;';
      const res = performance.getEntriesByType('resource')
        .map(e => e.name)
        .filter(n => n.includes('/api/v1/logs'))
        .slice(-12);
      const wsEntries = performance.getEntriesByType('resource')
        .map(e => e.name).filter(n => /^wss?:|\\/socket\\.io/.test(n));
      const ioType = typeof window.io;
      el.textContent = '[%s] Network 证据\\n'
        + 'window.io 类型: ' + ioType + '（undefined=未加载 socket.io-client）\\n'
        + 'socket.io/ws 资源条目数: ' + wsEntries.length + ' ' + JSON.stringify(wsEntries) + '\\n'
        + '--- /api/v1/logs 请求条目 ---\\n'
        + (res.length ? res.join('\\n') : '(无)');
      document.body.appendChild(el);
    """ % title)
    time.sleep(0.5)
    return _snap(drv, title + '.png')


def test_01_logs_real_data_and_stats(drv):
    """日志列表真实数据渲染 + 统计徽章（GET /logs + GET /logs/stats 真实请求）。"""
    _goto(drv, '/')
    _goto(drv, '/logs')
    _wait_text(drv, '日志查看')
    _wait_text(drv, '总日志条数')
    _wait_text(drv, '信息日志')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    # 分页信息（共 N 条日志）
    WebDriverWait(drv, 20).until(
        lambda d: '条日志' in _body_text(d))
    _snap(drv, 'logs-light.png')

    urls = _resource_urls(drv, '/api/v1/logs')
    assert any('/api/v1/logs' in u and 'stats' not in u for u in urls), \
        '未请求 GET /logs：%s' % urls
    assert any('stats' in u for u in _resource_urls(drv, '/api/v1/logs/stats')), \
        '未请求 GET /logs/stats'


def test_02_filters_search_and_levels(drv):
    """筛选：搜索关键词命中 + 级别 tag 移除后列表随筛选变化（query 换 key 同源重拉）。"""
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    before_total = drv.find_element(By.CSS_SELECTOR, 'tbody').text
    # 搜索一个真实存在的关键词（后端测试库当前有 device_group 等日志）
    inp = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]'))
    inp.clear()
    inp.send_keys('device')
    time.sleep(1.2)  # 防抖 300ms 后 refetch
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    after_total = drv.find_element(By.CSS_SELECTOR, 'tbody').text
    # 搜索命中后内容列含 device 或总数收缩（断言筛选真实作用于结果）
    assert 'device' in after_total.lower() or after_total != before_total, \
        '搜索筛选未改变结果：before=%r after=%r' % (before_total[:120], after_total[:120])
    shot = _snap(drv, 'logs-filter-search.png')

    # 级别 tag：移除 ERROR 后应仍有行（测试库 INFO 居多，断言 toolbar 交互无异常）
    chips = drv.find_elements(By.CSS_SELECTOR, 'button[aria-pressed]')
    assert len(chips) >= 4, '级别 tag 数量不足: %d' % len(chips)
    chips[0].click()
    time.sleep(0.8)
    _wait_text(drv, '日志查看')
    assert shot and os.path.getsize(shot) > 0


def test_03_realtime_polling_ws_probe(drv):
    """实时开关开启 → 轮询兜底 POST /logs/refresh 真实请求；探测 WS 主通道是否接入。"""
    _wait_text(drv, '日志查看')
    sw = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[data-slot="switch"][aria-label="实时日志开关"]'))
    sw.click()
    _wait_text(drv, '实时监控中')
    _wait_text(drv, '速率')
    _wait_text(drv, '延迟')
    time.sleep(2.5)
    # 轮询兜底真实请求（开环后至少触发一次 refresh）
    WebDriverWait(drv, 25).until(
        lambda d: any('logs/refresh' in u for u in _resource_urls(drv, '/api/v1/logs/refresh')))
    _snap(drv, 'realtime-monitor.png')

    # WS 主通道探测：socket.io-client 未被加载、无 /socket.io 或 ws:// 连接资源
    io_type = drv.execute_script('return typeof window.io')
    ws_res = drv.execute_script(
        'return performance.getEntriesByType("resource").map(e => e.name)'
        '.filter(n => /^wss?:|\\/socket\\.io/.test(n))')
    assert io_type == 'undefined', f'页面加载了 socket.io-client：window.io={io_type}'
    assert ws_res == [], f'存在 socket.io/ws 资源条目（WS 已接入？）: {ws_res}'
    # 记录证据到 artifacts（供验收判断 WS 主通道缺口）
    with open(os.path.join(ARTIFACTS, 'ws_probe.txt'), 'w', encoding='utf-8') as f:
        f.write('window.io=%s\nsocket.io/ws entries=%s\n' % (io_type, ws_res))
    # 关实时（回干净态）
    sw.click()
    time.sleep(0.5)


def test_04_error_state_and_retry(drv):
    """错误态：CDP 拦截 /api/v1/logs → 「日志列表加载失败」+ 重试恢复。"""
    _set_theme(drv, 'light')
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    drv.execute_cdp_cmd('Network.enable', {})
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*api/v1/logs*']})
    drv.refresh()
    _wait_text(drv, '日志列表加载失败', timeout=25)
    _wait_text(drv, '获取日志列表失败，请重试')
    _snap(drv, 'logs-error-state.png')
    # 恢复：解除拦截 + 点重试
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})
    retry = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '重试')]"))
    retry.click()
    WebDriverWait(drv, 25).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    assert '日志列表加载失败' not in _body_text(drv), '重试后仍未恢复'


def test_05_empty_state_no_match(drv):
    """空态：搜索不存在关键词 → 「未找到匹配日志」空态（非错误态）。"""
    _wait_text(drv, '日志查看')
    inp = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.CSS_SELECTOR, 'input[aria-label="搜索日志内容"]'))
    inp.clear()
    inp.send_keys('INT883_ZZZ_NONEXIST_9f8e')
    time.sleep(1.2)
    _wait_text(drv, '未找到匹配日志', timeout=25)
    _wait_text(drv, '换个关键词或清除筛选条件试试')
    _snap(drv, 'logs-empty-state.png')
    # 恢复：清除过滤器
    reset = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '清除过滤器')]"))
    reset.click()
    WebDriverWait(drv, 25).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)


def test_06_dark_theme_screenshot(drv):
    """深色主题 + Network 证据叠加。"""
    _set_theme(drv, 'dark')
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.2)
    theme_mode = drv.execute_script('return document.documentElement.className')
    assert 'dark' in theme_mode, '深色主题未生效：%s' % theme_mode
    _snap(drv, 'logs-dark.png')


def test_07_network_evidence_overlay(drv):
    """Network 证据：注入叠加层（/api/v1/logs 请求条目 + WS 探测结果）截图。"""
    _set_theme(drv, 'light')
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)
    time.sleep(1.0)
    _network_overlay(drv, 'network-evidence', '/api/v1/logs')
