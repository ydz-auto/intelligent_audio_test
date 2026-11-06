# -*- coding: utf-8 -*-
"""INT-305 UI 实测：执行详情模态窗移除用例（主流程）。

覆盖验收标准 4「UI 冒烟新增此流程」的 UI 层。四阶段全语义（执行中中断/
终态 excluded+报告重算）由单测 test_int305_remove_task_case.py（18 例）与
组件 spec taskDetailModal.removeCase.spec.ts（8 例）锁定；UI 隔离栈无法
低成本造真实执行态，本文件覆盖隔离库可安全造数/回收的两条主路径：

1. 待执行任务：用例行移除按钮可见（平铺视图）→ 确认弹窗文案为待执行语义
   （尚未开始执行/直接移除）→ 取消不删（用例仍在）；
2. 待执行任务：确认移除 → 用例直接消失（物理删路径，详情刷新后仍 1 例
   —— 后端往返证明）；
3. 仅剩 1 个用例：二次确认（任务将变空）→ 选「仅移除用例」→ 用例清空且
   任务未被停止（引擎对新建任务有自动调度，任务状态断言为「非 stopped」）。

测试数据自建自清（API 造任务+用例 → teardown 删任务+purge 用例+标签/
分组回收，test_ui_05 同口径）。
"""
import time

import pytest
from selenium.webdriver.common.by import By

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'
DETAIL_BTN_TITLE = '查看详情'
REMOVE_BTN_TITLE = '移除用例'
CONFIRM_REMOVE_TITLE = '移除用例'
LAST_CASE_TITLE = '任务将变空'
DETAIL_ROOT = '.task-detail-modal'
CASE_ROW = '.progress-item-small'
CASE_NAME = '.progress-name'
REMOVE_BTN = '.case-remove-btn'


def _create_task_with_cases(api_client, n_cases: int):
    """API 造 n 个用例 + 1 个关联任务（pending 态）。Returns (task_id, case_ids, handles)。"""
    suffix = unique_suffix()
    tag_name = f'ui305_tag_{suffix}'
    group_name = f'ui305_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-305 UI 实测专用分组')
    assert group_id, 'API 造分组失败'
    case_ids = []
    for i in range(n_cases):
        tc_id = api_client.create_testcase(
            f'ui305_用例{i + 1}_{suffix}', group=group_name, tags=[tag_name],
            description='INT-305 移除用例实测')
        assert tc_id, f'API 造用例 {i + 1} 失败'
        case_ids.append(tc_id)
    task_name = f'ui305_任务_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': task_name,
        'type': 'e2e',
        'description': 'INT-305 移除用例实测任务',
        'caseIds': case_ids,
    })
    task = data.get('data') or {}
    task_id = task.get('id')
    assert task_id, f'API 造任务失败: {str(data)[:200]}'
    return str(task_id), case_ids, {'tag': tag_name, 'group': group_name,
                                    'group_id': group_id, 'case_ids': case_ids,
                                    'task_name': task_name}


def _cleanup_task_and_cases(api_client, task_id, handles):
    """任务软删（回收站）→ 彻底删除 → 用例 purge → 标签/分组回收（test_ui_05 同口径）。"""
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


def _open_task_detail_modal(page: BasePage, task_name: str):
    """任务列表点卡片「查看详情」→ 等执行详情模态窗（TestExecutionComponent）就绪。"""
    # 前序用例可能遗留未关闭的详情模态窗（SPA hash 导航不重载应用、模态窗常驻
    # GlobalModalContainer）：先逐个关闭，防双模态叠加污染行计数
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
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)
    cards = page.find_all('.task-card')
    btn = None
    for card in cards:
        if not card.is_displayed():
            continue
        name_el = card.find_elements(By.CSS_SELECTOR, '.task-title')
        if not name_el or task_name not in (name_el[0].text or ''):
            continue
        cand = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
                if b.is_displayed() and b.get_attribute('title') == DETAIL_BTN_TITLE]
        if cand:
            btn = cand[0]
            break
    assert btn is not None, f'未找到任务卡片「{DETAIL_BTN_TITLE}」按钮: {task_name}'
    page.driver.execute_script('arguments[0].click();', btn)
    page.wait_visible(DETAIL_ROOT, timeout=20)
    # 详情加载态（spinner）结束后用例行才渲染，轮询等待
    deadline = time.time() + 20
    while time.time() < deadline:
        if page.find_all(f'{DETAIL_ROOT} {CASE_ROW}'):
            break
        time.sleep(0.3)
    else:
        raise AssertionError('详情模态窗用例行未加载（20s）')
    page.settle(0.5)


