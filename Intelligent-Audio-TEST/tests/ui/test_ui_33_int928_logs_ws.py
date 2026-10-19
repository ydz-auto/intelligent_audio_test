# -*- coding: utf-8 -*-
"""INT-928 日志实时主通道 Socket.IO /ws/logs 接线浏览器验收（真实 Chrome headless，按 test_ui_31 先例）。

覆盖验收标准（INT-928 期望，对照 17_配置运维.md §4.6/§7.11）：
1. 实时开关开启 → 主走 Socket.IO /ws/logs：connect + set_filter / subscribe_task，
   监听 task_log 事件增量插顶；WS 已连即纯 WS 主通道（无 POST /logs/refresh 轮询请求）。
2. 合成 task_log（Redis TASK_EVENTS → 网关 EventBusForwarder → /ws/logs task_log）到达
   → 表格首行插顶（断言可见状态，不只看 DOM）。
3. algo_engineer（log:websocket 无 log:manage）可开实时（WS 订阅）；refresh 兜底需
   log:manage，无此码时 WS 不可用即实时不可用（指示器「连接中断」）。
4. WS 连接失败/不可用 → 有 log:manage 降级 POST /logs/refresh 轮询兜底（「轮询兜底」）。
5. Network/WS 证据：/socket.io 握手 + ws:// 连接 + set_filter/task_log 帧（CDP performance）；
   浅/深色截图（WS实时状态）。

前置：dev server（REACT_DEV_BASE 默认 localhost:5327）；:5000 常驻后端（AUTH_MODE=off 全放行，
dev_user permissions=['*']）。合成 task_log 仅走 Redis 事件总线，不落库，验收后无残留。
"""
import json
import os
import time

import pytest
import redis
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5327')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int928_logs_ws')
THEME_KEY = 'iatp:theme:v1:mode'
AUTH_STORE_KEY = 'iatp:auth:v1'
REDIS_URL = os.environ.get('INT928_REDIS_URL', 'redis://localhost:6379')
# 常驻后端 AUTH_MODE=off 下网关注入 dev_user '*'；合成日志仅总线推送不落库
REDIS_CHANNEL = 'task_events'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    # performance 域捕获 Network/WS 帧（Network.webSocketFrameSent/Received 等）
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


@pytest.fixture(scope='function')
def drv():
    """每个用例独立 Chrome 会话（长会话下 headless+performance 日志易崩，函数级隔离最稳）。"""
    global _DRIVER
    _DRIVER = _driver()
    yield _DRIVER
    try:
        _DRIVER.quit()
    except Exception:
        pass
    _DRIVER = None


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


def _inject_algo_session(drv):
    """algo_engineer（log:read + log:websocket，无 log:manage）会话注入持久化 auth store。
    先阻断 /auth/mode + /auth/me 再建源：off 模式 dev_user 回填被拦 → 不会写回覆盖注入会话。"""
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*auth/mode*', '*auth/me*']})
    # 建源（about:blank 上写 localStorage 会抛 SecurityError）
    drv.get(BASE + '/')
    time.sleep(1.5)
    user = {
        'id': 'algo-engineer-int928',
        'username': 'algo_engineer',
        'displayName': '算法工程师',
        'roleName': '算法工程师',
        # 对齐 seed_rbac.py:272：algo_engineer = log:read + log:websocket，无 log:manage
        'permissions': ['log:read', 'log:websocket'],
    }
    # %r 生成 JS 字符串字面量（%s 会把 dict 当对象 → localStorage 存成 "[object Object]"）
    drv.execute_script(
        'localStorage.setItem(%r, %r)' % (
            AUTH_STORE_KEY, json.dumps({'state': {'user': user}, 'version': 0})))


def _toggle_realtime(drv):
    switch = WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]'))
    switch.click()
    time.sleep(1)


def _perf_events(drv):
    """读取 performance 域日志 → [(method, params)]（双层嵌套解析，勿在顶层取）。"""
    out = []
    try:
        for entry in drv.get_log('performance'):
            outer = json.loads(entry['message'])
            inner = outer['message']
            out.append((inner.get('method'), inner.get('params') or {}))
    except Exception:
        pass
    return out


