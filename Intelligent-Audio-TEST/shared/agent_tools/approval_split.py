# -*- coding: utf-8 -*-
"""审批拆单的对象计数与分块（INT-2571，方案 07 §9.4.1）。

一次 tool call 影响 > 20 个独立对象时必须拆成 N 张审批单（逐张决策、全批
批准后**一次执行**）。本模块是「哪些参数可拆、怎么数、怎么拆」的**唯一
事实源**：

- ``ArrayParam``：一个数组参数的分类（``split`` / ``atomic`` /
  ``not_applicable``）+ 参数路径 + 对象 kind；
- ``object_scope``：按 ``(工具, 动作, 参数路径)`` 数出**显式枚举**的独立对
  象（按 ``(kind, id)`` 去重，保持参数原顺序）；
- ``plan_approvals``：按阈值 / 粒度给出分块，并把每块的参数**收窄到本单对
  象**（完整参数仍留在 ``agent_tool_call.arguments``）。

三条硬口径（§9.4.1）：

1. 只数参数里显式枚举的对象；``mode=all`` / ``failed_only`` 这类由服务端决定
   影响面的**非枚举范围**计 1 个对象（``object_ref.ids`` 为空，范围语义由
   未被收窄的 ``proposal.arguments`` 展示），不伪造数量；
2. 一个参数可拆的前提是「只带其中一个对象时该调用仍然合法」——``merge`` 这
   种集合动作因此在注册表里标 ``atomic``，只计数、不拆单；
3. ``DESTRUCTIVE`` 恒一张单：即使注册表把参数标成 ``split``，分块也会被风
   险挡回去（拆单不得成为绕开二次确认的路径）。

注册期探针（``tests/agent_eval/coverage/test_int2571_approval_split.py``）
枚举写工具的数组参数（工具 Schema 顶层 + 各域模块声明的 body / items 数组
字段），漏分类判红；新增写工具数组参数必须在这里显式分类。
"""
from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 分类

SPLIT = 'split'                      # 可拆：每对象（或每 chunk）一张单
ATOMIC = 'atomic'                    # 只计数、不拆：集合动作 / DESTRUCTIVE
NOT_APPLICABLE = 'not_applicable'    # 属性 / 范围，不计入对象数
CLASSIFICATIONS: Tuple[str, ...] = (SPLIT, ATOMIC, NOT_APPLICABLE)

RISK_DESTRUCTIVE = 'DESTRUCTIVE'

# 参数路径语法：``ids`` / ``body.case_ids`` / ``items[].audio_id``
# 通配仅用于「整个容器下的数组字段都归同一类」（如维度 body 的字段属性）
_PATH_RE = re.compile(
    r'^(?P<key>[A-Za-z0-9_]+)(?P<each>\[\])?'
    r'(?:\.(?P<field>[A-Za-z0-9_]+|\*))?$')


class ObjectLimitExceeded(Exception):
    """单次调用影响对象超过上限（提案前拒绝，不建单、无副作用）。"""

    code = 'APPROVAL_OBJECT_LIMIT_EXCEEDED'

    def __init__(self, count: int, limit: int):
        self.count = int(count)
        self.limit = int(limit)
        super().__init__(
            f'单次调用影响对象 {self.count} 个，超过上限 {self.limit} 个；'
            '请拆成多次调用')


@dataclass(frozen=True)
class ArrayParam:
    """一个数组参数的分类登记（注册期探针的唯一输入）。

    - ``tool`` / ``action``：意图工具名与动作；``action=None`` 表示不限动作；
    - ``path``：参数路径（见 ``_PATH_RE``）；
    - ``kind``：对象 kind（``testcase`` / ``audio`` / ``task`` / ``device``）；
    - ``classification``：``split`` / ``atomic`` / ``not_applicable``；
    - ``when``：额外条件（例如 ``batch_action`` / ``body.mode``），不满足时
      该参数不参与计数（动作可能是非枚举范围）；
    - ``reason``：为什么这样分类（探针与文档都读它）。
    """

    tool: str
    action: Optional[str]
    path: str
    classification: str
    kind: Optional[str] = None
    when: Optional[Callable[[Mapping[str, Any]], bool]] = None
    reason: str = ''

    def __post_init__(self) -> None:
        if self.classification not in CLASSIFICATIONS:
            raise ValueError(
                f'{self.tool}.{self.action}.{self.path} 的分类非法：'
                f'{self.classification!r}（必须是 {"/".join(CLASSIFICATIONS)}）')
        if not _PATH_RE.match(self.path):
            raise ValueError(f'参数路径非法：{self.path!r}')
        if self.classification == SPLIT and not self.kind:
            raise ValueError(f'可拆参数必须声明对象 kind：{self.path}')

    @property
    def countable(self) -> bool:
        return self.classification in (SPLIT, ATOMIC) and bool(self.kind)


