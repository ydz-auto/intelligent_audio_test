# -*- coding: utf-8 -*-
"""INT-536 UI 实测：数据可见性一致性审计偏差修复（报告/音频/评估三域入口门控 + 评估切换/偏好）。

覆盖卡面验收 D3/D4/D5 的可浏览器实测部分 + D1/D2 在「可见资源即共享」口径下的入口渲染回归：

- 场景 A（D5）：评估维度「新增维度」表单可见性默认值随 localStorage `visibility_pref`
  变化（private/shared/缺省 shared）——纯前端行为，完整可实测；
- 场景 B（D3/D4）：评估维度表操作入口（上移/下移/编辑/测试API/删除）与
  INT-536 新增的「设为共享/设为私有」切换按钮在可见（共享）维度上渲染可用；
- 场景 C（D3 共享口径）：owner 建共享维度 → 非 owner（另一 tester）登录同列表可见
  且操作入口渲染（共享资源回落 RBAC 权限点，canEditResource 恒放行）；
- 场景 D（D1 报告列表）：报告列表对可见报告渲染「编辑/删除」入口（canEditResource
  对共享/无私有标记资源恒放行）——页面渲染回归，确认门控接入未破坏列表。

后端可见性契约（visibility 列 / PATCH /{id}/visibility / 行级 ACL）属 INT-423
（in_progress，不在本卡改动范围）：当前栈测试库各资源列表不返回 visibility，
私有资源场景无法经真实数据触发，门控「私有非 owner 隐藏」状态由前端单测
（INT-536 新增 6 个 spec）直接验证；本文件只做可实测流浏览器走查。

数据自建自清：API 造共享维度，teardown 删除；不落残留。
"""
import time
import uuid

import psycopg2

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from tests.ui.conftest import API_ROOT
from tests.ui.pages.base_page import BasePage
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import ApiClient, unique_suffix

EVAL_ROUTE = '/Evaluation'
EVAL_TITLE = '评估维度管理'
REPORTS_ROUTE = '/test-reports'
REPORTS_TITLE = '测试历史报告数据'

# 新增维度模态框可见性 radio（FormField fieldId = `field-${key}`）
VIS_RADIO_SHARED = '#field-visibility-shared'
VIS_RADIO_PRIVATE = '#field-visibility-private'
MODAL_SCOPE = '.crud-form-modal'
MODAL_CANCEL = '.crud-form-modal .btn-secondary'
TABLE_ROWS = '.data-table tbody tr'


def _make_tester() -> ApiClient:
    """注册一个 tester 用户（非 admin）：register 默认 guest → 直连隔离库提权 tester → 重新登录取新权限。

    用户账号为测试 fixture，teardown 由调用方经 _cleanup_user 删除（测试数据卫生硬规则）。
    """
    suffix = unique_suffix()
    username = f'ui536_user_{suffix}'
    admin = ApiClient(API_ROOT)
    admin.login('admin', 'admin123')
    admin.register(username, 'pass1234')
    api = ApiClient(API_ROOT)
    api.login(username, 'pass1234')
    url = bootstrap.isolated_db_url()
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE users SET role_id = (SELECT id FROM roles WHERE name=%s) '
                'WHERE username=%s', ('tester', username))
        conn.commit()
    finally:
        conn.close()
    api.login(username, 'pass1234')  # 角色变更后重新登录取 tester 权限
    api._ui536_username = username
    return api


def _cleanup_user(api: ApiClient):
    """teardown 直连隔离库物理删除测试用户账号。"""
    username = getattr(api, '_ui536_username', None)
    if not username:
        return
    try:
        conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM users WHERE username=%s', (username,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _switch_login(page: BasePage, api: ApiClient):
    """切换浏览器登录态到指定 API 用户（清空旧 localStorage → 注入新 token → 整页重启）。"""
    page.driver.get(f'{page.base_url}/#/login')
    page.wait_visible('.login-card', timeout=15)
    page.clear_login_state()
    page.inject_login_state(api.token, api.user)
    page.settle(0.5)


