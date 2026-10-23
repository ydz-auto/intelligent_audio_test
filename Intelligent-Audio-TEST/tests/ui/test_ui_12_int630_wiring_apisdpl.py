# -*- coding: utf-8 -*-
"""INT-630 UI 实测：接线·API适配/SPL 服务域 —— RMS SPL API 下拉全量 + 受影响页附图。

覆盖本卡改动（apisApi.getAll 查询参数 camelCase Domain → snake_case query，
对齐 api_gateway/schemas/api.py::ApiListQuery）在真实浏览器下的可见行为，
并对受影响页（API 定义管理 /SPLMapping 物理域与 API/Realtime RMS-SPL 域）
采集浅色/深色与关键交互态截图证据（devloop-protocol §2.5.3）。

数据口径：API + RMS-SPL 映射（隔离库）→ 浏览器实测 → teardown 删除
（INT-260 零残留红线）。
"""
import os

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import unique_suffix

SPL_ROUTE = '/SPLMapping'
API_TAB_TEXT = 'API/Realtime RMS-SPL'
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'artifacts', 'int630_evidence')


# ===== 测试数据自建 =====

def _create_api(api_client, name, suffix):
    """造 1 个被测 API（隔离库；meta 须非空——api_test_service 口径）。"""
    data = api_client.request('POST', '/apis', {
        'name': name,
        'vendor': 'INT-630测试',
        'endpoints': [{'endpoint': 'http://127.0.0.1:59998',
                       'max_process': 5, 'max_timeout': 30,
                       'max_audio_duration': 60, 'priority': 0}],
        'description': 'INT-630 接线 UI 实测',
        'status': 'online',
        'meta': {'purpose': f'INT-630 UI 实测 {suffix}'},
    })
    return str((data.get('data') or {}).get('id') or data.get('id'))


def _create_mapping(api_client, api_id, name):
    """造 1 条 API/RMS-SPL 映射（未校准，供页面展示）。"""
    data = api_client.request('POST', '/digital-spl', {
        'api_id': int(api_id),
        'name': name,
        'description': 'INT-630 UI 实测映射',
        'vendor': 'INT-630测试',
        'protocol': 'http',
        'reference_spl': 65,
        'reference_gain_linear': 1.0,
        'calibration_status': 'uncalibrated',
        'min_gain_linear': 0.001,
        'max_gain_linear': 10.0,
        'calibration_data': {'points': []},
    })
    return str((data.get('data') or {}).get('id') or data.get('id'))


@pytest.fixture()
def int630_data(api_client):
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

def _switch_to_api_rms_tab(page: BasePage, timeout: float = 30):
    """SPLMapping → API/Realtime RMS-SPL 页签（设备域为 v-show，JS 直点）。"""
    page.goto(SPL_ROUTE)
    page.wait_visible('.domain-tab-btn', timeout=timeout)
    page.settle(0.3)
    tab = next(t for t in page.find_all('.domain-tab-btn')
               if API_TAB_TEXT in (t.text or ''))
    page.driver.execute_script('arguments[0].click();', tab)
    page.settle(0.5)


def _api_filter_select(page: BasePage) -> 'selenium WebElement':
    """API 分区「所有 API」过滤下拉（唯一含『所有 API』选项的 select）。"""
    return next(
        s for s in page.find_all('select.form-input')
        if any('所有 API' in (o.text or '') for o in s.find_elements(By.TAG_NAME, 'option')))


def _mapping_modal_api_select(page: BasePage) -> 'selenium WebElement':
    """「添加 RMS-SPL 映射」弹窗内的『关联被测 API』select。"""
    modal = page.find_visible('.modal-content, .crud-form-modal', timeout=15)
    sel = next(
        s for s in modal.find_elements(By.CSS_SELECTOR, 'select')
        if any(o.text or o.get_attribute('value')
               for o in s.find_elements(By.TAG_NAME, 'option')))
    return sel


# ===== 核心回归：RMS SPL 配置页 API 下拉完整列出全部被测 API =====

def test_api_filter_dropdown_lists_all_apis(page, api_client, int630_data):
    """>10 个被测 API 时，API 过滤下拉应完整列出全部（per_page 不再截断）。"""
    suffix = unique_suffix()
    names = [f'ui630_api_{i}_{suffix}' for i in range(12)]
    for n in names:
        int630_data['apis'].append(_create_api(api_client, n, suffix))

    _switch_to_api_rms_tab(page)

    # 等 API 过滤下拉出现且选项就位（fetchApis 异步）
    WebDriverWait(page.driver, 30).until(
        lambda d: any('所有 API' in (o.text or '')
                      for o in d.find_elements(By.CSS_SELECTOR, 'select.form-input option')))
    page.settle(0.8)

    api_select = _api_filter_select(page)
    option_texts = [(o.text or '') for o in api_select.find_elements(By.TAG_NAME, 'option')]
    assert option_texts[0] == '所有 API', f'下拉首项应为「所有 API」：实际={option_texts[0]!r}'
    for n in names:
        assert any(n in t for t in option_texts), f'API 过滤下拉应包含被测 API {n!r}'
    assert len(option_texts) >= 13, \
        f'下拉应 ≥13 项（所有API + 12 被测 API）：实际 {len(option_texts)} 项'


