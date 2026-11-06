# -*- coding: utf-8 -*-
"""INT-401 UI 实测：挑选合并主链交互（任务详情入口 → 勾选加购 → 下单合并 → 溯源展示/缺失标注）。

负责人 2026-10-15 实测打回（INT-401）挑选合并流程疑点的真实页面走查：

1. 任务详情「加入购物车」入口 → CherryPickDialog 预筛选定位本任务执行结果
   （设计 §9 入口粒度：结果级勾选，非全局候选列表从头再筛）；
2. 候选列表勾选 → 加入购物车 → 购物车分组展示 → 去下单；
3. merge 出口填名称提交 → 跳转新任务详情（cherry-pick 容器任务，创建即 completed）；
4. 任务列表「挑选合并」页签展示容器任务 + 溯源展开显示来源任务分组；
5. 源结果删除后溯源标注「源结果已缺失」（引用方案 A 的 missing 场景，§10）。

只读语义：不依赖真实执行引擎——源任务/结果由 API 造任务+用例、隔离库直写
终态与 test_results 行构建（test_ui_05/09 同口径直写）；测试数据自建自清
（teardown 删任务 purge + 用例 purge + 标签/分组回收）。
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
# CherryPickDialog（挑选 → 购物车 → 下单三步向导）
CP_DIALOG = '.cp-dialog'
CP_ROWS = '.cp-list .cp-row'
CP_CHECKBOX = '.cp-list .cp-row .cp-checkbox'
CP_FOOTER_BTN = '.cp-footer button'
# 任务详情模态窗
TASK_DETAIL_MODAL = '.task-detail-modal'
# 挑选合并页签 + 溯源
CHERRY_TAB_TEXT = '挑选合并'
SOURCE_LIST = '.merged-source-list'
SOURCE_RESULTS = '.cp-source-results .cp-source-result'
MISSING_BADGE = '.missing-badge'


def _create_source_task(api_client, n_cases: int = 2):
    """API 造 n 个用例 + 1 个关联任务（pending 新建态）。

    Returns:
        (task_id, [case_id...], cleanup_handles dict)
    """
    suffix = unique_suffix()
    tag_name = f'ui401_tag_{suffix}'
    group_name = f'ui401_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-401 挑选合并 UI 实测专用分组')
    assert group_id, 'API 造分组失败'
    case_ids = []
    for i in range(n_cases):
        tc_id = api_client.create_testcase(
            f'ui401_用例{i + 1}_{suffix}', group=group_name, tags=[tag_name],
            description='INT-401 挑选合并主链实测')
        assert tc_id, f'API 造用例 {i + 1} 失败'
        case_ids.append(tc_id)
    task_name = f'ui401_源任务_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': task_name,
        'type': 'e2e',
        'description': 'INT-401 挑选合并主链实测源任务',
        'caseIds': case_ids,
    })
    task = data.get('data') or {}
    task_id = task.get('id')
    assert task_id, f'API 造任务失败: {str(data)[:200]}'
    return str(task_id), case_ids, {'tag': tag_name, 'group': group_name,
                                    'group_id': group_id, 'case_ids': case_ids,
                                    'task_name': task_name}


def _seed_terminal_results(api_client, task_id: str, device_offset: int = 0):
    """隔离库直写源任务为 completed 并构造终态执行结果（INT-401 挑选数据源）。

    造 n 条 test_results（execution_status=completed）+ 同步 TaskCase 双状态
    落 completed，任务状态落 completed——满足 §10 仅终态任务可挑选。

    Returns:
        result_ids: list[int]（按用例序）
    """
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('UPDATE test_tasks SET status=%s WHERE id=%s',
                        ('completed', int(task_id)))
            cur.execute('SELECT test_case_id FROM task_case_relations WHERE task_id=%s',
                        (int(task_id),))
            tcase_ids = [r[0] for r in cur.fetchall()]
            assert tcase_ids, f'任务 {task_id} 无关联用例，无法构造执行结果'
            result_ids = []
            for i, cid in enumerate(tcase_ids):
                cur.execute(
                    'INSERT INTO test_results (task_id, test_case_id, device_id, api_id,'
                    ' algorithm_type, execution_status, algorithm_result, created_at, excluded)'
                    ' VALUES (%s,%s,%s,%s,%s,%s,%s, NOW(), 0) RETURNING id',
                    (int(task_id), cid, 7 + device_offset + i, None, 'asr',
                     'completed', '{"asr_result":"ui401文本%d"}' % i))
                result_ids.append(cur.fetchone()[0])
                cur.execute(
                    'UPDATE task_case_relations SET execution_status=%s, evaluation_status=%s,'
                    ' status=%s WHERE task_id=%s AND test_case_id=%s',
                    ('completed', 'completed', 'completed', int(task_id), cid))
            conn.commit()
            return result_ids
    finally:
        conn.close()


def _delete_source_results(result_ids):
    """物理删除源执行结果行（missing 场景构造：引用方案 A 的源结果被删）。"""
    import psycopg2

    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM test_results WHERE id = ANY(%s)', (list(result_ids),))
        conn.commit()
    finally:
        conn.close()


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


def _find_footer_button(bp: BasePage, text: str):
    """在 CherryPickDialog 底部定位按钮（按文本包含匹配，跳过禁用态说明）。"""
    for b in bp.find_all(CP_FOOTER_BTN):
        if not b.is_displayed():
            continue
        if text in (b.text or ''):
            return b
    return None


def _click_footer_button(bp: BasePage, text: str, timeout: float = 15):
    btn = WebDriverWait(bp.driver, timeout).until(
        lambda d: _find_footer_button(bp, text))
    bp.driver.execute_script('arguments[0].click();', btn)
    return btn


def _open_detail_and_pick(bp: BasePage, task_name: str):
    """打开任务详情模态窗并点击「加入购物车」→ 返回打开的 CherryPickDialog 容器。"""
    bp.goto(TASKS_ROUTE)
    bp.wait_visible('.task-card', timeout=25)
    bp.settle(0.5)
    card = None
    for c in bp.find_all('.task-card'):
        if not c.is_displayed():
            continue
        name_el = c.find_elements(By.CSS_SELECTOR, '.task-title')
        if name_el and task_name in (name_el[0].text or ''):
            card = c
            break
    assert card is not None, f'列表未出现源任务卡片: {task_name}'
    view = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
            if b.is_displayed() and b.get_attribute('title') == '查看详情']
    assert view, '源任务卡片应有「查看详情」入口'
    bp.driver.execute_script('arguments[0].click();', view[0])
    bp.wait_visible(TASK_DETAIL_MODAL, timeout=20)

    # 「加入购物车」按钮依赖详情异步进度态（终态任务才可见，实测约 1-3s 出现），
    # 固定 settle 断言偶发误失败 → 改 WebDriverWait 等待按钮出现（INT-401 返工）；
    # 栈负载高时权限/状态加载可达 15s+，放宽到 30s（INT-401 复验实测）
    pick = WebDriverWait(bp.driver, 30).until(
        lambda d: [b for b in d.find_elements(By.CSS_SELECTOR, f'{TASK_DETAIL_MODAL} button')
                   if b.is_displayed() and '加入购物车' in (b.text or '')])
    bp.driver.execute_script('arguments[0].click();', pick[0])

    WebDriverWait(bp.driver, 20).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, CP_DIALOG)))
    bp.settle(0.8)
    return bp.find_visible(CP_DIALOG, timeout=10)


def _extract_current_task_id(bp: BasePage):
    """从当前路由提取任务 id（下单成功后跳转 /tasks/{id}）。"""
    route = bp.current_route() or ''
    parts = route.strip('/').split('/')
    if len(parts) >= 2 and parts[0] == 'tasks' and parts[1].isdigit():
        return int(parts[1])
    return None


def _cleanup_container_task(api_client, task_id):
    """容器任务清理（软删回收站 → 彻底删除 purge；INT-401 返工：purge 已清
    task_cherry_pick_relations，PG FK 不再违约，容器可彻底删除）。"""
    try:
        api_client.request('POST', '/tasks/batch-action',
                           {'action': 'delete', 'task_ids': [int(task_id)]})
    except Exception:
        pass
    try:
        api_client.request('DELETE', f'/tasks/{task_id}/purge')
    except Exception:
        pass


@pytest.fixture()
def cherry_pick_source(api_client):
    """造 2 用例 1 源任务 + 隔离库直写终态与执行结果（挑选数据源）。

    teardown 全量回收（零残留）：源任务/用例/标签/分组 + 测试内下单创建的
    容器任务（container_task_ids 由用例下单后回填）。
    """
    task_id, case_ids, handles = _create_source_task(api_client, n_cases=2)
    result_ids = _seed_terminal_results(api_client, task_id)
    container_task_ids = []
    yield {'task_id': task_id, 'case_ids': case_ids, 'result_ids': result_ids,
           'container_task_ids': container_task_ids, 'name': handles['task_name'],
           **handles}
    for cid in container_task_ids:
        _cleanup_container_task(api_client, cid)
    _cleanup_task_and_cases(api_client, task_id, handles)


def test_cherry_pick_main_chain_merge(page, cherry_pick_source):
    """挑选合并主链：详情入口 → 结果勾选加购 → 购物车 → 下单合并 → 跳转新任务详情。

    对照设计 §3/§9：结果粒度挑选（入口经 presetTaskId 定位本任务结果）、
    跨步向导、merge 出口生成新任务并跳转详情。
    """
    dialog = _open_detail_and_pick(page, cherry_pick_source['name'])

    # 步骤1 挑选：候选列表 = 本任务执行结果（恰 2 条，非全库候选从头再筛）
    WebDriverWait(page.driver, 20).until(
        lambda d: len(dialog.find_elements(By.CSS_SELECTOR, CP_ROWS)) >= 1)
    page.settle(0.5)
    rows = dialog.find_elements(By.CSS_SELECTOR, CP_ROWS)
    assert len(rows) == 2, \
        f'预筛选应定位本任务 2 条执行结果（若为全库候选则远大于 2）：实际 {len(rows)}'

    # 勾选 2 条 → 加入购物车（计数 2）
    checks = dialog.find_elements(By.CSS_SELECTOR, CP_CHECKBOX)
    assert len(checks) == 2, f'候选行复选框应为 2 个：实际 {len(checks)}'
    for c in checks:
        page.driver.execute_script('arguments[0].click();', c)
    page.settle(0.3)
    _click_footer_button(page, '加入购物车')

    # 步骤2 购物车：分组展示 + 去下单可用
    page.settle(0.5)
    dialog = page.find_visible(CP_DIALOG, timeout=10)
    cart_text = dialog.text
    assert '我的购物车' in cart_text, '加购后应进入购物车步骤'
    _click_footer_button(page, '去下单')

    # 步骤3 下单：填名称提交（单来源任务无配置不一致确认）
    page.settle(0.5)
    dialog = page.find_visible(CP_DIALOG, timeout=10)
    name_input = dialog.find_elements(By.CSS_SELECTOR,
                                      'input[placeholder="新任务名称（必填）"]')
    assert name_input, 'merge 出口应渲染新任务名称输入框'
    page.driver.execute_script(
        "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
        name_input[0], 'ui401_合并任务_' + unique_suffix())
    page.settle(0.2)
    _click_footer_button(page, '提交下单')

    # 下单成功 → 按出口跳转新任务详情（设计 §9：下单成功 → 购物车出清 → 按出口跳转）
    WebDriverWait(page.driver, 25).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, TASK_DETAIL_MODAL)))
    page.settle(0.8)
    assert '/tasks/' in page.current_route(), \
        f'merge 下单后应跳转新任务详情路由: {page.current_route()}'
    # 记录容器任务 id（teardown 清理，避免挑选合并页签旧容器卡残留干扰后续用例）
    cid = _extract_current_task_id(page)
    if cid:
        cherry_pick_source['container_task_ids'].append(cid)


def test_cherry_pick_tab_source_trace_and_missing(page, api_client, cherry_pick_source):
    """挑选合并页签展示容器任务 + 溯源展开显示来源任务；源结果删除后标注缺失。

    验收 §12.2 溯源：容器任务卡片「源结果溯源」展开 → 来源任务分组 + 引用结果；
    源结果删除后（missing 场景）逐条标注「源结果已缺失」（引用方案 A，§10）。
    """
    # 先走一遍主链下单（与 test_cherry_pick_main_chain_merge 相同入口 → 生成容器任务）
    dialog = _open_detail_and_pick(page, cherry_pick_source['name'])
    WebDriverWait(page.driver, 20).until(
        lambda d: len(dialog.find_elements(By.CSS_SELECTOR, CP_ROWS)) >= 1)
    page.settle(0.5)
    checks = dialog.find_elements(By.CSS_SELECTOR, CP_CHECKBOX)
    assert len(checks) >= 1, '候选列表应含本任务执行结果'
    for c in checks:
        page.driver.execute_script('arguments[0].click();', c)
    page.settle(0.3)
    _click_footer_button(page, '加入购物车')
    page.settle(0.5)
    _click_footer_button(page, '去下单')
    page.settle(0.5)
    dialog = page.find_visible(CP_DIALOG, timeout=10)
    name_input = dialog.find_elements(By.CSS_SELECTOR,
                                      'input[placeholder="新任务名称（必填）"]')
    assert name_input, 'merge 出口应渲染新任务名称输入框'
    container_name = 'ui401_溯源任务_' + unique_suffix()
    page.driver.execute_script(
        "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
        name_input[0], container_name)
    page.settle(0.2)
    _click_footer_button(page, '提交下单')
    # 跳转详情后回列表进「挑选合并」页签
    WebDriverWait(page.driver, 25).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, TASK_DETAIL_MODAL)))
    page.settle(0.5)
    # 记录容器任务 id（teardown 清理）
    cid = _extract_current_task_id(page)
    if cid:
        cherry_pick_source['container_task_ids'].append(cid)

    page.goto(f'{TASKS_ROUTE}?tab=cherryPick')
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)

    def _container_wrap():
        """定位本次创建的容器任务卡片 wrap（按名称精确命中，避免旧容器卡误点）。"""
        for wrap in page.find_all('.published-card-wrap'):
            titles = wrap.find_elements(By.CSS_SELECTOR, '.task-title')
            if titles and container_name in (titles[0].text or ''):
                return wrap
        return None

    # 溯源展开：来源任务分组可见（源任务名 + 结果 N 条）
    # 防陈旧点击：卡片刷新后旧引用点击无事件，未展开则重试（INT-401 复验实测）
    for attempt in range(4):
        wrap = WebDriverWait(page.driver, 15).until(lambda d: _container_wrap())
        toggle = wrap.find_element(By.CSS_SELECTOR, SOURCE_LIST + ' .merged-source-list-title')
        page.driver.execute_script('arguments[0].click();', toggle)
        page.settle(1.0)
        if wrap.find_elements(By.CSS_SELECTOR, SOURCE_LIST + ' .merged-source-row'):
            break

    source_rows = wrap.find_elements(By.CSS_SELECTOR, SOURCE_LIST + ' .merged-source-row')
    assert any(cherry_pick_source['name'] in (r.text or '')
               for r in source_rows if r.is_displayed()), \
        f'溯源应显示来源任务分组: {cherry_pick_source["name"]}'

    # 缺失场景：物理删除源结果 → 刷新重进 → 溯源标注「源结果已缺失」
    _delete_source_results(cherry_pick_source['result_ids'])
    page.goto(f'{TASKS_ROUTE}?tab=cherryPick')
    page.wait_visible('.task-card', timeout=25)
    page.settle(0.5)
    for attempt in range(4):
        wrap = WebDriverWait(page.driver, 15).until(lambda d: _container_wrap())
        toggle = wrap.find_element(By.CSS_SELECTOR, SOURCE_LIST + ' .merged-source-list-title')
        page.driver.execute_script('arguments[0].click();', toggle)
        page.settle(1.0)
        if wrap.find_elements(By.CSS_SELECTOR, SOURCE_LIST + ' .merged-source-row'):
            break

    missing = [r for r in wrap.find_elements(By.CSS_SELECTOR, SOURCE_RESULTS)
               if r.is_displayed() and '源结果已缺失' in (r.text or '')]
    assert missing, \
        f'源结果删除后溯源应标注「源结果已缺失」：实际={[r.text for r in wrap.find_elements(By.CSS_SELECTOR, SOURCE_RESULTS) if r.is_displayed()]}'


def test_pick_entry_hidden_for_pending_task(page, api_client, cherry_pick_source):
    """待执行（pending）任务详情无「加入购物车」入口（§10 仅终态任务可挑选）。

    新造一个保持 pending 的任务，详情模态窗内不应出现挑选入口。
    """
    task_id, case_ids, handles = _create_source_task(api_client, n_cases=1)
    try:
        page.goto(TASKS_ROUTE)
        page.wait_visible('.task-card', timeout=25)
        page.settle(0.5)
        card = None
        for c in page.find_all('.task-card'):
            if not c.is_displayed():
                continue
            name_el = c.find_elements(By.CSS_SELECTOR, '.task-title')
            if name_el and handles['task_name'] in (name_el[0].text or ''):
                card = c
                break
        assert card is not None, f'列表未出现 pending 任务卡片: {handles["task_name"]}'
        view = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
                if b.is_displayed() and b.get_attribute('title') == '查看详情']
        assert view, 'pending 任务卡片应仍有「查看详情」入口'
        page.driver.execute_script('arguments[0].click();', view[0])
        page.wait_visible(TASK_DETAIL_MODAL, timeout=20)
        page.settle(0.8)
        pick = [b for b in page.find_all(f'{TASK_DETAIL_MODAL} button')
                if b.is_displayed() and '加入购物车' in (b.text or '')]
        assert not pick, 'pending 任务详情不应出现「加入购物车」入口（仅终态可挑选）'
    finally:
        _cleanup_task_and_cases(api_client, task_id, handles)
