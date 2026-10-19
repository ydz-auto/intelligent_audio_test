# -*- coding: utf-8 -*-
"""INT-946 IAM/OAuth 分区接口失败 → 错误态+重试 验收（真实 Chrome headless）。

覆盖验收标准（对齐 option 分区 SettingsPage ErrorState 口径）：
1. `/system-settings/iam/users` 的 `/api/v1/auth/users` 请求失败 → ErrorState
   「加载失败」+ 分区说明 +「重试」按钮（非空态「暂无用户」）。
2. `/system-settings/iam/roles` 的 `/api/v1/auth/roles` 失败 → ErrorState。
3. `/system-settings/auth/oauth-providers` 的 `/api/v1/auth/oauth-providers`
   失败 → ErrorState；清拦截后点「重试」→ 真实后端空数据 → 空态
   「尚未配置自定义 OAuth 提供方」（成功空数据 ≠ 错误态）。
4. 「重试」refetch 生效：清拦截后点「重试」恢复真实数据渲染。
5. Network 证据：三个端点均为真实请求（performance log 留证，无 mock）。
6. 浅色 + 深色截图。

失败模拟：window.fetch 打点 + 合成网络失败（Chrome 155 已移除
Network.setRequestInterception；memory: chrome-155-no-network-interception）。
用 Page.addScriptToEvaluateOnNewDocument 在文档启动即装补丁，拦截模式存
localStorage（int946_fail_patterns），导航前设置、重试前清空——非破坏性，
不动真实请求形态。

前置：dev server :5316（本 worktree）→ 常驻后端 :5000（AUTH_MODE=off
dev_user permissions=['*']）。
"""
import json
import os
import time
import winreg

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5316')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int946_iam_oauth')
THEME_KEY = 'iatp:theme:v1:mode'
PATTERN_KEY = 'int946_fail_patterns'

END_USERS = '/api/v1/auth/users'
END_ROLES = '/api/v1/auth/roles'
END_OAUTH = '/api/v1/auth/oauth-providers'

# 在每一个新文档启动阶段注入 fetch 补丁：命中 localStorage 里的拦截模式 → 合成网络失败。
FETCH_PATCH = r"""
(() => {
  if (window.__int946Patched) return;
  const origFetch = window.fetch;
  window.fetch = function (url, opts) {
    let u = '';
    if (typeof url === 'string') u = url;
    else if (url && url.url) u = url.url;
    try {
      const patterns = JSON.parse(localStorage.getItem('int946_fail_patterns') || '[]');
      if (patterns.some((p) => u.indexOf(p) !== -1)) {
        return Promise.reject(new TypeError('Failed to fetch (INT-946 synthetic)'));
      }
    } catch (e) { /* ignore */ }
    return origFetch.apply(this, arguments);
  };
  window.__int946Patched = true;
})()
"""


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs',
                          {'browser': 'ALL', 'performance': 'ALL'})
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()),
                                  exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                        {'source': FETCH_PATCH})
    # 先落到应用 origin：about:blank 上 localStorage 被禁用（data: URL 规则），
    # 首次导航建立 origin 后 localStorage 操作才可用。
    drv.get(BASE + '/')
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)
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
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.0)


def _set_fail(drv, patterns):
    drv.execute_script(
        'localStorage.setItem(%r, %r)' % (PATTERN_KEY, json.dumps(patterns)))


def _clear_fail(drv):
    drv.execute_script('localStorage.removeItem(%r)' % PATTERN_KEY)


def _set_theme(drv, mode):
    drv.execute_script(
        'try { localStorage.setItem(%r, %r) } catch (e) {}' % (THEME_KEY, mode))


def _click_button(drv, text, timeout=12):
    WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '%s')]" % text))
    drv.find_element(By.XPATH, "//button[contains(., '%s')]" % text).click()


def _shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    p = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(p)
    assert os.path.getsize(p) > 10_000, '截图过小: %s' % name
    return p


def _drain_perf(drv):
    """performance log 双层嵌套解析（memory: selenium-performance-log）。"""
    urls = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])['message']
            if msg.get('method') == 'Network.requestWillBeSent':
                url = msg['params']['request']['url']
                if '/api/' in url or '/auth/' in url:
                    urls.append(url)
    except Exception:
        pass
    return urls


def _assert_error_state(drv, title, desc):
    _wait_text(drv, title, timeout=25)
    _wait_text(drv, desc, timeout=5)
    btn = WebDriverWait(drv, 8).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '重试')]"))
    assert btn.is_displayed(), '「重试」按钮不可见'


def test_01_users_error_state_light(drv):
    """用户管理页：/auth/users 失败 → ErrorState（浅色），非空态。"""
    _set_theme(drv, 'light')
    _set_fail(drv, [END_USERS])
    _goto(drv, '/system-settings/iam/users')
    _wait_text(drv, '用户管理')
    _assert_error_state(drv, '加载失败', '用户列表加载失败，请重试')
    assert '暂无用户' not in _body_text(drv), '失败时不应落入空态「暂无用户」'
    _shot(drv, 'users-error-light.png')


