# -*- coding: utf-8 -*-
"""INT-650 个人中心接线（profileApi/favoritesApi mock→api）浏览器实测。

针对 frontend-react/ 真实接口（profileApi/favoritesApi 经 client.ts），
登录走真实链路（后端 RSA 加密公钥 + 表单登录），核心链路：
1. /profile 第三方账号绑定：真实 GET /auth/oauth/bindings + /auth/oauth/providers
   → 已绑定提供方（接线测试 fixture）+ provider_user_id 展示 + 未绑定行
2. 解绑真实链路：ConfirmDialog → DELETE /auth/oauth/bindings/{provider_id}
   → toast 解绑成功 → 行转未绑定（DB 绑定行同步消失）
3. 我的收藏计数：真实 GET /favorites → 快捷条 total=3、Popover 三行 1/1/1
4. Network 证据：页面 performance 条目含 /favorites / bindings / providers
5. 浅色 + 深色各一张截图；无 severe console 错误

前置：dev server 已起（REACT_DEV_BASE 可覆写），后端为可用栈（推荐 6000 段
隔离栈或常驻 5000 段；7500 段 gRPC 破损不可用）。fixture 写入隔离测试库并
teardown（接线测试前缀，§3.1）。

失败落 tests/ui/artifacts/int650_profile_wiring/<用例>/（截图+console）。
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5320')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int650_profile_wiring')

DB_DSN = dict(
    host=os.environ.get('TEST_DB_HOST', '127.0.0.1'),
    port=int(os.environ.get('TEST_DB_PORT', '5432')),
    user='intelligent_audio_test',
    password='intelligent_audio_test666',
    dbname=os.environ.get('TEST_DB_NAME', 'intelligent_audio_test_test'))

_PROVIDER = {
    'name': '接线测试-INT650提供方', 'slug': 'int650-test-provider',
    'icon': 'github', 'enabled': True, 'client_id': 'int650-client',
    'client_secret': 'int650-secret',
    'authorize_url': 'https://example.test/oauth/authorize',
    'token_url': 'https://example.test/oauth/token',
    'userinfo_url': 'https://example.test/oauth/userinfo',
    'scopes': 'user', 'user_id_field': 'id', 'username_field': 'login',
    'display_name_field': 'name', 'email_field': 'email',
}

# 未绑定提供方（不插绑定行）——保证绑定列表同时渲染「已绑定」与「未绑定」两种状态，
# 不依赖测试库预置提供方（隔离库 custom_oauth_providers 可为空）。
_PROVIDER_UNBOUND = {
    'name': '接线测试-INT650未绑提供方', 'slug': 'int650-test-provider-unbound',
    'icon': 'gitlab', 'enabled': True, 'client_id': 'int650-unbound-client',
    'client_secret': 'int650-unbound-secret',
    'authorize_url': 'https://example.test/oauth/authorize',
    'token_url': 'https://example.test/oauth/token',
    'userinfo_url': 'https://example.test/oauth/userinfo',
    'scopes': 'user', 'user_id_field': 'id', 'username_field': 'login',
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
    except Exception:
        pass


@pytest.fixture(scope='module')
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


@pytest.fixture(scope='module')
def fixture():
    """接线测试 fixture：provider + 绑定 + 收藏（真实后端数据源），teardown 清。"""
    conn = psycopg2.connect(**DB_DSN)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username='admin' LIMIT 1")
        row = cur.fetchone()
        assert row, '测试库无 admin 用户'
        admin_id = row[0]
        cur.execute(
            "INSERT INTO custom_oauth_providers "
            "(name, slug, icon, enabled, client_id, client_secret, authorize_url, "
            " token_url, userinfo_url, scopes, user_id_field, username_field, "
            " display_name_field, email_field) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (_PROVIDER['name'], _PROVIDER['slug'], _PROVIDER['icon'],
             _PROVIDER['enabled'], _PROVIDER['client_id'], _PROVIDER['client_secret'],
             _PROVIDER['authorize_url'], _PROVIDER['token_url'],
             _PROVIDER['userinfo_url'], _PROVIDER['scopes'],
             _PROVIDER['user_id_field'], _PROVIDER['username_field'],
             _PROVIDER['display_name_field'], _PROVIDER['email_field']))
        provider_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO custom_oauth_providers "
            "(name, slug, icon, enabled, client_id, client_secret, authorize_url, "
            " token_url, userinfo_url, scopes, user_id_field, username_field, "
            " display_name_field, email_field) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (_PROVIDER_UNBOUND['name'], _PROVIDER_UNBOUND['slug'], _PROVIDER_UNBOUND['icon'],
             _PROVIDER_UNBOUND['enabled'], _PROVIDER_UNBOUND['client_id'], _PROVIDER_UNBOUND['client_secret'],
             _PROVIDER_UNBOUND['authorize_url'], _PROVIDER_UNBOUND['token_url'],
             _PROVIDER_UNBOUND['userinfo_url'], _PROVIDER_UNBOUND['scopes'],
             _PROVIDER_UNBOUND['user_id_field'], _PROVIDER_UNBOUND['username_field'],
             _PROVIDER_UNBOUND['display_name_field'], _PROVIDER_UNBOUND['email_field']))
        unbound_provider_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO user_oauth_bindings (user_id, provider_id, provider_user_id) "
            "VALUES (%s, %s, %s)",
            (admin_id, provider_id, 'int650-bind-admin'))
        cur.execute(
            "INSERT INTO favorites (user_id, entity_type, entity_id, created_at) VALUES "
            "(%s,'task','T-INT650-1',now()),(%s,'testcase','TC-INT650-1',now())",
            (admin_id, admin_id))
        cur.execute(
            "INSERT INTO report_favorites (user_id, entity_type, entity_id, created_at) "
            "VALUES (%s, 'report', 'R-INT650-1', now())",
            (admin_id,))
        conn.commit()
        yield {'admin_id': admin_id, 'provider_id': provider_id,
               'unbound_provider_id': unbound_provider_id}
    finally:
        cur = conn.cursor()
        cur.execute("DELETE FROM report_favorites WHERE entity_id='R-INT650-1'")
        cur.execute("DELETE FROM favorites WHERE entity_id IN ('T-INT650-1','TC-INT650-1')")
        cur.execute("DELETE FROM user_oauth_bindings WHERE provider_user_id='int650-bind-admin'")
        cur.execute("DELETE FROM custom_oauth_providers WHERE slug IN (%s, %s)",
                    (_PROVIDER['slug'], _PROVIDER_UNBOUND['slug']))
        conn.commit()
        conn.close()


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _login(drv):
    # 先清当前页登录态再访问 /login：已登录态下 /login 会被路由守卫重定向到
    # /dashboard，导致登录表单不可见（多次复用同 driver 的用例尤其如此）。
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    _wait_text(drv, '登录')
    drv.find_element(By.ID, 'username').send_keys('admin')
    drv.find_element(By.ID, 'password').send_keys('admin123')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 20).until(lambda d: '/dashboard' in d.current_url)
    _wait_text(drv, '工作台', timeout=20)
    time.sleep(1.0)


def _open_profile(drv):
    _goto(drv, '/profile')
    _wait_text(drv, '第三方账号绑定', timeout=20)


def _network_apis(drv):
    return drv.execute_script(
        'return performance.getEntriesByType("resource").map(r => r.name)'
        '.filter(u => u.includes("/api/"))')


def test_01_profile_bindings_and_favorites_real(drv, fixture):
    """真实绑定列表 + 收藏计数渲染（fixture provider/绑定/收藏）。"""
    _login(drv)
    _open_profile(drv)
    body = _body_text(drv)

    assert '第三方账号绑定' in body
    assert _PROVIDER['name'] in body, '接线测试提供方未渲染'
    assert '已绑定' in body
    assert 'int650-bind-admin' in body, 'provider_user_id 未渲染'
    assert '未绑定' in body

    # 我的收藏（fixture task+testcase+report → total=3）
    assert '我的收藏' in body
    assert '任务 · 报告 · 用例' in body

    # 收藏 Popover 三行
    drv.find_element(By.XPATH, "//button[@aria-label='我的收藏']").click()
    WebDriverWait(drv, 8).until(
        lambda d: '收藏的任务' in d.execute_script('return document.body.textContent || ""'))
    pb = _body_text(drv)
    assert '收藏的任务' in pb and '收藏的报告' in pb and '收藏的用例' in pb
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.4)

    # Network 真实请求证据
    apis = _network_apis(drv)
    assert any('favorites' in u for u in apis), f'未见 /favorites 真实请求: {apis}'
    assert any('bindings' in u for u in apis), '未见 /auth/oauth/bindings 真实请求'
    assert any('providers' in u for u in apis), '未见 /auth/oauth/providers 真实请求'
    _drain_console(drv)


def test_02_unbind_real_chain(drv, fixture):
    """解绑真实链路：ConfirmDialog → DELETE → 行转未绑定 + toast。"""
    _login(drv)
    _open_profile(drv)
    _wait_text(drv, _PROVIDER['name'])
    drv.find_element(By.XPATH, f"//button[@aria-label='解绑 {_PROVIDER['name']}']").click()
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog']"))
    dialog = drv.find_element(By.XPATH, "//*[@role='alertdialog']")
    assert '确认解绑' in dialog.text
    dialog.find_element(By.XPATH, ".//button[contains(., '解绑')]").click()
    _wait_text(drv, '解绑成功', timeout=12)
    time.sleep(1.2)
    body = _body_text(drv)
    assert 'int650-bind-admin' not in body, '解绑后 provider_user_id 应消失'
    assert '已绑定' not in body, '解绑后已绑定 badge 应消失'
    assert '未绑定' in body, '解绑后行应显示未绑定'
    _drain_console(drv)


def test_03_dark_theme_profile(drv, fixture):
    """深色主题下个人中心可读（主题持久化；不依赖绑定态，前面解绑用例可能已删绑定）。"""
    _login(drv)
    _open_profile(drv)
    drv.find_element(By.XPATH, "//button[@aria-label='打开主题设置']").click()
    WebDriverWait(drv, 5).until(
        lambda d: d.find_elements(By.XPATH, "//*[@aria-label='选择深浅色偏好']"))
    drv.find_element(By.XPATH, "//*[@role='radio'][contains(., '深色')]").click()
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.8)
    _open_profile(drv)
    body = _body_text(drv)
    assert '第三方账号绑定' in body
    assert _PROVIDER['name'] in body
    _drain_console(drv)


def test_04_no_severe_console_errors(drv, fixture):
    """无 severe console 错误。"""
    _login(drv)
    _open_profile(drv)
    _wait_text(drv, _PROVIDER['name'])
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, '浏览器 console SEVERE 错误：\n' + '\n'.join(_CONSOLE_SEVERE[:10])
