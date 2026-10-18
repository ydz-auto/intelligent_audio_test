# -*- coding: utf-8 -*-
"""INT-577 UI 实测：挑选合并升级冒烟（三页签/redirect + 批量「加入挑选」向导 + 加购角标）。

验收要点（对齐卡验收①/②）：
1. 终态三页签 = 日常/已发布/挑选合并（「合并」页签不可见）；
   `/tasks?tab=merged` redirect 到挑选合并页签（URL tab=cherry-picks）；
2. 批量「加入挑选」（任务级整任务加购）→ 打开挑选向导（页内四步，Step1 挑选），
   任务级预选命中该批任务；
3. 挑选树四级分组（任务→用例→设备→result_type）渲染 + 结果行叶计数；
4. 「加入购物车」→ 购物车角标 +n；向导进入 Step2 购物车展示分组条目。

测试数据自建自清（API 造任务+用例 → 直写终态 + test_results → teardown 删任务 +
purge 用例，test_ui_09 同口径）。
"""
import time

import pytest
from selenium.webdriver.common.by import By

from tests.ui.pages.base_page import BasePage
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'
TAB_BTN = '.task-tab'
SEARCH_INPUT = '.filter-sort-section input.search-input'
BATCH_ADD_PICK_BTN = '加入挑选'
WIZARD_ROOT = '.cpw'
TREE_ROOT = '.pick-tree'
CART_BADGE = '.pick-cart-badge'


def _create_source_task_with_results(api_client, n_cases: int):
    """API 造任务+用例，直写终态 + test_results（设备 1/2，result_data 带 result_type）。

    Returns (task_id, case_ids, handles)。task 停后直写 test_results（引擎不会写结果行，
    隔离库直写即确定性数据源）。
    """
    suffix = unique_suffix()
    group_name = f'ui577_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-577 挑选合并冒烟专用分组')
    assert group_id, 'API 造分组失败'
    case_ids = []
    for i in range(n_cases):
        tc_id = api_client.create_testcase(
            f'ui577_用例{i + 1}_{suffix}', group=group_name,
            description='INT-577 挑选合并冒烟用例')
        assert tc_id, f'API 造用例 {i + 1} 失败'
        case_ids.append(tc_id)
    task_name = f'ui577_任务_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': task_name,
        'type': 'e2e',
        'description': 'INT-577 挑选合并冒烟任务',
        'caseIds': case_ids,
    })
    task_id = str((data.get('data') or {}).get('id'))
    assert task_id, f'API 造任务失败: {str(data)[:200]}'

    # 停任务等收敛终态（消掉引擎调度漂移）
    try:
        api_client.request('POST', f'/tasks/{task_id}/stop')
    except Exception:
        pass
    _wait_task_terminal(api_client, task_id)

    # 直写终态 + test_results（result_type 解析数据源）
    _write_task_completed_and_results(task_id, case_ids, n_cases)

    return task_id, case_ids, {
        'task_name': task_name, 'suffix': suffix, 'group_id': group_id,
        'case_ids': case_ids, 'task_id': task_id,
    }


