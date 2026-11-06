# -*- coding: utf-8 -*-
"""INT-553 挑选向导 P3 批次 UI 实测（真实浏览器走查主流程，断言可见状态）。

覆盖卡面 4 项验收（INT-401 前端UX审计 P3 批次）：
- P3-1 筛选变更重置分页：挑选页翻到非首页后切换设备筛选 → 回到第 1 页且列表非空
  （原仅 taskId 重置分页，非首页切筛选会落到「第 N 页 / 0 条」）
- P3-2 步骤条不可跳步：挑选态点「下单」步骤不跳转且该步 locked 视觉反馈；
  顺序前进「购物车」可达；空购物车时「下单」步骤亦 locked
- P3-3 merge 出口名称空值提交禁用：checkout 态名称空值「提交下单」禁用，
  输入后可用；reexecute 出口名称空值仍可提交（名称可选）
- P3-4 legacy 状态挑选入口一致性：completed 任务详情「加入购物车」可见；
  后端历史遗留 'finished' 任务详情无该按钮（入口可见性与门控同源）

数据卫生：自建自清（API 造任务/用例/分组 → 隔离库直写状态与 test_results 行
→ teardown 物理删 test_results/设备行 + API 删任务 purge 用例回收标签分组），
验收完成后隔离库不留本卡测试残留。
"""
import time

import psycopg2
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'
# 任务卡片 → 详情模态窗
PICK_BTN = '.task-detail-modal .step-actions button.btn-info'
# 挑选向导（CherryPickDialog）
CP_STEPS = '.cp-steps .cp-step'
CP_PAGINATION = '.cp-pagination'
CP_PAGINATION_SPAN = '.cp-pagination span'
CP_ROW = '.cp-list .cp-row'
CP_CHECKBOX = '.cp-list .cp-checkbox'
CP_FILTER_SELECTS = '.cp-filters select'
CP_FOOTER_PRIMARY = '.cp-footer .cp-btn-primary'
MERGE_NAME_INPUT = 'input[placeholder="新任务名称（必填）"]'
REEXECUTE_CARD = '.cp-checkout-card'
# 现有隔离库设备（int-569 等并行 run 复用的隔离库基线；本测试新增的设备 B 自清）
EXISTING_DEVICE_ID = 21


def _db_url() -> str:
    return bootstrap.isolated_db_url()


def _db_exec(sql, params=()):
    conn = psycopg2.connect(_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row_id = None
            if cur.description:
                rows = cur.fetchall()
                if rows:
                    row_id = rows[0][0]
        conn.commit()
        return row_id
    finally:
        conn.close()


def _create_task_with_cases(api_client, n_cases: int = 2):
    """API 造 n 个用例 + 1 个关联任务（新建态，status=pending）。"""
    suffix = unique_suffix()
    tag_name = f'ui553_tag_{suffix}'
    group_name = f'ui553_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-553 挑选向导 UI 实测专用分组')
    assert group_id, 'API 造分组失败'
    case_ids = []
    for i in range(n_cases):
        tc_id = api_client.create_testcase(
            f'ui553_用例{i + 1}_{suffix}', group=group_name, tags=[tag_name],
            description='INT-553 挑选向导 P3 批次实测')
        assert tc_id, f'API 造用例 {i + 1} 失败'
        case_ids.append(tc_id)
    task_name = f'ui553_任务_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': task_name,
        'type': 'e2e',
        'description': 'INT-553 挑选向导实测任务',
        'caseIds': case_ids,
    })
    task = data.get('data') or {}
    task_id = task.get('id')
    assert task_id, f'API 造任务失败: {str(data)[:200]}'
    return str(task_id), case_ids, {'tag': tag_name, 'group': group_name,
                                    'group_id': group_id, 'case_ids': case_ids,
                                    'task_name': task_name}


