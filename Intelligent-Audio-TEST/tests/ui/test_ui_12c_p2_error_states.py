# -*- coding: utf-8 -*-
"""INT-401 审计 P2-1/P2-2 复验专项：加载失败错误态真实浏览器走查（INT-552/INT-551）。

审计发现（前端UX审计员 2026-10-16，INT-401 返工项）：
- P2-1 挑选向导候选/设备加载失败原静默清空成误导性空态；
- P2-2 挑选合并页签溯源加载失败原显示「暂无来源记录」误导文案。

开发修复：CherryPickDialog 引入 candidatesError/deviceError 可见错误条（含重试）、
CherryPickPanel 引入 per-task sourceErrorByTask 错误态（含重试）。

本文件经 Chrome CDP Network.setBlockedURLs 在真实页面模拟接口失败：
① 候选接口失败 → 步骤1 错误条 + 重试恢复（不误现空态）；
② 溯源接口失败 → 展开区错误 + 重试恢复（不误现「暂无来源」）。
只读语义同 test_ui_12：数据自建自清（teardown 零残留）。
"""
import psycopg2
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.test_ui_12_int401_cherry_pick import (
    _create_source_task,
    _seed_terminal_results,
    _cleanup_task_and_cases,
    _cleanup_container_task,
    _open_detail_and_pick,
    CP_DIALOG,
    CP_ROWS,
)
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'
# CherryPickDialog 错误态（INT-551）
CP_ERROR_BAR = '.cp-error-bar'
CP_FILTER_ERROR = '.cp-filter-error'
# 挑选合并页签 + 溯源错误态（INT-552）
SOURCE_LIST = '.merged-source-list'
SOURCE_ERROR = '.merged-source-error'
SOURCE_RETRY = '.merged-source-retry'
SOURCE_ROWS = '.merged-source-row'


def _seed_container_relations(container_task_id: int, result_ids, source_task_id: int,
                              source_task_name: str, source_case_ids):
    """隔离库直写 task_cherry_pick_relations（引用方案 A 溯源快照）——
    使容器任务出现在「挑选合并」页签并可供溯源接口读取。"""
    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            for i, rid in enumerate(result_ids):
                cur.execute(
                    'INSERT INTO task_cherry_pick_relations'
                    ' (cherry_pick_task_id, result_id, source_task_id, source_task_name,'
                    '  source_case_id, source_device_id, source_api_id, created_by_user_id, created_at)'
                    ' VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,NOW())',
                    (int(container_task_id), int(rid), int(source_task_id), source_task_name,
                     str(source_case_ids[i]), 7 + i, None))
        conn.commit()
    finally:
        conn.close()


def _set_blocked_urls(page, patterns):
    """CDP 网络阻断（模拟接口失败）；patterns 为 URL 子串列表，空列表解除阻断。"""
    page.driver.execute_cdp_cmd('Network.enable', {})
    page.driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': patterns})


@pytest.fixture()
def cherry_pick_source(api_client):
    """造 2 用例 1 源任务 + 隔离库直写终态与执行结果（挑选数据源）。

    teardown 全量回收（零残留）：源任务/用例/标签/分组。
    """
    task_id, case_ids, handles = _create_source_task(api_client, n_cases=2)
    result_ids = _seed_terminal_results(api_client, task_id)
    yield {'task_id': task_id, 'case_ids': case_ids, 'result_ids': result_ids,
           'name': handles['task_name'], **handles}
    _cleanup_task_and_cases(api_client, task_id, handles)


