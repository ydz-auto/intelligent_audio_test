# -*- coding: utf-8 -*-
"""INT-513 个人中心页可视稿 浏览器走查（真实 Chrome headless，按 test_ui_13 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. /profile 页面：身份卡（头像 fallback + 用户名/角色/用户 ID 徽章 + @username 次行）
   + 个人数据快捷条三格（我的收藏 6 / 我的任务「查看全部」/ 我的报告「查看全部」）
2. 收藏明细 Popover：点「我的收藏」格 → 收藏的任务/报告/用例三行计数
3. 个人信息卡：只读行（用户名/角色/用户 ID/邮箱/权限概览）+ 权限 Popover
   （demo_admin '*' 通配 → 「超级管理员持有全部权限（通配 *）」）
4. 账号安全卡：第三方绑定（GitHub 已绑定 / 企业统一认证 未绑定）+ 解绑 ConfirmDialog 取消
5. 快捷入口卡：工作台/系统设置/使用文档/关于平台 + 外观与主题 Alert
6. /AccountSettings 旧链 redirect → /profile（保留 bind_ticket query）
7. 无 severe console 错误

失败落 tests/ui/artifacts/int513_profile/<用例>/（截图+console+source）。
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
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int513_profile')

# 5273 = 本工作区常驻 dev server；env 可覆写
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
_CONSOLE_SEVERE = []


def _drain_console(drv):
    """把浏览器 console 累积的 SEVERE 条目归入会话级列表（get_log 只返回上次调用后的增量）。"""
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
    except Exception:
        pass


@pytest.fixture(scope='session')
def drv():
    global _DRIVER
    _DRIVER = _driver()
    # 会话级登录（demo_admin 权限 '*'），单跑任意用例也能通过路由守卫
    try:
        _login(_DRIVER)
    except Exception:
        pass
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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _login(drv, username='demo_admin'):
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _open_profile(drv):
    """进入 /profile 并等身份卡渲染完成（等待用户名出现，跳过加载骨架）。"""
    _goto(drv, '/profile')
    WebDriverWait(drv, 15).until(
        lambda d: 'demo_admin' in d.execute_script('return document.body.textContent || ""'))


# ── 1. 身份卡 + 个人数据快捷条 ────────────────────────────────────────────────
def test_01_profile_header_and_quick_stats(drv):
    _open_profile(drv)
    body = _body_text(drv)

    # 浏览器/标签标题（§3.7 路由 meta 口径）
    assert '个人中心' in drv.title, f'document.title 应为个人中心，实际：{drv.title}'

    # 身份行：@username 次行 + 角色徽章（admin=超级管理员，§3.2）+ 用户 ID 徽章
    assert '@demo_admin' in body
    assert '超级管理员' in body
    assert '用户 ID mock-user-001' in body

    # 头像 fallback = 用户名首字符大写（D）
    avatar = drv.find_element(By.CSS_SELECTOR, '[data-slot="avatar"]')
    assert avatar.text.strip() == 'D', f'头像 fallback 应为 D，实际：{avatar.text.strip()!r}'

    # 个人数据快捷条三格（§3.3）：我的收藏计数 2+1+3=6；任务/报告计数未落前「查看全部」
    assert '我的收藏' in body
    assert '我的任务' in body
    assert '我的报告' in body
    assert '任务 · 报告 · 用例' in body
    assert '我创建的任务' in body
    assert '我生成的报告' in body
    assert '查看全部' in body


# ── 2. 收藏明细 Popover（§3.3.1）──────────────────────────────────────────────
def test_02_favorites_popover(drv):
    _open_profile(drv)
    # 点「我的收藏」格（aria-label=我的收藏 的触发钮）
    drv.find_element(By.XPATH, "//button[@aria-label='我的收藏']").click()
    WebDriverWait(drv, 8).until(
        lambda d: '收藏的任务' in d.execute_script('return document.body.textContent || ""'))

    body = _body_text(drv)
    assert '收藏的任务' in body
    assert '收藏的报告' in body
    assert '收藏的用例' in body
    # 计数行（demo_admin 三行均可见）：2 / 1 / 3
    rows = drv.find_elements(By.XPATH, "//*[@data-slot='popover-content']//a")
    assert len(rows) == 3, f'收藏明细行数应为 3，实际：{len(rows)}'
    assert '2' in rows[0].text and '1' in rows[1].text and '3' in rows[2].text
    # 关闭 Popover（Esc）
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.4)


# ── 3. 个人信息卡（只读行 + 权限概览 Popover，§3.4）────────────────────────────
def test_03_personal_info_card(drv):
    _open_profile(drv)
    body = _body_text(drv)

    assert '个人信息' in body
    assert '账号基础信息与权限概览' in body
    assert '用户名' in body
    assert '角色' in body
    assert '用户 ID' in body
    assert '邮箱' in body
    assert '权限概览' in body
    assert '当前页面为只读展示。如需修改用户名、邮箱或重置密码，请联系平台管理员。' in body

    # 权限概览 Popover（demo_admin permissions=['*'] → 通配单行）
    drv.find_element(By.XPATH, "//button[@aria-label='查看权限清单']").click()
    WebDriverWait(drv, 8).until(
        lambda d: '超级管理员持有全部权限（通配 *）' in d.execute_script(
            'return document.body.textContent || ""'))
    webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.4)


# ── 4. 账号安全卡（登录与认证 + 第三方绑定，§3.5）──────────────────────────────
def test_04_account_security_bindings(drv):
    _open_profile(drv)
    body = _body_text(drv)

    assert '账号安全' in body
    assert '登录密码与第三方账号绑定' in body
    assert '登录与认证' in body
    assert '第三方账号绑定' in body
    assert '绑定后可使用对应第三方账号直接登录本账号' in body
    assert 'GitHub' in body and '已绑定' in body
    assert '企业统一认证' in body and '未绑定' in body

    # 解绑确认框（§3.5.2）：点 GitHub 行「解绑」→ ConfirmDialog → 取消（不改状态）
    drv.find_element(By.XPATH, "//button[@aria-label='解绑 GitHub']").click()
    WebDriverWait(drv, 8).until(
        lambda d: d.find_elements(By.XPATH, "//*[@role='alertdialog']"))
    dialog = drv.find_element(By.XPATH, "//*[@role='alertdialog']")
    assert '确认解绑' in dialog.text
    assert '确认解绑「GitHub」？解绑后将无法使用该第三方账号登录。' in dialog.text
    dialog.find_element(By.XPATH, ".//button[contains(., '取消')]").click()
    time.sleep(0.4)
    assert not drv.find_elements(By.XPATH, "//*[@role='alertdialog']"), '取消后确认框应关闭'


# ── 5. 快捷入口卡 + 外观提示（§3.6/§3.6.1）─────────────────────────────────────
def test_05_quick_links_card(drv):
    _open_profile(drv)
    body = _body_text(drv)

    assert '快捷入口' in body
    assert '平台概览与快捷操作' in body
    assert '站点、用户与权限、认证、外观与主题等' in body
    assert '使用手册与 API 手册' in body
    assert '平台版本与服务状态' in body
    assert '外观与主题' in body
    assert '主题、字体、圆角、密度等外观偏好，可在右上角主题面板或「系统设置 → 外观与主题」中调整。' in body

    # 点击「工作台」→ /dashboard
    drv.find_element(By.XPATH, "//a[contains(., '工作台') and contains(., '平台概览与快捷操作')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/dashboard' in d.current_url)


# ── 6. /AccountSettings 旧链 redirect（§2.1/§3.5.2）───────────────────────────
def test_06_account_settings_redirect(drv):
    # 无 query：落 /profile
    _goto(drv, '/AccountSettings')
    WebDriverWait(drv, 15).until(lambda d: '/profile' in d.current_url)
    assert '/AccountSettings' not in drv.current_url
    time.sleep(0.5)

    # 携 bind_ticket query：redirect 携票转入 /profile，页面 onMount 消化（§3.5.2）
    # → toast「绑定成功」→ 清 query（避免刷新重复提交）
    _goto(drv, '/AccountSettings?bind_ticket=mock-ticket-001')
    WebDriverWait(drv, 15).until(lambda d: '/profile' in d.current_url)
    WebDriverWait(drv, 8).until(
        lambda d: '绑定成功' in d.execute_script('return document.body.textContent || ""'))
    WebDriverWait(drv, 8).until(lambda d: 'bind_ticket' not in d.current_url)
    time.sleep(0.5)


# ── 7. 无 severe console 错误 ─────────────────────────────────────────────────
def test_07_no_severe_console_errors(drv):
    _open_profile(drv)
    _drain_console(drv)
    assert not _CONSOLE_SEVERE, f'浏览器 console SEVERE 错误：\n' + '\n'.join(_CONSOLE_SEVERE[:10])
