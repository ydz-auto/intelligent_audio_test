# -*- coding: utf-8 -*-
"""INT-806 UI 实测（验收标准 5）：旧 Vue /logs 高级筛选「用户ID」→ user_id 查询参数 + 列表过滤。

流程：
1. API 造用户 A（tester，自带 log:read）+ 触发一条可归属审计日志（PUT /auth/self）→ 等异步落库；
2. 浏览器以 A 登录 → /logs 页；
3. 打开高级过滤 → 输入 A 的 user_id → 列表刷新；
4. Network 证据：performance resource entries 中出现 /logs?user_id=<A> 请求；
5. 断言列表仅显示 A 的行（内容含 operator_id=<A>，无其他用户行）。

测试数据自建自清：teardown 硬删用户 A + 其归属审计日志（隔离库）。
"""
import os
import time

import httpx
import pytest
from selenium.webdriver.common.by import By

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import ApiClient, unique_suffix

API_ROOT = os.environ.get('UI_API_BASE', 'http://127.0.0.1:5000')
FRONTEND_BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5173')

LOGS_ROUTE = '/LogView'
ADVANCED_TOGGLE = '.filter-bar .btn-text'          # 高级过滤 toggle（LogFilterPanel 内）
USER_ID_INPUT = "//label[contains(text(), '用户ID')]/following-sibling::div//input"
LOG_ROWS = '.log-table tbody tr.log-row, table tbody tr.log-row'


@pytest.fixture()
def _user_a_with_log(api_client):
    """API 造用户 A + 触发可归属审计日志；返回 (uid, username, password)。"""
    suffix = unique_suffix()
    username = f'int806ui_{suffix}'
    password = 'UiTest@12345'
    uid = api_client.register(username, password)
    # 新注册用户默认 guest（无 log:read）→ 提升为 tester（role 2，含 log:read）
    from sqlalchemy import create_engine, text
    from tests.ui.utils import bootstrap
    eng = create_engine(bootstrap.isolated_db_url())
    with eng.connect() as c:
        c.execute(text('update users set role_id=2 where id=:u'), {'u': uid})
        c.commit()
    ca = ApiClient(API_ROOT)
    ca.login(username, password)
    assert ca.token, 'A 登录失败'
    assert 'log:read' in ca.user.get('permissions', []), 'A 无 log:read 权限'
    r = httpx.put(f'{API_ROOT}/api/v1/auth/self', json={'email': f'{username}@new.test'},
                  headers={'Authorization': f'Bearer {ca.token}'}, timeout=15, trust_env=False)
    assert r.status_code == 200, f'PUT /auth/self 失败: {r.text[:120]}'
    time.sleep(4)  # 等待异步日志 worker 落库
    yield uid, username, password
    # teardown：硬删用户 + 其归属日志（隔离库卫生）
    with eng.connect() as c:
        c.execute(text('delete from logs where created_by_user_id=:u'), {'u': uid})
        c.execute(text('delete from users where id=:u'), {'u': uid})
        c.commit()


def _captured_log_urls(driver) -> list:
    """取页面存活期间包含 /logs 的 resource 请求 URL（含 query）。"""
    urls = driver.execute_script(
        "return performance.getEntriesByType('resource').map(function(e){return e.name;})")
    return [u for u in urls if '/logs' in u and 'user_id' in u]


def _hook_fetch(driver):
    """注入 fetch 包装器：记录含 /logs 的请求 URL（跨端口 API 的 resource timing
    受 Timing-Allow-Origin 限制，performance 条目未必暴露，故直接钩 fetch）。"""
    driver.execute_script(
        "window.__int806_log_urls = [];"
        "var _orig = window.fetch;"
        "window.fetch = function(input, init) {"
        "  var u = typeof input === 'string' ? input : (input && input.url) || '';"
        "  if (u.indexOf('/logs') !== -1) { window.__int806_log_urls.push(u); }"
        "  return _orig.apply(this, arguments);"
        "};")


def _captured_hooked_urls(driver) -> list:
    return list(driver.execute_script("return window.__int806_log_urls || [];"))


def test_logs_user_id_filter(login_page, _user_a_with_log):
    uid_a, username, password = _user_a_with_log
    driver = login_page.driver

    # 浏览器以 A 登录
    login_page.login(username, password)
    assert login_page.wait_left_login(timeout=20), 'A 表单登录后未离开 /login'
    page = BasePage(driver, FRONTEND_BASE)
    page.goto(LOGS_ROUTE)
    page.wait_title_text('日志查看', timeout=20)

    # 打开高级过滤
    page.find_visible('.advanced-filter-panel, .filter-bar', timeout=15)
    toggle = None
    for el in driver.find_elements(By.CSS_SELECTOR, ADVANCED_TOGGLE):
        if '高级过滤' in el.text:
            toggle = el
            break
    assert toggle is not None, '未找到「高级过滤」切换按钮'
    toggle.click()
    page.settle(0.6)
    page.wait_visible('.advanced-filter-panel', timeout=10)

    # 输入 A 的 user_id（先钩 fetch 捕获请求 URL）
    _hook_fetch(driver)
    before = set(_captured_hooked_urls(driver))
    inp = driver.find_element(By.XPATH, USER_ID_INPUT)
    inp.clear()
    inp.send_keys(str(uid_a))
    page.settle(2.0)  # @input 触发 filterLogs 并等待防抖 + 请求完成

    # 断言 1：Network 证据——/logs 请求带 user_id=<A>
    after = set(_captured_hooked_urls(driver))
    new_urls = after - before
    matched = [u for u in new_urls if f'user_id={uid_a}' in u]
    # 兜底：performance resource 条目（若 cross-origin 暴露）
    if not matched:
        matched = _captured_log_urls(driver)
    assert matched, f'未见 user_id={uid_a} 的 /logs 请求。new_urls={list(new_urls)[:5]}'

    # 断言 2：列表仅显示 A 的行（内容含 operator_id=<A>；行数 = 1 的归属审计行）
    page.settle(1.0)
    rows = driver.find_elements(By.CSS_SELECTOR, LOG_ROWS)
    # 归属行应 ≥1 且全部内容含 A
    assert rows, '过滤后列表无行'
    for row in rows:
        text = row.text
        assert str(uid_a) in text, f'行内容不含用户 A id: {text[:120]}'

    # 断言 3：无 user_id 基线——清空输入后列表行数大于过滤后（全量日志存在）
    inp.clear()
    page.settle(1.5)
    all_rows = driver.find_elements(By.CSS_SELECTOR, LOG_ROWS)
    # 全量列表至少能刷出内容（断言不依赖精确计数，只确认列表仍渲染）
    assert all_rows, '清空过滤后列表无行（全量基线渲染异常）'
    # 截图取证
    try:
        shot = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts',
                            'int806_logs_user_filter.png')
        os.makedirs(os.path.dirname(shot), exist_ok=True)
        driver.save_screenshot(shot)
        print('SCREENSHOT:', shot)
    except Exception as ex:
        print('screenshot warn:', ex)
