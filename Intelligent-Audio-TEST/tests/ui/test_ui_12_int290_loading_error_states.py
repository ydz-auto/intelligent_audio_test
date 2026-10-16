# -*- coding: utf-8 -*-
"""INT-290 UI 实测：C 域列表页加载/错误态（Evaluation / HistoryReports）。

缺陷（INT-261 C 域 UX 审计）：Evaluation 错误态写入状态但模板从未渲染、列表视图
无任何加载指示（仅分组视图有）；HistoryReports loading ref 贯穿 loadReports 但
模板无任何加载指示。修复后真实浏览器走查主流程（断言可见状态，非仅 DOM 存在）：

1. Evaluation 后端不可用（CDP 拦截 /api/v1/evaluation/dimensions）→ 错误条可见
   （含「获取评估维度失败」文案 + 重试按钮），「暂无评估维度数据」空态被抑制；
   解除拦截点「重试」→ 维度正常渲染（错误条/loading 条消失）。
2. Evaluation 慢网络（CDP 节流整页加载）→ loading bar 可见；加载中切「列表
   视图」loading bar 仍显示（INT-290 核心缺口：列表视图此前无任何加载指示）；
   解除节流 → bar 消失、列表视图渲染维度表格。
3. HistoryReports 慢网络 → loading bar（「正在加载报告...」）可见、空态不闪；
   解除节流 → bar 消失、报告卡片正常渲染。

只读语义：全程不改库（两页均为读页面；CDP 拦截/节流只作用于浏览器网络层，
不触发服务端副作用），无测试数据写入，无需 teardown 清理。
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

EVALUATION_ROUTE = '/Evaluation'
HISTORY_REPORTS_ROUTE = '/history-reports'

EVAL_LOADING = '.evaluation-loading-bar'
EVAL_ERROR = '.evaluation-error-banner'
EVAL_ERROR_RETRY = '.evaluation-error-banner .btn-sm'
EVAL_EMPTY = '.empty-dimensions'
EVAL_LIST_TOGGLE = 'button.btn-toggle[title="列表视图"]'
EVAL_TABLE = '.data-table'

HR_LOADING = '.history-reports-loading-bar'
HR_NO_DATA = '.no-data'
HR_CARD = '.reports-section .card'

BLOCK_PATTERN = '*api/v1/evaluation/dimensions*'


# ── CDP 网络层原语（Selenium execute_cdp_cmd）──────────────
def _throttle_latency(driver, latency_ms: int = 2500):
    """全局网络节流（RTT 延迟）；用于制造可观测的加载中窗口。"""
    driver.execute_cdp_cmd('Network.enable', {})
    driver.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False,
        'latency': latency_ms,
        'downloadThroughput': 10485760,   # 10 MB/s，不限流
        'uploadThroughput': 10485760,
    })


def _unthrottle(driver):
    driver.execute_cdp_cmd('Network.emulateNetworkConditions', {
        'offline': False,
        'latency': 0,
        'downloadThroughput': 10485760,
        'uploadThroughput': 10485760,
    })


def _block_eval_dimensions(driver):
    """拦截评估维度接口（模拟后端不可用，fetch 立即失败）。"""
    driver.execute_cdp_cmd('Network.enable', {})
    driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': [BLOCK_PATTERN]})


def _unblock(driver):
    driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})


def test_evaluation_error_banner_shows_on_backend_failure_and_retry_recovers(page):
    """后端不可用 → 错误条（文案+重试）+ 空态抑制；解除拦截点重试 → 维度渲染。"""
    _block_eval_dimensions(page.driver)
    try:
        page.goto(EVALUATION_ROUTE)
        banner = WebDriverWait(page.driver, 25).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, EVAL_ERROR)))
        assert '获取评估维度失败' in banner.text, \
            f'错误条缺缺陷文案: {banner.text!r}'
        assert '重试' in banner.text, \
            f'错误条缺重试按钮: {banner.text!r}'
        # 错误态不得显示「暂无评估维度数据」空态（误导）
        assert not page.exists(EVAL_EMPTY), '错误态不应显示空态'
    finally:
        _unblock(page.driver)
    page.settle(0.5)

    # 重试：重新拉取，成功 → 错误条消失、loading 结束、维度表格渲染
    page.driver.execute_script(
        'arguments[0].click();',
        page.find(EVAL_ERROR_RETRY))
    WebDriverWait(page.driver, 25).until_not(
        EC.visibility_of_element_located((By.CSS_SELECTOR, EVAL_ERROR)))
    WebDriverWait(page.driver, 15).until_not(
        EC.visibility_of_element_located((By.CSS_SELECTOR, EVAL_LOADING)))
    page.settle(0.5)
    assert page.exists(EVAL_TABLE), '重试成功应渲染维度表格'
    assert not page.exists(EVAL_EMPTY), '有数据时不应显示空态'


def test_evaluation_list_view_loading_bar_during_slow_load(page):
    """慢网络整页加载：loading bar 可见；加载中切列表视图仍有指示（核心缺口）。"""
    # 整页加载前置节流：SPA boot + 路由 chunk + fetch 全被延迟，
    # 组件挂载即渲染 loading bar，留出可观测的加载中窗口
    _throttle_latency(page.driver, latency_ms=2500)
    try:
        page.goto(EVALUATION_ROUTE)
        bar = WebDriverWait(page.driver, 40).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, EVAL_LOADING)))
        assert '正在加载评估维度' in bar.text, \
            f'loading bar 文案缺失: {bar.text!r}'
        # 加载中切「列表视图」：loading bar 仍显示（INT-290 核心缺口）
        page.click(EVAL_LIST_TOGGLE)
        page.settle(0.3)
        assert page.find(EVAL_LOADING).is_displayed(), \
            '列表视图加载中应显示 loading bar'
        assert not page.exists(EVAL_EMPTY), '加载中不应显示空态'
    finally:
        _unthrottle(page.driver)

    WebDriverWait(page.driver, 40).until_not(
        EC.visibility_of_element_located((By.CSS_SELECTOR, EVAL_LOADING)))
    page.settle(0.5)
    assert page.exists(EVAL_TABLE), '加载完成后列表视图应渲染维度表格'
    assert 'active' in page.find(EVAL_LIST_TOGGLE).get_attribute('class'), \
        '当前应处于列表视图'


def test_history_reports_loading_bar_during_slow_load(page):
    """慢网络整页加载：HistoryReports loading bar 可见、空态不闪；完成后报告渲染。"""
    _throttle_latency(page.driver, latency_ms=2500)
    try:
        page.goto(HISTORY_REPORTS_ROUTE)
        bar = WebDriverWait(page.driver, 40).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, HR_LOADING)))
        assert '正在加载报告' in bar.text, f'loading bar 文案异常: {bar.text!r}'
        # 加载中不显示「暂无报告数据」空态（与加载条并存误导）
        assert not page.exists(HR_NO_DATA), '加载中不应显示空数据提示'
    finally:
        _unthrottle(page.driver)

    WebDriverWait(page.driver, 40).until_not(
        EC.visibility_of_element_located((By.CSS_SELECTOR, HR_LOADING)))
    page.settle(0.5)
    # 加载完成后：报告卡片渲染（隔离库有报告）或空态收敛，二者必居其一
    assert page.exists(HR_CARD) or page.exists(HR_NO_DATA), \
        '加载完成后应渲染报告列表或空态'
