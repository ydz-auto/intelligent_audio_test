# -*- coding: utf-8 -*-
"""INT-607 壳/导航/RBAC 接线浏览器验收（真实 Chrome headless + 常驻后端 :5000 + 本 worktree dev server）。

覆盖验收标准（INT-607）：
1. 真实后端登录（AUTH_MODE=off 注入 dev_user '*' 全放行）→ 导航/RBAC 过滤基线（6 顶栏 / 14 侧栏）。
2. 五系统角色 × 权限串（seed_rbac.py 实测权限清单）逐角色核对导航过滤（隐藏而非置灰）：
   admin '*' → 6 顶栏 / 14 侧栏；tester → 6/13（SPL 隐藏）；algo_engineer → 6/11（设备/SPL/系统设置隐藏）；
   device_admin → 4/3（报告/排行榜隐藏；侧栏概览/设备/SPL）；guest → 5/3（排行榜隐藏；侧栏概览/灵犀Agent/报告中心）。
3. 无权限直达 URL → /403?from=<pathname> 兜底 + 来源页回显（guest→/tasks、device_admin→/reports）。
4. 权限变化（登录态切换）后导航即时收敛：dev_user 全量 → 注入 guest 会话刷新 → 顶栏/侧栏收敛为 guest 集合。
5. 全局算法切换器按 algorithm:read 显隐（device_admin/guest 隐藏整钮）。

会话注入口径：AUTH_MODE=off 常驻后端无 token 时 GET /auth/me 回填 dev_user(['*'])；
逐角色用 CDP Network.setBlockedURLs 拦掉 /auth/me + localStorage 预注入 zustand persist
会话（iatp:auth:v1），使 hydrateSession 的 getMe 失败回落保留注入会话（catch 分支「保留现有状态」）。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5331')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'artifacts', 'int607_shell')
os.makedirs(ARTIFACTS, exist_ok=True)

AUTH_STORE_KEY = 'iatp:auth:v1'
TOKEN_KEY = 'iatp:auth:token:v1'

# ---- 五系统角色 × 权限串（seed_rbac.py 实测清单，2026-10-18 读库核对一致）----
ROLES = {
    'admin': {'user_id': 1, 'username': 'admin', 'role_name': '超级管理员', 'permissions': ['*']},
    'tester': {'user_id': 2, 'username': 'tester', 'role_name': '测试工程师', 'permissions': [
        'task:read', 'task:create', 'task:update', 'task:delete', 'task:execute',
        'task:merge', 'task:batch', 'task:reextract', 'task:publish',
        'task:export', 'task:import', 'task:cherry_pick', 'task.result.review',
        'published_task:read', 'published_task:execute', 'published_task:version',
        'published_task:archive',
        'testcase:read', 'testcase:create', 'testcase:update', 'testcase:delete',
        'testcase:copy', 'testcase:preview', 'testcase:import_export',
        'audio:read', 'audio:upload', 'audio:update', 'audio:delete',
        'audio:convert', 'audio:folder',
        'device:read',
        'api_config:read', 'api_config:create', 'api_config:update',
        'api_config:delete', 'api_config:test',
        'report:read', 'report:create', 'report:update', 'report:delete',
        'report:compare', 'report:download_log',
        'benchmark:ranking:read', 'benchmark:ranking:compute',
        'benchmark:baseline:read', 'benchmark:baseline:write',
        'benchmark:baseline:publish', 'benchmark:mapping:manage',
        'benchmark:report:read', 'benchmark:report:publish',
        'evaluation:read', 'evaluation:execute', 'evaluation:dim_manage',
        'evaluation:category_manage', 'evaluation:import_export',
        'algorithm:read', 'algorithm:case_param_manage',
        'group:read', 'group:create', 'group:update', 'group:delete',
        'tag:read', 'tag:create', 'tag:update', 'tag:delete',
        'log:read', 'log:manage', 'log:websocket',
        'home:read', 'home:refresh',
        'status:read', 'option:read', 'option:write',
        'sse:read',
        'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ]},
    'algo_engineer': {'user_id': 3, 'username': 'algo_engineer', 'role_name': '算法工程师', 'permissions': [
        'task:read', 'published_task:read', 'testcase:read', 'audio:read',
        'api_config:read',
        'report:read', 'report:create', 'report:update', 'report:publish',
        'report:compare', 'report:download_log',
        'benchmark:ranking:read', 'benchmark:ranking:compute',
        'benchmark:baseline:read', 'benchmark:baseline:write',
        'benchmark:baseline:publish', 'benchmark:mapping:manage',
        'benchmark:report:read', 'benchmark:report:publish',
        'evaluation:read', 'evaluation:dim_manage', 'evaluation:category_manage',
        'evaluation:import_export',
        'algorithm:read', 'algorithm:definition_manage', 'algorithm:group_manage',
        'algorithm:param_manage', 'algorithm:case_param_manage',
        'group:read', 'tag:read', 'log:read', 'log:websocket',
        'home:read', 'status:read', 'option:read', 'sse:read',
        'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ]},
    'device_admin': {'user_id': 4, 'username': 'device_admin', 'role_name': '设备管理员', 'permissions': [
        'device:read', 'device:create', 'device:update', 'device:delete', 'device:control',
        'playback:read', 'playback:create', 'playback:update', 'playback:delete', 'playback:control',
        'spl:read', 'spl:create', 'spl:update', 'spl:delete', 'spl:test_tone',
        'digital_spl:read', 'digital_spl:create', 'digital_spl:update', 'digital_spl:delete',
        'lab:create', 'lab:update', 'lab:delete',
        'home:read', 'status:read', 'option:read', 'sse:read',
        'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ]},
    'guest': {'user_id': 5, 'username': 'guest', 'role_name': '游客', 'permissions': [
        'report:read', 'report:compare', 'home:read', 'status:read', 'sse:read',
        'auth:login', 'auth:callback', 'auth:refresh', 'auth:logout', 'auth:me',
    ]},
}

TOP_NAV_FULL = ['主页', '工作台', '报告', '排行榜', '文档', '关于']
TOP_NAV_EXPECT = {
    'admin': TOP_NAV_FULL,
    'tester': TOP_NAV_FULL,
    'algo_engineer': TOP_NAV_FULL,
    'device_admin': ['主页', '工作台', '文档', '关于'],
    'guest': ['主页', '工作台', '报告', '文档', '关于'],
}
SIDEBAR_ALL = ['概览', '灵犀Agent', '开始测试', '任务管理', '用例管理', '音频管理', '设备管理',
               '报告中心', '算法配置', '评估维度', 'SPL 映射', '标签管理', '日志查看', '系统设置']
SIDEBAR_EXPECT = {
    'admin': SIDEBAR_ALL,
    'tester': [i for i in SIDEBAR_ALL if i != 'SPL 映射'],
    'algo_engineer': [i for i in SIDEBAR_ALL if i not in ('设备管理', 'SPL 映射', '系统设置')],
    'device_admin': ['概览', '设备管理', 'SPL 映射'],
    'guest': ['概览', '灵犀Agent', '报告中心'],
}

# 无权限直达 → 403 用例（角色，URL，期望 from）
FORBIDDEN_CASES = [
    ('guest', '/tasks/daily', '/tasks/daily'),
    ('device_admin', '/reports', '/reports'),
    ('device_admin', '/logs', '/logs'),
    ('guest', '/system-settings/site', '/system-settings/site'),
]


def _user_json(role_key):
    r = ROLES[role_key]
    return {
        'id': str(r['user_id']),
        'username': r['username'],
        'displayName': r['username'],
        'roleName': r['role_name'],
        'permissions': r['permissions'],
    }


def inject_session(driver, role_key):
    """注入指定角色会话到 localStorage（zustand persist iatp:auth:v1）。"""
    user = _user_json(role_key)
    payload = json.dumps({'state': {'user': user}, 'version': 0})
    driver.execute_script(
        f"localStorage.setItem('{AUTH_STORE_KEY}', {json.dumps(payload)});"
        f"localStorage.removeItem('{TOKEN_KEY}');"
    )


def block_me(driver):
    driver.execute_cdp_cmd('Network.enable', {})
    driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['*auth/me*']})


def unblock_me(driver):
    driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})


def set_theme(driver, theme):
    driver.execute_script(
        f"localStorage.setItem('iatp:theme:v1:mode', '{theme}');"
    )


def get_top_nav(driver):
    """收集页面头部 TopNav 链接文本（宽屏横向链接）。"""
    try:
        nav_els = driver.find_elements(By.CSS_SELECTOR, 'header nav a')
    except Exception:
        return []
    titles = []
    for el in nav_els:
        t = el.text.strip()
        if t:
            titles.append(t)
    return titles


def get_sidebar_items(driver):
    """收集侧栏菜单项文本（data-slot=sidebar-menu-button）。"""
    try:
        els = driver.find_elements(By.CSS_SELECTOR, '[data-slot="sidebar-menu-button"] span')
    except Exception:
        return []
    items = []
    for el in els:
        t = el.text.strip()
        if t and t not in items:
            items.append(t)
    return items


def get_algorithm_switcher(driver):
    try:
        return len(driver.find_elements(By.CSS_SELECTOR, '[aria-label="切换全局算法"]')) > 0
    except Exception:
        return False


def wait_ready(driver, timeout=25):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            "return document.querySelector('header nav') != null || document.querySelector('[data-slot=\"sidebar-menu-button\"]') != null"
        )
    )


def nav_to_dashboard(driver):
    driver.get(BASE + '/dashboard')
    wait_ready(driver)
    time.sleep(1.5)


def main():
    results = []
    ok_all = True

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1440,900')
    options.add_argument('--hide-scrollbars')
    driver = webdriver.Chrome(options=options)

    driver.set_window_size(1440, 900)

    def check(name, condition, detail=''):
        nonlocal ok_all
        status = 'PASS' if condition else 'FAIL'
        if not condition:
            ok_all = False
        print(f'[{status}] {name} {detail}')
        results.append((status, name, detail))

    # ========== 1. 基线：真实后端 AUTH_MODE=off dev_user（*）全放行 ==========
    unblock_me(driver)
    driver.get(BASE + '/dashboard')
    wait_ready(driver)
    time.sleep(2)
    top = get_top_nav(driver)
    side = get_sidebar_items(driver)
    check('基线 dev_user 顶栏', top == TOP_NAV_FULL, f'实际={top}')
    check('基线 dev_user 侧栏', side == SIDEBAR_ALL, f'实际={side}')
    driver.save_screenshot(os.path.join(ARTIFACTS, 'shell_admin_light.png'))
    # 深色
    set_theme(driver, 'dark')
    driver.get(BASE + '/dashboard')
    wait_ready(driver)
    time.sleep(1.5)
    driver.save_screenshot(os.path.join(ARTIFACTS, 'shell_admin_dark.png'))
    set_theme(driver, 'light')

    # ========== 2. 逐角色注入会话 → 导航/RBAC 过滤核对 ==========
    block_me(driver)
    for role_key in ['tester', 'algo_engineer', 'device_admin', 'guest']:
        inject_session(driver, role_key)
        driver.get(BASE + '/dashboard')
        wait_ready(driver)
        time.sleep(2)
        top = get_top_nav(driver)
        side = get_sidebar_items(driver)
        check(f'{role_key} 顶栏过滤', top == TOP_NAV_EXPECT[role_key], f'实际={top}')
        check(f'{role_key} 侧栏过滤', side == SIDEBAR_EXPECT[role_key], f'实际={side}')
        # 算法切换器按 algorithm:read 显隐
        algo = get_algorithm_switcher(driver)
        algo_expect = role_key in ('tester', 'algo_engineer', 'admin')
        check(f'{role_key} 算法切换器 {"显" if algo_expect else "隐"}', algo == algo_expect, f'实际={"显" if algo else "隐"}')
        # 截图：guest 浅+深；其余角色浅色一张
        if role_key == 'guest':
            driver.save_screenshot(os.path.join(ARTIFACTS, f'shell_{role_key}_light.png'))
            set_theme(driver, 'dark')
            driver.get(BASE + '/dashboard')
            wait_ready(driver)
            time.sleep(1.5)
            driver.save_screenshot(os.path.join(ARTIFACTS, f'shell_{role_key}_dark.png'))
            set_theme(driver, 'light')
        elif role_key in ('tester', 'device_admin'):
            driver.save_screenshot(os.path.join(ARTIFACTS, f'shell_{role_key}_light.png'))

    # ========== 3. 无权限直达 URL → /403?from 兜底 ==========
    for role_key, url, expect_from in FORBIDDEN_CASES:
        inject_session(driver, role_key)
        driver.get(BASE + url)
        time.sleep(2.5)
        cur = driver.current_url
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(cur)
        path_q = cur.replace(BASE, '')
        qs = parse_qs(parsed.query)
        ok_403 = parsed.path == '/403' and qs.get('from', [''])[0] == expect_from
        # 页面回显来源页
        body = driver.find_element(By.TAG_NAME, 'body').text
        echo_ok = expect_from in body
        check(f'403 兜底 {role_key}→{url}', ok_403, f'实际 URL={path_q}')
        check(f'403 来源页回显 {role_key}→{url}', echo_ok, f'页面包含 {expect_from}')
        if role_key == 'guest':
            driver.save_screenshot(os.path.join(ARTIFACTS, 'guest_403_light.png'))
            set_theme(driver, 'dark')
            driver.get(BASE + url)
            time.sleep(2.5)
            driver.save_screenshot(os.path.join(ARTIFACTS, 'guest_403_dark.png'))
            set_theme(driver, 'light')

    # ========== 4. 权限变化（登录态切换）→ 导航即时收敛 ==========
    unblock_me(driver)
    driver.get(BASE + '/dashboard')  # 真实 dev_user（*）全量
    wait_ready(driver)
    time.sleep(2)
    top_admin = get_top_nav(driver)
    side_admin = get_sidebar_items(driver)
    check('收敛前置：dev_user 全量顶栏', top_admin == TOP_NAV_FULL, f'实际={top_admin}')
    check('收敛前置：dev_user 全量侧栏', side_admin == SIDEBAR_ALL, f'实际={side_admin}')
    # 切 guest 会话（block /auth/me + 注入 localStorage → 刷新）
    block_me(driver)
    inject_session(driver, 'guest')
    driver.get(BASE + '/dashboard')
    wait_ready(driver)
    time.sleep(2)
    top_guest = get_top_nav(driver)
    side_guest = get_sidebar_items(driver)
    check('收敛后：guest 顶栏', top_guest == TOP_NAV_EXPECT['guest'], f'实际={top_guest}')
    check('收敛后：guest 侧栏', side_guest == SIDEBAR_EXPECT['guest'], f'实际={side_guest}')

    # ========== 汇总 ==========
    passed = sum(1 for s, _, _ in results if s == 'PASS')
    failed = sum(1 for s, _, _ in results if s == 'FAIL')
    print(f'\n==== INT-607 浏览器验收：{passed} 通过 / {failed} 失败 ====')
    for s, name, detail in results:
        print(f'  [{s}] {name}')
    return ok_all


if __name__ == '__main__':
    import sys
    ok = main()
    sys.exit(0 if ok else 1)
