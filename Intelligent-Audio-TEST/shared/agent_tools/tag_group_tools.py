# -*- coding: utf-8 -*-
"""标签 / 用例分组写意图工具 ``tag_group_manage`` 的动作表（INT-2468，M2）。

动作形态沿用预留 Schema（方案 §6.1）：``action`` = create / update / delete /
batch_tag，CRUD 另带 ``target_kind`` = tag / group。

| action | target_kind | 目标接口 | 权限 | 风险 |
|---|---|---|---|---|
| ``create`` | ``tag`` | ``POST /api/v1/tags``（``tag_create``） | ``tag:create`` | WRITE |
| ``update`` | ``tag`` | ``PUT /api/v1/tags/{tag_id}``（``tag_update``） | ``tag:update`` | WRITE |
| ``delete`` | ``tag`` | ``DELETE /api/v1/tags/{tag_id}`` | ``tag:delete`` | **DESTRUCTIVE** |
| ``create`` | ``group`` | ``POST /api/v1/groups``（``group_create``） | ``group:create`` | WRITE |
| ``update`` | ``group`` | ``PUT /api/v1/groups/{group_id}``（``group_update``） | ``group:update`` | WRITE |
| ``delete`` | ``group`` | ``DELETE /api/v1/groups/{group_id}`` | ``group:delete`` | **DESTRUCTIVE** |
| ``batch_tag`` | — | ``POST /api/v1/testcases/batch``（``add_tags`` / ``remove_tags`` / ``rename_tag``） | 见下 | 见下 |

批量打标的子动作与基线口径：

- ``add_tags`` / ``remove_tags``：给一批用例加 / 去标签，权限 ``testcase:update``；
  ``add_tags`` 对不存在的标签名会由仓储 ``get_or_create_tag`` 自动登记标签字典
  （实测与产品页一致，不是失败）；需要指定颜色 / 分类 / 可见性时先 ``create``
  建标签；
- ``rename_tag``：标签级改名，作用于全部引用用例，网关按删除级权限校验
  （``testcase:delete``），动作级风险记为 ``DESTRUCTIVE``；
- ``batch_tag`` 不带 ``target_kind``（标签是改名 / 加去动作，不是「对标签资源
  CRUD」），带了会被参数白名单拒绝，不做静默忽略。

分组删除使用内部入口 ``group_delete_query``：网关的 ``DELETE /groups/{id}``
支持 ``cascade`` 查询参数（分组下有未删除用例时缺省会 400），``group_delete``
的 MCP Schema 没有声明该查询参数，直接复用会把它静默丢弃。标签删除同理
（``tag_delete_query``，``DELETE /tags/{id}?cascade=``）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.agent_tools.mcp_registry import tool_entry
from shared.agent_tools.testcase_write_tools import TESTCASE_BATCH_TOOL
from shared.agent_tools.write_support import (
    RISK_DESTRUCTIVE, WriteAction, require_body, require_identifier,
    require_positive_int, require_string_list, require_text, resolve_domain,
)

TARGET_KINDS: Tuple[str, ...] = ('tag', 'group')

# 批量打标的子动作（与 task_service CaseBatchService 的 handler 键逐字一致）
BATCH_ADD_TAGS = 'add_tags'
BATCH_REMOVE_TAGS = 'remove_tags'
BATCH_RENAME_TAG = 'rename_tag'
BATCH_ACTIONS: Tuple[str, ...] = (BATCH_ADD_TAGS, BATCH_REMOVE_TAGS,
                                  BATCH_RENAME_TAG)
# 子动作 → (权限, 风险)：改名作用于全部引用用例，按删除级权限与破坏性风险
_BATCH_POLICY: Dict[str, Tuple[Tuple[str, ...], str]] = {
    BATCH_ADD_TAGS: (('testcase:update',), 'WRITE'),
    BATCH_REMOVE_TAGS: (('testcase:update',), 'WRITE'),
    BATCH_RENAME_TAG: (('testcase:delete',), RISK_DESTRUCTIVE),
}

# 内部入口：带 cascade 查询参数的删除工具（MCP 表里的 tag_delete / group_delete
# 没有声明该查询参数，DELETE 的 build_path 只放行 query_params，复用它会把
# cascade 静默丢掉）。名称与 MCP 工具区分，避免索引 / 注册表混淆。
TAG_DELETE_TOOL: dict = tool_entry(
    'tag_delete_query', '删除标签（可级联清除用例上的引用）',
    {'tag_id': {'type': 'integer', 'description': '标签 ID', 'required': True},
     'cascade': {'type': 'boolean', 'description': '是否级联'}},
    ['tag:delete'], 'DELETE', '/api/v1/tags/{tag_id}',
    path_params=['tag_id'], query_params=['cascade'])
GROUP_DELETE_TOOL: dict = tool_entry(
    'group_delete_query', '删除用例分组（cascade 可连分组下用例一并处置）',
    {'group_id': {'type': 'string', 'description': '分组 ID（UUID）',
                  'required': True},
     'cascade': {'type': 'boolean', 'description': '是否级联'}},
    ['group:delete'], 'DELETE', '/api/v1/groups/{group_id}',
    path_params=['group_id'], query_params=['cascade'])

INTERNAL_TOOLS: Dict[str, dict] = {
    TAG_DELETE_TOOL['name']: TAG_DELETE_TOOL,
    GROUP_DELETE_TOOL['name']: GROUP_DELETE_TOOL,
    TESTCASE_BATCH_TOOL['name']: TESTCASE_BATCH_TOOL,
}

# CRUD 动作 × 目标类型 → 动作定义。``target_kind`` 只用于选工具，进参数白名单
# 是为了允许调用方传它；``_prepare`` 在选完工具后把它从合并参数里剔除，
# 不参与路径拼接，也不进 POST/PUT 的 body。
CRUD_ACTIONS: Dict[Tuple[str, str], WriteAction] = {
    ('tag', 'create'): WriteAction(
        tool='tag_create', params=('target_kind', 'body'),
        required=('target_kind', 'body'), permissions=('tag:create',)),
    ('tag', 'update'): WriteAction(
        tool='tag_update', params=('target_kind', 'tag_id', 'body'),
        required=('target_kind', 'tag_id', 'body'),
        permissions=('tag:update',)),
    ('tag', 'delete'): WriteAction(
        tool=TAG_DELETE_TOOL['name'],
        params=('target_kind', 'tag_id', 'cascade'),
        required=('target_kind', 'tag_id'),
        permissions=('tag:delete',), risk=RISK_DESTRUCTIVE),
    ('group', 'create'): WriteAction(
        tool='group_create', params=('target_kind', 'body'),
        required=('target_kind', 'body'), permissions=('group:create',)),
    ('group', 'update'): WriteAction(
        tool='group_update', params=('target_kind', 'group_id', 'body'),
        required=('target_kind', 'group_id', 'body'),
        permissions=('group:update',)),
    ('group', 'delete'): WriteAction(
        tool=GROUP_DELETE_TOOL['name'],
        params=('target_kind', 'group_id', 'cascade'),
        required=('target_kind', 'group_id'),
        permissions=('group:delete',), risk=RISK_DESTRUCTIVE),
}

BATCH_TAG_ACTION: WriteAction = WriteAction(
    tool=TESTCASE_BATCH_TOOL['name'],
    params=('batch_action', 'ids', 'tags', 'old_tag_name', 'new_tag_name'),
    required=('batch_action',),
    # 子动作级权限 / 风险在 ``permissions_for`` / ``risk_for`` 里解析
    permissions=('testcase:update',))

# 意图 action → 是否为 CRUD（batch_tag 单独处理）
CRUD_ACTION_NAMES: Tuple[str, ...] = ('create', 'update', 'delete')
ACTION_NAMES: Tuple[str, ...] = CRUD_ACTION_NAMES + ('batch_tag',)


def _prepare(action: str, merged: Dict[str, Any]) -> Optional[str]:
    kind = merged.pop('target_kind', None)
    if action == 'create':
        error = require_body(merged, action=action, required_fields=('name',))
        return error
    if action == 'update':
        if kind == 'tag':
            error = require_positive_int(merged.get('tag_id'), 'tag_id', action)
        else:
            error = require_identifier(merged.get('group_id'), 'group_id', action)
        return error or require_body(merged, action=action)
    # action == 'delete'
    if merged.get('cascade') is not None and \
            not isinstance(merged.get('cascade'), bool):
        return f'action=delete 的 cascade 必须是布尔值'
    if kind == 'tag':
        return require_positive_int(merged.get('tag_id'), 'tag_id', action)
    return require_identifier(merged.get('group_id'), 'group_id', action)


def _prepare_batch(action: str, merged: Dict[str, Any]) -> Optional[str]:
    sub = merged.get('batch_action')
    if sub not in BATCH_ACTIONS:
        return (f'action=batch_tag 的 batch_action 取值必须是 '
                f'{"/".join(BATCH_ACTIONS)} 之一')
    if sub == BATCH_RENAME_TAG:
        # 网关 TestCaseBatchActionRequest.ids 是必填字段（实测缺省直接 400）：
        # rename_tag 是标签级动作，语义上不按用例筛选，按前端基线显式传空数组。
        ids = merged.get('ids')
        if ids is not None and (not isinstance(ids, list) or ids):
            return ('batch_action=rename_tag 是标签级动作（作用于全部引用用例），'
                    'ids 只接受空数组；不要按用例筛选改名')
        error = require_text(merged.get('old_tag_name'), 'old_tag_name', action)
        if error:
            return error
        error = require_text(merged.get('new_tag_name'), 'new_tag_name', action)
        if error:
            return error
        if merged['old_tag_name'] == merged['new_tag_name']:
            return 'batch_action=rename_tag 的新旧标签名不能相同'
        old_tag_name = merged['old_tag_name']
        new_tag_name = merged['new_tag_name']
        merged.clear()
        merged['body'] = {
            'action': BATCH_RENAME_TAG,
            'ids': [],
            'old_tag_name': old_tag_name,
            'new_tag_name': new_tag_name,
        }
        return None
    error = require_string_list(merged.get('ids'), 'ids', action)
    if error:
        return error
    error = require_string_list(merged.get('tags'), 'tags', action)
    if error:
        return error
    ids = list(merged['ids'])
    tags = list(merged['tags'])
    merged.clear()
    merged['body'] = {'action': sub, 'ids': ids, 'tags': tags}
    return None


def resolve(arguments: Optional[Dict[str, Any]]
            ) -> Tuple[Optional[dict], Optional[Dict[str, Any]], Optional[str]]:
    """解析 ``tag_group_manage`` 调用为 ``(目标工具项, 合并参数, 错误文本)``。"""
    values = dict(arguments or {})
    action = values.get('action')
    if action == 'batch_tag':
        return resolve_domain({'batch_tag': BATCH_TAG_ACTION}, values,
                              label='tag_group_manage',
                              tools=INTERNAL_TOOLS, prepare=_prepare_batch)
    if action not in CRUD_ACTION_NAMES:
        return None, None, (
            f'action 取值必须是 {"/".join(ACTION_NAMES)} 之一')
    kind = values.get('target_kind')
    if kind not in TARGET_KINDS:
        return None, None, (
            f'action={action} 必须指定 target_kind，取值 '
            f'{"/".join(TARGET_KINDS)} 之一')
    spec = CRUD_ACTIONS[(kind, action)]
    return resolve_domain({str(action): spec}, values,
                          label='tag_group_manage',
                          tools=INTERNAL_TOOLS, prepare=_prepare)


def permissions_for(action: Any, arguments: Optional[Dict[str, Any]] = None
                    ) -> Optional[Tuple[str, ...]]:
    """动作级权限：CRUD 按 target_kind，batch_tag 按子动作。"""
    values = dict(arguments or {})
    if action == 'batch_tag':
        policy = _BATCH_POLICY.get(values.get('batch_action'))
        return policy[0] if policy else None
    if action not in CRUD_ACTION_NAMES:
        return None
    spec = CRUD_ACTIONS.get((values.get('target_kind'), str(action)))
    return spec.permissions if spec else None


def risk_for(action: Any, arguments: Optional[Dict[str, Any]] = None
             ) -> Optional[str]:
    """动作级风险：删除与 rename_tag 为 ``DESTRUCTIVE``。"""
    values = dict(arguments or {})
    if action == 'batch_tag':
        policy = _BATCH_POLICY.get(values.get('batch_action'))
        return policy[1] if policy else None
    if action not in CRUD_ACTION_NAMES:
        return None
    spec = CRUD_ACTIONS.get((values.get('target_kind'), str(action)))
    return spec.risk if spec else None


__all__ = [
    'ACTION_NAMES', 'BATCH_ACTIONS', 'BATCH_ADD_TAGS', 'BATCH_REMOVE_TAGS',
    'BATCH_RENAME_TAG', 'BATCH_TAG_ACTION', 'CRUD_ACTIONS', 'CRUD_ACTION_NAMES',
    'GROUP_DELETE_TOOL', 'INTERNAL_TOOLS', 'TAG_DELETE_TOOL', 'TARGET_KINDS',
    'permissions_for', 'resolve', 'risk_for',
]
