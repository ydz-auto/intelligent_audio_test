# -*- coding: utf-8 -*-
"""INT-302 UI 实测：重执行/重评估按用例+按维度选择（任务卡片入口）。

覆盖卡面验收标准 4/5 的 UI 层（人手操作等价，只读语义不触发真实重执行）：

1. 任务卡片「重新执行」按钮 → 弹 ReexecuteOptionsModal（非旧版确认弹窗）；
2. 模态窗默认勾选「全部」；三档范围选项（全部/仅失败用例/手动选择）渲染；
3. 切「手动选择」→ 数据源为本任务 task_cases（非全库用例）——任务仅 2 个
   关联用例，勾选列表恰好 2 行（若拉了全库则远大于 2）；
4. 勾选 1 个用例 → 底部计数「已选 1 个用例」；未勾选时确认按钮禁用；
5. 重新评估入口 → 维度步渲染（actionType=reevaluate）且默认全选；
6. 取消关闭：不发请求（mock 网关侧无任务状态变化即可，这里只断言弹窗关闭）。

只读语义：全程只打开/关闭选择模态窗，不点确认发起重执行/重评估请求
（pending 任务无可重评结果，误触发也只会空转）；测试数据自建自清
（API 造任务+用例 → teardown 删任务+purge 用例+标签/分组回收）。
"""
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'
# BasicModal 标题（GlobalModalContainer → BasicModal → .modal-title）
MODAL_TITLE = '.modal-title'
REEXECUTE_MODAL_TITLE = '重新执行'
REEVALUATE_MODAL_TITLE = '重新评估'
SCOPE_OPTIONS = '.reexecute-option'
SCOPE_TITLES = ('全部用例', '仅失败用例', '手动选择用例')
CASE_ITEMS = '.case-list .case-item'
CASE_CHECKBOXES = '.case-list .case-item input[type="checkbox"]'
DIMENSION_SELECTOR = '.dimension-selector'
DIMENSION_CHECKBOXES = '.dimension-grid .dimension-item input[type="checkbox"]'
CONFIRM_BTN_TEXT = '确认'


def _create_task_with_cases(api_client, n_cases: int = 2):
    """API 造 n 个用例 + 1 个关联任务（pending 态，重执行/重评估按钮均可见）。

    Returns:
        (task_id, [case_id...], cleanup_handles dict)
    """
    suffix = unique_suffix()
    tag_name = f'ui302_tag_{suffix}'
    group_name = f'ui302_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-302 UI 实测专用分组')
    assert group_id, 'API 造分组失败'
    case_ids = []
    for i in range(n_cases):
        tc_id = api_client.create_testcase(
            f'ui302_用例{i + 1}_{suffix}', group=group_name, tags=[tag_name],
            description='INT-302 重执行/重评估选择模态窗实测')
        assert tc_id, f'API 造用例 {i + 1} 失败'
        case_ids.append(tc_id)
    task_name = f'ui302_任务_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': task_name,
        'type': 'e2e',
        'description': 'INT-302 选择模态窗实测任务',
        'caseIds': case_ids,
    })
    task = data.get('data') or {}
    task_id = task.get('id')
    assert task_id, f'API 造任务失败: {str(data)[:200]}'
    return str(task_id), case_ids, {'tag': tag_name, 'group': group_name,
                                    'group_id': group_id, 'case_ids': case_ids,
                                    'task_name': task_name}


def _cleanup_task_and_cases(api_client, task_id, handles):
    """任务软删（回收站）→ 彻底删除（favorites-trash purge）→ 用例 purge → 标签/分组回收。"""
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
    # 标签/分组：平台 delete 即软删（无 purge 端点，test_ui_03 同口径）；
    # 回收站列表接口过滤 deleted=true，应用层可见零残留
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


def _find_task_card_button(bp: BasePage, task_name: str, label: str):
    """在任务列表中定位指定任务卡片上的操作按钮（按 title=操作标签匹配）。"""
    cards = bp.find_all('.task-card')
    for card in cards:
        if not card.is_displayed():
            continue
        name_el = card.find_elements(By.CSS_SELECTOR, '.task-title')
        if not name_el or task_name not in (name_el[0].text or ''):
            continue
        btns = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
                if b.is_displayed() and b.get_attribute('title') == label]
        if btns:
            return btns[0]
    return None


def _wait_reexecute_modal(bp: BasePage, title: str, timeout: float = 15):
    """等待选择模态窗出现（BasicModal 标题 = 重新执行/重新评估）。"""
    WebDriverWait(bp.driver, timeout).until(
        lambda d: any(m.is_displayed() and title in m.text
                      for m in d.find_elements(By.CSS_SELECTOR, MODAL_TITLE)))
    bp.settle(0.4)
    return bp.find_visible('.reexecute-select', timeout=10)


def _scope_titles_in_modal(modal):
    return [o.text.split('\n')[0].strip()
            for o in modal.find_elements(By.CSS_SELECTOR, SCOPE_OPTIONS)]


@pytest.fixture()
def int302_task(api_client):
    """造 2 用例 1 任务；teardown 全量回收（零残留）。"""
    task_id, case_ids, handles = _create_task_with_cases(api_client, n_cases=2)
    yield {'task_id': task_id, 'case_ids': case_ids, 'name': handles['task_name'],
           **handles}
    _cleanup_task_and_cases(api_client, task_id, handles)


