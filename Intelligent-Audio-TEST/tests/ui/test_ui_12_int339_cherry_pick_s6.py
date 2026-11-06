# -*- coding: utf-8 -*-
"""INT-339 S6 前端打回修复验收（浏览器实测）。

前端 UX 审计（2026-10-15 10:19Z）打回、开发工程师A 修复轮（commit 46bf7b28）
新增确认项，本实测走真实浏览器验证可见状态（test_ui_05 先例，断言可见
状态而非仅 DOM 存在）：

- P2-1 筛选变更重置页码：第 2 页改执行状态 → 回到第 1 页且有结果
- P2-2 saveAsSet DTO camelCase 收敛：另存挑选集成功提示/挑选集行显示条数
  （视图层读 itemCount，snake_case 不再泄漏）
- P2-3 溯源展开/收起对称 + 多卡独立缓存：标题行常显可再收起；展开卡 A 后
  展开卡 B，卡 A 溯源不被覆盖（toggleSource 漏加 taskId 修复——展开必渲染）
- P3-1 候选/购物车行设备显示名称（非裸 ID）

数据口径：全部写入隔离库 intelligent_audio_test_test（栈门禁强制），
自建自清；源任务经 API 创建 + 直写 completed，test_results 直插，容器任务
经真实 checkout_merge 下单生成（源任务保持原样红线不触碰）。
"""
import time

import psycopg2
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils import bootstrap
from tests.ui.utils.api_client import unique_suffix

TASKS_ROUTE = '/tasks'
PICK_TAB_TEXT = '挑选合并'
PICK_CART_ENTRY = '.pick-cart-entry'
CP_DIALOG = '.cp-dialog'
CP_CLOSE = '.cp-close'
CP_ROW = '.cp-row'
CP_ROW_META = '.cp-row-meta'
CP_GROUP_TITLE = '.cp-group-title'
CP_PAGINATION = '.cp-pagination'
CP_FILTERS_SELECT = '.cp-filters select'
CP_CHECKBOX = '.cp-checkbox'
CP_TOOLBAR_INFO = '.cp-toolbar-info'
CP_SETS = '.cp-sets .cp-set-row'
CP_SET_NAME = '.cp-set-name'
CP_SET_COUNT = '.cp-group-count'


# ==================== 数据准备（API + 隔离库直写） ====================

