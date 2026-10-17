# -*- coding: utf-8 -*-
"""INT-606 认证链路接线浏览器验收（真实 Chrome headless，按 test_ui_27 先例）。

覆盖验收标准：
1. 登录→工作台 真实链路走通（真实后端 api_gateway :5000 + 5273 前端；rsbuild proxy
   /api → localhost:5000）；错误码 105/106/网络失败逐条触发核对呈现。
2. AUTH_MODE=off 开放模式 Alert 正常。
3. OAuth 提供方列表真实接口渲染（真实 GET /auth/oauth/providers）。
前置：5273 dev server 已在跑（服务共享 UX checkout 的 INT-606 代码）；:5000 后端
已由 5000 段 run_all.py 栈提供（复用/只读探测，不停止）。
"""
import json
import os
import time

import psycopg2
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'tests', 'ui', 'artifacts', 'int606_auth')

# 5000 段 run_all.py 栈（--test-db 隔离库）实际 DATABASE_URL 指向
# intelligent_audio_test_test；DSN 可由环境变量覆盖（本 run 起自己的栈时后端库
# 在 5432），默认值兼容 15433（旧共享栈）。provider fixture 写测试库并 teardown。
DB_DSN = dict(
    host=os.environ.get('TEST_DB_HOST', '127.0.0.1'),
    port=int(os.environ.get('TEST_DB_PORT', '15433')),
    user='intelligent_audio_test',
    password='intelligent_audio_test666',
    dbname=os.environ.get('TEST_DB_NAME', 'intelligent_audio_test_test'))

# OAuth 提供方渲染临时 fixture（验收只读探测共享 5000 段栈；写隔离测试库，用后删除）
_OAUTH_FIXTURE = {
    'name': 'Int606TestProvider', 'slug': 'int606-test-provider', 'icon': 'github',
    'enabled': True, 'client_id': 'int606-test-client', 'client_secret': 'int606-test-secret',
    'authorize_url': 'https://example.test/oauth/authorize',
    'token_url': 'https://example.test/oauth/token',
    'userinfo_url': 'https://example.test/oauth/userinfo', 'scopes': 'user',
    'user_id_field': 'id', 'username_field': 'login',
    'display_name_field': 'name', 'email_field': 'email',
}


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


def _insert_oauth_fixture():
    conn = psycopg2.connect(**DB_DSN)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO custom_oauth_providers "
            "(name, slug, icon, enabled, client_id, client_secret, authorize_url, "
            " token_url, userinfo_url, scopes, user_id_field, username_field, "
            " display_name_field, email_field) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING id",
            (_OAUTH_FIXTURE['name'], _OAUTH_FIXTURE['slug'], _OAUTH_FIXTURE['icon'],
             _OAUTH_FIXTURE['enabled'], _OAUTH_FIXTURE['client_id'],
             _OAUTH_FIXTURE['client_secret'], _OAUTH_FIXTURE['authorize_url'],
             _OAUTH_FIXTURE['token_url'], _OAUTH_FIXTURE['userinfo_url'],
             _OAUTH_FIXTURE['scopes'], _OAUTH_FIXTURE['user_id_field'],
             _OAUTH_FIXTURE['username_field'], _OAUTH_FIXTURE['display_name_field'],
             _OAUTH_FIXTURE['email_field']))
        row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
    finally:
        conn.close()


def _delete_oauth_fixture(row_id):
    conn = psycopg2.connect(**DB_DSN)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM custom_oauth_providers WHERE id=%s", (row_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_login_real_chain_to_workbench(drv):
    """登录→工作台真实链路：admin/admin123（DEV_DEFAULT 默认凭证）→ toast 欢迎回来 → /dashboard。"""
    _clear_storage(drv)
    _fill_and_submit_login(drv, 'admin', 'admin123')
    _wait_text(drv, '欢迎回来！')
    WebDriverWait(drv, 15).until(lambda d: '/dashboard' in d.current_url)
    _wait_text(drv, '工作台', timeout=15)
    assert '/dashboard' in drv.current_url, f'登录后未到工作台：{drv.current_url}'


def test_error_106_wrong_password_toast(drv):
    """错误码 106：错误密码 → sonner toast「登录失败：用户名或密码错误」。"""
    _clear_storage(drv)
    _fill_and_submit_login(drv, 'admin', 'wrong-password-999')
    _wait_text(drv, '登录失败：用户名或密码错误')


