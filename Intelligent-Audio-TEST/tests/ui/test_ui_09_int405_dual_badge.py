# -*- coding: utf-8 -*-
"""INT-405 UI 实测：任务列表/详情双徽章可见且随状态刷新（验收标准 4）。

废弃前端单值合成状态后，执行状态与评估状态两维独立展示（双徽章），
口径对齐 INT-301（utils/taskStatusBadge 单一源 + §8.2/§8.3 文案映射）。

三条路径：
1. 可见性——任务卡片（列表页，INT-301 基线）与详情用例行（INT-405 改造点）
   各自渲染执行徽章 + 评估徽章（维度 title 正确、文案非空）；
2. 独立性判别——直写用例双状态 A=(completed,calculating)、B=(running,pending)
   后重开详情：A 行必须同时显示「已完成 + 计算中」两个徽章（旧合成口径只出
   一个混合标签「计算中」，执行侧信息丢失——本断言即 INT-405 判别点），
   B 行「执行中 + 待评估」；徽章随 DB 状态刷新（重开=重新拉取）；
3. 展示即筛选——执行/评估两维下拉与行内徽章同源：筛「执行中」只命中执行中
   的行、筛「计算中」只命中评估计算中的行，且命中行徽章文案 == 筛选项
   （对齐 INT-301 F1 展示与筛选口径严格一致）。

状态漂移防护：新建任务会被引擎自动调度（test_ui_06 实证），fixture 先 stop
并等任务收敛到终态再直写双状态；断言轮询「UI == 详情接口两维原值」并在
失败时重写+重开一次（引擎终态后不再写用例行，重试即排除时序巧合）。

测试数据自建自清（API 造任务+用例 → 停任务 → 直写状态 → teardown 删任务 +
purge 用例 + 标签/分组回收，test_ui_05/06 同口径）。
"""
import time

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from tests.ui.pages.base_page import BasePage
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'
DETAIL_BTN_TITLE = '查看详情'
DETAIL_ROOT = '.task-detail-modal'
CASE_ROW = '.progress-item-small'
CASE_NAME = '.progress-name'
EXEC_BADGE = '.exec-status-badge'
EVAL_BADGE = '.eval-status-badge'

# 徽章文案口径（与 frontend domain 映射严格一致）：
# 执行 = getTaskStatusLabel（§8.2），评估 = getCaseEvaluationStatusText（§8.3）
EXEC_LABELS = {
    'pending': '待执行',
    'queued': '排队中',
    'running': '执行中',
    'completed': '已完成',
    'stopped': '已停止',
    'failed': '执行失败',
}
EVAL_LABELS = {
    'pending': '待评估',
    'queued': '待评估',
    'running': '评估中',
    'calculating': '计算中',
    'completed': '已完成',
    'stopped': '已停止',
    'failed': '评估失败',
}
# 评估域独有文案：绝不允许出现在执行徽章（出现即两维串了）
EVAL_ONLY_LABELS = {'待评估', '评估中', '计算中', '评估失败'}

TASK_TERMINAL_STATUSES = ('completed', 'failed', 'stopped', 'skipped')


def _create_task_with_cases(api_client, n_cases: int):
    """API 造 n 个用例 + 1 个关联任务（新建态）。Returns (task_id, case_ids, handles)。"""
    suffix = unique_suffix()
    tag_name = f'ui405_tag_{suffix}'
    group_name = f'ui405_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-405 双徽章实测专用分组')
    assert group_id, 'API 造分组失败'
    case_ids = []
    for i in range(n_cases):
        tc_id = api_client.create_testcase(
            f'ui405_用例{i + 1}_{suffix}', group=group_name, tags=[tag_name],
            description='INT-405 双徽章实测用例')
        assert tc_id, f'API 造用例 {i + 1} 失败'
        case_ids.append(tc_id)
    task_name = f'ui405_任务_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': task_name,
        'type': 'e2e',
        'description': 'INT-405 双徽章实测任务',
        'caseIds': case_ids,
    })
    task = data.get('data') or {}
    task_id = task.get('id')
    assert task_id, f'API 造任务失败: {str(data)[:200]}'
    return str(task_id), case_ids, {'tag': tag_name, 'group': group_name,
                                    'group_id': group_id, 'case_ids': case_ids,
                                    'task_name': task_name, 'suffix': suffix}


