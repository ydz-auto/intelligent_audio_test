# -*- coding: utf-8 -*-
"""INT-330 UI 实测：RMS-SPL 校准弹窗行级校验阻塞提交 + 按参考生成恒显示 + 分页控件。

覆盖卡面三缺陷的 UI 层（真实浏览器走查，断言可见状态而非仅 DOM 存在）：

缺陷1（P2）：行级校验错误存在时提交按钮禁用（含未触碰的既有坏点——打开弹窗
            即亮红字并阻塞，超范围值不再放行落库）；改回合法值解禁；
缺陷2（P3）：「按参考生成」入口恒显示；已有非空点集时两步确认防误覆盖；
缺陷3（P3）：映射总数 > 默认每页条数时 API 分区出现分页控件，可翻页查看
            （对齐设备侧交互，>100 条不再静默截断的 UI 层证据）。

数据口径：API 造 API + RMS-SPL 映射（隔离库）→ 浏览器实测 → teardown
删除映射 + API（INT-260 零残留红线）。只读语义：除「合法值提交」用例外
不点提交按钮（不触发真实校准写操作）。
"""
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import unique_suffix

SPL_ROUTE = '/SPLMapping'
API_TAB_TEXT = 'API/Realtime RMS-SPL'
CALIB_MODAL_TITLE = 'RMS-SPL 数字校准'
ADD_POINT_BTN_TEXT = '添加校准点'
CALIB_BTN_TEXT = '校准'
SUBMIT_BTN = '.modal-footer .btn-primary'
POINT_ROW = '.point-row'
POINT_ERROR = '.point-error'
REGEN_BTN = '.points-toolbar button'


# ===== 测试数据自建 =====

def _create_api(api_client, suffix):
    """造 1 个被测 API（隔离库；meta 须非空——api_test_service 口径）。"""
    data = api_client.request('POST', '/apis', {
        'name': f'ui330_api_{suffix}',
        'vendor': 'INT-330测试',
        'api_url': 'http://127.0.0.1:59999',
        'description': 'INT-330 校准弹窗 UI 实测',
        'status': 'online',
        'meta': {'purpose': 'INT-330 UI 实测'},
    })
    return str((data.get('data') or {}).get('id') or data.get('id'))


def _create_mapping(api_client, api_id, name, points=None):
    """造 1 条 API/RMS-SPL 映射；points 为空列表=未校准，非空=已校准。"""
    data = api_client.request('POST', '/digital-spl', {
        'api_id': int(api_id),
        'name': name,
        'description': 'INT-330 UI 实测映射',
        'vendor': 'INT-330测试',
        'protocol': 'http',
        'reference_spl': 65,
        'reference_gain_linear': 1.0,
        'calibration_status': 'uncalibrated' if not points else 'calibrated',
        'min_gain_linear': 0.001,
        'max_gain_linear': 10.0,
        'calibration_data': {'points': points or []},
    })
    return str((data.get('data') or {}).get('id') or data.get('id'))


@pytest.fixture()
def int330_data(api_client):
    """API + 映射创建与回收（teardown 全量删除，零残留）。"""
    handles = {'apis': [], 'mappings': []}
    yield handles
    for m in handles['mappings']:
        try:
            api_client.request('DELETE', f'/digital-spl/{m}')
        except Exception:
            pass
    for a in handles['apis']:
        try:
            api_client.request('DELETE', f'/apis/{a}')
        except Exception:
            pass


# ===== 浏览器交互原语 =====

def _open_calibration_modal(page: BasePage, mapping_name: str, timeout: float = 30):
    """SPLMapping → API/Realtime RMS-SPL 页签 → 目标映射「校准」→ 弹窗出现。"""
    page.goto(SPL_ROUTE)
    page.wait_visible('.domain-tab-btn', timeout=timeout)
    page.settle(0.3)
    # 切 API/Realtime RMS-SPL 页签（设备域为 v-show，需按文本找按钮 JS 直点）
    tab = next(t for t in page.find_all('.domain-tab-btn')
               if API_TAB_TEXT in (t.text or ''))
    page.driver.execute_script('arguments[0].click();', tab)
    page.settle(0.3)

    # 目标映射行（API 分区表格唯一选择器 .rms-spl-table）
    row = WebDriverWait(page.driver, timeout).until(
        lambda d: next(
            (r for r in d.find_elements(By.CSS_SELECTOR, '.rms-spl-table tbody tr')
             if mapping_name in (r.text or '')),
            None))
    cal_btn = next(b for b in row.find_elements(By.CSS_SELECTOR, '.cell-actions button')
                   if CALIB_BTN_TEXT in (b.text or ''))
    page.driver.execute_script('arguments[0].click();', cal_btn)

    WebDriverWait(page.driver, timeout).until(
        lambda d: any(m.is_displayed() and CALIB_MODAL_TITLE in m.text
                      for m in d.find_elements(By.CSS_SELECTOR, '.modal-title')))
    page.settle(0.4)
    return page.find_visible('.api-rms-spl-calibration-modal', timeout=10)