def _set_pref(page: BasePage, value: str):
    page.driver.execute_script(f"window.localStorage.setItem('visibility_pref', '{value}');")
    page.settle(0.2)


def _clear_pref(page: BasePage):
    page.driver.execute_script("window.localStorage.removeItem('visibility_pref');")
    page.settle(0.2)


def _go_eval(page: BasePage):
    page.goto(EVAL_ROUTE)
    page.wait_title_text(EVAL_TITLE, timeout=25)
    page.settle(0.5)


def _click_new_dim(page: BasePage):
    """点击 header-right 中文本为「新增维度」的按钮（按文本定位；等 header 按钮稳定渲染）。"""
    page.wait_visible('.header-right button', timeout=15)
    btns = page.find_all('.header-right button')
    for b in btns:
        if '新增维度' in (b.text or ''):
            page.driver.execute_script('arguments[0].click();', b)
            return
    raise AssertionError(f'未找到「新增维度」按钮；header-right 按钮数={len(btns)}，文本={[b.text for b in btns][:6]}')


def _open_new_dim_modal(page: BasePage):
    _click_new_dim(page)
    page.wait_visible(MODAL_SCOPE, timeout=15)


def _radio_checked(page: BasePage, css: str) -> bool:
    el = page.find(css, timeout=10)
    return bool(el.get_attribute('checked'))


def _row_by_text(page: BasePage, text: str):
    for tr in page.find_all(TABLE_ROWS):
        if text in (tr.text or ''):
            return tr
    return None


@pytest.fixture()
def owner_api() -> ApiClient:
    """owner（tester，非 admin）API 客户端；teardown 物理删除账号。"""
    api = _make_tester()
    yield api
    _cleanup_user(api)


@pytest.fixture()
def other_api() -> ApiClient:
    """非 owner（另一 tester）API 客户端；teardown 物理删除账号。"""
    api = _make_tester()
    yield api
    _cleanup_user(api)


@pytest.fixture()
def shared_dim(owner_api) -> dict:
    """owner 建一条共享评估维度；teardown owner 删除，库内零残留。"""
    suffix = unique_suffix()
    name = f'ui536_dim_{suffix}'
    body = {
        'name': name, 'description': 'INT-536 共享维度实测',
        'type': 'auto', 'categoryId': None, 'dimensionType': 'main', 'parentDimensionId': None,
        'apiUrl': '', 'resultType': 1, 'resultMin': 0, 'resultMax': 100, 'decimalPlaces': 2,
        'weight': 5, 'status': True, 'rule': {'rules': [], 'defaultScore': 0}, 'requiredInputs': [],
        'outputFields': [], 'statisticMethod': 'average', 'aggDenominator': 'case', 'excludeRounds': [],
        'apiEndpoints': [], 'associatedAlgorithms': [], 'llmJudgeConfig': {},
    }
    data = owner_api.request('POST', '/evaluation/dimensions', body)
    dim_id = (data.get('data') or {}).get('id')
    assert dim_id, f'owner 建共享维度失败: {str(data)[:200]}'
    yield {'id': dim_id, 'name': name}
    try:
        owner_api.request('DELETE', f'/evaluation/dimensions/{dim_id}')
    except Exception:
        pass
    # 后端维度删除为软删（deleted=True），直连隔离库物理删除防表内残留（测试数据卫生硬规则）
    try:
        conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM dimensions WHERE id=%s', (dim_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def test_a_eval_new_dim_default_follows_pref(page):
    """D5：新增维度表单可见性默认值随 visibility_pref（private/shared/缺省 shared）。"""
    _go_eval(page)

    # pref=private → 新增维度 → radio 默认私有
    _set_pref(page, 'private')
    _open_new_dim_modal(page)
    assert _radio_checked(page, VIS_RADIO_PRIVATE), 'pref=private 时新增维度应默认选中「私有」'
    assert not _radio_checked(page, VIS_RADIO_SHARED), 'pref=private 时「共享」不应选中'
    page.click(MODAL_CANCEL, timeout=10)
    page.wait_gone(MODAL_SCOPE, timeout=10)

    # pref=shared → 新增维度 → radio 默认共享
    _set_pref(page, 'shared')
    _open_new_dim_modal(page)
    assert _radio_checked(page, VIS_RADIO_SHARED), 'pref=shared 时新增维度应默认选中「共享」'
    assert not _radio_checked(page, VIS_RADIO_PRIVATE), 'pref=shared 时「私有」不应选中'
    page.click(MODAL_CANCEL, timeout=10)
    page.wait_gone(MODAL_SCOPE, timeout=10)

    # 缺省（无 pref）→ 默认共享
    _clear_pref(page)
    _open_new_dim_modal(page)
    assert _radio_checked(page, VIS_RADIO_SHARED), '无 pref 时新增维度应默认选中「共享」'
    page.click(MODAL_CANCEL, timeout=10)
    page.wait_gone(MODAL_SCOPE, timeout=10)


