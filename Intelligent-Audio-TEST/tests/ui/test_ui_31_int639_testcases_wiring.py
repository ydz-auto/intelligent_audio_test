# -*- coding: utf-8 -*-
"""INT-639 用例页 infra mock→api 接线浏览器验收（真实 Chrome headless，按 test_ui_28 先例）。

覆盖验收标准：
- testcases-api / groups-api / tags-api 经基座 client.ts 切真实后端端点（真实请求核对）。
- 受影响页浏览器实测：用例管理 by-group 列表（分组头+用例卡）/ 搜索 / 编辑抽屉 /
  批量勾选浮条 / 标签 facet / by-tag 视图 / 标签管理页。
- 「试听播放双模式」验收项实测：浏览器播放 / 实验室播放两种模式（按 issue 补充要求截图）。
- 深浅两套主题下改动页截图。

前置：5273 dev server 已在本 worktree 起（rsbuild proxy /api → localhost:5000）；
:5000 后端为常驻 5000 段 run_all.py 栈（只读探测，不 stop / 不重启）。
本卡为纯只读走查：不写入任何共享库 fixture。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int639_wiring')

# 真实数据断言基准（5000 段栈共享库现网数据，2026-10-18 探测）
REAL_GROUP = '环境理解'
REAL_CASE = '测试用例_HJ050'
REAL_TAG = 'INT308'
REAL_TAG_R3 = 'INT308R3'

_DRIVER = None
_CONSOLE_JS_ERRORS = []


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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _clear_storage(drv):
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')


def _fill_and_submit_login(drv, username, password):
    _goto(drv, '/login')
    _wait_text(drv, '登录')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys(password)
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()


def _ensure_logged_in(drv, tries=3):
    """保证已登录：直航 /dashboard，若被重定向到 /login 则走 admin/admin123 真实登录链。

    5000 段常驻栈偶发重启（2026-10-18 观测）：加密初始化失败时短暂等待后重试。
    """
    for attempt in range(1, tries + 1):
        _goto(drv, '/dashboard')
        if '/login' not in drv.current_url:
            break
        _fill_and_submit_login(drv, 'admin', 'admin123')
        ok = False
        for _ in range(4):
            time.sleep(2)
            if '/dashboard' in drv.current_url and '欢迎回来！' in _body_text(drv):
                ok = True
                break
            if '/login' in drv.current_url and '加密初始化失败' in _body_text(drv):
                break  # 后端未就绪，重试
        if ok:
            break
        if attempt < tries:
            time.sleep(5)
    WebDriverWait(drv, 25).until(lambda d: '/dashboard' in d.current_url)
    _wait_text(drv, '工作台', timeout=25)


def _set_theme(drv, name):
    """切主题（深色/浅色），与 test_ui_29 同款：主题设置按钮 → 偏好 radio。"""
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    _js_click(drv, f"//*[@role='radio'][contains(., '{name}')]")
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC
    time.sleep(0.5)


def _js_click(drv, xpath):
    el = drv.find_element(By.XPATH, xpath)
    drv.execute_script('arguments[0].click()', el)


def _shot(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(os.path.dirname(d), exist_ok=True)
    drv.save_screenshot(d)
    return d


def _inject_fetch_logger(drv):
    drv.execute_script("""
    window.__INT639_REQS__ = [];
    const _origFetch = window.fetch;
    window.fetch = function(...args) {
      try {
        const u = (typeof args[0] === 'string') ? args[0] : (args[0] && args[0].url);
        if (u && String(u).includes('/api/v1/')) window.__INT639_REQS__.push(String(u));
      } catch (e) {}
      return _origFetch.apply(this, args);
    };
    const _origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      try { if (String(url).includes('/api/v1/')) window.__INT639_REQS__.push(String(url)); }
      catch (e) {}
      return _origOpen.call(this, method, url, ...rest);
    };
    """)


def _read_requests(drv):
    try:
        return drv.execute_script('return window.__INT639_REQS__ || []') or []
    except Exception:
        return []


def _drain_console(drv):
    try:
        for entry in drv.get_log('browser'):
            lvl = entry.get('level', '')
            msg = entry.get('message', '')
            if lvl == 'SEVERE' and 'Failed to load resource' not in msg:
                _CONSOLE_JS_ERRORS.append(msg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_01_login_and_bygroup_real_data_network(drv):
    """登录 → /testcases/by-group 真实数据渲染 + 真实请求核对（/testcases /groups 等）。

    关键：注入 fetch 日志器后用侧栏 SPA 导航进入用例管理页，捕获真实 API 请求，
    证明列表/分组数据不再来自 mock。
    """
    _clear_storage(drv)
    _ensure_logged_in(drv)
    # 工作台就绪 → 注入请求日志器 → 侧栏 SPA 进入用例管理（不整页刷新，日志器存活）
    _inject_fetch_logger(drv)
    _js_click(drv, "//a[contains(@href, '/testcases')]")
    WebDriverWait(drv, 20).until(lambda d: '/testcases/by-group' in d.current_url)
    _wait_text(drv, REAL_GROUP, timeout=20)
    _wait_text(drv, REAL_CASE, timeout=20)

    reqs = _read_requests(drv)
    api_urls = sorted(set(reqs))
    assert any('/api/v1/testcases' in u for u in api_urls), \
        f'未捕获真实 /testcases 请求：{api_urls}'
    assert any('/api/v1/groups' in u for u in api_urls), \
        f'未捕获真实 /groups 请求：{api_urls}'
    # mock 残留自检：不应出现 mock 桩关键字请求
    assert not any('mock' in u.lower() for u in api_urls), f'出现 mock 请求：{api_urls}'

    _shot(drv, '01-bygroup-light.png')
    _drain_console(drv)


def test_02_search_keyword_hj050(drv):
    """搜索 HJ050 → 列表被真实 keyword 过滤（GET /testcases?keyword=HJ050）。"""
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_GROUP, timeout=20)
    _inject_fetch_logger(drv)
    inp = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索用例']")
    inp.clear()
    inp.send_keys('HJ050')
    time.sleep(2.0)  # 防抖
    _wait_text(drv, '测试用例_HJ050', timeout=15)
    body = _body_text(drv)
    assert '测试用例_HJ049' not in body, 'HJ049 不应出现在 HJ050 搜索结果中'
    reqs = _read_requests(drv)
    kw = [u for u in reqs if 'keyword=HJ050' in u or 'keyword' in u]
    assert kw, f'搜索未携带 keyword 真实请求：{reqs}'
    _shot(drv, '02-search-hj050.png')
    _drain_console(drv)


def test_03_edit_drawer_real_prefill(drv):
    """点开用例编辑抽屉 → 真实用例名/分组预填（非 mock）。"""
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_CASE, timeout=20)
    # 行内「编辑用例」按钮（case-card actionBtn aria-label）
    btn = drv.find_element(By.XPATH,
        f"//button[contains(@aria-label, '编辑用例')][ancestor::*[contains(., '{REAL_CASE}')]]")
    btn.click()
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '编辑用例')]"))
    dtext = _body_text(drv)
    assert REAL_CASE in dtext, '编辑抽屉未预填真实用例名'
    _shot(drv, '03-edit-drawer.png')
    # 关闭抽屉（ESC）
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.8)
    _drain_console(drv)


def test_04_batch_select_floating_bar(drv):
    """批量勾选 → 底部浮条「n 个用例已选择」出现。"""
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_CASE, timeout=20)
    boxes = drv.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
    clicked = 0
    for box in boxes[:6]:
        try:
            if not box.is_enabled():
                continue
            box.click()
            clicked += 1
            if clicked >= 2:
                break
        except Exception:
            continue
    assert clicked >= 2, '未能勾选至少 2 个用例'
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]"))
    _shot(drv, '04-batch-select.png')
    _drain_console(drv)


def test_05_tag_facet_real_tags(drv):
    """标签 facet 打开 → 真实标签（INT308/INT308R3 等）渲染；未分类分组可见。"""
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_CASE, timeout=20)
    # 打开标签 facet（工具栏「标签」Popover）
    drv.find_element(By.XPATH, "//button[contains(., '标签')]").click()
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, "//button[contains(., '未分类')]"))
    _wait_text(drv, REAL_TAG, timeout=8)
    _shot(drv, '05-tag-facet.png')
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.5)
    _drain_console(drv)


def test_06_bytag_view(drv):
    """/testcases/by-tag 标签视图 → 真实数据驱动（现库无打标签用例 → 正确空态）。"""
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-tag')
    _wait_text(drv, '没有找到标签分组的测试用例', timeout=20)
    _shot(drv, '06-bytag-view.png')
    _drain_console(drv)


def test_07_tag_management_page(drv):
    """标签管理页 → 真实标签（INT308/INT308R3）登记表渲染。"""
    _ensure_logged_in(drv)
    _goto(drv, '/TagManagement')
    _wait_text(drv, '标签管理', timeout=20)
    _wait_text(drv, REAL_TAG_R3, timeout=20)
    _shot(drv, '07-tags-light.png')
    _drain_console(drv)


def test_08_audio_preview_dual_mode_evidence(drv):
    """试听播放双模式验收项实测：打开用例「预览音频」→ 配置弹窗（两种模式单选存在）。

    预期按 issue 补充要求应接真实端点（GET /audios/{id}/stream / POST /testcases/{id}/preview）；
    实测记录当前行为（demo 演示态 → 结论为打回项证据）。
    """
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_CASE, timeout=20)
    # 打开 HJ050 用例的预览音频配置弹窗
    btn = drv.find_element(By.XPATH,
        f"//button[contains(@aria-label, '预览音频')][ancestor::*[contains(., '{REAL_CASE}')]]")
    btn.click()
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '音频试听配置')]"))
    dtext = _body_text(drv)
    assert '浏览器播放' in dtext and '实验室播放' in dtext, \
        '试听配置弹窗应同时具备浏览器播放/实验室播放两种模式'
    _shot(drv, '08a-audio-config-dialog.png')

    # 注入请求日志器 → 点「开始试听」→ 记录是否发出真实 preview/stream 请求
    _inject_fetch_logger(drv)
    _js_click(drv, "//*[@role='dialog']//button[contains(., '开始试听')]")
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='dialog'][contains(., '测试用例预览')]"))
    time.sleep(1.0)
    reqs = _read_requests(drv)
    preview_reqs = [u for u in reqs if '/preview' in u or '/stream' in u or 'audios/' in u]
    dtext = _body_text(drv)
    _shot(drv, '08b-audio-player.png')
    # 记录证据（供结论判定，不在此断言成败——以页面实际呈现为准）
    print(f'[INT639-EVIDENCE] preview/stream 真实请求: {preview_reqs}')
    print(f'[INT639-EVIDENCE] 弹窗文案含「演示」: {"演示" in dtext}')
    _drain_console(drv)


def test_09_dark_theme_pages(drv):
    """深色主题下改动页可读性走查 + 截图（by-group / 标签管理 / by-tag）。"""
    _ensure_logged_in(drv)
    _set_theme(drv, '深色')
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_CASE, timeout=20)
    _shot(drv, '09a-bygroup-dark.png')
    _goto(drv, '/TagManagement')
    _wait_text(drv, REAL_TAG_R3, timeout=20)
    _shot(drv, '09b-tags-dark.png')
    _goto(drv, '/testcases/by-tag')
    _wait_text(drv, '没有找到标签分组的测试用例', timeout=20)
    _shot(drv, '09c-bytag-dark.png')
    # 还原浅色
    _set_theme(drv, '浅色')
    _drain_console(drv)


def test_10_no_js_runtime_errors(drv):
    _ensure_logged_in(drv)
    _goto(drv, '/testcases/by-group')
    _wait_text(drv, REAL_CASE, timeout=20)
    time.sleep(1.0)
    _drain_console(drv)
    assert not _CONSOLE_JS_ERRORS, \
        '浏览器控制台存在 JS 运行时严重错误：\n' + '\n'.join(_CONSOLE_JS_ERRORS[-10:])
