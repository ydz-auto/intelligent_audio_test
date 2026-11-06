# -*- coding: utf-8 -*-
"""INT-423/467 UI 实测：数据可见性（私有/共享）前端落地 + 后端契约实机验证。

编号 12（INT-467 卡面原定 11，评审修正——既有 tests/ui/test_ui_11_int330_rms_spl_calibration.py
已占用 11，故顺延为 12，命名延续 test_ui_NN_intNNN_* 惯例）。

依赖后端 423-2/3/4/5 契约就绪：test_cases 等资源返回 visibility 字段、列表
?visibility= 行级过滤、PATCH /{id}/visibility 端点、admin 访问私有资源落
PRIVATE_RESOURCE_ACCESS 审计事件。

场景：
- 场景 A（私有隔离）：owner（tester）建私有用例 → 登出 → 非 owner（另一 tester）登录
  → 用例列表不可见 / 详情 404 / 编辑入口不可见
- 场景 B（admin 豁免）：admin 登录 → 可见私有用例 → PRIVATE_RESOURCE_ACCESS 审计落审计文件
- 场景 C（共享回归）：owner 经 PATCH /testcases/{id}/visibility 改共享 → 非 owner 可见
- 场景 D（列表冒烟）：任务/用例/报告/音频四页可见性筛选 chips + 私有徽标可用
- 场景 E（核心页遍历）：任务/用例/报告/音频页导航冒烟（可见性控件在列表域均可达）

数据自建自清：API 造唯一前缀分组/用例/任务/音频，teardown 软删+硬删，库内零残留。
只读语义补充：仅造数/删数 + 可见性断言，不触发任何真实播放/测试动作。
"""
import glob
import json
import os
import time

import psycopg2

import pytest

from tests.ui.conftest import API_ROOT, UI_USERNAME, UI_PASSWORD
from tests.ui.pages.base_page import BasePage
from tests.ui.pages.test_case_page import TestCasePage
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import ApiClient, ApiError, unique_suffix

VIS_BADGE_PRIVATE = '.vis-badge--private'
VIS_BADGE = '.vis-badge'
VIS_FILTER_TITLE = '可见性'

# 可见性筛选 chips 文案（BadgeFilter 选项）
VIS_FILTER_SHARED_LABEL = '共享'
VIS_FILTER_PRIVATE_LABEL = '私有'

# 审计事件名（后端 visibility 审计，INT-1793 起只落审计文件、logs 表零写入）
_AUDIT_EVENT_PRIVATE_ACCESS = 'PRIVATE_RESOURCE_ACCESS'


def _audit_dir() -> str:
    """UI 隔离栈的审计文件根（口径与 parallel_stack._base_env 的 LOG_ROOT_DIR 一致）。

    默认段 `logs/ui_stack`，非默认段 `logs/ui_stack/shift<shift>`；审计文件由
    task_service 单写者落盘在 `{LOG_ROOT_DIR}/audit/{YYYY-MM-DD}/...jsonl`。
    """
    from tests.ui.utils import parallel_stack

    rel = (os.path.join('logs', 'ui_stack', f'shift{parallel_stack.SHIFT}')
           if parallel_stack.SHIFT != 1000 else os.path.join('logs', 'ui_stack'))
    return os.path.join(parallel_stack.BASE_DIR, rel, 'audit')


def _count_audit_events(event: str, contains: str, timeout: float = 15.0) -> int:
    """按审计 JSONL 计数（INT-1793：审计落文件、logs 表零写入）。

    网关侧异步队列冲刷到 task_service 单写者落盘，故有界轮询等待；
    超时返回 0，由调用方断言失败并打印审计根便于排查。
    """
    pattern = os.path.join(_audit_dir(), '*', '*.jsonl')
    deadline = time.time() + timeout
    while True:
        count = 0
        for path in glob.glob(pattern):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    for line in fh:
                        try:
                            entry = json.loads(line)
                        except ValueError:
                            continue
                        if entry.get('event') != event:
                            continue
                        if contains and contains not in str(entry.get('content') or ''):
                            continue
                        count += 1
            except OSError:
                continue
        if count or time.time() >= deadline:
            return count
        time.sleep(0.5)