def test_p2_1_candidate_error_bar_and_retry(page, cherry_pick_source):
    """P2-1：候选接口失败 → 步骤1 可见错误条（含重试），空态不误现；重试恢复。"""
    dialog = _open_detail_and_pick(page, cherry_pick_source['name'])
    # 候选初载成功：本任务 2 条执行结果
    WebDriverWait(page.driver, 20).until(
        lambda d: len(dialog.find_elements(By.CSS_SELECTOR, CP_ROWS)) >= 1)
    page.settle(0.5)
    assert dialog.find_elements(By.CSS_SELECTOR, CP_ERROR_BAR) == [], \
        '初载成功时不应出现错误条'

    # 阻断候选接口 → 切换执行状态筛选触发 loadCandidates → 请求失败
    _set_blocked_urls(page, ['*cherry-picks/candidates*'])
    status_select = dialog.find_element(By.CSS_SELECTOR, 'select.cp-input')
    page.driver.execute_script(
        "var s=arguments[0]; s.value='completed'; s.dispatchEvent(new Event('change',{bubbles:true}));",
        status_select)
    page.settle(1.2)

    err = WebDriverWait(page.driver, 15).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, CP_ERROR_BAR)))
    assert '执行结果加载失败' in (err.text or ''), \
        f'候选失败应显示可见错误条（含失败原因）：实际 {err.text!r}'
    retry = err.find_elements(By.CSS_SELECTOR, 'button')
    assert retry and '重试' in (retry[0].text or ''), '错误条应含重试按钮'

    # 解除阻断 → 重试 → 候选恢复（错误条消失 + 结果行可见）
    _set_blocked_urls(page, [])
    page.driver.execute_script('arguments[0].click();', retry[0])
    WebDriverWait(page.driver, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, CP_ERROR_BAR)) == 0)
    WebDriverWait(page.driver, 20).until(
        lambda d: len(dialog.find_elements(By.CSS_SELECTOR, CP_ROWS)) >= 1)
    page.settle(0.3)
    assert dialog.find_elements(By.CSS_SELECTOR, CP_ROWS), '重试后候选列表应恢复'


def test_p2_2_source_error_bar_and_retry(page, api_client, cherry_pick_source):
    """P2-2：溯源接口失败 → 展开区可见错误（含重试），「暂无来源」空态不误现；重试恢复。

    容器任务 + 溯源关系经隔离库直写构造（复用 test_ui_12 溯源主链数据形态）。
    """
    # 容器任务：API 造任务 + 直写关系表
    suffix = unique_suffix()
    container_name = f'ui401_错误态容器_{suffix}'
    data = api_client.request('POST', '/tasks', {
        'name': container_name,
        'type': 'e2e',
        'description': 'INT-401 P2-2 溯源错误态实测容器任务',
        'caseIds': cherry_pick_source['case_ids'],
    })
    container_id = (data.get('data') or {}).get('id')
    assert container_id, f'API 造容器任务失败: {str(data)[:200]}'
    _seed_container_relations(
        container_id,
        cherry_pick_source['result_ids'],
        int(cherry_pick_source['task_id']),
        cherry_pick_source['name'],
        [str(c) for c in cherry_pick_source['case_ids']],
    )
    try:
        page.goto(f'{TASKS_ROUTE}?tab=cherryPick')
        page.wait_visible('.task-card', timeout=25)
        page.settle(0.5)

        def _container_wrap():
            for wrap in page.find_all('.published-card-wrap'):
                titles = wrap.find_elements(By.CSS_SELECTOR, '.task-title')
                if titles and container_name in (titles[0].text or ''):
                    return wrap
            return None

        wrap = WebDriverWait(page.driver, 15).until(lambda d: _container_wrap())

        # 阻断溯源接口 → 展开 → 溯源加载失败 → 错误态
        _set_blocked_urls(page, ['*cherry-picks/*/source*'])
        toggle = wrap.find_element(By.CSS_SELECTOR, SOURCE_LIST + ' .merged-source-list-title')
        page.driver.execute_script('arguments[0].click();', toggle)
        err = WebDriverWait(page.driver, 15).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, SOURCE_ERROR)))
        assert '溯源加载失败' in (err.text or ''), \
            f'溯源失败应显示可见错误：实际 {err.text!r}'
        assert '暂无来源' not in (err.text or ''), \
            '失败态不应误现「暂无来源记录」空态文案'
        retry = err.find_elements(By.CSS_SELECTOR, SOURCE_RETRY)
        assert retry, '溯源错误态应含重试按钮'

        # 解除阻断 → 重试 → 溯源恢复（来源任务分组可见）
        _set_blocked_urls(page, [])
        page.driver.execute_script('arguments[0].click();', retry[0])
        WebDriverWait(page.driver, 20).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, SOURCE_ERROR) == [])
        rows = WebDriverWait(page.driver, 20).until(
            lambda d: [r for r in d.find_elements(By.CSS_SELECTOR, SOURCE_LIST + ' ' + SOURCE_ROWS)
                       if r.is_displayed()])
        assert any(cherry_pick_source['name'] in (r.text or '') for r in rows), \
            f'重试后溯源应显示来源任务分组：{cherry_pick_source["name"]}'
    finally:
        _cleanup_container_task(api_client, container_id)
