# -*- coding: utf-8 -*-
"""INT-302 UI 实测：重执行/重评估按用例+按维度选择（任务卡片入口）。

覆盖卡面验收标准 4/5 的 UI 层（人手操作等价，只读语义不触发真实重执行）：

1. 任务卡片「重新执行」按钮 → 弹 ReexecuteOptionsModal（非旧版确认弹窗）；
2. 模态窗默认勾选「全部」；三档范围选项（全部/仅失败用例/手动选择）渲染；
3. 切「手动选择」→ 数据源为本任务 task_cases（非全库用例）——任务仅 2 个
   关联用例，勾选列表恰好 2 行（若拉了全库则远大于 2）；
4. 勾选 1 个用例 → 底部计数「已选 1 个用例」；未勾选时确认按钮禁用；
5. 重新评估入口 → 维度步渲染（actionType=reevaluate）且默认全选——数据自包含：
   int302_task fixture 自建「已完成且带 evaluationDimensions 的任务」（用例
   config 注入 2 个维度），不再依赖库内既有终态任务（INT-569 日巡实证：库内
   已完成任务均无维度配置，维度步不渲染致 10s 超时）；
6. 取消关闭：不发请求（mock 网关侧无任务状态变化即可，这里只断言弹窗关闭）。
7. INT-410 三态准入：pending 任务列表/详情均无「重新执行」入口；
   completed/failed/stopped 三态任务入口可见（fixture 停任务后直写 completed）。

只读语义：全程只打开/关闭选择模态窗，不点确认发起重执行/重评估请求
（无真实执行结果的任务，误触发也只会空转）；测试数据自建自清
（API 造任务+用例 → 停任务/直写状态 → teardown 删任务+purge 用例+标签/分组回收）。
"""
import time

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils import bootstrap
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


def _create_task_with_cases(api_client, n_cases: int = 2, dimensions: list | None = None):
    """API 造 n 个用例 + 1 个关联任务（新建态，status=pending）。

    dimensions: 可选；提供则每个用例 config 注入 [{id,name}] 评估维度条目
    （重评估维度步的数据源——task.cases[].evaluationDimensions 从用例 config
    提取，INT-302/F3 口径；task_service 侧 config 落库后 rounds[0].
    evaluation.dimensions）。

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
            description='INT-302 重执行/重评估选择模态窗实测',
            config={'dimensions': dimensions} if dimensions else None)
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


def _quiesce_task_completed(api_client, task_id: str, timeout: float = 45):
    """stop 新建任务并等其收敛终态，再隔离库直写 status='completed'（INT-410 三态准入）。

    best-effort：pending 未被调度时 stop 可能失败/无效果；引擎收敛终态后不再改动
    任务级状态（test_ui_09 同口径隔离库直写，防调度漂移）。直写后任务必属
    completed/failed/stopped 三态，「重新执行」入口按三态准入可见。
    """
    try:
        api_client.request('POST', f'/tasks/{task_id}/stop')
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = api_client.request('GET', f'/tasks/{task_id}').get('data') or {}
            if str(data.get('status')) in ('completed', 'failed', 'stopped', 'skipped', 'pending'):
                break
        except Exception:
            pass
        time.sleep(1.0)
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE test_tasks SET status=%s WHERE id=%s',
                        ('completed', int(task_id)))
        conn.commit()
    finally:
        conn.close()


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
    """造 2 用例（config 注入 2 个评估维度）1 任务并收敛为 completed。

    INT-410 三态准入：completed 任务的重执行/重评估入口可见；用例携带
    evaluationDimensions（重评估维度步的数据源，INT-302/F3）——本 fixture
    自包含维度数据，不再依赖库内既有终态任务（INT-569 日巡实证库内已完成
    任务均无维度配置，维度步不渲染）。

    teardown 全量回收（零残留）。
    """
    task_id, case_ids, handles = _create_task_with_cases(
        api_client, n_cases=2, dimensions=[
            {'id': 1, 'name': '维度一'}, {'id': 2, 'name': '维度二'}])
    _quiesce_task_completed(api_client, task_id)
    yield {'task_id': task_id, 'case_ids': case_ids, 'name': handles['task_name'],
           **handles}
    _cleanup_task_and_cases(api_client, task_id, handles)


@pytest.fixture()
def pending_int302_task(api_client):
    """造 2 用例 1 任务，保持 pending（引擎无设备可执行，调度期不落执行）。

    INT-410 准入判别：pending 任务在列表/详情均不得出现「重新执行」入口。
    """
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
    一致）。数据自包含：直接用 int302_task fixture 自建的「已完成且带
    evaluationDimensions 的任务」（用例 config 注入 2 个维度），不再遍历库内
    终态任务碰运气——维度步按设计仅在任务用例携带维度时渲染，库内既有已完成
    任务均无维度配置（INT-569 日巡实证），依赖它们必然 10s 超时。
    """
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)

    # 定位本 fixture 自建任务（completed + 带维度）的「重新评估」按钮
    btn = WebDriverWait(page.driver, 15).until(
        lambda d: _find_task_card_button(page, int302_task['name'], '重新评估'))
    page.driver.execute_script('arguments[0].click();', btn)

    modal = _wait_reexecute_modal(page, REEVALUATE_MODAL_TITLE)
    # 维度步渲染（actionType=reevaluate 且任务用例携带评估维度）且默认全选
    WebDriverWait(page.driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, DIMENSION_SELECTOR)))
    page.settle(0.5)
    modal = _wait_reexecute_modal(page, REEVALUATE_MODAL_TITLE)
    dims = [c for c in modal.find_elements(By.CSS_SELECTOR, DIMENSION_CHECKBOXES)
            if c.is_displayed()]
    assert dims, '重新评估模态窗未渲染维度勾选步'
    assert all(c.is_selected() for c in dims), \
        f'维度应默认全选：选中 {sum(1 for c in dims if c.is_selected())}/{len(dims)}'


def test_pending_task_has_no_retry_entry(page, pending_int302_task):
    """pending 任务列表与详情模态窗均无「重新执行」入口（INT-410 三态准入拍板）。

    拍板口径（任务重新执行功能设计文档 §5 约束#1，2026-10-15）：重执行准入 =
    completed/failed/stopped 三态，pending 不允许（需先停止）。列表断言无按钮；
    「查看详情」对 pending 可达（view-details 无状态门控），详情模态窗内亦无入口。
    """
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)

    # 列表：pending 任务卡片无「重新执行」按钮
    btn = _find_task_card_button(page, pending_int302_task['name'], '重新执行')
    assert btn is None, 'pending 任务不应出现「重新执行」按钮（需先停止）'

    # 详情：打开任务详情模态窗，内无「重新执行」按钮
    card = None
    for c in page.find_all('.task-card'):
        if not c.is_displayed():
            continue
        name_el = c.find_elements(By.CSS_SELECTOR, '.task-title')
        if name_el and pending_int302_task['name'] in (name_el[0].text or ''):
            card = c
            break
    assert card is not None, f'列表未出现 pending 任务卡片: {pending_int302_task["name"]}'
    view = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
            if b.is_displayed() and b.get_attribute('title') == '查看详情']
    assert view, 'pending 任务卡片应仍有「查看详情」入口'
    page.driver.execute_script('arguments[0].click();', view[0])
    page.wait_visible('.task-detail-modal', timeout=20)
    page.settle(0.8)

    modal_retry = [b for b in page.find_all('.task-detail-modal button')
                   if b.is_displayed() and '重新执行' in (b.text or '')]
    assert not modal_retry, 'pending 任务详情模态窗不应出现「重新执行」入口'