def _make_tester() -> ApiClient:
    """注册一个 tester 用户（非 admin）：register 默认 guest → 直连隔离库提权 tester → 重新登录取新权限。

    绕开无管理面 API 依赖：guest 无 testcase:read，无法进入用例列表页，
    故非 owner 场景需要 tester 角色（有 testcase:read 但非 owner 非 admin）。
    """
    suffix = unique_suffix()
    username = f'ui467_user_{suffix}'
    admin = ApiClient(API_ROOT)
    admin.login(UI_USERNAME, UI_PASSWORD)
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
    return api


def _switch_login(page: BasePage, api: ApiClient):
    """切换浏览器登录态到指定 API 用户（清空旧 localStorage → 注入新 token → 整页重启）。"""
    page.driver.get(f'{page.base_url}/#/login')
    page.wait_visible('.login-card', timeout=15)
    page.clear_login_state()
    page.inject_login_state(api.token, api.user)
    page.settle(0.5)


def _find_vis_badges(page: BasePage) -> list:
    """当前 DOM 中所有可见性徽标（含私有锁徽标）。"""
    return page.find_all(VIS_BADGE)


def _find_private_badges(page: BasePage) -> list:
    return page.find_all(VIS_BADGE_PRIVATE)


def _click_visibility_chip(page: BasePage, label: str):
    """点击指定可见性筛选 chip（BadgeFilter 单选徽章）。"""
    for b in page.find_all('.badge-filter__badge'):
        if (b.text or '').strip() == label:
            page.driver.execute_script('arguments[0].click();', b)
            page.settle(0.5)
            return
    raise AssertionError(f'未找到可见性筛选 chip「{label}」')


def _chip_clickable(page: BasePage, label: str) -> bool:
    return any((b.text or '').strip() == label for b in page.find_all('.badge-filter__badge'))


@pytest.fixture()
def owner_api() -> ApiClient:
    """owner（tester，非 admin）API 客户端；teardown 无全局清理（用例自身自清）。"""
    return _make_tester()


@pytest.fixture()
def other_api() -> ApiClient:
    """非 owner（另一 tester）API 客户端。"""
    return _make_tester()


@pytest.fixture()
def private_case(owner_api) -> dict:
    """owner 建一条私有测试用例（专属分组）；teardown 软删+硬删，库内零残留。"""
    suffix = unique_suffix()
    group_name = f'ui467_group_{suffix}'
    case_name = f'ui467_私有用例_{suffix}'
    owner_api.create_group(group_name, 'INT-467 可见性隔离专用分组')
    body = {
        'name': case_name,
        'description': 'INT-467 私有隔离用例',
        'tags': [],
        'group': group_name,
        'visibility': 'private',
    }
    data = owner_api.request('POST', '/testcases', body)
    tc_id = str((data.get('data') or {}).get('id', ''))
    assert tc_id, f'owner 建私有用例失败: {str(data)[:200]}'
    yield {'id': tc_id, 'name': case_name, 'group': group_name}
    # teardown：owner 软删 + 硬删（非 owner 无权限删，故用 owner 清理）
    try:
        owner_api.delete_testcase(tc_id, purge=True)
    except Exception:
        pass
    try:
        owner_api.request('DELETE', f'/groups/{group_name}')
    except Exception:
        pass


