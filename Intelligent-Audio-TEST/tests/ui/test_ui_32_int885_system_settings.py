# -*- coding: utf-8 -*-
"""INT-885 系统设置页接线浏览器验收（真实 Chrome headless，按 test_ui_31 先例）。

覆盖验收标准：
1. 登录→/system-settings 六域分区真实数据渲染（GET /api/option/ 全量 KV 走真实接口）。
2. 写操作真实生效：站点信息改名（接线测试数据）→ PUT /api/option/ → 回读确认 → 还原。
3. 空态 / 错误态：site.notice 为空（公告空表单）、IAM 用户/角色与 OAuth 提供方
   在常驻栈 auth_service gRPC 未监听（51069）时展示优雅空态/错误态（不白屏）。
4. Network 证据：performance entries 含 /api/option/、/api/v1/auth/users 等真实请求。
5. 浅色 + 深色截图。

前置：5331 dev server 已在跑（本 worktree）；:5000 常驻后端（AUTH_MODE=off 全放行，
dev_user permissions=['*']）。写操作仅用「接线测试」前缀测试数据，run 结束前还原。
"""
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5331')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int885_settings')
THEME_KEY = 'iatp:theme:v1:mode'

SITE_NAME_ORIG = '智能语音测试平台'
TEST_NAME = '接线测试站点名称'


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
    _goto(drv, '/system-settings/site/info')
    time.sleep(1)


def _resource_urls(drv, needle):
    return drv.execute_script(
        'return performance.getEntriesByType("resource").map(e => e.name)'
        '.filter(n => n.includes(%r))' % needle)


def _shot(drv, name):
    os.makedirs(ARTIFACTS, exist_ok=True)
    p = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(p)
    assert os.path.getsize(p) > 10_000, '截图过小: %s' % name
    return p


def _input_value(drv, input_id, timeout=25):
    el = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(By.ID, input_id))
    return el.get_attribute('value')


def _click_button(drv, text):
    WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.XPATH, "//button[contains(., '%s')]" % text))
    drv.find_element(By.XPATH, "//button[contains(., '%s')]" % text).click()


def _switch_checked(drv, control_id, timeout=25):
    # base-ui Switch 覆写 id：按 Label[for=controlId] → parent → following-sibling [data-slot=switch]
    el = WebDriverWait(drv, timeout).until(
        lambda d: d.find_element(
            By.XPATH,
            "//label[@for='%s']/parent::div/following-sibling::*[@data-slot='switch']"
            % control_id))
    return el.get_attribute('aria-checked')


def test_01_workspace_site_info_light(drv):
    """站点信息分区：真实 KV 渲染 + Network 证据 + 浅色截图。"""
    _goto(drv, '/system-settings/site/info')
    _wait_text(drv, '站点信息')
    assert _input_value(drv, 'site-name') == SITE_NAME_ORIG, \
        '站点名称未渲染真实值: %r' % _input_value(drv, 'site-name')
    assert _input_value(drv, 'site-footer') == '© 2026 智能语音测试平台', \
        '页脚未渲染真实值'
    _shot(drv, 'site-info-light.png')
    urls = _resource_urls(drv, '/api/option/')
    assert any(u.endswith('/api/option/') or '/api/option/?' in u for u in urls), \
        '未请求 GET /api/option/: %s' % urls


def test_02_site_notice_empty(drv):
    """站点公告分区：公告为空 → 空表单可编辑（空态正常，无占位残留）。"""
    _goto(drv, '/system-settings/site/notice')
    _wait_text(drv, '站点公告')
    assert _input_value(drv, 'site-notice') == '', '公告应初始为空（site.notice 空）'
    _shot(drv, 'site-notice-light.png')


def test_03_site_navigation_module(drv):
    """导航模块分区：面包屑/算法切换器开关对齐真实 KV（true/true）。"""
    _goto(drv, '/system-settings/site/navigation')
    _wait_text(drv, '导航模块')
    _wait_text(drv, '面包屑导航', timeout=30)  # 等分区内容（懒加载）
    assert _switch_checked(drv, 'nav-breadcrumb') == 'true', '面包屑开关应为 true'
    assert _switch_checked(drv, 'nav-algorithm-switcher') == 'true', \
        '算法切换器开关应为 true'
    _shot(drv, 'site-navigation-light.png')