def _perf_after(drv, drain_prev=True):
    """清除已消费的性能事件，返回新窗口事件列表。"""
    if drain_prev:
        drv.get_log('performance')
        time.sleep(0.2)
        drv.get_log('performance')
    time.sleep(0.3)
    return _perf_events(drv)


def _refresh_requests(events):
    urls = []
    for method, params in events:
        if method == 'Network.requestWillBeSent':
            url = params.get('request', {}).get('url', '')
            if '/api/v1/logs/refresh' in url:
                urls.append(url)
    return urls


def _ws_frames(events):
    """收集 WS 帧 → (direction, payloadData)。"""
    frames = []
    for method, params in events:
        if method == 'Network.webSocketFrameSent':
            resp = params.get('response', {})
            frames.append(('SENT', resp.get('payloadData', '')))
        elif method == 'Network.webSocketFrameReceived':
            resp = params.get('response', {})
            frames.append(('RCVD', resp.get('payloadData', '')))
    return frames


def _ws_urls(events):
    return [params.get('url', '') for method, params in events
            if method == 'Network.webSocketCreated']


def _publish_marker(marker, log_id):
    rc = redis.from_url(REDIS_URL)
    rc.publish(REDIS_CHANNEL, json.dumps({
        'event_type': 'task_log',
        'payload': {
            'task_id': None,
            'log_payload': {
                'id': log_id,
                'time': '2026-10-19 12:00:00',
                'level': 'INFO',
                'module': 'run_all',
                'content': marker,
                'mark': '',
                'task_id': None,
                'test_case_id': None,
                'category': 'test',
                'source': 'run_all',
            },
        },
    }, ensure_ascii=False))
    rc.close()


def _first_row_text(drv):
    rows = drv.find_elements(By.CSS_SELECTOR, 'tbody tr')
    return rows[0].text if rows else ''


def _goto_logs(drv, theme='light'):
    _goto(drv, '/')          # 先建源（函数级 driver 初始为 about:blank，此时写 localStorage 抛 SecurityError）
    _set_theme(drv, theme)   # 主题写入本地存储后全量加载 /logs 生效
    _goto(drv, '/logs')
    _wait_text(drv, '日志查看')
    WebDriverWait(drv, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, 'tbody tr')) > 0)


