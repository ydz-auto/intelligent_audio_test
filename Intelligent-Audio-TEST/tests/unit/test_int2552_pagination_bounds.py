# -*- coding: utf-8 -*-
"""INT-2552：查询类意图工具分页边界统一（page ≥ 1 / per_page ≤ 200）。

缺陷：``testcase_query`` / ``device_query`` / ``task_query`` / ``log_diagnose``
（以及同型的 audio / evaluation 查询）此前只校验 ``≥ 1``，没有 ``per_page``
上界；实测 ``per_page=100000`` 一次返回数千行，进入 Loop 后被 8000 字符硬截断
成不可解析 JSON 回灌模型。

本文件验收（卡面可测标准 1 / 2 / 5）：

1. 四个工具的 ``per_page`` 上界、``page`` 下界越界均被拒绝，边界值
   （``per_page=200`` / ``page=1``）正常通过；
2. Schema 的 ``minimum`` / ``maximum`` 与工具层常量同源（``pagination``）；
3. 既有 ``report_query`` 口径不回归。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.agent_tools import device_tools, intent_tools
from shared.agent_tools import pagination

# (工具, 接受分页参数的动作) —— 卡面点名的四个 + 同型查询工具
PAGED_CALLS = [
    ('testcase_query', 'list'),
    ('device_query', 'list'),
    ('task_query', 'list'),
    ('log_diagnose', 'search'),
    ('report_query', 'list'),
    ('audio_query', 'list'),
    ('evaluation_query', 'dimensions'),
]


def _schema(name):
    return intent_tools.INTENT_TOOL_BY_NAME[name].parameters


@pytest.mark.parametrize('name, action', PAGED_CALLS)
def test_schema_bounds_come_from_shared_constants(name, action):
    """Schema 的 page / per_page 上下界与工具层常量同源（禁两份数字）。"""
    props = _schema(name)['properties']
    assert props['page']['minimum'] == pagination.PAGE_MIN
    assert 'maximum' not in props['page']  # 页码不设上界，翻页取
    assert props['per_page']['minimum'] == pagination.PAGE_MIN
    assert props['per_page']['maximum'] == pagination.PER_PAGE_MAX
    assert props['per_page']['description'].endswith(
        f'最大 {pagination.PER_PAGE_MAX}')


@pytest.mark.parametrize('name, action', PAGED_CALLS)
def test_schema_rejects_out_of_range(name, action):
    """Schema 层先拒：越界不进入工具层，也不会上游请求。"""
    schema = _schema(name)
    assert intent_tools.validate_arguments(
        schema, {'action': action, 'per_page': pagination.PER_PAGE_MAX + 1})
    assert intent_tools.validate_arguments(
        schema, {'action': action, 'per_page': 100000})
    assert intent_tools.validate_arguments(
        schema, {'action': action, 'page': 0})
    # 边界值正常通过
    assert intent_tools.validate_arguments(
        schema, {'action': action, 'page': 1,
                 'per_page': pagination.PER_PAGE_MAX}) is None


@pytest.mark.parametrize('name, action', PAGED_CALLS)
def test_tool_layer_rejects_out_of_range(name, action):
    """工具层再兜一次：Schema 被绕过时同样拒绝，且不解析出上游目标。"""
    for arguments in ({'action': action, 'per_page': 100000},
                      {'action': action, 'per_page': pagination.PER_PAGE_MAX + 1},
                      {'action': action, 'page': 0},
                      {'action': action, 'page': -1},
                      {'action': action, 'per_page': 0}):
        tool, merged, error = intent_tools.resolve_rest_call(name, arguments)
        assert tool is None and merged is None, arguments
        assert error and '参数' in error, arguments
        # 超限文案必须给出边界与动作，便于模型自我修正
        assert str(pagination.PER_PAGE_MAX) in error or 'page' in error, arguments


@pytest.mark.parametrize('name, action', PAGED_CALLS)
def test_tool_layer_accepts_boundary_values(name, action):
    """边界值（page=1 / per_page=200）正常解析为目标工具。"""
    tool, merged, error = intent_tools.resolve_rest_call(
        name, {'action': action, 'page': 1,
               'per_page': pagination.PER_PAGE_MAX})
    assert error is None
    assert tool is not None
    assert merged['page'] == 1
    assert merged['per_page'] == pagination.PER_PAGE_MAX


def test_device_tools_normalize_rejects_over_max():
    """``device_query`` 动作归一函数自身也要拦（不依赖 resolve 入口）。"""
    assert device_tools.normalize_arguments(
        'list', {'per_page': 100000})
    assert device_tools.normalize_arguments(
        'list', {'page': 0})
    assert device_tools.normalize_arguments(
        'list', {'page': 1, 'per_page': pagination.PER_PAGE_MAX}) is None


def test_report_query_bounds_do_not_regress():
    """报告域既有口径（per_page ≤ 200）保持不变。"""
    assert intent_tools.resolve_rest_call(
        'report_query', {'action': 'list', 'per_page': 1000})[2]
    assert intent_tools.resolve_rest_call(
        'report_query', {'action': 'list', 'per_page': 200})[2] is None
    assert intent_tools.resolve_rest_call(
        'report_query', {'action': 'cases', 'report_id': 426,
                         'page': -1})[2]


def test_error_message_is_readable():
    """错误文案是模型可读的参数错误，不含 SQL / 上游异常痕迹。"""
    _, _, error = intent_tools.resolve_rest_call(
        'log_diagnose', {'action': 'search', 'per_page': 100000})
    assert '参数 per_page' in error and '200' in error
    for noise in ('psycopg2', 'LINE', 'HINT', 'Traceback'):
        assert noise not in error