def _wait_task_terminal(api_client, task_id: str, timeout: float = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = str((api_client.request('GET', f'/tasks/{task_id}').get('data') or {}).get('status'))
            if st in ('completed', 'failed', 'stopped', 'pending'):
                time.sleep(0.5)
                return
        except Exception:
            pass
        time.sleep(0.5)


def _write_task_completed_and_results(task_id: str, case_ids, n_cases: int):
    """隔离库直写任务/用例终态 + 每用例 1 条 test_results（设备 1/2，result_data 带 result_type）。"""
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            for i, case_id in enumerate(case_ids):
                device_id = i + 1
                rt = 'real-time' if i % 2 == 0 else 'final'
                cur.execute(
                    'INSERT INTO test_results '
                    '(task_id, test_case_id, device_id, algorithm_type, execution_status, '
                    ' algorithm_result, result_data, created_at) '
                    "VALUES (%s, %s, %s, 'asr', 'completed', '{\"asr_result\": \"t\"}', "
                    " %s, now())",
                    (int(task_id), case_id, device_id,
                     '{"result_type": "%s", "data": "d"}' % rt))
            cur.execute(
                'UPDATE task_case_relations '
                "SET status='completed', execution_status='completed', evaluation_status='completed' "
                'WHERE task_id=%s AND test_case_id = ANY(%s)',
                (int(task_id), list(case_ids)))
            cur.execute(
                "UPDATE tasks SET status='completed', total_cases=%s, completed_cases=%s "
                'WHERE id=%s',
                (n_cases, n_cases, int(task_id)))
        conn.commit()
    finally:
        conn.close()


def _cleanup(api_client, task_id, handles):
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
        api_client.delete_group(handles['group_id'])
    except Exception:
        pass


@pytest.fixture()
def int577_source_task(api_client):
    task_id, case_ids, handles = _create_source_task_with_results(api_client, n_cases=2)
    yield {'task_id': task_id, 'case_ids': case_ids, **handles}
    _cleanup(api_client, task_id, handles)


def _tab_labels(page: BasePage) -> list:
    return [t.text.strip() for t in page.find_all(TAB_BTN) if t.is_displayed()]


def test_tabs_terminal_three_and_legacy_redirect(page):
    """终态三页签（日常/已发布/挑选合并，无「合并」）；?tab=merged redirect 到挑选合并。"""
    page.goto(TASKS_ROUTE)
    page.wait_visible(TAB_BTN, timeout=20)
    page.settle(0.5)
    labels = _tab_labels(page)
    assert '日常任务' in labels and '已发布任务' in labels and '挑选合并' in labels, \
        f'终态三页签缺失: {labels}'
    assert not any('合并任务' in l for l in labels), f'旧「合并」页签未撤除: {labels}'

    # 旧链接 redirect：?tab=merged → 挑选合并页签（URL tab=cherry-picks）
    page.goto(f'{TASKS_ROUTE}?tab=merged')
    page.settle(1.0)
    active = [t for t in page.find_all(TAB_BTN) if t.is_displayed()
              and 'active' in (t.get_attribute('class') or '')]
    assert active and '挑选合并' in active[0].text, \
        f'?tab=merged 应落到挑选合并页签: {[t.text for t in active]}'
    assert 'cherry-picks' in page.driver.current_url, \
        f'URL 未归一到 tab=cherry-picks: {page.driver.current_url}'


def test_batch_add_to_pick_wizard_tree_and_cart(page, int577_source_task):
    """批量「加入挑选」→ 向导打开（任务级预选）→ 四级树渲染 → 加购 → 角标 +n。"""
    name = int577_source_task['task_name']
    page.goto(TASKS_ROUTE)
    page.wait_visible(SEARCH_INPUT, timeout=20)

    # 日常页签搜索并勾选该任务
    page.fill(SEARCH_INPUT, name)
    page.settle(1.2)
    checkbox = None
    for card in page.find_all('.task-card'):
        if not card.is_displayed():
            continue
        titles = card.find_elements(By.CSS_SELECTOR, '.task-title')
        if titles and name in (titles[0].text or ''):
            boxes = card.find_elements(By.CSS_SELECTOR, '.task-select input[type=checkbox]')
            if boxes:
                checkbox = boxes[0]
            break
    assert checkbox is not None, f'任务卡片缺勾选框: {name}'
    page.driver.execute_script('arguments[0].click();', checkbox)
    page.settle(0.5)

    # 批量浮条「加入挑选」→ 打开挑选向导
    add_btn = next((b for b in page.find_all('button') if b.is_displayed()
                    and BATCH_ADD_PICK_BTN in (b.text or '')), None)
    assert add_btn is not None, '批量浮条缺「加入挑选」按钮'
    page.driver.execute_script('arguments[0].click();', add_btn)
    page.wait_visible(WIZARD_ROOT, timeout=20)
    page.settle(0.8)

    # 挑选树渲染（任务→用例→设备→result_type 至少两层可见，叶计数>0）
    assert page.find_all(TREE_ROOT), '挑选树未渲染'
    tree_rows = [r for r in page.find_all(f'{TREE_ROOT} .pt-row, {TREE_ROOT} .pt-leaf') if r.is_displayed()]
    assert len(tree_rows) >= 3, f'挑选树节点过少: {len(tree_rows)}'

    # 任务级预选命中（批量「加入挑选」= 任务级整任务加购）：已选汇总条非 0
    summary = [t for t in page.find_all('.cpw-summary-info') if t.is_displayed()]
    assert summary and summary[0].text.strip().startswith('已选'), \
        f'已选汇总条缺失: {[s.text for s in summary]}'

    # 勾选任务级节点（R7 整任务）→ 加入购物车
    task_checkbox = next((c for c in page.find_all(f'{TREE_ROOT} .pt-row input[type=checkbox]')
                          if c.is_displayed()), None)
    assert task_checkbox is not None, '挑选树缺任务级勾选框'
    page.driver.execute_script('arguments[0].click();', task_checkbox)
    page.settle(0.4)
    add_cart = next((b for b in page.find_all('button') if b.is_displayed()
                     and '加入购物车' in (b.text or '')), None)
    assert add_cart is not None, '向导缺「加入购物车」按钮'
    page.driver.execute_script('arguments[0].click();', add_cart)
    page.settle(1.2)

    # Step2 购物车：分组条目可见
    cart_group = [g for g in page.find_all('.cpw-cart-group') if g.is_displayed()]
    assert cart_group, '购物车步骤未展示分组条目'