def _seed_second_device() -> int:
    """隔离库直插第二台设备（P3-1 设备筛选目标；唯一 name 便于回收）。"""
    suffix = unique_suffix()
    dev_id = _db_exec(
        "INSERT INTO devices (name, model, type, system, system_version, app_name,"
        " app_version, status, deleted) VALUES (%s,'modelB','phone','HarmonyOS',"
        " '1.0.0','App','1.0.0','online',false) RETURNING id",
        (f'ui553_设备B_{suffix}',))
    assert dev_id, '隔离库直插设备 B 失败'
    return int(dev_id)


def _seed_results(task_id, case_ids, device_b_id):
    """给已完成任务直插 test_results：设备A(现有 21) 30 条 + 设备B 51 条。

    51 条保证未筛选时第 2 页可达；设备B 51 条保证切到设备B 筛选后仍有多页
    （翻到第 2 页后切筛选 → 修复后回第 1 页，修复前停留第 2 页仅 1 条）。
    """
    conn = psycopg2.connect(_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            rows = []
            for _ in range(30):
                rows.append((int(task_id), str(case_ids[0]), EXISTING_DEVICE_ID))
            for _ in range(51):
                rows.append((int(task_id), str(case_ids[1]), int(device_b_id)))
            cur.executemany(
                "INSERT INTO test_results (task_id, test_case_id, device_id,"
                " execution_status, algorithm_type, excluded) VALUES"
                " (%s,%s,%s,'completed','mock',0)", rows)
        conn.commit()
    finally:
        conn.close()


def _cleanup(api_client, task_id, handles, extra_device_id=None):
    """全量回收：test_results/设备行物理删 → 任务软删 purge → 用例 purge → 标签/分组。"""
    if extra_device_id:
        try:
            _db_exec('DELETE FROM test_results WHERE task_id=%s', (int(task_id),))
            _db_exec('DELETE FROM devices WHERE id=%s', (int(extra_device_id),))
        except Exception:
            pass
    try:
        api_client.request('POST', '/tasks/batch-action',
                           {'action': 'delete', 'task_ids': [int(task_id)]})
    except Exception:
        pass
    try:
        api_client.request('DELETE', f'/tasks/{task_id}/purge')
    except Exception:
        pass
    for tc_id in handles.get('case_ids', []):
        api_client.delete_testcase(tc_id)
    try:
        tags = api_client.request('GET', '/tags?page=1&perPage=200&search=' + handles['tag'])
        items = (tags.get('data') or {})
        items = items.get('items') if isinstance(items, dict) else items
        for t in (items or []):
            if t.get('name') == handles['tag']:
                api_client.delete_tag(t.get('id'))
                break
    except Exception:
        pass
    try:
        api_client.delete_group(handles['group_id'])
    except Exception:
        pass


def _clear_cart(api_client):
    """清空当前用户购物车（浏览器用例间隔离；无条目时 DELETE 亦安全）。"""
    try:
        api_client.request('DELETE', '/tasks/cherry-picks/cart/items')
    except Exception:
        pass


@pytest.fixture()
def int553_completed_task(api_client):
    """造 2 用例 1 任务 + 直写 completed + 81 条 test_results（含第二台设备）。"""
    _clear_cart(api_client)
    task_id, case_ids, handles = _create_task_with_cases(api_client, n_cases=2)
    _db_exec("UPDATE test_tasks SET status='completed' WHERE id=%s", (int(task_id),))
    dev_b = _seed_second_device()
    _seed_results(task_id, case_ids, dev_b)
    yield {'task_id': task_id, 'case_ids': case_ids, 'device_b_id': dev_b,
           'name': handles['task_name'], **handles}
    _cleanup(api_client, task_id, handles, extra_device_id=dev_b)


@pytest.fixture()
def int553_legacy_task(api_client):
    """造 1 用例 1 任务 + 直写 legacy 'finished'（P3-4：入口不可见即不可点）。"""
    _clear_cart(api_client)
    task_id, case_ids, handles = _create_task_with_cases(api_client, n_cases=1)
    _db_exec("UPDATE test_tasks SET status='finished' WHERE id=%s", (int(task_id),))
    yield {'task_id': task_id, 'case_ids': case_ids, 'name': handles['task_name'],
           **handles}
    _cleanup(api_client, task_id, handles)


def _open_task_detail(page: BasePage, task_name: str):
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)
    card = None
    for c in page.find_all('.task-card'):
        if not c.is_displayed():
            continue
        name_el = c.find_elements(By.CSS_SELECTOR, '.task-title')
        if name_el and task_name in (name_el[0].text or ''):
            card = c
            break
    assert card is not None, f'列表未出现任务卡片: {task_name}'
    view = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
            if b.is_displayed() and b.get_attribute('title') == '查看详情']
    assert view, f'任务卡片无「查看详情」入口: {task_name}'
    page.driver.execute_script('arguments[0].click();', view[0])
    page.wait_visible('.task-detail-modal', timeout=20)
    page.settle(0.8)


