# -*- coding: utf-8 -*-
"""INT-401 P1-3 复验专项走查（ad hoc，真实浏览器）：终态(completed)任务详情
「加入购物车」入口即时出现 + 暂停/停止按钮不误显。

P1-3 原缺陷：终态任务详情 taskStatus 卡 PENDING → 挑选入口不显示、暂停/停止误显。
开发修复：fetchTaskDetails 以 GET /tasks/{id} status 初始化 taskStatus +
useTaskProgress 重连在途 HTTP 兜底结果不丢弃。
本文件在隔离栈 + 隔离库上复现 P1-3 场景并断言两个方向的可见状态。
"""
import psycopg2
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.test_ui_12_int401_cherry_pick import (
    _create_source_task,
    _seed_terminal_results,
    _cleanup_task_and_cases,
    CP_DIALOG,
)
from tests.ui.utils import bootstrap

TASKS_ROUTE = '/tasks'
TASK_DETAIL_MODAL = '.task-detail-modal'


def _hard_sweep_orphans():
    """DB 硬删本文件产生的软删孤儿标签/分组（后端在用例 purge 时自动软删孤标签，
    API delete 对已软删行返回「未找到」——物理行仍留库，需 DB 直删归零）。"""
    conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tags WHERE (name LIKE 'ui401%' OR name LIKE 'ui12b%') AND deleted=true")
            cur.execute("DELETE FROM test_case_groups WHERE (name LIKE 'ui401%' OR name LIKE 'ui12b%') AND deleted=true")
        conn.commit()
    finally:
        conn.close()


def test_p13_completed_detail_pick_visible_pause_stop_hidden(page, api_client):
    """终态任务详情：加入购物车入口即时可见（≤15s），暂停/停止不显示。

    这是 P1-3 打回场景的稳定复现（连续 2 次实测原为必现）：
    造 completed 任务 → 列表打开详情 → 断言正向（有挑选入口）+ 反向（无暂停/停止）。
    """
    task_id, case_ids, handles = _create_source_task(api_client, n_cases=1)
    result_ids = _seed_terminal_results(api_client, task_id)
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
        assert card is not None, f'列表未出现源任务卡片: {handles["task_name"]}'
        view = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
                if b.is_displayed() and b.get_attribute('title') == '查看详情']
        assert view, '任务卡片应有「查看详情」入口'
        page.driver.execute_script('arguments[0].click();', view[0])
        page.wait_visible(TASK_DETAIL_MODAL, timeout=20)

        # 正向：终态任务「加入购物车」入口应即时出现（P1-3 修复后应 <15s）
        pick = WebDriverWait(page.driver, 15).until(
            lambda d: [b for b in d.find_elements(By.CSS_SELECTOR, f'{TASK_DETAIL_MODAL} button')
                       if b.is_displayed() and '加入购物车' in (b.text or '')])
        assert pick, 'completed 任务详情应显示「加入购物车」入口'

        # 反向：暂停/停止按钮不应出现在终态任务详情
        modal_buttons = page.driver.find_elements(
            By.CSS_SELECTOR, f'{TASK_DETAIL_MODAL} button')
        pause = [b for b in modal_buttons if b.is_displayed()
                 and ('暂停' in (b.text or '') or '停止' in (b.text or ''))]
        assert not pause, \
            f'completed 任务详情不应显示暂停/停止按钮：实际={[b.text for b in pause]}'

        # 再验证挑选入口点击后能打开 CherryPickDialog（链路不因本次走查新增断言而断）
        page.driver.execute_script('arguments[0].click();', pick[0])
        WebDriverWait(page.driver, 20).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, CP_DIALOG)))
        page.settle(0.8)
        dialog = page.find_visible(CP_DIALOG, timeout=10)
        assert dialog.is_displayed(), '点击加入购物车应打开 CherryPickDialog'
        print('P1-3 走查通过：completed 详情挑选入口可见、暂停/停止隐藏、向导可开')
    finally:
        _cleanup_task_and_cases(api_client, task_id, handles)
        _hard_sweep_orphans()


def test_p13_regression_running_detail_pause_stop_visible_pick_hidden(page, api_client):
    """回归：运行中(running)任务详情仍显示暂停/停止、无挑选入口（P1-3 修复不破坏活跃态）。

    GET /tasks/{id} status 初始化后 running 任务应立即呈现操作集（暂停/停止），
    不应出现挑选入口（§10 仅终态可挑）。
    """
    task_id, case_ids, handles = _create_source_task(api_client, n_cases=1)
    try:
        # 直写任务为 running（无需执行引擎，仅验证详情操作集门控）
        conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute('UPDATE test_tasks SET status=%s WHERE id=%s',
                            ('running', int(task_id)))
            conn.commit()
        finally:
            conn.close()

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
        assert card is not None, f'列表未出现 running 任务卡片: {handles["task_name"]}'
        view = [b for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button')
                if b.is_displayed() and b.get_attribute('title') == '查看详情']
        assert view, '任务卡片应有「查看详情」入口'
        page.driver.execute_script('arguments[0].click();', view[0])
        page.wait_visible(TASK_DETAIL_MODAL, timeout=20)
        page.settle(1.0)

        # 暂停/停止应可见（运行中操作集）
        modal_buttons = page.driver.find_elements(
            By.CSS_SELECTOR, f'{TASK_DETAIL_MODAL} button')
        pause_stop = [b for b in modal_buttons if b.is_displayed()
                      and ('暂停' in (b.text or '') or '停止' in (b.text or ''))]
        assert pause_stop, 'running 任务详情应显示暂停/停止操作'

        # 挑选入口不应出现（仅终态可挑）
        pick = [b for b in modal_buttons if b.is_displayed()
                and '加入购物车' in (b.text or '')]
        assert not pick, 'running 任务详情不应显示「加入购物车」入口'
        print('P1-3 回归通过：running 详情暂停/停止可见、无挑选入口')
    finally:
        # 数据卫生：running 态任务走软删/purge 会被业务门禁拒绝（不能删运行中任务），
        # 先复位为 completed 再走标准清理链，保证隔离库零残留
        conn = psycopg2.connect(bootstrap.isolated_db_url(), connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute('UPDATE test_tasks SET status=%s WHERE id=%s',
                            ('completed', int(task_id)))
            conn.commit()
        finally:
            conn.close()
        _cleanup_task_and_cases(api_client, task_id, handles)
        _hard_sweep_orphans()