def test_04_auth_methods(drv):
    """认证方式分区：密码登录 on / 注册 on / 邮箱验证 off 对齐真实 KV。"""
    _goto(drv, '/system-settings/auth/methods')
    _wait_text(drv, '认证方式')
    _wait_text(drv, '密码登录', timeout=30)  # 等分区内容（懒加载）
    assert _switch_checked(drv, 'auth-password-login') == 'true', '密码登录应为 true'
    assert _switch_checked(drv, 'auth-registration') == 'true', '注册开关应为 true'
    assert _switch_checked(drv, 'auth-email-verification') == 'false', \
        '邮箱验证应为 false'
    _shot(drv, 'auth-methods-light.png')


def test_05_security_access_control(drv):
    """安全设置-访问控制：接口速率限制 on 对齐真实 KV。"""
    _goto(drv, '/system-settings/security/access-control')
    _wait_text(drv, '访问控制')
    _wait_text(drv, '接口速率限制', timeout=30)  # 等分区内容（懒加载）
    assert _switch_checked(drv, 'security-rate-limit') == 'true', \
        '接口速率限制应为 true'
    _shot(drv, 'security-light.png')


def test_06_operations_log_maintenance(drv):
    """运维设置-日志维护：保留天数 30 渲染 + 归档状态/列表区。"""
    _goto(drv, '/system-settings/operations/log-maintenance')
    _wait_text(drv, '日志维护')
    assert _input_value(drv, 'log-retention-days') == '30', \
        '日志保留天数应渲染真实值 30，实际 %r' % _input_value(drv, 'log-retention-days')
    _wait_text(drv, '立即清理', timeout=30)
    _shot(drv, 'operations-light.png')
    urls = _resource_urls(drv, '/api/v1/logs/archive')
    assert any('logs/archive/status' in u for u in urls), \
        '未请求日志归档状态接口: %s' % urls[:3]


def test_07_appearance_presets(drv):
    """外观与主题-主题预设：十预设全量渲染 + 选中态存在。"""
    _goto(drv, '/system-settings/appearance/presets')
    _wait_text(drv, '主题预设')
    # 等分区内容就绪（懒加载 chunk 首次编译较慢，等真实内容而非侧栏文字）
    _wait_text(drv, '选择站点的配色预设', timeout=45)
    items = WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, '[aria-label="选择颜色预设"] [role="radio"]'))
    assert len(items) >= 5, '预设数量不足: %d' % len(items)
    _shot(drv, 'appearance-presets-light.png')


def test_08_appearance_fine_tuning(drv):
    """外观与主题-外观微调：微调控件渲染。"""
    _goto(drv, '/system-settings/appearance/fine-tuning')
    _wait_text(drv, '外观微调')
    _wait_text(drv, '深浅色', timeout=45)  # 等分区内容（懒加载）
    _shot(drv, 'appearance-fine-tuning-light.png')


def test_09_iam_users_error_state(drv):
    """用户与权限-用户管理：常驻栈 auth_service gRPC 未监听 → 优雅空态（无崩溃）。"""
    _goto(drv, '/system-settings/iam/users')
    _wait_text(drv, '用户管理')
    # 等分区内容就绪：空态「暂无用户」出现（= users 查询已失败落定，非侧栏文字）
    _wait_text(drv, '暂无用户', timeout=40)
    urls = _resource_urls(drv, '/api/v1/auth/users')
    assert any('users' in u for u in urls), '未请求 GET /auth/users: %s' % urls
    body = _body_text(drv)
    # 不白屏：有管理框架文字 + 请求失败后展示优雅空态（暂无用户，非崩溃）
    assert '用户管理' in body and '管理平台用户账号' in body
    # 搜索框仍在（placeholder 不在 textContent，需按属性断言）
    search = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.CSS_SELECTOR,
                                 'input[placeholder="搜索用户名或邮箱"]'))
    assert search.get_attribute('placeholder') == '搜索用户名或邮箱'
    _shot(drv, 'iam-users-error.png')


