# -*- coding: utf-8 -*-
"""INT-924 UI 实测：音频管理筛选面板徽章筛选 竖排→横排（旧 Vue）。

验收标准走查清单（纯布局改动卡，只读 + 前端状态断言，不加库内测试数据）：
1. 四个徽章筛选（音频格式/采样率/音频时长/音频类型）标题与徽章同行、
   徽章自然换行、不溢出；
2. 标签云：标题「标签云」与标签搜索框同行（flex-wrap），窄屏可换行；
3. 操作按钮行（重置筛选 / 应用筛选）仍底部右对齐、可用；
4. 跨组件状态同步：选中徽章 + 点「应用筛选」→ 列表按新条件刷新；重置 → 列表回全量；
5. 回归抽查：格式 / 采样率徽章筛选仍生效（选中后 apply 改变列表行数，reset 回全量）。

证据：浅色 + 深色截图落盘 tests/ui/artifacts/int924_*（.dark 为结构预留类，
注入到 <html> 使面板底色 #fff → #2a2a2a，与实施者自测同口径）。
"""
import os
import time

from selenium.webdriver.common.by import By

from tests.ui.pages.base_page import BasePage

AUDIO_ROUTE = '/AudioImport'
FILTER_GRID = '.filter-grid'
BADGE_GROUPS = '.filter-grid > .badge-filter'
TAG_CLOUD = '.filter-item--tag-cloud'
ACTIONS_ITEM = '.filter-actions-item'
PANEL = '.filter-panel'
ROWS = '.data-table tbody tr'
EMPTY_STATE = '.empty-state'

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts')


def _rect(el):
    r = el.rect
    return {'x': r['x'], 'y': r['y'], 'width': r['width'], 'height': r['height']}


def _center_y(r):
    return r['y'] + r['height'] / 2


def _right(r):
    return r['x'] + r['width']


def _badge_group_texts(group):
    return [b.text.strip() for b in group.find_elements(By.CSS_SELECTOR, '.badge-filter__badge')]


def _row_count(page, timeout=10):
    """等列表行稳定后返回当前可见行数（0 = 空态）。"""
    page.settle(0.5)
    rows = page.find_all(ROWS)
    if not rows:
        # 空态：等 .empty-state 可见
        page.wait_visible(EMPTY_STATE, timeout=timeout)
        return 0
    return len(rows)