def test_02_users_retry_recovers(drv):
    """用户管理页：清拦截点「重试」→ 真实用户数据渲染。"""
    _clear_fail(drv)
    _click_button(drv, '重试')
    _wait_text(drv, 'admin', timeout=20)
    _shot(drv, 'users-recovered-light.png')


def test_03_roles_error_state_light(drv):
    """角色权限页：/auth/roles 失败 → ErrorState（浅色），非空态。"""
    _set_fail(drv, [END_ROLES])
    _goto(drv, '/system-settings/iam/roles')
    _wait_text(drv, '角色权限管理')
    _assert_error_state(drv, '加载失败', '角色列表加载失败，请重试')
    assert '暂无自定义角色' not in _body_text(drv), '失败时不应落入空态'
    _shot(drv, 'roles-error-light.png')


def test_04_roles_retry_recovers(drv):
    """角色权限页：清拦截点「重试」→ 真实角色数据渲染（admin/tester）。"""
    _clear_fail(drv)
    _click_button(drv, '重试')
    _wait_text(drv, '超级管理员', timeout=20)
    _shot(drv, 'roles-recovered-light.png')


def test_05_oauth_error_state_light(drv):
    """OAuth 提供方页：/auth/oauth-providers 失败 → ErrorState（浅色）。"""
    _set_fail(drv, [END_OAUTH])
    _goto(drv, '/system-settings/auth/oauth-providers')
    _wait_text(drv, 'OAuth 提供方')
    _assert_error_state(drv, '加载失败', 'OAuth 提供方列表加载失败，请重试')
    assert '尚未配置自定义 OAuth 提供方' not in _body_text(drv), \
        '失败时不应落入空态「尚未配置…」'
    _shot(drv, 'oauth-error-light.png')


def test_06_oauth_retry_shows_empty_not_error(drv):
    """OAuth 页：清拦截点「重试」→ 成功且空数据 → 空态（非错误态）。"""
    _clear_fail(drv)
    _click_button(drv, '重试')
    _wait_text(drv, '尚未配置自定义 OAuth 提供方', timeout=20)
    assert '加载失败' not in _body_text(drv), '空数据不应显示错误态'
    _shot(drv, 'oauth-empty-light.png')


def test_07_dark_theme_error_states(drv):
    """深色：三页错误态深色截图 + 主题实际生效。"""
    _set_theme(drv, 'dark')
    _set_fail(drv, [END_USERS])
    _goto(drv, '/system-settings/iam/users')
    _wait_text(drv, '用户管理')
    _assert_error_state(drv, '加载失败', '用户列表加载失败，请重试')
    WebDriverWait(drv, 15).until(
        lambda d: 'dark' in d.execute_script(
            'return document.documentElement.className'))
    time.sleep(0.5)
    _shot(drv, 'users-error-dark.png')

    _set_fail(drv, [END_ROLES])
    _goto(drv, '/system-settings/iam/roles')
    _wait_text(drv, '角色权限管理')
    _assert_error_state(drv, '加载失败', '角色列表加载失败，请重试')
    _shot(drv, 'roles-error-dark.png')

    _set_fail(drv, [END_OAUTH])
    _goto(drv, '/system-settings/auth/oauth-providers')
    _wait_text(drv, 'OAuth 提供方')
    _assert_error_state(drv, '加载失败', 'OAuth 提供方列表加载失败，请重试')
    _shot(drv, 'oauth-error-dark.png')


def test_08_network_evidence(drv):
    """Network 证据：三个端点真实请求（performance log），无 mock 残留。"""
    _set_theme(drv, 'light')
    _clear_fail(drv)
    seen = set()
    for path, end in [
        ('/system-settings/iam/users', END_USERS),
        ('/system-settings/iam/roles', END_ROLES),
        ('/system-settings/auth/oauth-providers', END_OAUTH),
    ]:
        _drain_perf(drv)  # 清空旧缓冲，只看本轮
        _goto(drv, path)
        time.sleep(2.5)
        urls = _drain_perf(drv)
        hits = [u for u in urls if end in u]
        assert hits, '未请求真实端点 %s: %s' % (end, urls[:5])
        seen.update(hits)
    os.makedirs(ARTIFACTS, exist_ok=True)
    with open(os.path.join(ARTIFACTS, 'network_evidence.json'), 'w',
              encoding='utf-8') as f:
        json.dump({'endpoints': sorted(seen)}, f, ensure_ascii=False, indent=2)
    assert any(END_USERS in u for u in seen)
    assert any(END_ROLES in u for u in seen)
    assert any(END_OAUTH in u for u in seen)