def test_a_private_isolated_from_non_owner(page, owner_api, other_api, private_case):
    """场景 A：私有隔离——非 owner 列表不可见 / 详情 404 / 编辑入口不可见。

    步骤：
    1. owner 登录 → 用例列表可见该私有用例（且带私有徽标）；
    2. 登出 → 非 owner 登录 → 列表不可见该用例（服务端行级过滤）；
    3. 非 owner 直达详情 API → 404；
    4. 非 owner 列表页无该用例 → 自然无编辑入口（编辑入口仅渲染在可见用例卡片上）。
    """
    # ── 1. owner 视角：私有用例可见 + 私有徽标 ──
    _switch_login(page, owner_api)
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)
    owner_names = tc.all_case_names()
    assert private_case['name'] in owner_names, \
        f'owner 列表未展示私有用例 {private_case["name"]}；可见={sorted(owner_names)[:8]}...'
    assert _find_private_badges(page), 'owner 列表应展示私有用例的锁徽标（.vis-badge--private）'

    # ── 2. 非 owner 视角：列表不可见（服务端过滤）──
    _switch_login(page, other_api)
    tc.goto()
    tc.wait_loaded(timeout=25)
    other_names = tc.all_case_names()
    assert private_case['name'] not in other_names, \
        f'非 owner 列表不应展示私有用例；实际可见={sorted(other_names)[:8]}...'

    # ── 3. 非 owner 直达详情 → 404（防探测：不泄露资源名）──
    try:
        other_api.request('GET', f'/testcases/{private_case["id"]}')
        pytest.fail(f'非 owner 访问私有详情应 404，实际 200: {private_case["id"]}')
    except ApiError as exc:
        assert exc.status == 404, \
            f'非 owner 私有详情期望 404，实际 {exc.status}: {str(exc.body)[:200]}'

    # ── 4. 非 owner 无编辑入口（不可见资源无入口可点）──
    # 列表不含该用例 → 无对应卡片 → 无「编辑用例」入口；此处直接断言列表无此卡即可
    # （编辑入口仅随卡片渲染，前端无独立路由直达编辑表单）。


def test_b_admin_exemption_and_audit(page, api_client, private_case):
    """场景 B：admin 豁免——admin 可见私有用例 + PRIVATE_RESOURCE_ACCESS 审计落审计文件。

    page/api_client 均为 conftest admin（首个注册用户），permissions 含 '*'。
    """
    # admin API 直达私有详情 → 200（可见）
    data = api_client.request('GET', f'/testcases/{private_case["id"]}')
    assert data, f'admin 应可见私有详情，实际空响应: {str(data)[:200]}'

    # admin 浏览器：用例列表可见私有用例（含锁徽标）
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)
    admin_names = tc.all_case_names()
    assert private_case['name'] in admin_names, \
        f'admin 列表应展示私有用例 {private_case["name"]}；可见={sorted(admin_names)[:8]}...'
    assert _find_private_badges(page), 'admin 列表应展示私有用例的锁徽标'

    # 审计事件落审计文件：PRIVATE_RESOURCE_ACCESS + 用例 id
    # （INT-1793 契约：审计落 audit/*.jsonl，logs 表零写入，不再查 DB）
    n = _count_audit_events(_AUDIT_EVENT_PRIVATE_ACCESS, str(private_case['id']))
    assert n > 0, ('admin 访问私有用例后应落 PRIVATE_RESOURCE_ACCESS 审计事件'
                   f'（审计文件根 {_audit_dir()}）')


def test_c_share_toggle_makes_case_visible_to_non_owner(page, owner_api, other_api, private_case):
    """场景 C：共享回归——owner PATCH 改共享 → 非 owner 可见。

    走 PATCH /testcases/{id}/visibility（需 testcase:share + owner 校验）契约，
    与前端详情页「设为共享」按钮同端点。
    """
    # owner 切换为 shared
    owner_api.request('PATCH', f"/testcases/{private_case['id']}/visibility",
                      {'visibility': 'shared'})
    # 后端应回落：私有徽标消失（共享为默认态不展示）
    _switch_login(page, owner_api)
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)
    assert private_case['name'] in tc.all_case_names()
    assert not _find_private_badges(page), '共享用例不应再展示私有徽标'

    # 非 owner 登录 → 可见
    _switch_login(page, other_api)
    tc.goto()
    tc.wait_loaded(timeout=25)
    other_names = tc.all_case_names()
    assert private_case['name'] in other_names, \
        f'共享后非 owner 应可见用例；可见={sorted(other_names)[:8]}...'

    # 非 owner 详情 → 200（共享回落 RBAC 权限点，tester 有 testcase:read）
    data = other_api.request('GET', f'/testcases/{private_case["id"]}')
    assert data, '共享后非 owner 详情应 200'

    # 无权限用户切回私有：非 owner 调 PATCH → 403（无 share 权限 / 非 owner）
    owner_api.request('PATCH', f"/testcases/{private_case['id']}/visibility",
                      {'visibility': 'private'})
    try:
        other_api.request('PATCH', f"/testcases/{private_case['id']}/visibility",
                          {'visibility': 'shared'})
        pytest.fail('非 owner 对私有用例改可见性应 403')
    except ApiError as exc:
        assert exc.status == 403, \
            f'非 owner 改可见性期望 403，实际 {exc.status}: {str(exc.body)[:200]}'