def test_int924_filter_panel_horizontal_layout(page):
    """核心布局走查：徽章筛选标题与徽章同行、不溢出；标签云同行；按钮右对齐。"""
    page.goto(AUDIO_ROUTE)
    page.wait_visible(FILTER_GRID, timeout=30)
    # 等列表数据渲染完成（行或空态），避免过渡期测量
    page.settle(0.8)
    if not page.exists(ROWS):
        page.wait_visible(EMPTY_STATE, timeout=15)

    grid = page.find(FILTER_GRID)
    grid_rect = _rect(grid)
    groups = page.find_all(BADGE_GROUPS)
    assert len(groups) == 4, f'筛选面板应恰有 4 组徽章筛选：实际 {len(groups)}'

    # 1) 四组徽章筛选：标题与徽章同行（中心 Y 差 <= 12px）
    expected_titles = ('音频格式', '采样率', '音频时长', '音频类型')
    for i, g in enumerate(groups):
        title = g.find_element(By.CSS_SELECTOR, '.badge-filter__title')
        badges = g.find_element(By.CSS_SELECTOR, '.badge-filter__badges')
        assert expected_titles[i] in title.text, \
            f'第 {i + 1} 组标题应为 {expected_titles[i]}：实际 {title.text!r}'
        dy = abs(_center_y(_rect(title)) - _center_y(_rect(badges)))
        assert dy <= 12, f'「{expected_titles[i]}」标题与徽章应同行（中心 Y 差 <=12px）：实际 {dy:.1f}px'
        # 徽章容器不溢出 filter-grid 右缘
        gr = _rect(g)
        assert _right(gr) <= _right(grid_rect) + 2, \
            f'「{expected_titles[i]}」徽章组超出面板右缘：{_right(gr):.1f} > {_right(grid_rect):.1f}'

    # 2) 标签云：标题与搜索框同行（flex-wrap 第一行），不溢出
    tc = page.find(TAG_CLOUD)
    tc_label = tc.find_element(By.CSS_SELECTOR, '.filter-label')
    tc_search = tc.find_element(By.CSS_SELECTOR, '.tag-search-wrapper')
    assert '标签云' in tc_label.text, f'标签云标题文案异常: {tc_label.text!r}'
    dy_tc = abs(_center_y(_rect(tc_label)) - _center_y(_rect(tc_search)))
    assert dy_tc <= 12, f'标签云标题应与搜索框同行（中心 Y 差 <=12px）：实际 {dy_tc:.1f}px'
    tc_rect = _rect(tc)
    assert _right(tc_rect) <= _right(grid_rect) + 2, \
        f'标签云块超出面板右缘：{_right(tc_rect):.1f} > {_right(grid_rect):.1f}'
    # 标签 chip 流渲染（依赖库内标签数据，缺标签时显示 no-data-tip，不算失败）
    assert page.exists('.tag-filter'), '标签云 chip 容器缺失'

    # 3) 操作按钮行：位于筛选区（徽章/标签云）下方独立一行、右对齐
    actions = page.find(ACTIONS_ITEM)
    act_rect = _rect(actions)
    # flex-wrap + flex:1 1 100% 令操作按钮行换到新行：其 top 应 >= 其余 flex 子项最大 bottom
    content_bottom = max(
        _rect(el)['y'] + _rect(el)['height']
        for el in page.find_all('.filter-grid > *')
        if not el.get_attribute('class') or 'filter-actions-item' not in el.get_attribute('class')
    )
    assert act_rect['y'] >= content_bottom - 2, \
        '操作按钮行应在筛选区下方独立一行'
    # 按钮右缘贴近面板右缘（右对齐，padding ~24px）
    panel_rect = _rect(page.find(PANEL))
    gap_right = _right(panel_rect) - _right(_rect(actions.find_element(By.CSS_SELECTOR, '.filter-actions')))
    assert 0 <= gap_right <= 40, f'操作按钮应右对齐（距面板右缘 0-40px）：实际 {gap_right:.1f}px'
    btns = [b.text.strip() for b in actions.find_elements(By.CSS_SELECTOR, '.filter-actions button')]
    assert '重置筛选' in btns and '应用筛选' in btns, f'操作按钮缺失: {btns}'

    page.settle(0.3)


def test_int924_narrow_viewport_wrap_no_overflow(page):
    """窄屏（900px）下徽章 / 标签云仍自然换行、不横向溢出。"""
    page.goto(AUDIO_ROUTE)
    page.wait_visible(FILTER_GRID, timeout=30)
    page.settle(0.8)
    page.driver.set_window_size(900, 1000)
    page.settle(0.5)

    grid = page.find(FILTER_GRID)
    grid_rect = _rect(grid)
    groups = page.find_all(BADGE_GROUPS)
    assert len(groups) == 4
    for i, g in enumerate(groups):
        gr = _rect(g)
        assert _right(gr) <= _right(grid_rect) + 2, \
            f'窄屏第 {i + 1} 组徽章横向溢出：{_right(gr):.1f} > {_right(grid_rect):.1f}'
        title = g.find_element(By.CSS_SELECTOR, '.badge-filter__title')
        badges = g.find_element(By.CSS_SELECTOR, '.badge-filter__badges')
        dy = abs(_center_y(_rect(title)) - _center_y(_rect(badges)))
        assert dy <= 12, f'窄屏「{title.text}」标题与徽章不同行：{dy:.1f}px'
    tc = page.find(TAG_CLOUD)
    tc_rect = _rect(tc)
    assert _right(tc_rect) <= _right(grid_rect) + 2, '窄屏标签云横向溢出'

    page.driver.set_window_size(1600, 1000)
    page.settle(0.4)