def _modal_submit(page: BasePage):
    """弹窗可见的「提交校准」按钮（Scope 到可见 modal footer）。"""
    return next(b for b in page.find_all(SUBMIT_BTN) if b.is_displayed())


def _data_rows(modal):
    """弹窗内点行（排除表头行 .point-row--head）。"""
    return [r for r in modal.find_elements(By.CSS_SELECTOR, POINT_ROW)
            if 'point-row--head' not in (r.get_attribute('class') or '')]


def _click_add_point(page: BasePage, modal):
    btn = next(b for b in modal.find_elements(By.CSS_SELECTOR, '.points-header button')
               if ADD_POINT_BTN_TEXT in (b.text or ''))
    page.driver.execute_script('arguments[0].click();', btn)
    page.settle(0.3)


def _set_row_input(row, idx: int, value: str):
    """行内第 idx 个 number 输入框清空重填（v-model.number 触发 input 事件）。"""
    el = row.find_elements(By.CSS_SELECTOR, 'input')[idx]
    el.clear()
    el.send_keys(str(value))


# ===== 缺陷1（P2）：行级校验阻塞提交 =====

def test_out_of_range_target_spl_blocks_submit(page, api_client, int330_data):
    """手输 targetSpl=500 → 红字 + 提交禁用；改回合法值 → 解禁可提交。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, suffix)
    int330_data['apis'].append(api_id)
    map_name = f'ui330_map_blocksubmit_{suffix}'
    int330_data['mappings'].append(_create_mapping(api_client, api_id, map_name))

    modal = _open_calibration_modal(page, map_name)
    assert not _data_rows(modal), '新映射打开弹窗应为空点集'

    _click_add_point(page, modal)
    rows = _data_rows(modal)
    assert len(rows) == 1, '点击「添加校准点」应出现 1 个空行'

    submit = _modal_submit(page)
    # 空模板行未触碰 → 不阻塞，但无有效点 → 提交仍禁用（validPoints 为空）
    assert not submit.is_enabled(), '空点集下提交应禁用'

    # 手输超范围 targetSpl=500（合法增益）→ 红字 + 禁用
    _set_row_input(rows[0], 0, '500')
    _set_row_input(rows[0], 1, '1')
    page.settle(0.3)
    errors = modal.find_elements(By.CSS_SELECTOR, POINT_ERROR)
    assert any('目标 SPL' in (e.text or '') for e in errors), \
        f'超范围 targetSpl 应显示目标 SPL 红字：实际={[e.text for e in errors]}'
    assert 'has-error' in rows[0].get_attribute('class'), '坏点行应有 has-error 样式'
    assert not submit.is_enabled(), '行级校验错误存在时提交按钮应禁用'

    # 改回合法值 → 红字消失 + 提交可用
    _set_row_input(rows[0], 0, '80')
    page.settle(0.3)
    assert not modal.find_elements(By.CSS_SELECTOR, POINT_ERROR), '合法值下红字应消失'
    assert submit.is_enabled(), '合法点集下提交按钮应可用'


def test_existing_bad_point_blocks_submit_on_mount(page, api_client, int330_data):
    """已校准映射带坏点（targetSpl=500）→ 打开弹窗即亮红字、提交禁用（未触碰也阻塞）。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, suffix)
    int330_data['apis'].append(api_id)
    map_name = f'ui330_map_existingbad_{suffix}'
    int330_data['mappings'].append(_create_mapping(api_client, api_id, map_name, points=[
        {'target_spl': 500, 'gain_linear': 1.0, 'rms_dbfs': None},
        {'target_spl': 65, 'gain_linear': 1.0, 'rms_dbfs': None},
    ]))

    modal = _open_calibration_modal(page, map_name)
    rows = _data_rows(modal)
    assert len(rows) == 2, '既有 2 点应原样渲染'

    errors = modal.find_elements(By.CSS_SELECTOR, POINT_ERROR)
    assert any('目标 SPL' in (e.text or '') for e in errors), \
        '既有坏点挂载即应亮红字（未触碰也要校验）'
    assert 'has-error' in rows[0].get_attribute('class'), '坏点行应有 has-error 样式'
    assert not _modal_submit(page).is_enabled(), '既有坏点存在时提交应禁用（不得静默放行落库）'

    # 修正坏点 → 解禁
    _set_row_input(rows[0], 0, '80')
    page.settle(0.3)
    assert not modal.find_elements(By.CSS_SELECTOR, POINT_ERROR), '修正后红字应消失'
    assert _modal_submit(page).is_enabled(), '修正后提交应可用'