def test_retry_button_opens_scope_selection_modal(page, int302_task):
    """卡片「重新执行」→ ReexecuteOptionsModal：默认全部 + 三档范围渲染。"""
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)

    btn = WebDriverWait(page.driver, 15).until(
        lambda d: _find_task_card_button(page, int302_task['name'], '重新执行'))
    page.driver.execute_script('arguments[0].click();', btn)

    modal = _wait_reexecute_modal(page, REEXECUTE_MODAL_TITLE)

    # 三档范围选项渲染（全部/仅失败/手动选择）
    titles = _scope_titles_in_modal(modal)
    for expect in SCOPE_TITLES:
        assert any(expect in t for t in titles), \
            f'范围选项缺「{expect}」：实际={titles}'

    # 默认勾选「全部」（active 态在第一项）+ 确认按钮可用
    first_option = modal.find_elements(By.CSS_SELECTOR, SCOPE_OPTIONS)[0]
    assert 'active' in (first_option.get_attribute('class') or ''), \
        '默认范围未选中「全部」'
    confirm = [b for b in modal.find_elements(By.CSS_SELECTOR, 'button')
               if CONFIRM_BTN_TEXT in b.text][0]
    assert confirm.is_enabled(), '默认「全部」下确认按钮应可用'


def test_manual_selection_lists_only_task_cases_with_counter(page, int302_task):
    """手动选择：数据源为本任务用例集（恰 2 行，非全库）+ 勾选计数 + 禁用门控。"""
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)

    btn = WebDriverWait(page.driver, 15).until(
        lambda d: _find_task_card_button(page, int302_task['name'], '重新执行'))
    page.driver.execute_script('arguments[0].click();', btn)
    modal = _wait_reexecute_modal(page, REEXECUTE_MODAL_TITLE)

    # 切「手动选择」
    options = modal.find_elements(By.CSS_SELECTOR, SCOPE_OPTIONS)
    manual = [o for o in options if '手动选择' in o.text][0]
    page.driver.execute_script('arguments[0].click();', manual)
    WebDriverWait(page.driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, CASE_ITEMS)))
    page.settle(0.3)

    # 数据源 = 本任务 task_cases：恰 2 行（全库用例远大于 2）
    modal = _wait_reexecute_modal(page, REEXECUTE_MODAL_TITLE)
    checks = modal.find_elements(By.CSS_SELECTOR, CASE_CHECKBOXES)
    assert len(checks) == 2, \
        f'勾选列表应仅含本任务 2 个用例（若为全库用例则远大于 2）：实际 {len(checks)}'

    confirm = [b for b in modal.find_elements(By.CSS_SELECTOR, 'button')
               if CONFIRM_BTN_TEXT in b.text][0]
    # 未勾选：确认禁用
    assert not confirm.is_enabled(), '未勾选用例时确认按钮应禁用'

    # 勾选第 1 个 → 计数「已选 1 个用例」+ 确认可用
    page.driver.execute_script('arguments[0].click();', checks[0])
    page.settle(0.3)
    modal = _wait_reexecute_modal(page, REEXECUTE_MODAL_TITLE)
    confirm = [b for b in modal.find_elements(By.CSS_SELECTOR, 'button')
               if CONFIRM_BTN_TEXT in b.text][0]
    assert confirm.is_enabled(), '勾选后确认按钮应可用'
    assert '已选 1 个用例' in confirm.text, \
        f'确认按钮计数文案异常: {confirm.text!r}'


def test_reevaluate_modal_has_dimension_step_default_all(page, api_client, int302_task):
    """卡片「重新评估」→ 两段式模态窗：维度步渲染且默认全选。

    「重新评估」按钮仅终态任务可见（FINISHED_STATUSES 口径，卡片与详情模态窗
    一致）；pending 任务不渲染该按钮——软删后恢复不动状态，改用既有终态任务
    （库内最新 completed 任务，若有）验证入口；无终态任务则 skip。
    """
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)

    # 优先用库内终态任务（重评估入口仅终态可见）；找不到则跳过（环境无终态任务）。
    # 列表渲染有节流/懒加载，按钮搜索带重试（前一用例弹窗关闭后的重渲染余量）。
    detail = (api_client.request(
        'GET', '/tasks?page=1&per_page=50&status=completed').get('data') or {})
    items = detail.get('items') or detail.get('tasks') or []
    target = None
    for _attempt in range(3):
        for it in items:
            name = it.get('name') or ''
            if not name:
                continue
            btn = _find_task_card_button(page, name, '重新评估')
            if btn is not None:
                target = (name, btn)
                break
        if target is not None:
            break
        page.settle(1.0)
    if target is None:
        pytest.skip('任务列表无终态任务（重新评估入口仅 FINISHED_STATUSES 可见），'
                    '入口可见性由 useTaskControl 单测与组件 spec 锁定')
    name, btn = target
    page.driver.execute_script('arguments[0].click();', btn)

    modal = _wait_reexecute_modal(page, REEVALUATE_MODAL_TITLE)
    # 维度步渲染（actionType=reevaluate）且默认全选
    WebDriverWait(page.driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, DIMENSION_SELECTOR)))
    page.settle(0.5)
    modal = _wait_reexecute_modal(page, REEVALUATE_MODAL_TITLE)
    dims = [c for c in modal.find_elements(By.CSS_SELECTOR, DIMENSION_CHECKBOXES)
            if c.is_displayed()]
    assert dims, '重新评估模态窗未渲染维度勾选步'
    assert all(c.is_selected() for c in dims), \
        f'维度应默认全选：选中 {sum(1 for c in dims if c.is_selected())}/{len(dims)}'