def _open_pick_wizard(page: BasePage, task_name: str):
    """打开任务详情 → 点「加入购物车」→ 挑选向导可见。"""
    _open_task_detail(page, task_name)
    pick = WebDriverWait(page.driver, 15).until(
        lambda d: [b for b in d.find_elements(By.CSS_SELECTOR, PICK_BTN) if b.is_displayed()])
    assert pick, 'completed 任务详情应展示「加入购物车」入口'
    page.driver.execute_script('arguments[0].click();', pick[0])
    page.wait_visible('.cp-dialog', timeout=15)
    page.settle(0.8)


def _cp_step(page: BasePage, label: str):
    steps = page.find_all(CP_STEPS)
    for s in steps:
        if label in (s.text or ''):
            return s
    return None


def _wait_page(page: BasePage, page_no: int, timeout: float = 10):
    WebDriverWait(page.driver, timeout).until(
        lambda d: any(f'第 {page_no} 页' in (s.text or '')
                      for s in d.find_elements(By.CSS_SELECTOR, CP_PAGINATION_SPAN)))
    page.settle(0.3)


def _wait_row_count(page: BasePage, count: int, timeout: float = 10):
    """等候选行数达到预期（INT-985 重交付加固：分页 span 先行更新、行数据异步落地，
    直接等行数避免与筛选请求的响应覆盖竞态）。"""
    WebDriverWait(page.driver, timeout).until(
        lambda d: len(page.find_all(CP_ROW)) == count)


