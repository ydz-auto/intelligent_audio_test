# -*- coding: utf-8 -*-
"""INT-260 首批 UI 用例 · 视图切换域：分组/标签视图数据一致性（防吞用例回归）。

数据自建自清（issue 口径）：API 造唯一前缀用例（带唯一标签）→ UI 断言两个视图
都能看到同一份数据 → teardown API 彻底删除（purge + 标签删除），库内零残留。
"""
import pytest

from tests.ui.pages.test_case_page import TestCasePage
from tests.ui.utils.api_client import unique_suffix


@pytest.fixture()
def seeded_case(api_client):
    """造一条带唯一标签的用例（含专属分组）；teardown 彻底删除 + 标签/分组回收。"""
    suffix = unique_suffix()
    case_name = f'ui260_一致性用例_{suffix}'
    tag_name = f'ui260_tag_{suffix}'
    group_name = f'ui260_group_{suffix}'
    group_id = api_client.create_group(group_name, 'INT-260 视图一致性专用分组')
    assert group_id, 'API 造分组失败（前置数据自建失败，非 UI 缺陷则查栈）'
    tc_id = api_client.create_testcase(case_name, group=group_name, tags=[tag_name],
                                       description='INT-260 视图切换一致性用例')
    assert tc_id, 'API 造用例失败（前置数据自建失败，非 UI 缺陷则查栈）'
    yield {'id': tc_id, 'name': case_name, 'tag': tag_name,
           'group': group_name, 'group_id': group_id}
    api_client.delete_testcase(tc_id)
    # 标签回收：列表接口按名匹配后删除（用例 purge 后标签仍留）
    try:
        tags = api_client.request('GET', '/tags?page=1&perPage=200&search=' + tag_name)
        items = (tags.get('data') or {})
        items = items.get('items') if isinstance(items, dict) else items
        for t in (items or []):
            if t.get('name') == tag_name:
                api_client.delete_tag(t.get('id'))
                break
    except Exception:
        pass
    try:
        api_client.delete_group(group_id)
    except Exception:
        pass


def test_tag_group_view_switch_consistency(page, seeded_case):
    """核心回归：分组视图与标签视图展示同一用例（切换不吞数据）。

    缺陷背景：视图切换类"人手操作"缺陷曾吞用例——分组视图可见、切到标签视图
    用例消失（或反之）。双向切换 + 两侧均断言用例名可见。
    """
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)

    # 分组视图：用例名出现在某个分组下
    assert tc.view_mode() == 'group'
    group_view = tc.all_case_names()
    assert seeded_case['name'] in group_view, \
        f'分组视图未展示新用例 {seeded_case["name"]}；可见={sorted(group_view)[:8]}...'

    # 切标签视图：唯一标签出现，且其下可见同一用例
    tc.switch_view('tag')
    tag_cats = tc.categories()
    assert seeded_case['tag'] in tag_cats, \
        f'标签视图未出现标签 {seeded_case["tag"]}；可见标签={sorted(tag_cats)[:8]}...'
    assert seeded_case['name'] in tag_cats.get(seeded_case['tag'], set()), \
        f'标签 {seeded_case["tag"]} 下未展示用例 {seeded_case["name"]}'

    # 切回分组视图：数据仍在（往返一致性）
    tc.switch_view('group')
    back = tc.all_case_names()
    assert seeded_case['name'] in back, '切回分组视图后用例消失（视图切换吞数据）'


def test_view_switch_case_count_stable(page, seeded_case):
    """往返切换后用例总数不缩水（防吞用例回归的计数口径）。"""
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)

    first = len(tc.all_case_names())
    assert first >= 1, '分组视图至少应有 API 造的 1 条用例'

    tc.switch_view('tag')
    tag_count = len(tc.all_case_names())
    assert tag_count >= 1, '标签视图至少应有 1 条用例'

    tc.switch_view('group')
    assert len(tc.all_case_names()) == first, '往返切换后分组视图用例数缩水'


def test_tag_view_only_shows_expected_tag(page, seeded_case):
    """标签视图按标签聚合：自建唯一标签出现，且其下用例名精确匹配。"""
    tc = TestCasePage(page.driver, page.base_url)
    tc.goto()
    tc.wait_loaded(timeout=25)
    tc.switch_view('tag')

    tags = tc.categories()
    assert seeded_case['tag'] in tags, f'标签视图缺少自建标签 {seeded_case["tag"]}'
    assert tags[seeded_case['tag']] == {seeded_case['name']}, \
        f'唯一标签下应只有自建用例: {tags[seeded_case["tag"]]!r}'