def _cleanup_task_and_cases(api_client, task_id, handles):
    """任务软删 → 彻底删除 → 用例 purge → 标签/分组回收（test_ui_06 同口径）。"""
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
        try:
            api_client.delete_testcase(tc_id)
        except Exception:
            pass
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


def _quiesce_task(api_client, task_id: str, timeout: float = 45):
    """stop 新建任务并等其收敛终态，消掉引擎自动调度对直写状态的漂移。

    best-effort：pending 未被调度时 stop 可能失败/无效果，任务不在执行中即视为
    静默（后续断言仍按 UI==接口 同源比对，不会被两侧互搏误报）。
    """
    try:
        api_client.request('POST', f'/tasks/{task_id}/stop')
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = api_client.request('GET', f'/tasks/{task_id}').get('data') or {}
            if str(data.get('status')) in TASK_TERMINAL_STATUSES or \
               str(data.get('status')) == 'pending':
                # pending=从未被调度（不会再有进度推送）；终态=执行已结束
                time.sleep(1.0)
                return
        except Exception:
            pass
        time.sleep(1.0)


def _set_case_dual_status(task_id: str, case_id: str, execution_status: str,
                          evaluation_status: str, status: str):
    """隔离库直写用例双状态（模拟后端派生落值；teardown 随任务清理，零残留）。"""
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE task_case_relations '
                'SET execution_status=%s, evaluation_status=%s, status=%s '
                'WHERE task_id=%s AND test_case_id=%s',
                (execution_status, evaluation_status, status, int(task_id), case_id))
        conn.commit()
    finally:
        conn.close()


def _close_open_modals(page: BasePage):
    """SPA hash 导航不重载应用、详情模态窗常驻：逐个关闭防叠加污染行计数。"""
    for _ in range(5):
        overlays = [o for o in page.find_all('.modal-overlay') if o.is_displayed()]
        if not overlays:
            break
        close_btns = [c for c in overlays[-1].find_elements(By.CSS_SELECTOR, '.modal-close')
                      if c.is_displayed()]
        if close_btns:
            page.driver.execute_script('arguments[0].click();', close_btns[-1])
        else:
            break
        page.settle(0.3)


def _find_task_card(page: BasePage, task_name: str, timeout: float = 25):
    """列表页（日常页签）按搜索框过滤后找任务卡片。"""
    page.goto(TASKS_ROUTE)
    page.wait_visible('.filter-sort-section input.search-input', timeout=timeout)
    page.fill('.filter-sort-section input.search-input', task_name, timeout=timeout)
    page.settle(1.0)
    for card in page.find_all('.task-card'):
        if not card.is_displayed():
            continue
        title = card.find_elements(By.CSS_SELECTOR, '.task-title')
        if title and task_name in (title[0].text or ''):
            return card
    return None


def _open_task_detail_modal(page: BasePage, task_name: str):
    """任务列表点卡片「查看详情」→ 等详情用例行就绪。"""
    _close_open_modals(page)
    card = _find_task_card(page, task_name)
    assert card is not None, f'列表未出现任务卡片: {task_name}'
    cand = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
            if b.is_displayed() and b.get_attribute('title') == DETAIL_BTN_TITLE]
    assert cand, f'任务卡片缺「查看详情」按钮: {task_name}'
    page.driver.execute_script('arguments[0].click();', cand[0])
    page.wait_visible(DETAIL_ROOT, timeout=20)
    deadline = time.time() + 20
    while time.time() < deadline:
        if _visible_rows(page):
            break
        time.sleep(0.3)
    else:
        raise AssertionError('详情模态窗用例行未加载（20s）')
    page.settle(0.5)