# ---------------------------------------------------------------- 注册表
#
# 定稿表见 §9.4.1「M2 现行可拆参数登记」。**新增写工具数组参数必须在这里显式
# 分类**（split / atomic / not_applicable），注册期测试漏分类判红。

def _batch_add_remove(arguments: Mapping[str, Any]) -> bool:
    return arguments.get('batch_action') in ('add_tags', 'remove_tags')


def _mode_is_selected(arguments: Mapping[str, Any]) -> bool:
    body = arguments.get('body')
    return isinstance(body, Mapping) and body.get('mode') == 'selected'


ARRAY_PARAMS: Tuple[ArrayParam, ...] = (
    # ---- 可拆（每对象一张单） ----
    ArrayParam(
        'tag_group_manage', 'batch_tag', 'ids', SPLIT, kind='testcase',
        when=_batch_add_remove,
        reason='按用例批量加 / 去标签：每张单只含一个用例时调用仍合法'),
    ArrayParam(
        'audio_annotate', 'batch_annotate', 'items[].audio_id', SPLIT,
        kind='audio',
        reason='批量标注：每项自带 audio_id，单对象调用合法'),
    ArrayParam(
        'task_run', 'retry', 'body.case_ids', SPLIT, kind='testcase',
        when=_mode_is_selected,
        reason='按所选用例重跑（mode=selected）：单一用例重跑合法'),
    ArrayParam(
        'evaluation_manage', 'reevaluate', 'body.case_ids', SPLIT,
        kind='testcase', when=_mode_is_selected,
        reason='按所选用例重评估（mode=selected）：单一用例重评估合法'),
    # ---- 只计数、不拆 ----
    ArrayParam(
        'device_control', 'batch', 'device_ids', ATOMIC, kind='device',
        reason='DESTRUCTIVE：批量设备控制恒一张单 + confirm=true（INT-2467），'
               '只展示对象数，不拆单'),
    ArrayParam(
        'task_run', 'merge', 'body.task_ids', ATOMIC, kind='task',
        reason='原子集合动作：少一个任务就非法（MERGE_MIN_TASKS），不可拆'),
    # ---- 属性 / 范围，不计入对象数 ----
    ArrayParam(
        'tag_group_manage', 'batch_tag', 'tags', NOT_APPLICABLE,
        reason='标签名是属性（对每个对象施加同样的标签），不是独立对象'),
    ArrayParam(
        'audio_import', 'confirm', 'tags', NOT_APPLICABLE,
        reason='导入时给该音频打的标签：属性'),
    ArrayParam(
        'audio_annotate', 'set_algorithms', 'algorithms', NOT_APPLICABLE,
        reason='算法体系是该音频的属性集合，对象只有 audio_id 一个'),
    ArrayParam(
        'audio_annotate', 'batch_annotate', 'items[].tags', NOT_APPLICABLE,
        reason='单项的标签属性'),
    ArrayParam(
        'audio_annotate', 'batch_annotate', 'items[].annotations',
        NOT_APPLICABLE, reason='单项的标注属性'),
    ArrayParam(
        'audio_annotate', 'batch_annotate', 'items', NOT_APPLICABLE,
        reason='items 是容器字段：其对象由 items[].audio_id 逐项枚举'
               '（见上方的可拆登记），容器本身不重复计数'),
    ArrayParam(
        'testcase_write', 'tag', 'tags', NOT_APPLICABLE,
        reason='给单个用例加 / 去的标签是属性；对象是用例本身（tc_id）'),
    ArrayParam(
        'evaluation_manage', 'reevaluate', 'body.dimension_ids',
        NOT_APPLICABLE,
        reason='重评估的维度范围（跑哪些维度），不是独立业务对象'),
    # 维度 body 的数组字段（api_endpoints / required_inputs / output_fields /
    # associated_algorithms）是字段属性，不是对象枚举：按动作登记通配分类，
    # 注册期探针逐个枚举后按通配匹配，漏登记的新动作会被判红。
    ArrayParam(
        'evaluation_manage', 'dimension_create', 'body.*', NOT_APPLICABLE,
        reason='维度字段属性（端点 / 输入 / 输出 / 关联算法），不构成对象枚举'),
    ArrayParam(
        'evaluation_manage', 'dimension_update', 'body.*', NOT_APPLICABLE,
        reason='维度字段属性（端点 / 输入 / 输出 / 关联算法），不构成对象枚举'),
)


def _wildcard(path: str) -> Optional[str]:
    """``body.case_ids`` → ``body.*``；``items[].tags`` → ``items[].*``。"""
    key, each, field = _parse(path)
    if field is None:
        return None
    return f'{key}{"[]" if each else ""}.*'