def _insert_device(db_url: str, name: str) -> int:
    conn = psycopg2.connect(db_url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO devices (name, model, type, system, system_version,"
                " app_name, app_version, status, deleted, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())"
                " RETURNING id",
                (name, 'ui339-model', 'android', 'android', '14', 'app', '1.0',
                 'online', False))
            dev_id = cur.fetchone()[0]
        conn.commit()
        return int(dev_id)
    finally:
        conn.close()


def _create_task(api_client, name: str, case_ids) -> int:
    data = api_client.request('POST', '/tasks', {
        'name': name, 'type': 'e2e',
        'description': 'INT-339 S6 浏览器实测源任务',
        'caseIds': case_ids,
    })
    tid = (data.get('data') or {}).get('id')
    assert tid, f'API 造任务失败: {str(data)[:200]}'
    return int(tid)


def _complete_task(db_url: str, task_id: int) -> None:
    conn = psycopg2.connect(db_url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE test_tasks SET status='completed' WHERE id=%s",
                        (task_id,))
        conn.commit()
    finally:
        conn.close()


def _insert_result(db_url: str, task_id: int, case_id: str, device_id,
                   exec_status: str) -> int:
    conn = psycopg2.connect(db_url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO test_results (task_id, test_case_id, device_id,"
                " execution_status, excluded, created_at)"
                " VALUES (%s, %s, %s, %s, 0, now()) RETURNING id",
                (task_id, case_id, device_id, exec_status))
            rid = cur.fetchone()[0]
        conn.commit()
        return int(rid)
    finally:
        conn.close()


def _checkout_merge(api_client, result_ids, name: str) -> int:
    api_client.request('POST', '/tasks/cherry-picks/cart/items',
                       {'result_ids': result_ids})
    data = api_client.request('POST', '/tasks/cherry-picks/cart/checkout',
                              {'action': 'merge', 'name': name})
    d = data.get('data') or {}
    tid = d.get('taskId') or d.get('task_id')
    assert tid, f'下单 merge 失败: {str(data)[:200]}'
    return int(tid)


def _setup_cherry_data(api_client):
    """造源任务 A（2 结果）/ 源任务 B（55 结果，分页用）+ 2 个挑选合并容器任务。"""
    suffix = unique_suffix()
    db_url = bootstrap.isolated_db_url()
    device_name = f'ui339_设备_{suffix}'
    device_id = _insert_device(db_url, device_name)
    group_name = f'ui339_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-339 S6 浏览器实测分组')
    case_ids = [
        api_client.create_testcase(
            f'ui339_用例1_{suffix}', group=group_name,
            description='INT-339 S6 浏览器实测用例'),
        api_client.create_testcase(
            f'ui339_用例2_{suffix}', group=group_name,
            description='INT-339 S6 浏览器实测用例'),
    ]
    task_a_name = f'ui339_源A_{suffix}'
    task_a_id = _create_task(api_client, task_a_name, case_ids)
    task_b_name = f'ui339_源B_{suffix}'
    task_b_id = _create_task(api_client, task_b_name, case_ids)
    _complete_task(db_url, task_a_id)
    _complete_task(db_url, task_b_id)
    res_a1 = _insert_result(db_url, task_a_id, case_ids[0], device_id, 'completed')
    res_a2 = _insert_result(db_url, task_a_id, case_ids[1], device_id, 'completed')
    bulk_ids = []
    for i in range(55):
        bulk_ids.append(_insert_result(
            db_url, task_b_id, f'ui339_bulk{i}_{suffix}', None, 'completed'))
    c1_name = f'ui339_容器1_{suffix}'
    c1_id = _checkout_merge(api_client, [res_a1, res_a2], c1_name)
    c2_name = f'ui339_容器2_{suffix}'
    c2_id = _checkout_merge(api_client, [bulk_ids[0]], c2_name)
    return {
        'suffix': suffix, 'db_url': db_url,
        'device_name': device_name, 'device_id': device_id,
        'group_id': group_id, 'group_name': group_name, 'case_ids': case_ids,
        'task_a_id': str(task_a_id), 'task_a_name': task_a_name,
        'task_b_id': str(task_b_id), 'task_b_name': task_b_name,
        'res_a1': res_a1, 'res_a2': res_a2, 'bulk_result_ids': bulk_ids,
        'c1_id': str(c1_id), 'c1_name': c1_name,
        'c2_id': str(c2_id), 'c2_name': c2_name,
    }


def _cleanup_cherry_data(api_client, h):
    """teardown：购物车/挑选集 → 关系/结果/设备 → 任务（软删+purge）→ 用例/分组。

    顺序优先解除 FK（task_cherry_pick_relations.cherry_pick_task_id →
    test_tasks.id），再删任务；全部 best-effort。
    """
    db_url = h['db_url']
    # 1. API 清购物车 + 删我的挑选集（先解除 set_items FK）
    try:
        api_client.request('DELETE', '/tasks/cherry-picks/cart/items')
    except Exception:
        pass
    try:
        sets = api_client.request('GET', '/tasks/cherry-picks/sets')
        sets = (sets.get('data') or {}).get('items') or []
        for s in sets:
            name = str(s.get('name', ''))
            if name.startswith('ui339_'):
                try:
                    api_client.request('DELETE', f"/tasks/cherry-picks/sets/{s['id']}")
                except Exception:
                    pass
    except Exception:
        pass
    # 2. 直接 DB：关系 → 结果 → 设备 → 残留购物车/挑选集（API 失败兜底）
    conn = psycopg2.connect(db_url, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'DELETE FROM task_cherry_pick_relations'
                ' WHERE cherry_pick_task_id IN (%s, %s)',
                (int(h['c1_id']), int(h['c2_id'])))
            all_res = [h['res_a1'], h['res_a2']] + h['bulk_result_ids']
            cur.execute('DELETE FROM test_results WHERE id = ANY(%s)', (all_res,))
            cur.execute('DELETE FROM devices WHERE id = %s', (h['device_id'],))
            cur.execute(
                'DELETE FROM cherry_pick_set_items WHERE set_id IN'
                ' (SELECT id FROM cherry_pick_sets WHERE name LIKE %s)',
                (r'ui339\_%',))
            cur.execute(
                'DELETE FROM cherry_pick_sets WHERE name LIKE %s', (r'ui339\_%',))
            cur.execute(
                'DELETE FROM cherry_pick_cart_items'
                ' WHERE source_task_id IN (%s, %s)',
                (int(h['task_a_id']), int(h['task_b_id'])))
        conn.commit()
    finally:
        conn.close()
    # 3. 任务软删 + purge（容器 C1/C2 与源任务 A/B）
    for tid in (h['c1_id'], h['c2_id'], h['task_a_id'], h['task_b_id']):
        try:
            api_client.request('POST', '/tasks/batch-action',
                               {'action': 'delete', 'task_ids': [int(tid)]})
        except Exception:
            pass
        try:
            api_client.request('DELETE', f'/tasks/{tid}/purge')
        except Exception:
            pass
    # 4. 用例 + 分组回收
    for tc_id in h.get('case_ids', []):
        try:
            api_client.delete_testcase(tc_id)
        except Exception:
            pass
    try:
        api_client.delete_group(h['group_id'])
    except Exception:
        pass


@pytest.fixture(scope='module')
def cherry_pick_s6_data(api_client):
    handles = _setup_cherry_data(api_client)
    try:
        yield handles
    finally:
        _cleanup_cherry_data(api_client, handles)


# ==================== 浏览器交互辅助 ====================

def _find_button_by_text(page, text: str, timeout: float = 12):
    def _find(d):
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and text in (b.text or ''):
                return b
        return None
    return WebDriverWait(page.driver, timeout).until(_find)


def _find_button_in(page, scope_css: str, text: str, timeout: float = 12):
    """在指定容器内找按钮（防跨容器误配：对话框外/弹窗后同文案按钮）。"""
    def _find(d):
        scopes = d.find_elements(By.CSS_SELECTOR, scope_css)
        if not scopes:
            return None
        for b in scopes[0].find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and text in (b.text or ''):
                return b
        return None
    return WebDriverWait(page.driver, timeout).until(_find)


def _js_click_button(page, scope_css: str, text: str, timeout: float = 20):
    """容器内找按钮并 JS 点击；弹窗重渲染致元素 stale / 按钮晚渲染致 timeout 时
    重找重点（稳定交互）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            btn = _find_button_in(page, scope_css, text, timeout=6)
            page.driver.execute_script('arguments[0].click();', btn)
            return
        except Exception as exc:
            msg = str(exc).lower()
            if 'stale' not in msg and 'timeout' not in msg:
                raise
            page.settle(0.4)
    raise RuntimeError(f'点击按钮超时（重试耗尽）: {text} in {scope_css}')


def _find_card_by_name(page, name: str, timeout: float = 20):
    def _find(d):
        for card in d.find_elements(By.CSS_SELECTOR, '.task-card'):
            if not card.is_displayed():
                continue
            titles = card.find_elements(By.CSS_SELECTOR, '.task-title')
            if titles and name in (titles[0].text or ''):
                return card
        return None
    return WebDriverWait(page.driver, timeout).until(_find)


def _find_card_button(card, label: str):
    for b in card.find_elements(By.CSS_SELECTOR, '.task-actions button'):
        if b.is_displayed() and b.get_attribute('title') == label:
            return b
    return None


def _wait_rows(page, n: int, timeout: float = 20):
    WebDriverWait(page.driver, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, CP_ROW)) == n)
    page.settle(0.4)


def _wait_filter_select(page, option_value: str, timeout: float = 20):
    """等待 .cp-filters 里某个 select 出现指定 value 的 option，返回该 select。"""
    def _find(d):
        for sel in d.find_elements(By.CSS_SELECTOR, CP_FILTERS_SELECT):
            opts = sel.find_elements(By.TAG_NAME, 'option')
            if any(o.get_attribute('value') == option_value for o in opts):
                return sel
        return None
    return WebDriverWait(page.driver, timeout).until(_find)


def _page_indicator(page) -> str:
    for el in page.find_all(f'{CP_PAGINATION} span'):
        txt = el.text.strip()
        if txt.startswith('第'):
            return txt
    return ''


def _open_pick_dialog_from_detail(page, task_id, task_name, timeout: float = 40):
    """任务详情「加入购物车」入口 → CherryPickDialog（INT-401 presetTaskId 预筛选）。"""
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-card', timeout=timeout)
    page.settle(0.5)
    card = _find_card_by_name(page, task_name)
    view = _find_card_button(card, '查看详情')
    assert view is not None, f'任务卡片缺「查看详情」入口: {task_name}'
    page.driver.execute_script('arguments[0].click();', view)
    page.wait_visible('.task-detail-modal', timeout=timeout)
    page.settle(0.8)
    add = _find_button_in(page, '.task-detail-modal', '加入购物车', timeout=40)
    assert add is not None, '任务详情缺「加入购物车」入口（任务应为终态）'
    page.driver.execute_script('arguments[0].click();', add)
    page.wait_visible(CP_DIALOG, timeout=25)
    page.settle(0.8)


def _find_card_wrap(page, name: str, timeout: float = 25):
    """挑选合并面板中按任务名找卡片容器（含溯源列表）。"""
    def _find(d):
        for wrap in d.find_elements(By.CSS_SELECTOR, '.published-card-wrap'):
            titles = wrap.find_elements(By.CSS_SELECTOR, '.task-title')
            if titles and name in (titles[0].text or ''):
                return wrap
        return None
    return WebDriverWait(page.driver, timeout).until(_find)


def _source_title(wrap):
    return wrap.find_element(By.CSS_SELECTOR, '.merged-source-list-title')


def _chevron(wrap):
    return wrap.find_element(By.CSS_SELECTOR, '.merged-source-toggle')


def _is_source_body_visible(wrap) -> bool:
    bodies = wrap.find_elements(By.CSS_SELECTOR, '.merged-source-body')
    return bool(bodies) and bodies[0].is_displayed()


def _wait_source_rows(wrap, timeout: float = 15):
    WebDriverWait(wrap, timeout).until(
        lambda w: w.find_elements(By.CSS_SELECTOR, '.merged-source-row'))
    return wrap.find_element(By.CSS_SELECTOR, '.merged-source-body')


# ==================== 用例 ====================

def test_pick_dialog_candidate_device_name(page, cherry_pick_s6_data):
    """P3-1：候选行设备显示名称（非裸 ID）；任务详情加购入口预筛选本任务结果。"""
    h = cherry_pick_s6_data
    _open_pick_dialog_from_detail(page, h['task_a_id'], h['task_a_name'])
    _wait_rows(page, 2)
    metas = [el.text for el in page.find_all(CP_ROW_META)]
    assert len(metas) == 2, f'预筛选后应恰 2 条候选（实际 {len(metas)}）'
    for m in metas:
        assert f'设备 {h["device_name"]}' in m, f'候选行设备未显示名称: {m!r}'
    page.js_click(CP_CLOSE)


def test_save_as_set_shows_item_count(page, api_client, cherry_pick_s6_data):
    """P2-2：另存挑选集 → 挑选集行显示条数（视图读 itemCount）；购物车行设备名（P3-1）。"""
    h = cherry_pick_s6_data
    set_name = f'ui339_挑选集_{h["suffix"]}'
    try:
        _open_pick_dialog_from_detail(page, h['task_a_id'], h['task_a_name'])
        _wait_rows(page, 2)
        # 全选本页（2 条候选）→ 加购按钮计数（2）
        _js_click_button(page, CP_DIALOG, '全选本页')
        page.settle(0.3)
        add = _find_button_in(page, CP_DIALOG, '加入购物车')
        assert '（2）' in (add.text or ''), f'加购按钮计数异常: {add.text!r}'
        _js_click_button(page, CP_DIALOG, '加入购物车')
        # 购物车步：共 2 条 + 行设备名称
        WebDriverWait(page.driver, 15).until(
            lambda d: '共 2 条' in ' '.join(
                el.text for el in d.find_elements(By.CSS_SELECTOR, CP_TOOLBAR_INFO)))
        cart_metas = [el.text for el in page.find_all(CP_ROW_META)]
        assert any(f'设备 {h["device_name"]}' in m for m in cart_metas), \
            f'购物车行设备名缺失: {cart_metas!r}'
        # 另存挑选集
        _js_click_button(page, CP_DIALOG, '另存为挑选集')
        page.wait_visible('.input-confirm-modal', timeout=12)
        page.fill('.input-confirm-modal .form-input', set_name)
        _js_click_button(page, '.input-confirm-modal', '保存')
        # 挑选集行出现并显示条数（itemCount）
        WebDriverWait(page.driver, 15).until(
            lambda d: any(set_name in (el.text or '')
                          for el in d.find_elements(By.CSS_SELECTOR, CP_SET_NAME)))
        rows = [r for r in page.find_all(CP_SETS)
                if set_name in (r.find_element(By.CSS_SELECTOR, CP_SET_NAME).text or '')]
        assert rows, '另存后挑选集行未出现'
        count_text = rows[0].find_element(By.CSS_SELECTOR, CP_SET_COUNT).text
        assert '2 条' in count_text, f'挑选集行条数显示异常: {count_text!r}'
        page.js_click(CP_CLOSE)
    finally:
        try:
            api_client.request('DELETE', '/tasks/cherry-picks/cart/items')
        except Exception:
            pass
        try:
            sets = api_client.request('GET', '/tasks/cherry-picks/sets')
            sets = (sets.get('data') or {}).get('items') or []
            for s in sets:
                if str(s.get('name', '')) == set_name:
                    api_client.request(
                        'DELETE', f"/tasks/cherry-picks/sets/{s['id']}")
        except Exception:
            pass


def test_filter_change_resets_page_one(page, cherry_pick_s6_data):
    """P2-1：第 2 页改执行状态筛选 → 回到第 1 页且有结果。"""
    h = cherry_pick_s6_data
    page.goto(TASKS_ROUTE)
    page.wait_visible(PICK_CART_ENTRY, timeout=30)
    page.js_click(PICK_CART_ENTRY)
    page.wait_visible(CP_DIALOG, timeout=20)
    # 来源任务 = 源B（55 结果 → 分页）
    sel_task = _wait_filter_select(page, h['task_b_id'])
    Select(sel_task).select_by_value(h['task_b_id'])
    WebDriverWait(page.driver, 25).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, CP_ROW)) == 50)
    page.settle(1.0)
    assert len(page.find_all(CP_ROW)) == 50, '筛选后候选列表不稳定'
    assert _page_indicator(page) == '第 1 页', f'初始页码异常: {_page_indicator(page)!r}'
    # 下一页 → 第 2 页（余 5 条）
    page.driver.execute_script(
        'arguments[0].click();', _find_button_in(page, CP_DIALOG, '下一页'))
    WebDriverWait(page.driver, 15).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, CP_ROW)) == 5)
    page.settle(0.4)
    assert _page_indicator(page) == '第 2 页', f'翻页后页码异常: {_page_indicator(page)!r}'
    # 改执行状态（completed）→ 回到第 1 页且有结果（P2-1 判定点）
    sel_exec = _wait_filter_select(page, 'completed')
    Select(sel_exec).select_by_value('completed')
    WebDriverWait(page.driver, 25).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, CP_ROW)) == 50)
    page.settle(1.0)
    assert len(page.find_all(CP_ROW)) == 50, '筛选变更后候选列表不稳定'
    assert _page_indicator(page) == '第 1 页', \
        f'筛选变更未重置页码: {_page_indicator(page)!r}'
    page.js_click(CP_CLOSE)


def test_panel_source_trace_expand_collapse_per_card(page, cherry_pick_s6_data):
    """P2-3：溯源标题行常显可展开/收起；多卡独立缓存互不覆盖。"""
    h = cherry_pick_s6_data
    page.goto(TASKS_ROUTE)
    page.wait_visible('.task-tab', timeout=30)
    tab = None
    for t in page.find_all('.task-tab'):
        if t.is_displayed() and PICK_TAB_TEXT in (t.text or ''):
            tab = t
            break
    assert tab is not None, '任务列表无「挑选合并」页签'
    page.driver.execute_script('arguments[0].click();', tab)
    # 容器 C1 卡片（含溯源列表，初始收起）
    wrap1 = _find_card_wrap(page, h['c1_name'], timeout=30)
    assert not _is_source_body_visible(wrap1), '溯源列表初始应为收起'
    assert 'fa-chevron-down' in _chevron(wrap1).get_attribute('class'), \
        '初始 chevron 应为向下（收起态）'
    # 展开 C1 → 溯源渲染源A + 2 条
    page.driver.execute_script(
        'arguments[0].click();', _source_title(wrap1))
    body1 = _wait_source_rows(wrap1)
    assert 'fa-chevron-up' in _chevron(wrap1).get_attribute('class'), \
        '展开态 chevron 应为向上'
    txt1 = body1.text
    assert h['task_a_name'] in txt1, f'C1 溯源未显示源A: {txt1!r}'
    assert '结果 2 条' in txt1, f'C1 溯源条数异常: {txt1!r}'
    # 再点标题 → 收起（P2-3：标题行常显可再收起）
    page.driver.execute_script(
        'arguments[0].click();', _source_title(wrap1))
    WebDriverWait(page.driver, 8).until(
        lambda d: not _is_source_body_visible(wrap1))
    assert 'fa-chevron-down' in _chevron(wrap1).get_attribute('class'), \
        '收起态 chevron 应为向下'
    # 再展开 C1，然后展开 C2 → C1 溯源不被 C2 覆盖（多卡独立缓存）
    page.driver.execute_script(
        'arguments[0].click();', _source_title(wrap1))
    _wait_source_rows(wrap1)
    wrap2 = _find_card_wrap(page, h['c2_name'])
    page.driver.execute_script(
        'arguments[0].click();', _source_title(wrap2))
    body2 = _wait_source_rows(wrap2)
    txt2 = body2.text
    assert h['task_b_name'] in txt2, f'C2 溯源未显示源B: {txt2!r}'
    assert '结果 1 条' in txt2, f'C2 溯源条数异常: {txt2!r}'
    txt1_after = wrap1.find_element(
        By.CSS_SELECTOR, '.merged-source-body').text
    assert h['task_a_name'] in txt1_after, f'C1 溯源被 C2 覆盖: {txt1_after!r}'
    assert h['task_b_name'] not in txt1_after, 'C1 溯源混入 C2 内容'