def _visible_rows(page: BasePage):
    return [r for r in page.find_all(f'{DETAIL_ROOT} {CASE_ROW}') if r.is_displayed()]


def _row_case_name(row) -> str:
    """textContent 而非 .text：虚列表 translateY 容器内首行 .text 读空（test_ui_06 实证）。"""
    name_el = row.find_elements(By.CSS_SELECTOR, CASE_NAME)
    return (name_el[0].get_attribute('textContent') or '').strip() if name_el else ''


def _row_badges(row):
    """行内 (执行徽章元素, 评估徽章元素)。"""
    execs = row.find_elements(By.CSS_SELECTOR, EXEC_BADGE)
    evals = row.find_elements(By.CSS_SELECTOR, EVAL_BADGE)
    return (execs[0] if execs else None, evals[0] if evals else None)


def _badge_text(el) -> str:
    return (el.get_attribute('textContent') or '').strip() if el is not None else ''


def _rows_as_badge_map(page: BasePage) -> dict:
    """用例名 → (执行徽章文案, 评估徽章文案)。"""
    out = {}
    for r in _visible_rows(page):
        exec_el, eval_el = _row_badges(r)
        out[_row_case_name(r)] = (_badge_text(exec_el), _badge_text(eval_el))
    return out


def _write_two_cases_dual_status(task_id, case_a, case_b):
    """A=(completed, calculating→status evaluating)、B=(running, pending→running)。

    status 取后端 derive_task_case_status 对这两组两维的派生值，保持三字段自洽。
    """
    _set_case_dual_status(task_id, case_a, 'completed', 'calculating', 'evaluating')
    _set_case_dual_status(task_id, case_b, 'running', 'pending', 'running')


@pytest.fixture()
def int405_task(api_client):
    task_id, case_ids, handles = _create_task_with_cases(api_client, n_cases=2)
    _quiesce_task(api_client, task_id)
    yield {'task_id': task_id, 'case_ids': case_ids, 'name': handles['task_name'], **handles}
    _cleanup_task_and_cases(api_client, task_id, handles)


def test_list_and_detail_rows_render_dual_badges(page, int405_task):
    """路径 1：列表卡片与详情用例行均渲染执行+评估双徽章（title 维度正确、文案非空）。"""
    card = _find_task_card(page, int405_task['name'])
    assert card is not None, '列表未出现新建任务卡片'
    exec_badges = card.find_elements(By.CSS_SELECTOR, EXEC_BADGE)
    eval_badges = card.find_elements(By.CSS_SELECTOR, EVAL_BADGE)
    assert len(exec_badges) >= 1, '任务卡片缺执行徽章（INT-301 基线回归）'
    assert len(eval_badges) >= 1, '任务卡片缺评估徽章（INT-301 基线回归）'

    _open_task_detail_modal(page, int405_task['name'])
    rows = _visible_rows(page)
    assert len(rows) == 2, f'详情应有 2 行用例: {len(rows)}'
    for r in rows:
        name = _row_case_name(r)
        exec_el, eval_el = _row_badges(r)
        assert exec_el is not None, f'{name} 行缺执行徽章'
        assert eval_el is not None, f'{name} 行缺评估徽章'
        assert exec_el.get_attribute('title') == '执行状态'
        assert eval_el.get_attribute('title') == '评估状态'
        exec_text, eval_text = _badge_text(exec_el), _badge_text(eval_el)
        assert exec_text and eval_text, f'{name} 行徽章文案为空: {exec_text!r}/{eval_text!r}'
        assert exec_text not in EVAL_ONLY_LABELS, \
            f'{name} 行执行徽章串入评估域文案（双维未独立）: {exec_text!r}'