def test_mapping_modal_api_options_list_all_apis(page, api_client, int630_data):
    """「添加 RMS-SPL 映射」弹窗的『关联被测 API』下拉同样列出全部（>10 不再截断）。"""
    suffix = unique_suffix()
    names = [f'ui630_mapapi_{i}_{suffix}' for i in range(12)]
    for n in names:
        int630_data['apis'].append(_create_api(api_client, n, suffix))

    _switch_to_api_rms_tab(page)
    page.settle(0.8)

    # 等 API 过滤下拉就位（fetchApis 完成），再开新增映射弹窗
    WebDriverWait(page.driver, 30).until(
        lambda d: any('所有 API' in (o.text or '')
                      for o in d.find_elements(By.CSS_SELECTOR, 'select.form-input option')))
    page.settle(0.3)
    add_btn = next(b for b in page.find_all('button')
                   if '添加 RMS-SPL 映射' in (b.text or ''))
    page.driver.execute_script('arguments[0].click();', add_btn)
    page.settle(0.6)

    api_sel = _mapping_modal_api_select(page)
    opt_texts = [(o.text or '') for o in api_sel.find_elements(By.TAG_NAME, 'option')]
    for n in names:
        assert any(n in t for t in opt_texts), f'映射弹窗 API 下拉应包含 {n!r}'
    assert len(opt_texts) >= 12, \
        f'映射弹窗 API 下拉应 ≥12 项（12 被测 API）：实际 {len(opt_texts)} 项'


# ===== 受影响页截图证据（浅色 + 深色 + 关键交互态） =====

def _snap(page: BasePage, name: str):
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    path = os.path.join(EVIDENCE_DIR, name)
    page.driver.save_screenshot(path)
    print(f'[INT-630] 截图: {path}')
    return path


def test_evidence_screenshots(page, api_client, int630_data):
    """受影响页浅色+深色 + 关键交互态截图（devloop-protocol §2.5.3）。"""
    suffix = unique_suffix()
    api_id = _create_api(api_client, f'ui630_evidence_api_{suffix}', suffix)
    int630_data['apis'].append(api_id)
    map_id = _create_mapping(api_client, api_id, f'ui630_evidence_map_{suffix}')
    int630_data['mappings'].append(map_id)

    # 1) /SPLMapping 物理域（浅色）
    page.goto(SPL_ROUTE)
    page.wait_visible('.domain-tab-btn', timeout=30)
    page.settle(0.8)
    _snap(page, 'spl_physical_light.png')
    # 深色
    page.driver.execute_script('document.documentElement.classList.add("dark");')
    page.settle(0.3)
    _snap(page, 'spl_physical_dark.png')
    page.driver.execute_script('document.documentElement.classList.remove("dark");')

    # 2) /SPLMapping API/Realtime RMS-SPL 域（浅色 + 深色）
    _switch_to_api_rms_tab(page)
    WebDriverWait(page.driver, 30).until(
        lambda d: any('所有 API' in (o.text or '')
                      for o in d.find_elements(By.CSS_SELECTOR, 'select.form-input option')))
    page.settle(0.8)
    _snap(page, 'spl_rms_light.png')
    page.driver.execute_script('document.documentElement.classList.add("dark");')
    page.settle(0.3)
    _snap(page, 'spl_rms_dark.png')
    page.driver.execute_script('document.documentElement.classList.remove("dark");')

    # 3) 关键交互态：API 过滤下拉（展开前 DOM 全量选项）+ 新增映射弹窗
    api_select = _api_filter_select(page)
    page.driver.execute_script(
        'arguments[0].scrollIntoView({block:"center"}); arguments[0].focus();', api_select)
    page.settle(0.3)
    _snap(page, 'spl_rms_api_filter_focused.png')
    add_btn = next(b for b in page.find_all('button')
                   if '添加 RMS-SPL 映射' in (b.text or ''))
    page.driver.execute_script('arguments[0].click();', add_btn)
    page.settle(0.6)
    _snap(page, 'spl_rms_add_mapping_modal.png')

    # 4) API 定义管理页（/APITest）
    page.driver.execute_script(
        'Array.from(document.querySelectorAll(".modal-content")).forEach(m => m.remove());')
    page.goto('/APITest')
    page.wait_visible('.main-content', timeout=20)
    page.settle(1.0)
    _snap(page, 'apitest_light.png')
    page.driver.execute_script('document.documentElement.classList.add("dark");')
    page.settle(0.3)
    _snap(page, 'apitest_dark.png')