def test_remove_point_keeps_error_on_remaining_row(page, api_client, int330_data):
    """删行后 touched 按行 uid 记账：剩余坏点红字不丢失、提交仍禁用（边角回归）。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, suffix)
    int330_data['apis'].append(api_id)
    map_name = f'ui330_map_delkeep_{suffix}'
    int330_data['mappings'].append(_create_mapping(api_client, api_id, map_name))

    modal = _open_calibration_modal(page, map_name)
    _click_add_point(page, modal)
    _click_add_point(page, modal)
    rows = _data_rows(modal)
    assert len(rows) == 2

    # 第 2 行手输超范围值 → 红字出现
    _set_row_input(rows[1], 0, '500')
    _set_row_input(rows[1], 1, '1')
    page.settle(0.3)
    assert len(modal.find_elements(By.CSS_SELECTOR, POINT_ERROR)) == 1

    # 删除第 1 行 → 红字仍在、提交仍禁用（uid 记账不错位）
    del_btn = rows[0].find_elements(By.CSS_SELECTOR, '.icon-btn')[0]
    page.driver.execute_script('arguments[0].click();', del_btn)
    page.settle(0.3)
    rows = _data_rows(modal)
    assert len(rows) == 1
    assert 'has-error' in rows[0].get_attribute('class'), '删行后剩余坏点红字不应丢失'
    assert not _modal_submit(page).is_enabled(), '剩余坏点存在时提交应仍禁用'


def test_valid_submit_closes_modal(page, api_client, int330_data):
    """合法点集提交：走 onConfirm（单次校准），成功后弹窗关闭（重复 POST 回归）。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, suffix)
    int330_data['apis'].append(api_id)
    map_name = f'ui330_map_validsubmit_{suffix}'
    int330_data['mappings'].append(_create_mapping(api_client, api_id, map_name))

    modal = _open_calibration_modal(page, map_name)
    _click_add_point(page, modal)
    rows = _data_rows(modal)
    _set_row_input(rows[0], 0, '65')
    _set_row_input(rows[0], 1, '1.0')
    page.settle(0.3)

    submit = _modal_submit(page)
    assert submit.is_enabled(), '合法点集下提交应可用'
    page.driver.execute_script('arguments[0].click();', submit)
    page.settle(0.5)

    # 提交成功后弹窗关闭（仅 close，不二次 POST）
    WebDriverWait(page.driver, 15).until(
        lambda d: not any(m.is_displayed() and CALIB_MODAL_TITLE in m.text
                          for m in d.find_elements(By.CSS_SELECTOR, '.modal-title')))


# ===== 缺陷2（P3）：按参考生成入口恒显示 + 两步确认 =====

def test_regenerate_visible_with_existing_points_and_two_step_confirm(page, api_client, int330_data):
    """已有点集时「按参考生成」仍可见；点一次进入确认态不覆盖，再点覆盖为 5 点。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, suffix)
    int330_data['apis'].append(api_id)
    map_name = f'ui330_map_regen_{suffix}'
    int330_data['mappings'].append(_create_mapping(api_client, api_id, map_name, points=[
        {'target_spl': 30, 'gain_linear': 0.5, 'rms_dbfs': None},
        {'target_spl': 90, 'gain_linear': 2.0, 'rms_dbfs': None},
    ]))

    modal = _open_calibration_modal(page, map_name)
    rows = _data_rows(modal)
    assert len(rows) == 2, '既有 2 点应原样渲染'

    # 入口恒显示（原实现已有点集时隐藏）
    regen = next(b for b in modal.find_elements(By.CSS_SELECTOR, REGEN_BTN)
                 if '按参考生成' in (b.text or ''))
    assert regen.is_displayed(), '已有点集时「按参考生成」入口应可见'
    assert 'btn-regenerate--armed' not in (regen.get_attribute('class') or ''), '初始不应处于确认态'

    # 第一次点击：不覆盖，进入确认态
    page.driver.execute_script('arguments[0].click();', regen)
    page.settle(0.3)
    assert len(_data_rows(modal)) == 2, '确认态下不应覆盖既有点集'
    regen = next(b for b in modal.find_elements(By.CSS_SELECTOR, REGEN_BTN)
                 if '按参考生成' in (b.text or '') or '再点一次确认覆盖' in (b.text or ''))
    assert '再点一次确认覆盖当前 2 个校准点' in (regen.text or ''), \
        f'应进入两步确认态：实际按钮文案={regen.text!r}'
    assert 'btn-regenerate--armed' in (regen.get_attribute('class') or ''), '确认态应有警示样式'

    # 第二次点击：覆盖为参考生成的 5 点（65dB 中心 ±20dB / 每 10dB 一点）
    page.driver.execute_script('arguments[0].click();', regen)
    page.settle(0.3)
    rows = _data_rows(modal)
    assert len(rows) == 5, '确认后应覆盖为 5 点'
    targets = [r.find_elements(By.CSS_SELECTOR, 'input')[0].get_attribute('value')
               for r in rows]
    assert [float(t) for t in targets] == [45.0, 55.0, 65.0, 75.0, 85.0], \
        f'参考生成 5 点应为 45/55/65/75/85：实际={targets}'


def test_regenerate_empty_points_generates_immediately(page, api_client, int330_data):
    """空点集时点「按参考生成」直接生成（无需两步确认）。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, suffix)
    int330_data['apis'].append(api_id)
    map_name = f'ui330_map_regenempty_{suffix}'
    int330_data['mappings'].append(_create_mapping(api_client, api_id, map_name))

    modal = _open_calibration_modal(page, map_name)
    regen = next(b for b in modal.find_elements(By.CSS_SELECTOR, REGEN_BTN)
                 if '按参考生成' in (b.text or ''))
    page.driver.execute_script('arguments[0].click();', regen)
    page.settle(0.3)
    rows = _data_rows(modal)
    assert len(rows) == 5, '空点集应直接生成 5 点'
    targets = [r.find_elements(By.CSS_SELECTOR, 'input')[0].get_attribute('value')
               for r in rows]
    assert [float(t) for t in targets] == [45.0, 55.0, 65.0, 75.0, 85.0], \
        f'参考生成 5 点应为 45/55/65/75/85：实际={targets}'