def test_badges_independent_and_refresh_with_state(page, int405_task):
    """路径 2（判别点）：直写 A=(completed,calculating)、B=(running,pending) 后，
    A 行同时显示「已完成 + 计算中」两个徽章——旧单值合成口径下一行只有一个
    混合标签（该组合会合成成「计算中」，执行侧「已完成」丢失），双徽章齐备
    且文案与两维一一对应即证明合成已废弃、徽章随状态刷新（重开=重新拉取）。"""
    case_a, case_b = int405_task['case_ids'][0], int405_task['case_ids'][1]
    suffix = int405_task['suffix']
    # 判别组合：执行维完成 + 评估维计算中（旧合成口径 → 单标签「计算中」）
    want_a = (EXEC_LABELS['completed'], EVAL_LABELS['calculating'])
    want_b = (EXEC_LABELS['running'], EVAL_LABELS['pending'])

    row_a = row_b = None
    deadline = time.time() + 12
    while time.time() < deadline:
        _write_two_cases_dual_status(int405_task['task_id'], case_a, case_b)
        _open_task_detail_modal(page, int405_task['name'])
        rendered = _rows_as_badge_map(page)
        row_a = next((v for k, v in rendered.items() if f'用例1_{suffix}' in k), None)
        row_b = next((v for k, v in rendered.items() if f'用例2_{suffix}' in k), None)
        if row_a == want_a and row_b == want_b:
            break
        time.sleep(0.6)

    assert row_a == want_a, \
        f'A 行应双徽章独立展示（{want_a[0]} + {want_a[1]}），实际 {row_a}——单标签即合成口径残留'
    assert row_b == want_b, f'B 行应「{want_b[0]} + {want_b[1]}」，实际 {row_b}'


def test_case_filters_are_dimension_aligned_with_badges(page, int405_task):
    """路径 3：执行/评估两维筛选与行内徽章同源——筛「执行中」只命中执行中的行、
    筛「计算中」只命中评估计算中的行，且命中行对应侧徽章文案 == 筛选项。"""
    case_a, case_b = int405_task['case_ids'][0], int405_task['case_ids'][1]
    _write_two_cases_dual_status(int405_task['task_id'], case_a, case_b)

    _open_task_detail_modal(page, int405_task['name'])
    selects = [s for s in page.find_all(f'{DETAIL_ROOT} select.form-input') if s.is_displayed()]
    assert len(selects) == 2, f'应为执行/评估两个筛选下拉: {len(selects)}'
    exec_sel, eval_sel = Select(selects[0]), Select(selects[1])

    # 执行维下拉不混入评估域独有选项（两维选项各自取自本维枚举）
    exec_options = [o.text for o in exec_sel.options]
    assert all('全部' in t or t not in EVAL_ONLY_LABELS for t in exec_options), \
        f'执行筛选混入评估域选项: {exec_options}'

    assert len(_rows_as_badge_map(page)) == 2, '初始应为 2 行'

    # 执行维筛「执行中」→ 仅 B 行，且命中行执行徽章 == 「执行中」
    exec_sel.select_by_visible_text('执行中')
    page.settle(0.6)
    only = _rows_as_badge_map(page)
    assert len(only) >= 1 and all('用例2' in k for k in only), \
        f'筛「执行中」应仅命中 B 行: {list(only)}'
    assert all(v[0] == '执行中' for v in only.values()), f'命中行执行徽章 != 筛选值: {only}'

    # 还原执行维，评估维筛「计算中」→ 仅 A 行，且命中行评估徽章 == 「计算中」
    exec_sel.select_by_value('all')
    page.settle(0.4)
    eval_sel.select_by_visible_text('计算中')
    page.settle(0.6)
    only = _rows_as_badge_map(page)
    assert len(only) >= 1 and all('用例1' in k for k in only), \
        f'筛「计算中」应仅命中 A 行: {list(only)}'
    assert all(v[1] == '计算中' for v in only.values()), f'命中行评估徽章 != 筛选值: {only}'