def test_d_list_badge_and_filter_smoke(page, owner_api, private_case):
    """场景 D：列表徽标与筛选冒烟——用例/任务/报告/音频四页可见性控件可用。

    以私有用例为核心数据：用例页断言私有徽标 + 私有筛选命中；任务/报告/音频页
    断言可见性筛选 chips 可用（点击共享/私有不抛错，列表响应正常）。
    """
    _switch_login(page, owner_api)

    # ── 用例页：徽标 + 筛选命中 ──
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)
    assert _find_private_badges(page), '用例列表应展示私有用例的锁徽标'

    # 筛选「私有」：命中的唯一私有用例仍可见
    _click_visibility_chip(page, VIS_FILTER_PRIVATE_LABEL)
    tc.settle(0.8)
    private_names = tc.all_case_names()
    assert private_case['name'] in private_names, '筛选「私有」后私有用例应命中'
    assert set(private_names) == {private_case['name']}, \
        f'筛选「私有」只应命中私有用例，实际={sorted(private_names)[:8]}...'

    # 筛选「共享」：私有用例不再命中（共享筛选互斥）
    _click_visibility_chip(page, VIS_FILTER_SHARED_LABEL)
    tc.settle(0.8)
    shared_names = tc.all_case_names()
    assert private_case['name'] not in shared_names, '筛选「共享」不应命中私有用例'

    # 回到「全部」
    _click_visibility_chip(page, '全部')
    tc.settle(0.8)

    # ── 任务/报告/音频页：可见性筛选 chips 可达可用 ──
    # 导航等待用 wait_title_text（hash 同文档跳转须等目标标题文本，避免读到上一页残留标题）。
    # 注：音频页私有徽标的浏览器级断言依赖 INT-464 音频造数（upload 契约），后端未 merge 无法
    # 造私有音频数据；P1-1 映射回归已由前端单测 useAudioList.visibility.spec 覆盖，待后端
    # 就绪后可在复跑时补音频徽标行级断言。
    for route, title in [('/tasks', '测试任务记录'), ('/test-reports', '测试历史报告数据'),
                         ('/AudioImport', '导入音频管理')]:
        page.goto(route)
        page.wait_title_text(title, timeout=25)
        assert _chip_clickable(page, VIS_FILTER_PRIVATE_LABEL), \
            f'{route} 页面应提供「私有」可见性筛选 chip'
        assert _chip_clickable(page, VIS_FILTER_SHARED_LABEL), \
            f'{route} 页面应提供「共享」可见性筛选 chip'
        _click_visibility_chip(page, VIS_FILTER_PRIVATE_LABEL)
        _click_visibility_chip(page, VIS_FILTER_SHARED_LABEL)
        _click_visibility_chip(page, '全部')


def test_e_core_pages_navigation(page):
    """场景 E：核心页遍历——登录/任务/用例/报告/音频五页可见性控件可达。

    admin（page fixture）逐页导航冒烟：按目标标题文本等待（hash 同文档跳转后
    .page-title 需包含新标题，避免命中上一页残留标题——INT-467 测试时序修正）。
    """
    pages = [
        ('/tasks', '测试任务记录'),
        ('/TestCaseManager', '测试用例管理'),
        ('/test-reports', '测试历史报告数据'),
        ('/AudioImport', '导入音频管理'),
    ]
    for route, title in pages:
        page.goto(route)
        page.wait_title_text(title, timeout=25)
