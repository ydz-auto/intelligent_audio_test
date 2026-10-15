# -*- coding: utf-8 -*-
"""INT-377 React 基座浏览器走查（真实 Chrome headless，按 tests/ui 先例）。

针对 frontend-react/ mock 稿的基座级走查——无后端依赖，直接驱动 dev server：
1. /login 可达且登录表单渲染（中文文案）
2. mock 登录 → /dashboard 落地，导航壳渲染（TopNav 六项 + 侧栏四组十项）
3. 主题抽屉：10 预设齐全、lake-view 默认、切换后 body data 属性 + localStorage 持久化
4. 深浅色切换：html.dark class 生效并持久化（iatp:theme:v1:mode）
5. Ctrl+B 侧栏折叠：SidebarProvider wrapper data-state expanded/collapsed 切换
6. 系统设置 drill-in：侧栏树整树替换 + 「返回控制台」还原
7. 路由可达：错误页三件 + 业务页占位
8. 未登录守卫：/dashboard → /login?redirect=，登录后回跳原页
9. 右上角功能区：算法切换器（选算法写回 iatp:algorithm:v1 + 页面联动）/通知/语言/主题
10. 【已知缺陷】用户下拉点击后 Base UI MenuGroupLabel 上下文缺失 → 整树崩到 500 错误页

失败落 tests/ui/artifacts/int377_react_base/<用例>/（截图+console+source）。
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

# 栈门禁豁免：本文件走查 frontend-react/ mock 稿（无后端依赖），
# tests/ui/conftest.py 经 STACK_GATE_EXEMPT_MODULES 对本模块放行。

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int377_react_base')

# 3000 被 newAPI 参照实例（new-api.exe --port 3000）常驻占用；React dev server 钉死 5273
# （负责人 2026-10-15，rsbuild.config.ts server.port=5273 + strictPort:true），默认值对齐 5273。
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
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
    # Chrome 主版本 → 缓存同主版本 chromedriver（tests/ui/conftest 先例）
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
    WebDriverWait = _wait()
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _wait():
    from selenium.webdriver.support.ui import WebDriverWait
    return WebDriverWait


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _login(drv, username='demo_admin'):
    # 先清会话：已登录时 /login 的 beforeLoad 会 redirect 到 /dashboard，
    # 导致表单元素找不到（用例间状态泄漏防护）。
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    _wait()(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _open_theme_drawer(drv):
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='打开主题设置']").click()
    time.sleep(1.0)
    return drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")


def _close_theme_drawer(drv):
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)


# ── 1. 登录页可达与表单渲染 ──────────────────────────────────
def test_01_login_page_renders(drv):
    _goto(drv, '/login')
    txt = _body_text(drv)
    assert '用户名' in txt, f'登录表单缺「用户名」label：{txt[:200]}'
    assert '密码' in txt
    assert drv.find_element(By.ID, 'username').is_displayed()
    assert drv.find_element(By.ID, 'password').is_displayed()
    assert '登 录' in txt, '登录按钮文案缺失'


# ── 2. mock 登录 → 控制台壳渲染 ──────────────────────────────
def test_02_mock_login_lands_dashboard(drv):
    drv.get(BASE + '/login')
    time.sleep(1.5)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _login(drv)
    assert '/dashboard' in drv.current_url, f'登录后未落地 /dashboard：{drv.current_url}'
    txt = _body_text(drv)
    # TopNav 六项（02_导航栏.md §2.2 文案定稿：主页→控制台→报告→排行榜→文档→关于）
    for item in ['主页', '控制台', '报告', '排行榜', '文档', '关于']:
        assert item in txt, f'TopNav 缺「{item}」'
    # 侧栏四组十项（04_控制台.md §3.2）
    for item in ['总览', '工作台', '测试执行', '端到端测试', 'API 测试', '任务管理',
                 '测试资产', '用例管理', '音频管理', '设备管理', '报告中心',
                 '管理', '日志查看', '系统设置']:
        assert item in txt, f'侧栏缺「{item}」'
    # 右上角功能区六件 aria 可见（算法/搜索/通知/语言/主题/用户）
    for label in ['切换全局算法', '通知', '切换语言', '打开主题设置', '用户菜单']:
        drv.find_element(By.CSS_SELECTOR, f"button[aria-label='{label}']")


# ── 3. 主题抽屉：10 预设 + lake-view 默认 + 切换持久化 ────────
def test_03_theme_presets_and_persist(drv):
    _goto(drv, '/dashboard')
    drv.execute_script("window.localStorage.removeItem('iatp:theme:v1:preset')")
    _goto(drv, '/dashboard')
    sheet = _open_theme_drawer(drv)
    assert '外观设置' in sheet.text and '颜色预设' in sheet.text
    # 10 预设 aria-label 全量（THEME_PRESETS）
    labels = drv.execute_script(
        "return Array.from(document.querySelectorAll('span[role=radio][aria-label]'))"
        ".map(e => e.getAttribute('aria-label'))")
    for name in ['默认蓝', 'Anthropic', '简洁大字', '暗流', '玫瑰园', '湖光',
                 '落日', '林语', '海风', '薰衣草']:
        assert name in labels, f'预设缺「{name}」：{labels}'
    # lake-view 默认：无持久化值 + aria-checked 落在湖光
    assert drv.execute_script(
        "return window.localStorage.getItem('iatp:theme:v1:preset')") is None, \
        '默认预设不应写 localStorage'
    checked = drv.execute_script(
        "return Array.from(document.querySelectorAll('span[role=radio]'))"
        ".filter(e => e.getAttribute('aria-checked') === 'true')"
        ".map(e => e.getAttribute('aria-label'))")
    assert '湖光' in checked, f'默认选中预设不是湖光：{checked}'
    # 切换到 玫瑰园 → body data 属性 + localStorage 持久化
    drv.find_element(By.XPATH, "//span[@role='radio'][@aria-label='玫瑰园']").click()
    time.sleep(0.8)
    assert drv.execute_script(
        "return document.body.getAttribute('data-theme-preset')") == 'rose-garden'
    assert drv.execute_script(
        "return window.localStorage.getItem('iatp:theme:v1:preset')") == 'rose-garden'
    # 刷新后仍生效（持久化闭环）
    _goto(drv, '/dashboard')
    assert drv.execute_script(
        "return window.localStorage.getItem('iatp:theme:v1:preset')") == 'rose-garden', \
        '刷新后预设持久化丢失'
    # 重置回默认（lake-view）
    sheet = _open_theme_drawer(drv)
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='重置全部设置为默认值']").click()
    time.sleep(0.6)
    assert drv.execute_script(
        "return window.localStorage.getItem('iatp:theme:v1:preset')") is None
    _close_theme_drawer(drv)


# ── 4. 深浅色切换 ────────────────────────────────────────────
def test_04_dark_light_toggle(drv):
    _goto(drv, '/dashboard')
    _open_theme_drawer(drv)
    drv.find_element(By.XPATH, "//span[@role='radio'][@aria-label='选择深色']").click()
    time.sleep(0.6)
    assert drv.execute_script(
        "return document.documentElement.classList.contains('dark')"), \
        '切深色后 html.dark 未生效'
    assert drv.execute_script(
        "return window.localStorage.getItem('iatp:theme:v1:mode')") == 'dark', \
        '深色偏好未持久化'
    drv.find_element(By.XPATH, "//span[@role='radio'][@aria-label='选择浅色']").click()
    time.sleep(0.6)
    assert not drv.execute_script(
        "return document.documentElement.classList.contains('dark')"), \
        '切浅色后 html.dark 仍在'
    # 还原跟随系统
    drv.find_element(By.XPATH, "//span[@role='radio'][@aria-label='选择跟随系统']").click()
    time.sleep(0.5)
    _close_theme_drawer(drv)


# ── 5. Ctrl+B 侧栏折叠 ───────────────────────────────────────
def test_05_sidebar_ctrl_b_collapse(drv):
    _goto(drv, '/dashboard')
    time.sleep(0.8)
    # data-state 挂在 SidebarProvider 的 group wrapper（div.group）
    state_js = ("return (document.querySelector('div.group[data-state]')"
                "|| document.querySelector('[data-sidebar=sidebar]')"
                "|| {}).getAttribute && ((document.querySelector('div.group[data-state]')"
                "|| document.querySelector('[data-sidebar=sidebar]'))"
                ".getAttribute('data-state'))")
    before = drv.execute_script(state_js)
    assert before in ('expanded', 'collapsed'), f'侧栏初始状态异常：{before}'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, 'b')
    time.sleep(0.6)
    after = drv.execute_script(state_js)
    assert before != after, f'Ctrl+B 未切换侧栏状态（{before}→{after}）'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, 'b')
    time.sleep(0.6)
    restored = drv.execute_script(state_js)
    assert restored == before, f'再次 Ctrl+B 未还原（{after}→{restored}）'


# ── 6. 系统设置 drill-in ─────────────────────────────────────
def test_06_system_settings_drill_in(drv):
    _goto(drv, '/dashboard')
    time.sleep(0.8)
    drv.find_element(By.XPATH, "//a[contains(., '系统设置')]").click()
    _wait()(drv, 15).until(lambda d: '/system-settings' in d.current_url)
    time.sleep(1.0)
    txt = _body_text(drv)
    assert '返回控制台' in txt, 'drill-in 缺「返回控制台」入口'
    for item in ['站点设置', '用户管理', '角色与权限', '算法配置', '评估维度']:
        assert item in txt, f'设置树缺「{item}」'
    drv.find_element(By.XPATH, "//a[contains(., '返回控制台')]").click()
    _wait()(drv, 15).until(lambda d: '/dashboard' in d.current_url)
    time.sleep(1.0)
    assert '工作台' in _body_text(drv), '返回控制台后侧栏未还原'


# ── 7. 错误页与业务页占位路由可达 ────────────────────────────
def test_07_routes_reachable(drv):
    _login(drv)
    for path, expect in [('/403', '403'), ('/404', '404'), ('/500', '500'),
                         ('/system-settings/site', '站点设置'),
                         ('/tasks', '任务'), ('/testcases', '用例'),
                         ('/reports', '报告'), ('/rankings', '排行榜'),
                         ('/user-guide', '文档'), ('/about', '关于')]:
        _goto(drv, path)
        txt = _body_text(drv)
        assert expect in txt, f'{path} 未渲染预期内容「{expect}」：{txt[:120]}'


# ── 8. 未登录守卫 → /login?redirect= → 登录回跳 ──────────────
def test_08_auth_guard_redirects(drv):
    # 先清会话（前序用例可能已登录；登录态下 /tasks 不触发守卫）
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/tasks')
    _wait()(drv, 15).until(lambda d: '/login' in d.current_url)
    assert 'redirect=' in drv.current_url, f'守卫未携带回跳：{drv.current_url}'
    # 登录后回跳原页（sanitize 前置的回跳闭环）
    drv.find_element(By.ID, 'username').send_keys('demo_admin')
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    _wait()(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)
    assert '/tasks' in drv.current_url, f'登录后未回跳原页：{drv.current_url}'
    # 清会话再验守卫
    drv.execute_script("window.localStorage.removeItem('iatp:auth:v1')")
    _goto(drv, '/dashboard')
    _wait()(drv, 15).until(lambda d: '/login' in d.current_url)


# ── 9. 右上角功能区：算法切换器写回 + 通知/语言浮层 ───────────
def test_09_header_right_zone(drv):
    _login(drv)
    # 算法切换器：浮层开 → 选「流式识别引擎」→ 顶栏值 + LS 写回
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='切换全局算法']").click()
    time.sleep(1.0)
    drv.execute_script(
        "const s = Array.from(document.querySelectorAll('span'))"
        ".filter(e => e.children.length === 0 && e.textContent.trim() === '流式识别引擎')[0];"
        "s.closest('[role], button, [data-base-ui]').click()")
    time.sleep(0.8)
    cur = drv.find_element(
        By.CSS_SELECTOR, "button[aria-label='切换全局算法']").text
    assert '流式识别引擎' in cur, f'切换器未显示新算法：{cur}'
    algo = json.loads(drv.execute_script(
        "return window.localStorage.getItem('iatp:algorithm:v1')") or '{}')
    assert algo.get('state', {}).get('algorithmId') == 'asr-stream', \
        f'全局算法未写回 store：{algo}'
    # 联动：任务页顶栏 chip 显示当前算法（INT-344 契约）
    _goto(drv, '/tasks')
    assert '流式识别引擎' in _body_text(drv), '任务页未联动显示当前算法'
    # 通知浮层（页签：通知/公告）
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='通知']").click()
    time.sleep(0.8)
    tabs = drv.execute_script(
        "return Array.from(document.querySelectorAll('[role=tab]'))"
        ".map(e => e.textContent.trim())")
    assert '通知' in tabs and '公告' in tabs, f'通知浮层页签缺失：{tabs}'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.5)
    # 语言切换器浮层
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='切换语言']").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    assert ('中文' in txt) or ('English' in txt), '语言切换浮层未渲染'
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)


# ── 10.【缺陷确认】用户下拉点击 → 整树崩到 500 错误页 ─────────
def test_10_user_dropdown_known_bug(drv):
    """Base UI MenuGroupLabel 上下文缺失：DropdownMenuLabel 未包在
    DropdownMenuGroup 内，点击「用户菜单」触发 React 渲染错误 →
    根路由 errorComponent（500 版式）整树接管。已确认为交付缺陷，
    此用例固化复现路径供打回修复后回归。"""
    _login(drv)
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='用户菜单']").click()
    time.sleep(1.5)
    txt = _body_text(drv)
    # 修复后期望：下拉展开显示用户卡（displayName + roleName）
    assert '演示管理员' in txt and '超级管理员' in txt and '登出' in txt, (
        '用户下拉未正常展开（当前实现点击后 MenuGroupContext 缺失导致整树'
        f'崩到 500 错误页）。实际页面文本：{txt[:200]}')