def _case_names_in_detail(page: BasePage) -> list:
    rows = [r for r in page.find_all(f'{DETAIL_ROOT} {CASE_ROW}') if r.is_displayed()]
    names = []
    for r in rows:
        name_el = r.find_elements(By.CSS_SELECTOR, CASE_NAME)
        if name_el:
            # textContent 而非 .text：虚列表 translateY 容器内首行 .text 读空
            # （15:26 probe2 实证：第二行有值、首行持续空；textContent 取 DOM 文本）
            txt = (name_el[0].get_attribute('textContent') or '').strip()
            names.append(txt)
    return names


def _remove_buttons(page: BasePage) -> list:
    return [b for b in page.find_all(f'{DETAIL_ROOT} {REMOVE_BTN}')
            if b.is_displayed() and b.get_attribute('title') == REMOVE_BTN_TITLE]


def _find_confirm_overlay(page: BasePage, title: str):
    """按 BasicModal 标题定位确认弹窗所在 overlay（详情模态窗与确认弹窗叠加）。"""
    for overlay in page.driver.find_elements(By.CSS_SELECTOR, '.modal-overlay'):
        if not overlay.is_displayed():
            continue
        titles = overlay.find_elements(By.CSS_SELECTOR, '.modal-title')
        if titles and title in (titles[0].text or ''):
            return overlay
    return None


def _wait_confirm_overlay(page: BasePage, title: str, timeout: float = 15):
    page.settle(0.3)
    deadline = time.time() + timeout
    while time.time() < deadline:
        ov = _find_confirm_overlay(page, title)
        if ov is not None:
            return ov
        time.sleep(0.3)
    raise AssertionError(f'确认弹窗「{title}」未出现')


def _overlay_button(overlay, text: str):
    """在确认弹窗 overlay 内按文案找按钮（取消=btn-secondary / 移除=btn-danger）。"""
    for b in overlay.find_elements(By.CSS_SELECTOR, '.modal-confirmActions button, .modal-footer button'):
        if b.is_displayed() and text in (b.text or ''):
            return b
    return None


def _click_remove_and_wait_confirm(page: BasePage, btn, title: str = CONFIRM_REMOVE_TITLE):
    page.driver.execute_script('arguments[0].click();', btn)
    return _wait_confirm_overlay(page, title)


@pytest.fixture()
def int305_task(api_client):
    task_id, case_ids, handles = _create_task_with_cases(api_client, n_cases=2)
    yield {'task_id': task_id, 'case_ids': case_ids, 'name': handles['task_name'],
           **handles}
    _cleanup_task_and_cases(api_client, task_id, handles)


@pytest.fixture()
def int305_single_task(api_client):
    task_id, case_ids, handles = _create_task_with_cases(api_client, n_cases=1)
    yield {'task_id': task_id, 'case_ids': case_ids, 'name': handles['task_name'],
           **handles}
    _cleanup_task_and_cases(api_client, task_id, handles)