# ===== 缺陷3（P3）：API 分区映射列表分页 =====

def test_api_section_pagination_shows_and_pages(page, api_client, int330_data):
    """映射数 > 默认每页 10 条时出现分页控件，可翻页查看全部（>100 不截断的 UI 证据）。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, suffix)
    int330_data['apis'].append(api_id)
    # 造 12 条映射（> 默认 pageSize 10 触发分页）
    names = [f'ui330_map_pg_{i}_{suffix}' for i in range(12)]
    for n in names:
        int330_data['mappings'].append(_create_mapping(api_client, api_id, n))

    page.goto(SPL_ROUTE)
    page.wait_visible('.domain-tab-btn', timeout=30)
    page.settle(0.3)
    tab = next(t for t in page.find_all('.domain-tab-btn')
               if API_TAB_TEXT in (t.text or ''))
    page.driver.execute_script('arguments[0].click();', tab)

    # 等表格加载出首行
    WebDriverWait(page.driver, 30).until(
        lambda d: any(r.is_displayed() for r in d.find_elements(
            By.CSS_SELECTOR, '.rms-spl-table tbody tr')))
    page.settle(0.5)

    # 分页控件（仅可见的那个 = API 分区；设备分区 v-show 隐藏）
    pag = [p for p in page.find_all('.pagination-container') if p.is_displayed()]
    assert pag, '映射数 > 每页 10 条时 API 分区应出现分页控件'
    page.settle(0.3)

    # 概览统计为全量口径（首张 stat-card 数字 ≥ 12，未被分页截断）
    stat = [c for c in page.find_all('.stats-grid .stat-card') if c.is_displayed()]
    first_num = (stat[0].find_elements(By.CSS_SELECTOR, '.stat-number') or [None])[0]
    total_text = first_num.text if first_num is not None else ''
    assert total_text.isdigit() and int(total_text) >= 12, \
        f'概览映射数应为全量（≥12）：实际={total_text!r}'

    # 首页默认 10 行（pageSize=10）
    rows_p1 = [r for r in page.find_all('.rms-spl-table tbody tr') if r.is_displayed()]
    assert len(rows_p1) == 10, f'首页应恰 10 行：实际={len(rows_p1)}'
    first_p1 = rows_p1[0].text

    # 翻到第 2 页 → 行集合变化（可翻页查看全部）
    next_btn = [b for b in pag[0].find_elements(By.CSS_SELECTOR, '.pagination-btn')
                if '下一页' in (b.text or '') and b.is_enabled()]
    assert next_btn, f'分页控件应有可用的下一页按钮：实际按钮={[b.text for b in pag[0].find_elements(By.CSS_SELECTOR, "button")]}'
    page.driver.execute_script('arguments[0].click();', next_btn[0])
    page.settle(0.4)
    rows_p2 = [r for r in page.find_all('.rms-spl-table tbody tr') if r.is_displayed()]
    assert rows_p2, '翻页后第 2 页应仍有行'
    assert rows_p2[0].text != first_p1, '第 2 页首行应与第 1 页不同（分页生效）'
