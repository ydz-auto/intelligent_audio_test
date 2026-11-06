# -*- coding: utf-8 -*-
"""INT-528 UI 实测：用例回收站态搜索已删用例名 → 分组视图不再空白。

缺陷（INT-331 浏览器实测开出）：用例管理页「回收站」态在搜索框输入已删用例名，
分组列表渲染为空白——`fetchTestCases` 并行调 `getGroups({keyword})` 与
`getAll({onlyDeleted:true, keyword})`，而 `GET /groups` 的 keyword 筛选在
task_service 统计实现中硬过滤 deleted==False，已删用例被排除 → allGroups 为空。

INT-528 修复（方案A）：/groups 透传 only_deleted/favorite 口径，回收站态
keyword 命中已删用例时分组收敛不再为空；前端 getGroups 同步透传。

本文件以真实浏览器走查验收修复目标（对照 test_ui_05 先例，断言可见状态而非
仅 DOM 存在）：
1. 回收站态搜索已删用例名 → 分组列表出现匹配分组（本卡验收锚点，原 xfail）；
2. 回归：普通（活跃）态搜索已删用例名 → 不出现该分组（仍仅活跃口径）；
3. 回归：回收站态无 keyword → 分组卡计数为已删用例数（与可见数据一致）。

数据纪律：自建自清（unique_suffix 命名；teardown 软删+purge+删分组），
写操作只落在隔离库 intelligent_audio_test_test（conftest 隔离库守卫强制）。
"""
import time

import pytest
from selenium.webdriver.common.by import By

from tests.ui.utils.api_client import unique_suffix

# 用例管理页
TESTCASES_ROUTE = '/TestCaseManager'
BAR_TOGGLE = '.favorite-trash-bar .bar-toggle'
TRASH_TEXT = '回收站'
CATEGORY_CARD = '.category-card'
CATEGORY_TITLE = '.category-title'
CATEGORY_HEADER = '.category-header'
SEARCH_INPUT = '.search-box .search-input'
CASE_CARD = '.case-card'


def _bar_toggle(bp, text: str):
    for el in bp.find_all(BAR_TOGGLE):
        if el.is_displayed() and text in (el.text or ''):
            return el
    return None


def _set_bar_toggle(bp, text: str, on: bool):
    """点击工具栏开关到目标状态（已在目标态则跳过）。"""
    el = _bar_toggle(bp, text)
    assert el is not None, f'工具栏缺少「{text}」按钮'
    active = 'active' in (el.get_attribute('class') or '')
    if active == on:
        return
    bp.driver.execute_script('arguments[0].click();', el)
    bp.settle(0.6)


def _set_search(bp, text: str):
    """搜索框置值 + 派发 input（触发防抖后服务端重拉）。"""
    search = bp.find_visible(SEARCH_INPUT, timeout=10)
    bp.driver.execute_script(
        'arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event("input", {bubbles:true}));',
        search, text)
    bp.settle(1.5)


def _visible_cards(bp) -> list:
    return [c for c in bp.find_all(CATEGORY_CARD) if c.is_displayed()]


def _card_title(card) -> str:
    els = card.find_elements(By.CSS_SELECTOR, CATEGORY_TITLE)
    return els[0].text.strip() if els else ''


def _find_card_by_title(bp, name_part: str, timeout: float = 20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for card in _visible_cards(bp):
            if name_part in _card_title(card):
                return card
        bp.settle(0.5)
    return None


@pytest.fixture()
def int528_trash_case(api_client):
    """API 造 1 分组 + 1 用例；teardown 软删 + purge + 删分组（零残留）。"""
    suffix = unique_suffix()
    group_name = f'int528_group_{suffix}'
    case_name = f'int528_用例_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-528 回收站态搜索实测分组')
    assert group_id, 'API 造分组失败'
    tc_id = api_client.create_testcase(case_name, group=group_name, tags=[],
                                       description='INT-528 回收站态搜索实测用例')
    assert tc_id, f'API 造用例失败: {tc_id}'
    yield {'case_id': tc_id, 'group_id': group_id, 'group_name': group_name,
           'name': case_name, 'suffix': suffix}
    api_client.delete_testcase(tc_id, purge=True)
    try:
        api_client.delete_group(group_id)
    except Exception:
        pass


class TestInt528TrashSearch:
    """回收站态搜索已删用例 → 分组视图显示匹配分组（INT-528 验收）。"""

    def test_trash_search_deleted_case_shows_group(self, page, api_client, int528_trash_case):
        """本卡验收锚点：回收站态搜索已删用例名 → 分组列表出现匹配分组。"""
        tc_id = int528_trash_case['case_id']
        name = int528_trash_case['name']
        group_name = int528_trash_case['group_name']
        api_client.delete_testcase(tc_id, purge=False)

        page.goto(TESTCASES_ROUTE)
        page.wait_visible(BAR_TOGGLE, timeout=25)
        _set_bar_toggle(page, TRASH_TEXT, on=True)
        page.settle(1.0)
        _set_search(page, name)

        card = _find_card_by_title(page, group_name)
        assert card is not None, \
            '回收站态搜索已删用例名 → 分组视图空白（INT-528 缺陷复现：groups keyword 忽略已删用例）'
        # 分组卡计数为已删用例数（与可见数据一致）
        assert '1' in _card_title(card), f'分组卡计数未含已删用例: {_card_title(card)!r}'

    def test_active_search_excludes_deleted_case(self, page, api_client, int528_trash_case):
        """回归：普通（活跃）态搜索已删用例名 → 分组列表不出现该分组（仍仅活跃口径）。"""
        tc_id = int528_trash_case['case_id']
        name = int528_trash_case['name']
        group_name = int528_trash_case['group_name']
        api_client.delete_testcase(tc_id, purge=False)

        page.goto(TESTCASES_ROUTE)
        page.wait_visible(BAR_TOGGLE, timeout=25)
        _set_search(page, name)

        # 已删用例不在活跃口径 → keyword 唯一命中为空 → 无该分组卡
        assert _find_card_by_title(page, group_name, timeout=6) is None, \
            '普通态搜索竟显示了已删用例所在分组（活跃口径回归）'
        assert not any(group_name in _card_title(c) for c in _visible_cards(page)), \
            '活跃态分组列表混入已删用例所在分组'

    def test_trash_no_keyword_shows_deleted_group_card(self, page, api_client, int528_trash_case):
        """回归：回收站态无 keyword → 分组卡正常显示（计数走已删口径，分组不空白）。"""
        tc_id = int528_trash_case['case_id']
        group_name = int528_trash_case['group_name']
        api_client.delete_testcase(tc_id, purge=False)

        page.goto(TESTCASES_ROUTE)
        page.wait_visible(BAR_TOGGLE, timeout=25)
        _set_bar_toggle(page, TRASH_TEXT, on=True)
        page.settle(1.0)

        card = _find_card_by_title(page, group_name)
        assert card is not None, '回收站态无 keyword 时分组列表竟不含已删用例所在分组'