# ── P3-1：筛选变更重置分页 ──────────────────────────────────
def test_p3_1_device_filter_change_resets_to_page1(page, api_client, int553_completed_task):
    """翻到第 2 页后切换设备筛选 → 回到第 1 页且列表非空（原落在「第 2 页 / 0 条」）。"""
    _open_pick_wizard(page, int553_completed_task['name'])

    # 81 条候选 → 分页出现且在第 1 页
    WebDriverWait(page.driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, CP_PAGINATION)))
    assert any('第 1 页' in s.text for s in page.find_all(CP_PAGINATION_SPAN)), \
        '初始应位于第 1 页'
    rows_page1 = len(page.find_all(CP_ROW))
    assert rows_page1 == 50, f'第 1 页应满 50 条：实际 {rows_page1}'

    # 翻到第 2 页（未筛选 81 条 → 第 2 页 31 条）
    next_btn = [b for b in page.find_all(CP_PAGINATION + ' button')
                if b.is_displayed() and '下一页' in (b.text or '')]
    assert next_btn, '分页「下一页」按钮缺失'
    page.driver.execute_script('arguments[0].click();', next_btn[0])
    _wait_page(page, 2)
    # INT-985 重交付加固：第 2 页分页 span 先于响应更新，若在此切筛选，旧第 2 页
    # 响应可能后到并覆盖筛选结果（实测竞态）。先等第 2 页行真实渲染（行数 != 50）
    # 再切筛选，消除与筛选请求的响应竞态。
    WebDriverWait(page.driver, 10).until(
        lambda d: len(page.find_all(CP_ROW)) != 50)
    page.settle(0.3)

    # 切换设备筛选到设备 B（51 条）→ onFilterChange 重置 page=1 后重拉
    selects = page.find_all(CP_FILTER_SELECTS)
    # loadOptions 异步填充设备下拉：等待设备 B 选项出现（含诊断）
    dev_select_el = selects[1]  # 第 2 个下拉 = 设备
    try:
        WebDriverWait(page.driver, 10).until(
            lambda d: len(dev_select_el.find_elements(
                By.CSS_SELECTOR, f'option[value="{int553_completed_task["device_b_id"]}"]')) > 0)
    except Exception:
        cur_opts = [o.get_attribute('value') for o in
                    dev_select_el.find_elements(By.CSS_SELECTOR, 'option')]
        api_devs = []
        db_devs = []
        try:
            r = api_client.request('GET', '/test-devices?per_page=100')
            api_devs = [(d.get('id'), d.get('name')) for d in
                        (r.get('data') or {}).get('items') or []]
        except Exception as exc:
            api_devs = f'API ERR {exc}'
        try:
            conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
            with conn.cursor() as cur:
                cur.execute('SELECT id,name,deleted FROM devices ORDER BY id')
                db_devs = cur.fetchall()
            conn.close()
        except Exception as exc:
            db_devs = f'DB ERR {exc}'
        raise AssertionError(
            f'设备下拉缺 device_b_id={int553_completed_task["device_b_id"]}；'
            f'实际选项 values={cur_opts}；同时刻 API 设备={api_devs}；'
            f'同时刻 DB devices={db_devs}')
    dev_select = Select(dev_select_el)
    dev_select.select_by_value(str(int553_completed_task['device_b_id']))
    _wait_page(page, 1)
    # INT-985 重交付加固：设备筛选结果异步落地，等第 1 页行数达 50 再断言
    # （避免仅等分页 span 而响应未达时误判空列表）。
    _wait_row_count(page, 50)

    rows = page.find_all(CP_ROW)
    assert rows, '切设备筛选后应回到第 1 页且列表非空'
    assert len(rows) == 50, f'设备 B 51 条候选第 1 页应满 50 条：实际 {len(rows)}'


# ── P3-2：步骤条不可跳步 ───────────────────────────────────
def test_p3_2_step_bar_cannot_jump(page, int553_completed_task):
    """挑选态点「下单」不跳转且 locked；顺序前进「购物车」可达；空购物车「下单」locked。"""
    _open_pick_wizard(page, int553_completed_task['name'])

    checkout_step = _cp_step(page, '下单')
    assert checkout_step is not None, '步骤条缺「下单」'
    assert 'locked' in (checkout_step.get_attribute('class') or ''), \
        '挑选态「下单」步骤应带 locked 视觉反馈'

    # 点「下单」→ 仍停留挑选页（步骤条 active 仍在「挑选」）
    page.driver.execute_script('arguments[0].click();', checkout_step)
    page.settle(0.4)
    active = [s for s in page.find_all(CP_STEPS) if 'active' in (s.get_attribute('class') or '')]
    assert active and '挑选' in (active[0].text or ''), '点击 locked「下单」后应仍停留挑选页'

    # 顺序前进一格「购物车」→ 可进（任意位置可后退、最多前进一格）
    cart_step = _cp_step(page, '购物车')
    page.driver.execute_script('arguments[0].click();', cart_step)
    page.settle(0.6)
    active = [s for s in page.find_all(CP_STEPS) if 'active' in (s.get_attribute('class') or '')]
    assert active and '购物车' in (active[0].text or ''), '挑选态应可顺序前进到购物车'

    # 空购物车：购物车态「下单」步骤 locked（与「去下单」同门控）
    checkout_step = _cp_step(page, '下单')
    assert 'locked' in (checkout_step.get_attribute('class') or ''), \
        '空购物车时「下单」步骤应 locked'


