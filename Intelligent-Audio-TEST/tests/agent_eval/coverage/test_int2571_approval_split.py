# -*- coding: utf-8 -*-
"""INT-2571 §9.4.1 拆单注册表与对象计数的注册期探针。

本文件钉三件事：

1. **注册期枚举**：写工具的全部数组参数（工具 Schema 顶层数组 + 各域模块
   声明的 body / items 数组字段）必须能在
   ``shared.agent_tools.approval_split.ARRAY_PARAMS`` 里查到分类；漏分类判红
   （对齐 INT-2562 风险探针的 fail-closed）。
2. **分类合法性**：``split`` / ``atomic`` / ``not_applicable`` 之外取值、
   ``DESTRUCTIVE`` 工具被标 ``split``、同一动作多个 ``split`` 都判红。
3. **可拆前提**：每个 ``split`` 参数收窄到单个对象后，调用仍然合法
   （§9.4.1 第 1 条：「只带其中一个对象时该调用仍然合法」才可拆）。

另含对象计数 / 分块的纯函数用例（去重、阈值边界、粒度、对象上限、范围
语义、DESTRUCTIVE / 原子不拆、参数收窄）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.infrastructure.tools.registry_bridge import (
    SharedToolRegistryBridge,
)
from shared.agent_tools import (
    approval_split, audio_tools, evaluation_tools, intent_tools,
    task_write_tools,
)


# ---------------------------------------------------------------- 枚举来源

def _tool_array_paths():
    """写工具 Schema 的顶层数组参数：``(工具, None, 字段名)``。"""
    rows = []
    for tool in intent_tools.INTENT_TOOLS:
        if tool.risk == 'READ':
            continue
        properties = (tool.parameters or {}).get('properties') or {}
        for name, spec in properties.items():
            if isinstance(spec, dict) and spec.get('type') == 'array':
                rows.append((tool.name, None, name))
    return rows


def _nested_array_paths():
    """域模块声明的嵌套数组字段：``(工具, 动作, 参数路径)``。"""
    rows = []
    for field in task_write_tools.RETRY_BODY_ARRAY_FIELDS:
        rows.append(('task_run', 'retry', f'body.{field}'))
    for field in task_write_tools.MERGE_BODY_ARRAY_FIELDS:
        rows.append(('task_run', 'merge', f'body.{field}'))
    for action, fields in evaluation_tools.EVALUATION_BODY_ARRAY_FIELDS.items():
        for field in fields:
            rows.append(('evaluation_manage', action, f'body.{field}'))
    for field in audio_tools.AUDIO_ANNOTATE_ITEM_ARRAY_FIELDS:
        rows.append(('audio_annotate', 'batch_annotate',
                     f'items[].{field}'))
    # items 的对象标识字段本身不是数组，但可拆参数路径就是它
    # （``items[].audio_id``）：域模块声明了容器键，探针据此认为可枚举。
    rows.append(('audio_annotate', 'batch_annotate',
                 f'items[].{audio_tools.AUDIO_ANNOTATE_ITEM_KEY}'))
    return rows


def _discovered_paths():
    return _tool_array_paths() + _nested_array_paths()


def _covers(tool: str, action, path: str) -> bool:
    """``(工具, 动作, 路径)`` 是否已被注册表分类（顶层字段动作无关）。"""
    if approval_split.classification_for(tool, action, path) is not None:
        return True
    if action is not None:
        return False
    return any(rule.tool == tool and rule.path == path
               for rule in approval_split.ARRAY_PARAMS)


# ---------------------------------------------------------------- 注册期

def test_every_write_array_param_is_classified():
    """写工具新增数组参数必须显式分类（split / atomic / not_applicable）。"""
    missing = [f'{tool}.{action or "*"}.{path}'
               for tool, action, path in _discovered_paths()
               if not _covers(tool, action, path)]
    assert not missing, f'以下写工具数组参数未在 ARRAY_PARAMS 分类：{missing}'


def test_every_registered_path_is_enumerable():
    """注册表里的具体路径必须能被枚举来源复现（不留孤儿条目）。

    容器通配（``body.*``）是为「整个容器的数组字段同属一类」准备的，由
    ``test_every_write_array_param_is_classified`` 的正向断言兜底，这里跳过。
    """
    discovered = {(tool, path) for tool, _action, path in _discovered_paths()}
    nested = {(tool, action, path)
              for tool, action, path in _nested_array_paths()}
    orphans = []
    for rule in approval_split.ARRAY_PARAMS:
        if rule.path.endswith('.*'):
            continue
        if rule.action is None:
            if (rule.tool, rule.path) not in discovered:
                orphans.append(f'{rule.tool}.{rule.path}')
            continue
        if (rule.tool, rule.action, rule.path) not in nested:
            # 顶层字段的登记可以带动作（例如 testcase_write.tag.tags），
            # 只要该字段本身是工具 Schema 的顶层数组即视为可枚举
            if (rule.tool, rule.path) not in discovered:
                orphans.append(f'{rule.tool}.{rule.action}.{rule.path}')
    assert not orphans, f'注册表路径无法被枚举来源复现：{orphans}'


def test_destructive_tools_are_never_splittable():
    """DESTRUCTIVE 恒一张单：注册表也不允许把它的参数标成 split。"""
    offenders = []
    for rule in approval_split.ARRAY_PARAMS:
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(rule.tool)
        if tool is None:
            offenders.append(f'{rule.tool} 不是已注册意图工具')
            continue
        if tool.risk == 'DESTRUCTIVE' and rule.classification == \
                approval_split.SPLIT:
            offenders.append(f'{rule.tool}.{rule.action}.{rule.path}')
    assert not offenders, f'DESTRUCTIVE 工具被标成可拆：{offenders}'


def test_at_most_one_splittable_param_per_action():
    """一个动作至多一个可拆参数：多参数同时拆会造出对象归属歧义。"""
    seen = {}
    for rule in approval_split.ARRAY_PARAMS:
        if rule.classification != approval_split.SPLIT:
            continue
        key = (rule.tool, rule.action)
        seen.setdefault(key, []).append(rule.path)
    duplicated = {key: paths for key, paths in seen.items() if len(paths) > 1}
    assert not duplicated, f'同一动作登记了多个可拆参数：{duplicated}'


# ---------------------------------------------------------------- 可拆前提

# 每个可拆动作的最小合法样本（用真实工具 Schema / 域解析校验）
_SAMPLES = {
    ('tag_group_manage', 'batch_tag'): {
        'action': 'batch_tag', 'batch_action': 'add_tags',
        'ids': ['c1', 'c2'], 'tags': ['接线测试']},
    ('audio_annotate', 'batch_annotate'): {
        'action': 'batch_annotate',
        'items': [{'audio_id': 1, 'tags': ['a']}, {'audio_id': 2}]},
    ('task_run', 'retry'): {
        'action': 'retry', 'task_id': 1,
        'body': {'mode': 'selected', 'case_ids': ['c1', 'c2']}},
    ('evaluation_manage', 'reevaluate'): {
        'action': 'reevaluate',
        'body': {'task_id': 1, 'mode': 'selected',
                 'case_ids': ['c1', 'c2']}},
}


def _split_rules():
    return [rule for rule in approval_split.ARRAY_PARAMS
            if rule.classification == approval_split.SPLIT]


def test_split_samples_are_valid_to_begin_with():
    """自证：样本本身是合法调用，后面的「单对象仍合法」才有意义。"""
    bridge = SharedToolRegistryBridge()
    for rule in _split_rules():
        sample = _SAMPLES.get((rule.tool, rule.action))
        assert sample is not None, f'{rule.tool}.{rule.action} 缺可拆样本'
        assert rule.when is None or rule.when(sample), (
            f'{rule.tool}.{rule.action} 的样本不满足可拆条件')
        error = bridge.validate(rule.tool, sample)
        assert error is None, f'{rule.tool}.{rule.action} 样本不合法：{error}'


def test_single_object_chunk_stays_a_valid_call():
    """只带一个对象时调用仍然合法 —— 这是「可拆」的定义（§9.4.1 第 1 条）。"""
    bridge = SharedToolRegistryBridge()
    for rule in _split_rules():
        sample = _SAMPLES[(rule.tool, rule.action)]
        plan = approval_split.plan_approvals(
            rule.tool, sample, threshold=1, chunk_size=1, max_objects=100)
        assert plan.total == 2, f'{rule.tool}.{rule.action} 未按对象拆分'
        for chunk in plan.chunks:
            assert chunk.object_ref
            assert len(chunk.object_ref['ids']) == 1
            error = bridge.validate(rule.tool, chunk.arguments)
            assert error is None, (
                f'{rule.tool}.{rule.action} 收窄后不合法：{error}；'
                f'args={chunk.arguments}')


# ---------------------------------------------------------------- 对象计数

def test_counts_explicit_objects_and_dedupes():
    scope = approval_split.object_scope('tag_group_manage', {
        'action': 'batch_tag', 'batch_action': 'add_tags',
        'ids': ['c1', 'c2', 'c1'], 'tags': ['t']})
    assert scope.kind == 'testcase'
    assert scope.ids == ('c1', 'c2')
    assert scope.counted == 2
    assert scope.splittable


def test_threshold_is_strictly_greater_than():
    ids = [f'c{i}' for i in range(21)]
    equal = approval_split.plan_approvals('tag_group_manage', {
        'action': 'batch_tag', 'batch_action': 'remove_tags',
        'ids': ids[:20], 'tags': ['t']}, threshold=20)
    over = approval_split.plan_approvals('tag_group_manage', {
        'action': 'batch_tag', 'batch_action': 'remove_tags',
        'ids': ids, 'tags': ['t']}, threshold=20)
    assert equal.total == 1 and equal.object_count == 20
    assert over.total == 21 and over.object_count == 21
    assert over.chunks[0].total == 21


def test_chunk_size_groups_objects():
    ids = [f'c{i}' for i in range(21)]
    plan = approval_split.plan_approvals('tag_group_manage', {
        'action': 'batch_tag', 'batch_action': 'add_tags',
        'ids': ids, 'tags': ['t']}, threshold=20, chunk_size=5)
    assert plan.total == 5
    assert [len(chunk.ids) for chunk in plan.chunks] == [5, 5, 5, 5, 1]
    assert all(chunk.total == 5 for chunk in plan.chunks)
    # 参数收窄到本单对象（完整参数由调用方另行保留）
    assert plan.chunks[0].arguments['ids'] == ids[:5]
    assert plan.chunks[0].arguments['tags'] == ['t']


def test_narrowed_items_keep_other_item_fields():
    items = [{'audio_id': i, 'annotations': [{'k': i}]} for i in range(1, 4)]
    plan = approval_split.plan_approvals('audio_annotate', {
        'action': 'batch_annotate', 'items': items}, threshold=1)
    assert plan.total == 3
    assert plan.chunks[1].arguments['items'] == [items[1]]
    assert plan.chunks[1].object_ref == {'kind': 'audio', 'ids': [2]}


def test_object_limit_rejects_before_any_split():
    ids = [f'c{i}' for i in range(101)]
    with pytest.raises(approval_split.ObjectLimitExceeded) as exc:
        approval_split.plan_approvals('tag_group_manage', {
            'action': 'batch_tag', 'batch_action': 'add_tags',
            'ids': ids, 'tags': ['t']}, max_objects=100)
    assert exc.value.count == 101
    assert exc.value.limit == 100
    assert exc.value.code == 'APPROVAL_OBJECT_LIMIT_EXCEEDED'


def test_destructive_batch_counts_but_never_splits():
    plan = approval_split.plan_approvals('device_control', {
        'action': 'batch', 'operation': 'reboot',
        'device_ids': list(range(1, 26))}, risk='DESTRUCTIVE', threshold=20)
    assert plan.total == 1
    assert plan.object_count == 25
    assert plan.chunks[0].object_ref == {
        'kind': 'device', 'ids': list(range(1, 26))}


def test_atomic_merge_counts_but_never_splits():
    plan = approval_split.plan_approvals('task_run', {
        'action': 'merge', 'body': {'task_ids': list(range(1, 26))}},
        threshold=20)
    assert plan.total == 1
    assert plan.object_count == 25
    assert plan.chunks[0].object_ref['kind'] == 'task'
    # 不拆时参数保持完整（不加窄）
    assert plan.chunks[0].arguments['body']['task_ids'] == list(range(1, 26))


def test_range_mode_counts_one_object():
    plan = approval_split.plan_approvals('evaluation_manage', {
        'action': 'reevaluate', 'body': {'task_id': 1, 'mode': 'all'}},
        threshold=20)
    assert plan.total == 1
    assert plan.object_count == 1
    assert plan.chunks[0].object_ref == {'kind': 'testcase', 'ids': []}
    # 范围语义由未收窄的参数承载（审批人能看到 mode=all）
    assert plan.chunks[0].arguments['body']['mode'] == 'all'


def test_unknown_write_tool_is_a_single_approval():
    plan = approval_split.plan_approvals('task_create', {
        'body': {'name': 'x'}}, threshold=20)
    assert plan.total == 1
    assert plan.object_count == 1
    assert plan.chunks[0].object_ref is None


def test_registry_guard_catches_unclassified_array_param():
    """护栏自证：新增一个数组参数而不登记分类，必须被枚举判红。"""
    discovered = _discovered_paths() + [('task_run', None, 'label_ids')]
    missing = [f'{tool}.{action or "*"}.{path}'
               for tool, action, path in discovered
               if not _covers(tool, action, path)]
    assert missing == ['task_run.*.label_ids']