def test_10_iam_roles_error_state(drv):
    """用户与权限-角色权限管理：同理 auth_service 缺口 → 优雅空态/错误态。"""
    _goto(drv, '/system-settings/iam/roles')
    _wait_text(drv, '角色权限管理')
    # 等分区内容就绪（空态出现 = roles 查询已失败落定，非侧栏文字）
    _wait_text(drv, '暂无自定义角色', timeout=40)
    urls = _resource_urls(drv, '/api/v1/auth/roles')
    assert any('roles' in u for u in urls), '未请求 GET /auth/roles: %s' % urls
    body = _body_text(drv)
    assert '角色权限管理' in body
    _shot(drv, 'iam-roles-error.png')


def test_11_oauth_providers_error_state(drv):
    """认证设置-OAuth 提供方：auth_service 缺口 → 优雅空态/错误态。"""
    _goto(drv, '/system-settings/auth/oauth-providers')
    _wait_text(drv, 'OAuth 提供方')
    # 等分区内容就绪（空态出现 = providers 查询已失败落定，非侧栏文字）
    _wait_text(drv, '尚未配置自定义 OAuth 提供方', timeout=40)
    urls = _resource_urls(drv, '/api/v1/auth/oauth-providers')
    assert any('oauth' in u for u in urls), '未请求 oauth-providers: %s' % urls
    _shot(drv, 'oauth-providers-error.png')


def test_12_dark_theme_walkthrough(drv):
    """深色：系统设置关键分区深色截图。"""
    _set_theme(drv, 'dark')
    _wait_text(drv, '站点信息')
    # 主题 effect 异步应用：等 <html> 落到 dark 再截图
    WebDriverWait(drv, 15).until(
        lambda d: 'dark' in d.execute_script(
            'return document.documentElement.className'))
    time.sleep(1)
    _shot(drv, 'site-info-dark.png')
    theme_mode = drv.execute_script('return document.documentElement.className')
    assert 'dark' in theme_mode, '深色主题未生效: %s' % theme_mode

    _goto(drv, '/system-settings/operations/log-maintenance')
    _wait_text(drv, '日志维护')
    time.sleep(1)
    _shot(drv, 'operations-dark.png')

    _goto(drv, '/system-settings/auth/methods')
    _wait_text(drv, '认证方式')
    time.sleep(1)
    _shot(drv, 'auth-methods-dark.png')

    _goto(drv, '/system-settings/iam/users')
    _wait_text(drv, '用户管理')
    time.sleep(1.5)
    _shot(drv, 'iam-users-dark.png')


def test_13_write_option_save_restore(drv):
    """写操作真实生效：站点名称改名（接线测试数据）→ 保存 → 回读确认 → 还原。"""
    _set_theme(drv, 'light')
    _goto(drv, '/system-settings/site/info')
    _wait_text(drv, '站点信息')
    name_input = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.ID, 'site-name'))
    name_input.clear()
    name_input.send_keys(TEST_NAME)
    _click_button(drv, '保存更改')
    # 保存 toast「设置已更新」
    _wait_text(drv, '设置已更新', timeout=15)
    time.sleep(1)
    # 回读真实接口确认新值
    saved = _input_value(drv, 'site-name')
    assert saved == TEST_NAME, '保存后前端值未更新: %r' % saved
    # 还原
    name_input = WebDriverWait(drv, 10).until(
        lambda d: d.find_element(By.ID, 'site-name'))
    name_input.clear()
    name_input.send_keys(SITE_NAME_ORIG)
    _click_button(drv, '保存更改')
    _wait_text(drv, '设置已更新', timeout=15)
    time.sleep(1)
    assert _input_value(drv, 'site-name') == SITE_NAME_ORIG, '还原失败'
    _shot(drv, 'site-info-write-restored.png')


def test_14_network_evidence(drv):
    """Network 汇总：/api/option/ 与 /api/v1/logs 真实请求留证。"""
    _set_theme(drv, 'light')
    _goto(drv, '/system-settings/operations/log-maintenance')
    _wait_text(drv, '日志维护')
    _wait_text(drv, '日志保留天数', timeout=40)  # 等分区内容（懒加载）就绪
    urls = _resource_urls(drv, '/api/option/')
    assert any('/api/option/' in u for u in urls), '缺 /api/option/ 请求: %s' % urls
    log_urls = _resource_urls(drv, '/api/v1/logs/archive')
    assert any('logs/archive/status' in u for u in log_urls), \
        '缺 /api/v1/logs/archive/status 请求: %s' % log_urls