def classification_for(tool: str, action: Optional[str],
                       path: str) -> Optional[ArrayParam]:
    """按 ``(工具, 动作, 参数路径)`` 查注册表（支持容器通配）。

    注册期探针与运行期共用同一查询：先精确匹配，再按容器通配
    （``body.*`` / ``items[].*``）兜底。
    """
    wildcard = _wildcard(path)
    fallback: Optional[ArrayParam] = None
    for rule in ARRAY_PARAMS:
        if rule.tool != tool or rule.path != path:
            continue
        if rule.action is None or rule.action == action:
            return rule
    if wildcard is None:
        return None
    for rule in ARRAY_PARAMS:
        if rule.tool != tool or rule.path != wildcard:
            continue
        if rule.action is None or rule.action == action:
            fallback = rule
            break
    return fallback


# ---------------------------------------------------------------- 对象计数

@dataclass(frozen=True)
class ObjectScope:
    """一次 tool call 的对象影响面（计数结果）。"""

    kind: Optional[str] = None
    ids: Tuple[Any, ...] = ()
    counted: int = 1
    scope: Optional[str] = None            # 非枚举范围语义（如 ``mode=all``）
    rule: Optional[ArrayParam] = None

    @property
    def splittable(self) -> bool:
        return self.rule is not None and self.rule.classification == SPLIT

    @property
    def object_ref(self) -> Optional[Dict[str, Any]]:
        """审批单上的 ``object_ref``：``{kind, ids}``；无对象种类时为空。"""
        if self.kind is None:
            return None
        return {'kind': self.kind, 'ids': list(self.ids)}


def _id_key(value: Any) -> Tuple[str, Any]:
    """去重键：同值不同类型（``5`` / ``"5"``）是不同对象。"""
    return (type(value).__name__, value)


def _parse(path: str) -> Tuple[str, bool, Optional[str]]:
    match = _PATH_RE.match(path)
    if match is None:  # pragma: no cover - 构造期已校验
        raise ValueError(f'参数路径非法：{path!r}')
    return (match.group('key'), bool(match.group('each')),
            match.group('field'))


def _rows(arguments: Mapping[str, Any],
          rule: ArrayParam) -> List[Tuple[Any, Any]]:
    """参数路径 → ``[(对象 id, 参数内选择器)]``（原顺序）。

    - ``ids``：顶层数组，选择器就是 id；
    - ``body.case_ids``：``arguments['body']['case_ids']``；
    - ``items[].audio_id``：``arguments['items']`` 里每项的 ``audio_id``，
      选择器是整项（收窄时要保留该对象的其它字段）。
    """
    key, each, field = _parse(rule.path)
    container = arguments.get(key)
    if container is None:
        return []
    if field is None:
        if not isinstance(container, (list, tuple)):
            return []
        return [(value, value) for value in container]
    if each:
        if not isinstance(container, (list, tuple)):
            return []
        rows = []
        for item in container:
            if isinstance(item, Mapping) and field in item:
                rows.append((item[field], item))
        return rows
    if not isinstance(container, Mapping):
        return []
    values = container.get(field)
    if not isinstance(values, (list, tuple)):
        return []
    return [(value, value) for value in values]


def _rule_applies(rule: ArrayParam,
                  arguments: Mapping[str, Any]) -> bool:
    if rule.action is not None and arguments.get('action') != rule.action:
        return False
    if rule.when is not None and not rule.when(arguments):
        return False
    return True


def _range_rule(tool: str,
                arguments: Mapping[str, Any]) -> Optional[ArrayParam]:
    """该动作的「范围型」可计对象参数（用于非枚举范围展示对象 kind）。"""
    for rule in ARRAY_PARAMS:
        if rule.tool != tool or not rule.countable:
            continue
        if rule.action is not None and arguments.get('action') != rule.action:
            continue
        return rule
    return None


def object_scope(tool: str, arguments: Optional[Mapping[str, Any]]) -> ObjectScope:
    """数出一次 tool call 显式枚举的独立对象（``(kind, id)`` 去重）。"""
    values = dict(arguments or {})
    seen: List[Tuple[str, Any]] = []
    dedupe = set()
    split_rule: Optional[ArrayParam] = None
    for rule in ARRAY_PARAMS:
        if rule.tool != tool or not rule.countable:
            continue
        if not _rule_applies(rule, values):
            continue
        rows = _rows(values, rule)
        if not rows:
            continue
        if rule.classification == SPLIT and split_rule is None:
            split_rule = rule
        for object_id, _selector in rows:
            key = (rule.kind, _id_key(object_id))
            if key in dedupe:
                continue
            dedupe.add(key)
            seen.append((rule.kind, object_id))
    if seen:
        kind = (split_rule.kind if split_rule is not None
                else seen[0][0])
        return ObjectScope(
            kind=kind,
            ids=tuple(object_id for _kind, object_id in seen),
            counted=len(seen),
            rule=split_rule,
        )

    # 非枚举范围：动作有可计参数，但本次调用没有显式枚举对象
    # （``mode=all`` / ``failed_only`` / 标签级 rename）。计 1 个对象并保留
    # 范围语义（``proposal.arguments`` 未被收窄，审批人能看到 mode）。
    fallback = _range_rule(tool, values)
    if fallback is not None:
        return ObjectScope(
            kind=fallback.kind, counted=1,
            scope=_scope_label(values), rule=None)
    return ObjectScope(counted=1)