def test_b_eval_dim_table_operations_and_toggle_rendered(page):
    """D3/D4：评估维度表操作入口（编辑/删除/上移/下移/测试API）与可见性切换按钮渲染。"""
    _go_eval(page)
    page.wait_visible(TABLE_ROWS, timeout=25)
    row = page.find(TABLE_ROWS, timeout=10)
    text = row.text
    # 操作入口（可见维度回落 canEditResource 恒放行）
    for label in ('编辑', '删除', '上移', '下移', '测试API'):
        assert label in text, f'维度行操作入口缺少「{label}」'
    # INT-536 D4 切换按钮：共享维度显示「设为私有」，私有维度显示「设为共享」
    assert ('设为私有' in text) or ('设为共享' in text), '维度行应提供「设为共享/设为私有」切换入口'
    # 可见性徽标仅私有资源渲染（VisibilityBadge v-if=private）；当前栈后端无 visibility
    # 列，共享/缺省不渲染——私有徽标渲染由前端单测 VisibilityBadge.spec 覆盖，此处不强断言。


def test_c_shared_dim_visible_to_nonowner_with_operations(page, owner_api, other_api, shared_dim):
    """D3 共享口径：非 owner 可见共享维度且操作入口渲染（canEditResource 对共享恒放行）。"""
    # 非 owner 登录 → 列表可见共享维度 + 操作入口
    _switch_login(page, other_api)
    _go_eval(page)
    page.wait_visible(TABLE_ROWS, timeout=25)
    row = _row_by_text(page, shared_dim['name'])
    assert row, f'非 owner 列表应展示共享维度 {shared_dim["name"]}'
    assert '编辑' in row.text and '删除' in row.text, '非 owner 对共享维度应渲染编辑/删除入口（共享回落 RBAC）'

    # owner 登录 → 同样可见可操作
    _switch_login(page, owner_api)
    _go_eval(page)
    page.wait_visible(TABLE_ROWS, timeout=25)
    row = _row_by_text(page, shared_dim['name'])
    assert row, f'owner 列表应展示共享维度 {shared_dim["name"]}'
    assert '编辑' in row.text and '删除' in row.text, 'owner 对共享维度应渲染编辑/删除入口'


def test_d_report_list_operations_rendered_for_visible_reports(page):
    """D1 报告列表：可见报告渲染「编辑/删除」入口（canEditResource 恒放行口径下的页面渲染回归）。"""
    page.goto(REPORTS_ROUTE)
    page.wait_title_text(REPORTS_TITLE, timeout=25)
    # 等待报告卡片渲染（隔离库种子报告；无卡片则跳过后续（当前环境无私有报告数据））
    page.wait_visible('.report-card', timeout=25)
    card = page.find('.report-card', timeout=10)
    # 查看入口恒在；编辑/删除按 canEditResource 渲染（可见报告=共享/无私有标记 → 放行）
    assert '查看报告' in card.text
    assert '删除' in card.text, '可见报告应渲染删除入口（canEditResource 对共享资源放行）'