def test_error_105_encryption_invalid_alert(drv):
    """错误码 105：提交失效密文 → 卡内 Alert「登录加密校验失败，请刷新页面重试」（不走 toast）。

    浏览器内 override window.fetch：将 /auth/login 请求体的 password_encrypted 改写成
    失效密文后放行 → 真实后端解密失败返回 105 → 表单 onSubmit 映射为卡内 Alert。
    """
    _clear_storage(drv)
    _goto(drv, '/login')
    _wait_text(drv, '登录')
    drv.execute_script(
        "const orig = window.fetch;"
        "window.fetch = async (url, opts) => {"
        "  if (typeof url === 'string' && url.includes('/auth/login')"
        "      && opts && String(opts.method).toUpperCase() === 'POST') {"
        "    const body = new URLSearchParams(opts.body);"
        "    body.set('password_encrypted', 'stale-invalid-cipher');"
        "    body.set('encryption_key_id', 'stale-key-id');"
        "    opts.body = body.toString();"
        "  }"
        "  return orig(url, opts);"
        "};")
    drv.find_element(By.ID, 'username').send_keys('admin')
    drv.find_element(By.ID, 'password').send_keys('admin123')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    _wait_text(drv, '登录加密校验失败，请刷新页面重试')


def test_network_failure_toast(drv):
    """网络失败：登录提交时 /auth/login POST 被浏览器 fetch 拒绝（网络层失败）→ toast「网络异常，请检查连接后重试」。

    CDP setBlockedURLs 会把 *auth/login* 一并挡住 encryption-key 预检（URL 同含 auth/login），
    触发的是加密初始化 Alert 而非网络 toast；故改用 fetch override 只对精确 POST /auth/login
    抛 TypeError，等价真实后端不可达的 fetch 失败路径（client.ts isNetworkError 分支）。
    """
    _clear_storage(drv)
    _goto(drv, '/login')
    _wait_text(drv, '登录')
    drv.execute_script(
        "const orig = window.fetch;"
        "window.fetch = async (url, opts) => {"
        "  const u = String(url);"
        "  const loginEnd = u.indexOf('/auth/login') + '/auth/login'.length === u.length;"
        "  if (loginEnd && opts && String(opts.method).toUpperCase() === 'POST') {"
        "    throw new TypeError('Failed to fetch');"
        "  }"
        "  return orig(url, opts);"
        "};")
    drv.find_element(By.ID, 'username').send_keys('admin')
    drv.find_element(By.ID, 'password').send_keys('admin123')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    _wait_text(drv, '网络异常，请检查连接后重试')


def test_auth_mode_off_open_alert(drv):
    """AUTH_MODE=off 兼容：登录页顶部开放模式 Alert 渲染正常（验收标准项）。"""
    _clear_storage(drv)
    _goto(drv, '/login')
    _wait_text(drv, '当前为开放模式：无需登录即可使用全部功能')
    btn = drv.find_element(By.XPATH, "//button[contains(., '进入工作台')]")
    assert btn.is_displayed(), '开放模式「进入工作台」按钮未渲染'


def test_auth_mode_off_enter_workbench_direct(drv):
    """打回项复测（INT-606 P2）：AUTH_MODE=off 清空 localStorage 后点「进入工作台」
    应直达 /dashboard（dev_user 放行），不再回跳 /login?redirect=%2Fdashboard。

    _authenticated 守卫先 await ensureAuthSession()：无 token 时 hydrateSession
    GET /auth/mode 判 off → GET /auth/me 回填后端注入 dev_user → user 就绪后放行。
    """
    _clear_storage(drv)
    _goto(drv, '/login')
    _wait_text(drv, '当前为开放模式：无需登录即可使用全部功能')
    drv.find_element(By.XPATH, "//button[contains(., '进入工作台')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/dashboard' in d.current_url)
    _wait_text(drv, '工作台', timeout=15)
    url = drv.current_url
    assert '/dashboard' in url, f'点「进入工作台」后未到达工作台：{url}'
    assert '/login' not in url, (
        f'回跳登录页（期望直达 /dashboard）：{url}')


def test_oauth_providers_real_render(drv):
    """OAuth 提供方列表真实接口渲染：插入启用提供方 → 登录页渲染「使用 {name} 登录」按钮。"""
    row_id = _insert_oauth_fixture()
    try:
        _clear_storage(drv)
        _goto(drv, '/login')
        _wait_text(drv, '登录')
        _wait_text(drv, f'使用 {_OAUTH_FIXTURE["name"]} 登录')
    finally:
        _delete_oauth_fixture(row_id)
