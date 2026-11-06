# -*- coding: utf-8 -*-
"""INT-295 P3 批次 · D 域视觉与代码卫生 —— 浏览器实测。

覆盖卡面改动中浏览器可观察的部分（按 test_ui_05 先例补交互实测，
断言可见状态而非仅 DOM 存在）：

1. 404 NotFound：非法路径 → `.not-found` 渲染，垂直居中区高改为
   `calc(100vh - header - footer)`（消除 60vh 页脚大段留白）；
2. TagManagement：无颜色标签兜底色走 `var(--color-indigo-500)`、
   「未分类」侧栏色块走 `var(--color-slate-400)`（computed 断言实际色值）；
3. AlgorithmConfig：详情参数表「组件」列 `.status-tag.component`
   色板走 `var(--secondary-light/--secondary-color)` token；
4. TestCaseListContainer：`.modal-overlay` 收敛到 `var(--z-index-modal)`
   且显式可见（服务端 stylesheet 规则断言，替代不可达的 audio-type 弹窗
   触发——当前 test_type 单值架构下 hasAPIConfig&&hasE2eConfig 恒 false）。

数据卫生：标签/分类自建自清（API 造 → teardown purge）；算法与 404 只读，
不写共享库/隔离库。
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import unique_suffix

TAG_ROUTE = '/TagManagement'
ALGO_ROUTE = '/AlgorithmConfig'
# 服务端 vite 已注入的 scoped stylesheet 里查找 .modal-overlay 规则文本
MODAL_OVERLAY_RULE_KEY = 'z-index: var(--z-index-modal)'


def _computed(bp: BasePage, css_selector: str, prop: str) -> str:
    return bp.driver.execute_script(
        "return getComputedStyle(document.querySelector(arguments[0]))[arguments[1]]",
        css_selector, prop)


def _wait_doc(bp: BasePage, css: str, timeout: int = 20):
    WebDriverWait(bp.driver, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, css)))
    return bp.driver.find_element(By.CSS_SELECTOR, css)


def _modal_overlay_rule_text(bp: BasePage) -> str:
    """扫描服务端 stylesheet，返回首条含 .modal-overlay 的规则 cssText。"""
    return bp.driver.execute_script(
        "let hit='';"
        "for (const sheet of document.styleSheets) {"
        "  let rules=[];"
        "  try { rules = sheet.cssRules || []; } catch (e) { continue; }"
        "  for (const r of rules) {"
        "    if (r && r.selectorText && r.selectorText.includes('.modal-overlay')) {"
        "      hit += r.cssText + '\\n';"
        "    }"
        "  }"
        "}"
        "return hit;")


def test_notfound_vertical_centering(page: BasePage):
    """404 页：非法路径渲染 + 内容区高按可视区 calc（非 60vh 留白）。"""
    page.goto('/DefinitelyNotARealRoute')
    el = _wait_doc(page, '.not-found')
    assert '页面不存在' in el.text, f'404 文案异常: {el.text!r}'
    inner_h = page.driver.execute_script('return window.innerHeight;')
    header_h = page.driver.execute_script(
        "return getComputedStyle(document.documentElement).getPropertyValue('--header-height');")
    footer_h = page.driver.execute_script(
        "return getComputedStyle(document.documentElement).getPropertyValue('--footer-height');")
    header_px = int(float(header_h.strip().rstrip('px')))
    footer_px = int(float(footer_h.strip().rstrip('px')))
    expected = inner_h - header_px - footer_px
    actual = _computed(page, '.not-found', 'minHeight')
    actual_px = int(float(actual.rstrip('px')))
    assert abs(actual_px - expected) <= 2, (
        f'.not-found min-height 应为 {expected}px（calc(100vh - header - footer)），'
        f'实际 {actual_px}px；若仍为 60vh≈{int(inner_h * 0.6)}px 则 INT-295 未生效')
    assert actual_px > inner_h * 0.6, (
        f'.not-found min-height {actual_px}px 未超过 60vh，calc 收敛未生效')


def _norm_css_color(value: str) -> str:
    """Selenium 对不同透明度格式返回 rgb()/rgba()，归一化为 rgb 三段比较。"""
    return value.replace('rgba(', 'rgb(').replace(', 1)', ')')


def test_tag_management_fallback_colors(page: BasePage, api_client):
    """标签管理：无颜色标签兜底 indigo-500；「未分类」侧栏 slate-400。"""
    suffix = unique_suffix()
    tag_name = f'int295_无色标签_{suffix}'
    tag_doc = api_client.create_tag(tag_name, 'INT-295 兜底色实测')
    tag_id = tag_doc.get('id') if isinstance(tag_doc, dict) else tag_doc
    assert tag_id, 'API 造标签失败'
    try:
        page.goto(TAG_ROUTE)
        _wait_doc(page, '.tg-tag-grid, .tg-empty-state', timeout=25)
        page.settle(0.6)
        # 定位本卡标签卡片（唯一前缀，避免误读其它数据）
        card = None
        for c in page.find_all('.tg-tag-card'):
            if tag_name in c.text:
                card = c
                break
        assert card is not None, f'标签网格未见 {tag_name}（页面无该标签卡片）'
        bar = card.find_element(By.CSS_SELECTOR, '.tg-tag-color-bar')
        bg = _norm_css_color(bar.value_of_css_property('background-color'))
        assert bg == 'rgb(99, 102, 241)', (
            f'无颜色标签兜底色应为 indigo-500 rgb(99,102,241)，实际 {bg!r}')
        # 「未分类」侧栏色块 = slate-400
        _wait_doc(page, '.tg-category-color', timeout=10)
        uncat = None
        for sw in page.find_all('.tg-category-color'):
            parent = sw.find_element(By.XPATH, '..')
            if '未分类' in parent.text:
                uncat = sw
                break
        assert uncat is not None, '侧栏未见「未分类」色块'
        ubg = _norm_css_color(uncat.value_of_css_property('background-color'))
        assert ubg == 'rgb(148, 163, 184)', (
            f'「未分类」色块应为 slate-400 rgb(148,163,184)，实际 {ubg!r}')
    finally:
        try:
            api_client.delete_tag(tag_id)
        except Exception:
            pass


def test_algorithm_config_component_column(page: BasePage):
    """算法配置：`.status-tag.component` 类走 token 色板（服务端 stylesheet 规则断言）。

    组件列详情视图仅经 handleView 进入（模板未挂可见入口），故以 stylesheet
    规则断言替代：内联 style 已收敛为 `.status-tag.component` CSS 类，
    背景/文字色走 `--secondary-light/--secondary-color` token。
    只读：不新建算法数据。
    """
    page.goto(ALGO_ROUTE)
    _wait_doc(page, '.algorithm-config-page tbody tr, .algorithm-config-page', timeout=25)
    page.settle(0.5)
    rules = page.driver.execute_script(
        "let hit='';"
        "for (const sheet of document.styleSheets) {"
        "  let rules=[];"
        "  try { rules = sheet.cssRules || []; } catch (e) { continue; }"
        "  for (const r of rules) {"
        "    if (r && r.selectorText && r.selectorText.includes('.status-tag.component')) {"
        "      hit += r.cssText + '\\n';"
        "    }"
        "  }"
        "}"
        "return hit;")
    assert 'background-color: var(--secondary-light)' in rules, (
        f'.status-tag.component 背景应收敛 var(--secondary-light):\n{rules[:500]}')
    assert 'color: var(--secondary-color)' in rules, (
        f'.status-tag.component 文字应收敛 var(--secondary-color):\n{rules[:500]}')


def test_testcaselistcontainer_modal_overlay_tokenized(page: BasePage):
    """TestCaseListContainer：.modal-overlay 收敛到 --z-index-modal 且显式可见。

    audio-type 弹窗在当前 test_type 单值架构下不可达（hasAPIConfig 与
    hasE2eConfig 由同一 recordTestType 派生，恒互斥），故以服务端 stylesheet
    规则断言替代真实触发：z-index 走 token + opacity/visibility 显式覆盖
    全局 .modal-overlay 隐藏态。
    """
    page.goto('/TestCaseManager')
    _wait_doc(page, '.test-case-list-container', timeout=25)
    rules = _modal_overlay_rule_text(page)
    assert MODAL_OVERLAY_RULE_KEY in rules, (
        f'服务端 stylesheet 未见 .modal-overlay 的 z-index token 规则:\n{rules[:500]}')
    assert 'opacity: 1' in rules and 'visibility: visible' in rules, (
        f'.modal-overlay 应显式覆盖全局隐藏态（opacity/visibility）:\n{rules[:500]}')
    assert 'z-index: 1001' not in rules and 'z-index: 9999' not in rules, (
        f'仍残留硬编码 z-index（应收敛 token）:\n{rules[:500]}')