def _scope_label(arguments: Mapping[str, Any]) -> Optional[str]:
    body = arguments.get('body')
    if isinstance(body, Mapping) and body.get('mode'):
        return f'mode={body.get("mode")}'
    if arguments.get('batch_action'):
        return f'batch_action={arguments.get("batch_action")}'
    return None


# ---------------------------------------------------------------- 分块

@dataclass(frozen=True)
class ApprovalChunk:
    """分块后的一张单：``index`` 从 1 开始。"""

    index: int
    total: int
    arguments: Dict[str, Any]
    object_ref: Optional[Dict[str, Any]]
    ids: Tuple[Any, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ApprovalPlan:
    """一次 tool call 的审批计划（1..N 张单）。"""

    object_count: int
    kind: Optional[str]
    scope: Optional[str]
    chunks: Tuple[ApprovalChunk, ...]

    @property
    def total(self) -> int:
        return len(self.chunks)


def _narrow(arguments: Mapping[str, Any], rule: ArrayParam,
            ids: Sequence[Any]) -> Dict[str, Any]:
    """把参数收窄到本单对象（浅层深拷贝，避免改动原调用参数）。"""
    narrowed = copy.deepcopy(dict(arguments))
    key, each, field = _parse(rule.path)
    wanted = {_id_key(value): value for value in ids}
    if field is None:
        narrowed[key] = [wanted[_id_key(v)] for v in ids]
        return narrowed
    container = narrowed.get(key)
    if each:
        narrowed[key] = [
            item for item in (container or [])
            if isinstance(item, Mapping)
            and _id_key(item.get(field)) in wanted]
        return narrowed
    body = dict(container or {})
    body[field] = [wanted[_id_key(v)] for v in ids]
    narrowed[key] = body
    return narrowed


def plan_approvals(tool: str, arguments: Optional[Mapping[str, Any]], *,
                   risk: str = 'WRITE', threshold: int = 20,
                   chunk_size: int = 1,
                   max_objects: int = 100) -> ApprovalPlan:
    """按配置给出审批分块计划；超过对象上限时抛 ``ObjectLimitExceeded``。

    - 严格 ``> threshold`` 才拆（``= threshold`` 不拆）；
    - ``DESTRUCTIVE`` 与 ``atomic`` 参数恒一张单（只展示对象数）；
    - 每块参数收窄到本单对象；不拆时参数原样保留（不加窄）。
    """
    values = dict(arguments or {})
    scope = object_scope(tool, values)
    if scope.counted > max(1, int(max_objects)):
        raise ObjectLimitExceeded(scope.counted, int(max_objects))
    limit = max(1, int(threshold))
    size = max(1, int(chunk_size))
    split = (scope.splittable
             and risk != RISK_DESTRUCTIVE
             and scope.counted > limit
             and scope.counted > 1)
    if not split:
        return ApprovalPlan(
            object_count=scope.counted, kind=scope.kind, scope=scope.scope,
            chunks=(ApprovalChunk(
                index=1, total=1, arguments=values,
                object_ref=scope.object_ref, ids=scope.ids),))
    rule = scope.rule
    assert rule is not None  # split 为真时必定来自 SPLIT 规则
    groups = [scope.ids[start:start + size]
              for start in range(0, len(scope.ids), size)]
    total = len(groups)
    chunks = tuple(
        ApprovalChunk(
            index=index, total=total,
            arguments=_narrow(values, rule, group),
            object_ref={'kind': scope.kind, 'ids': list(group)},
            ids=tuple(group))
        for index, group in enumerate(groups, start=1))
    return ApprovalPlan(object_count=scope.counted, kind=scope.kind,
                        scope=scope.scope, chunks=chunks)


def new_batch_id() -> str:
    """同批审批单共享的 ``batch_id``（32 位 hex，列宽 String(36)）。"""
    return uuid.uuid4().hex


__all__ = [
    'ARRAY_PARAMS', 'ATOMIC', 'ArrayParam', 'ApprovalChunk', 'ApprovalPlan',
    'CLASSIFICATIONS', 'NOT_APPLICABLE', 'ObjectLimitExceeded', 'ObjectScope',
    'RISK_DESTRUCTIVE', 'SPLIT', 'classification_for', 'new_batch_id',
    'object_scope', 'plan_approvals',
]