def test_int924_badge_apply_reset_sync(page):
    """跨组件状态同步：选中格式徽章 + 应用筛选 → 列表刷新；重置 → 回全量。"""
    page.goto(AUDIO_ROUTE)
    page.wait_visible(FILTER_GRID, timeout=30)
    initial = _row_count(page, timeout=15)
    assert initial > 0, '隔离库应有非删除音频行，初始列表非空（数据准备：既有 3 条 wav）'

    # 组 1 = 音频格式：选 MP3 → 应用筛选 → 0 行（空态）
    fmt_group = page.find_all(BADGE_GROUPS)[0]
    mp3 = [b for b in fmt_group.find_elements(By.CSS_SELECTOR, '.badge-filter__badge')
           if b.text.strip() == 'MP3']
    assert mp3, '格式组应有 MP3 徽章'
    page.driver.execute_script('arguments[0].click();', mp3[0])
    page.settle(0.3)
    page.click(ACTIONS_ITEM + ' .filter-actions button:nth-child(2)')  # 应用筛选
    assert _row_count(page, timeout=15) == 0, '选 MP3 + 应用筛选后列表应刷新为 0 行（无 mp3 数据）'
    page.wait_visible(EMPTY_STATE, timeout=10)

    # 重置筛选 → 回全量
    page.click(ACTIONS_ITEM + ' .filter-actions button:nth-child(1)')  # 重置筛选
    assert _row_count(page, timeout=15) == initial, f'重置筛选后应回 {initial} 行'

    # 回归抽查：格式 WAV（非空结果）+ 采样率 8 kHz（行数变化）
    fmt_group = page.find_all(BADGE_GROUPS)[0]
    wav = [b for b in fmt_group.find_elements(By.CSS_SELECTOR, '.badge-filter__badge')
           if b.text.strip() == 'WAV'][0]
    page.driver.execute_script('arguments[0].click();', wav)
    page.settle(0.3)
    page.click(ACTIONS_ITEM + ' .filter-actions button:nth-child(2)')
    n_wav = _row_count(page, timeout=15)
    assert n_wav > 0, '选 WAV + 应用筛选后应仍有匹配行（既有数据均为 wav）'
    page.click(ACTIONS_ITEM + ' .filter-actions button:nth-child(1)')
    assert _row_count(page, timeout=15) == initial

    sr_group = page.find_all(BADGE_GROUPS)[1]
    khz8 = [b for b in sr_group.find_elements(By.CSS_SELECTOR, '.badge-filter__badge')
            if b.text.strip() == '8 kHz'][0]
    page.driver.execute_script('arguments[0].click();', khz8)
    page.settle(0.3)
    page.click(ACTIONS_ITEM + ' .filter-actions button:nth-child(2)')
    n_8k = _row_count(page, timeout=15)
    assert n_8k < initial, f'选 8 kHz + 应用筛选后行数应减少（null 采样率行被过滤）：{n_8k} vs {initial}'
    page.click(ACTIONS_ITEM + ' .filter-actions button:nth-child(1)')
    assert _row_count(page, timeout=15) == initial


def test_int924_screenshots_light_dark(page):
    """浅色 + 深色截图（.dark 结构预留类注入 <html>）。"""
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    page.goto(AUDIO_ROUTE)
    page.wait_visible(FILTER_GRID, timeout=30)
    page.settle(1.0)

    light = os.path.join(ARTIFACT_DIR, 'int924_audio_filter_light.png')
    page.driver.save_screenshot(light)

    page.driver.execute_script('document.documentElement.classList.add("dark");')
    page.settle(0.6)
    dark = os.path.join(ARTIFACT_DIR, 'int924_audio_filter_dark.png')
    page.driver.save_screenshot(dark)

    assert os.path.isfile(light) and os.path.isfile(dark)
    print(f'[INT924] 截图: {light}\n[INT924] 截图: {dark}')