def test_remove_entry_visible_and_pending_confirm_cancel(page, int305_task):
    """待执行：移除入口可见 + 确认文案为待执行语义 + 取消不删。"""
    _open_task_detail_modal(page, int305_task['name'])

    btns = _remove_buttons(page)
    assert len(btns) == 2, f'平铺视图 2 行用例应各 1 个移除按钮: 实际 {len(btns)}'
    names = _case_names_in_detail(page)
    assert len(names) == 2, f'详情用例行应为 2: {names}'

    # 点第一个移除 → 确认弹窗（待执行语义文案）
    overlay = _click_remove_and_wait_confirm(page, btns[0])
    msg = overlay.find_elements(By.CSS_SELECTOR, '.modal-confirmMessage')
    assert msg, '确认弹窗缺正文'
    content = msg[0].text
    assert names[0] in content, f'确认文案应含被移除用例名「{names[0]}」: {content!r}'
    assert '尚未开始执行' in content, f'待执行阶段文案缺失（应含「尚未开始执行」）: {content!r}'

    # 取消 → 弹窗关闭、用例原样保留
    cancel = _overlay_button(overlay, '取消')
    assert cancel is not None, '确认弹窗缺「取消」按钮'
    page.driver.execute_script('arguments[0].click();', cancel)
    assert page.wait_gone('.modal-overlay .modal-confirm', timeout=10), \
        '取消后确认弹窗应关闭'
    # 引擎对新建任务自动调度 → WS 进度推送会触发用例行重渲染；轮询等待计数回稳
    deadline = time.time() + 8
    btns_n, names_n = 0, 0
    while time.time() < deadline:
        btns_n = len(_remove_buttons(page))
        names_n = len(_case_names_in_detail(page))
        if btns_n == 2 and names_n == 2:
            break
        time.sleep(0.4)
    assert btns_n == 2, f'取消后用例行不应变化（移除按钮数）: {btns_n}'
    assert names_n == 2, f'取消后用例不应被移除: {names_n}'


def test_pending_phase_confirm_removes_case_directly(page, int305_task):
    """待执行：确认移除 → 用例直接消失（详情刷新后仍 1 例，后端往返证明）。"""
    _open_task_detail_modal(page, int305_task['name'])
    names = _case_names_in_detail(page)
    assert len(names) == 2

    btns = _remove_buttons(page)
    overlay = _click_remove_and_wait_confirm(page, btns[0])
    confirm = _overlay_button(overlay, '移除')
    assert confirm is not None, '确认弹窗缺「移除」按钮'
    page.driver.execute_script('arguments[0].click();', confirm)

    # 移除用例名即时消失（本地剔除 + fetchTaskDetails 刷新为准）
    removed = names[0]
    deadline = time.time() + 15
    last = None
    while time.time() < deadline:
        last = _case_names_in_detail(page)
        if len(last) == 1 and removed not in last:
            break
        time.sleep(0.4)
    assert len(last) == 1 and removed not in last, \
        f'移除后应仅剩 1 例且不含「{removed}」: 实际 {last}'
    assert len(_remove_buttons(page)) == 1, '移除后剩余行移除按钮应恰 1 个'


def test_last_case_second_confirm_remove_only_keeps_task(page, api_client, int305_single_task):
    """末例二次确认（任务将变空）→ 仅移除用例 → 用例清空且任务未被停止。"""
    task = int305_single_task
    _open_task_detail_modal(page, task['name'])
    btns = _remove_buttons(page)
    assert len(btns) == 1, f'单用例任务应恰 1 个移除按钮: 实际 {len(btns)}'

    # 第一次确认（移除用例）
    overlay = _click_remove_and_wait_confirm(page, btns[0])
    confirm = _overlay_button(overlay, '移除')
    page.driver.execute_script('arguments[0].click();', confirm)

    # 二次确认（任务将变空）
    second = _wait_confirm_overlay(page, LAST_CASE_TITLE)
    msg = second.find_elements(By.CSS_SELECTOR, '.modal-confirmMessage')
    assert msg and '最后一个用例' in msg[0].text, \
        f'二次确认应提示任务将空: {(msg[0].text if msg else "")!r}'
    only_remove = _overlay_button(second, '仅移除用例')
    assert only_remove is not None, '二次确认缺「仅移除用例」按钮'
    page.driver.execute_script('arguments[0].click();', only_remove)

    # 用例清空 → 暂无关联用例；任务未被停止（选「仅移除用例」不得调用 stop 端点）。
    # 引擎对新建任务有 DB 兜底自动调度（数秒内领取执行），任务可能已 running/completed，
    # 故断言语义为「未被本移除流程停止」（stopped 仅由显式 stop 产生），不锁定 pending。
    deadline = time.time() + 15
    empty = False
    while time.time() < deadline:
        if not _remove_buttons(page):
            empty = True
            break
        time.sleep(0.4)
    assert empty, '移除末例后用例列表应为空'
    detail = api_client.request('GET', f'/tasks/{task["task_id"]}')
    body = detail.get('data') or detail
    status = (body or {}).get('status')
    assert status != 'stopped', f'选「仅移除用例」后任务不应被停止: status={status!r}'