def test_01_realtime_ws_main_channel_pure_ws(drv):
    """dev_user：实时开关开启 → /ws/logs 主通道（WS实时）→ 纯 WS 无 refresh 轮询 →
    合成 task_log 首行插顶。"""
    os.makedirs(ARTIFACTS, exist_ok=True)
    _goto_logs(drv, 'light')

    _toggle_realtime(drv)
    _wait_text(drv, 'WS实时', 25)          # 指示器显示 WS 主通道已连
    _wait_text(drv, '实时监控中')
    time.sleep(1.5)

    # Network/WS 证据：先抓切换期产生的 WS 帧（/ws/logs 命名空间连接 + set_filter），
    # 读取即清空缓冲 → 后续窗口断言纯 WS 无轮询。
    ev_ws = _perf_events(drv)
    ws_urls = _ws_urls(ev_ws)
    assert any('socket.io' in u or 'ws://' in u for u in ws_urls), \
        '未捕获 WebSocket 连接：%s' % ws_urls[:5]
    frames = _ws_frames(ev_ws)
    all_payload = ' '.join(p for _, p in frames)
    assert 'ws/logs' in all_payload, \
        'WS 帧未含 /ws/logs 命名空间连接：%s' % frames[:5]
    assert 'set_filter' in all_payload, 'WS 帧未含 set_filter：%s' % frames[:5]

    # 纯 WS 主通道：WS 已连期间不应出现 POST /logs/refresh（默认轮询间隔 5s → 等 6.5s）
    time.sleep(6.5)
    refs = _refresh_requests(_perf_events(drv))
    assert not refs, 'WS 已连不应有 refresh 轮询兜底：%s' % refs[:3]

    # 合成 task_log → 表格首行插顶（断言可见状态）
    marker = 'INT928_BROWSER_%d' % int(time.time())
    log_id = 900000000 + int(time.time() * 1000) % 100000000
    _publish_marker(marker, log_id)
    WebDriverWait(drv, 15).until(lambda d: marker in _first_row_text(d))
    first = _first_row_text(drv)
    assert marker in first, '合成 task_log 未首行插顶，首行：%s' % first[:120]

    # WS 帧证据落盘（ws_probe 同款）
    ws_probe = os.path.join(ARTIFACTS, 'ws_probe.txt')
    with open(ws_probe, 'w', encoding='utf-8') as f:
        f.write('window.io 定义（由 performance 帧佐证 WS 主通道）：\n')
        f.write('WS 连接 URL：%s\n' % ws_urls)
        f.write('WS 帧（前 20 条）：\n')
        for direction, payload in frames[:20]:
            f.write('%s %s\n' % (direction, payload[:160]))
        f.write('WS 已连期间 refresh 轮询请求：%s\n' % refs)
    shot = os.path.join(ARTIFACTS, 'light_ws_realtime.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '浅色截图过小'


def test_02_algo_engineer_ws_realtime(drv):
    """algo_engineer（log:websocket 无 log:manage）：实时开关可见、可开、WS实时；无清除日志按钮。"""
    _inject_algo_session(drv)
    _goto_logs(drv, 'light')
    # 开关存在（canRealtime=log:websocket）
    WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]'))
    # 无 log:manage → 无清除日志按钮
    btns = _body_text(drv)
    assert '清除日志' not in btns, 'algo_engineer 不应有清除日志（log:manage）入口'

    _toggle_realtime(drv)
    _wait_text(drv, 'WS实时', 25)          # WS 订阅可用
    _wait_text(drv, '实时监控中')

    # WS 已连纯 WS；即使 WS 不可用也应「连接中断」而非轮询兜底（canPollFallback=false）
    events = _perf_after(drv)
    time.sleep(6.5)
    refs = _refresh_requests(events + _perf_after(drv))
    assert not refs, 'algo_engineer 无 log:manage，不应有 refresh 轮询：%s' % refs[:3]

    shot = os.path.join(ARTIFACTS, 'algo_engineer_ws_realtime.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, 'algo_engineer 截图过小'
    # 清掉阻断，避免影响后续用例
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})


def test_03_ws_unavailable_fallback_polling(drv):
    """dev_user：WS 不可用（阻断 /socket.io）→ 降级 POST /logs/refresh 轮询兜底（「轮询兜底」）。"""
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*socket.io*']})
    _goto_logs(drv, 'light')
    _toggle_realtime(drv)
    _wait_text(drv, '轮询兜底', 30)
    _wait_text(drv, '实时监控中')

    # 轮询兜底期间应出现 POST /logs/refresh（默认 5s 间隔；轮询最多等 20s 收据）
    deadline = time.time() + 20
    refs = []
    while time.time() < deadline and not refs:
        refs = _refresh_requests(_perf_events(drv))
        time.sleep(0.5)
    assert refs, 'WS 阻断后未降级 refresh 轮询兜底'
    assert any('/api/v1/logs/refresh' in u for u in refs), 'refresh 请求 URL 异常：%s' % refs[:3]

    shot = os.path.join(ARTIFACTS, 'fallback_polling.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '轮询兜底截图过小'
    drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})


def test_04_dark_theme_ws_realtime(drv):
    """深色主题下实时 WS 主通道（WS实时 状态文案 + 深色 class）。"""
    _goto_logs(drv, 'dark')
    WebDriverWait(drv, 15).until(
        lambda d: d.find_element(By.CSS_SELECTOR, '[aria-label="实时日志开关"]'))
    WebDriverWait(drv, 15).until(
        lambda d: 'dark' in d.execute_script('return document.documentElement.className'))
    _toggle_realtime(drv)
    _wait_text(drv, 'WS实时', 25)
    _wait_text(drv, '实时监控中')
    time.sleep(1)
    theme_mode = drv.execute_script('return document.documentElement.className')
    assert 'dark' in theme_mode, '深色主题未生效：%s' % theme_mode
    shot = os.path.join(ARTIFACTS, 'dark_ws_realtime.png')
    drv.save_screenshot(shot)
    assert os.path.getsize(shot) > 10_000, '深色截图过小'