# ── P3-3：merge 出口名称空值提交禁用 ───────────────────────
def test_p3_3_merge_empty_name_disables_submit(page, api_client, int553_completed_task):
    """merge 名称空值「提交下单」禁用；输入后可用；reexecute 名称空值仍可提交。"""
    _open_pick_wizard(page, int553_completed_task['name'])
    page.wait_visible(CP_CHECKBOX, timeout=15)

    # 勾选 1 条候选 → 加入购物车 → 购物车步
    first_box = page.find_all(CP_CHECKBOX)[0]
    page.driver.execute_script('arguments[0].click();', first_box)
    page.settle(0.3)
    add_btn = [b for b in page.find_all(CP_FOOTER_PRIMARY) if b.is_displayed()
               and '加入购物车' in (b.text or '')]
    assert add_btn, '勾选后「加入购物车」按钮缺失'
    page.driver.execute_script('arguments[0].click();', add_btn[0])
    page.settle(0.6)
    go_btn = [b for b in page.find_all(CP_FOOTER_PRIMARY) if b.is_displayed()
              and '去下单' in (b.text or '')]
    assert go_btn, '购物车步「去下单」按钮缺失'
    page.driver.execute_script('arguments[0].click();', go_btn[0])
    page.wait_visible('.cp-checkout-card', timeout=15)
    page.settle(0.5)

    # merge 出口默认：名称空值 → 提交禁用
    submit = [b for b in page.find_all(CP_FOOTER_PRIMARY) if b.is_displayed()
              and '提交下单' in (b.text or '')]
    assert submit, 'checkout 步「提交下单」按钮缺失'
    assert not submit[0].is_enabled(), 'merge 名称空值时「提交下单」应禁用'

    # 输入名称 → 可用
    page.fill(MERGE_NAME_INPUT, 'ui553合并任务')
    page.settle(0.3)
    submit = [b for b in page.find_all(CP_FOOTER_PRIMARY) if b.is_displayed()
              and '提交下单' in (b.text or '')]
    assert submit[0].is_enabled(), 'merge 名称非空后「提交下单」应可用'

    # 切 reexecute 出口：名称空值仍可提交（名称可选）
    reex = [c for c in page.find_all(REEXECUTE_CARD) if '重新执行' in (c.text or '')]
    assert reex, 'reexecute 出口卡片缺失'
    page.driver.execute_script('arguments[0].click();', reex[0])
    page.settle(0.4)
    submit = [b for b in page.find_all(CP_FOOTER_PRIMARY) if b.is_displayed()
              and '提交下单' in (b.text or '')]
    assert submit[0].is_enabled(), 'reexecute 出口名称空值应仍可提交（名称可选）'


# ── P3-4：legacy 状态挑选入口一致性 ────────────────────────
def test_p3_4_completed_task_shows_pick_button(page, int553_completed_task):
    """completed 任务详情「加入购物车」按钮可见（挑选入口与门控同源）。"""
    _open_task_detail(page, int553_completed_task['name'])
    pick = WebDriverWait(page.driver, 15).until(
        lambda d: [b for b in d.find_elements(By.CSS_SELECTOR, PICK_BTN) if b.is_displayed()])
    assert pick, 'completed 任务详情应展示「加入购物车」入口'
    assert '加入购物车' in (pick[0].text or '')


def test_p3_4_legacy_finished_task_hides_pick_button(page, int553_legacy_task):
    """legacy 'finished' 任务详情无「加入购物车」（入口不可见即不可点）。"""
    _open_task_detail(page, int553_legacy_task['name'])
    # 等执行详情区渲染完成（任务数据异步返回），再断言入口不可见
    WebDriverWait(page.driver, 15).until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, '.task-detail-modal .step-actions')))
    page.settle(0.3)
    pick = [b for b in page.find_all(PICK_BTN) if b.is_displayed()]
    assert not pick, "legacy 'finished' 任务不应展示「加入购物车」入口（仅 completed/failed/stopped）"
