# -*- coding: utf-8 -*-
"""用例域写意图工具 ``testcase_write`` 的动作表（INT-2468，M2）。

动作与目标 REST（全部是网关既有写接口，不新增端点）：

| 动作 | 目标接口 | 权限 | 风险 |
|---|---|---|---|
| ``create`` | ``POST /api/v1/testcases``（``testcase_create``） | ``testcase:create`` | WRITE |
| ``update`` | ``PUT /api/v1/testcases/{tc_id}``（``testcase_update``） | ``testcase:update`` | WRITE |
| ``copy`` | ``POST /api/v1/testcases/{tc_id}/copy``（``testcase_copy``） | ``testcase:copy`` | WRITE |
| ``delete`` | ``DELETE /api/v1/testcases/{tc_id}``（``testcase_delete``） | ``testcase:delete`` | **DESTRUCTIVE** |
| ``tag`` | ``POST /api/v1/testcases/batch``（``add_tags`` / ``remove_tags``） | ``testcase:update`` | WRITE |

口径：

- **删除是软删**（``testcase_service.testcase_crud_service.delete`` →
  ``soft_delete_testcase``，进回收站）：Agent 侧只暴露删除，恢复 / 彻底删除
  仍是产品「回收站」页的操作（与 REST 语义一致，不另造口径）。即便如此，
  删除动作按 ``DESTRUCTIVE`` 提案，审批人能看到目标 ID 与请求预览。
- **新建必须归属分组**：创建服务对 ``group_id`` / ``group`` 都缺的请求直接
  400「缺少必要字段: group_id 或 group」（实测），工具层提前拦下。
- **打标签走批量接口的单 ID 形态**（``ids=[tc_id]``），不读改写：
  「加 / 去标签」服务端有原子语义，先 ``GET`` 再整列 ``PUT`` 会在并发下覆盖
  别人刚打的标签。整列替换请用 ``update`` 的 ``body.tags``。
- **幂等**：同一 tool_call 的重复执行由 M2 基座（INT-2466）的审批幂等键
  领取一次；批量接口自身也按 ``idempotency_key`` / 请求指纹在短窗口去重。
  工具层不额外生成幂等键，避免与审批层出现两套口径。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.agent_tools.mcp_registry import tool_entry
from shared.agent_tools.write_support import (
    RISK_DESTRUCTIVE, WriteAction, require_body, require_identifier,
    require_string_list, resolve_domain,
)

# 用例批量接口：网关有路由（api_gateway/routes/testcase_bp.py:batch_action），
# 外部 MCP 表未登记（INT-2453 的 207 项对外契约不外扩），作为内部写入口。
TESTCASE_BATCH_TOOL: dict = tool_entry(
    'testcase_batch', '用例批量写操作（批量打标等，body 带 action/ids）',
    {'body': {'type': 'object',
              'description': '批量操作参数（action / ids / tags / old_tag_name 等）'}},
    ['testcase:update'], 'POST', '/api/v1/testcases/batch')

INTERNAL_TOOLS: Dict[str, dict] = {
    TESTCASE_BATCH_TOOL['name']: TESTCASE_BATCH_TOOL,
}

# 打标签子动作：意图层的 add / remove → 批量接口的真实 action 取值
TAG_MODE_ACTIONS: Dict[str, str] = {
    'add': 'add_tags',
    'remove': 'remove_tags',
}
TAG_MODES: Tuple[str, ...] = tuple(TAG_MODE_ACTIONS)

ACTIONS: Dict[str, WriteAction] = {
    'create': WriteAction(
        tool='testcase_create', params=('body',), required=('body',),
        permissions=('testcase:create',)),
    'update': WriteAction(
        tool='testcase_update', params=('tc_id', 'body'),
        required=('tc_id', 'body'), permissions=('testcase:update',)),
    'copy': WriteAction(
        tool='testcase_copy', params=('tc_id',), required=('tc_id',),
        permissions=('testcase:copy',)),
    'delete': WriteAction(
        tool='testcase_delete', params=('tc_id',), required=('tc_id',),
        permissions=('testcase:delete',), risk=RISK_DESTRUCTIVE),
    'tag': WriteAction(
        tool=TESTCASE_BATCH_TOOL['name'],
        params=('tc_id', 'tag_mode', 'tags'),
        required=('tc_id', 'tag_mode', 'tags'),
        permissions=('testcase:update',)),
}

ACTION_NAMES: Tuple[str, ...] = tuple(ACTIONS)

# 新建用例的归属字段：task_service 的创建服务对二者都缺时直接 400
# （``缺少必要字段: group_id 或 group``，实测）。
CREATE_GROUP_FIELDS: Tuple[str, ...] = ('group_id', 'group')


def _prepare(action: str, merged: Dict[str, Any]) -> Optional[str]:
    """动作级归一：校验 ID / 正文，并把打标签展开成批量接口载荷。"""
    if action == 'create':
        error = require_body(merged, action=action, required_fields=('name',))
        if error:
            return error
        body = merged['body']
        if not any(body.get(name) for name in CREATE_GROUP_FIELDS):
            return ('action=create 的 body 需要 group_id 或 group（用例必须归属'
                    '分组；分组 ID 先用 tag-group 的 group_list 查）')
        return None
    if action == 'update':
        error = require_identifier(merged.get('tc_id'), 'tc_id', action)
        return error or require_body(merged, action=action)
    if action in ('copy', 'delete'):
        return require_identifier(merged.get('tc_id'), 'tc_id', action)
    # action == 'tag'
    error = require_identifier(merged.get('tc_id'), 'tc_id', action)
    if error:
        return error
    tag_mode = merged.get('tag_mode')
    if tag_mode not in TAG_MODE_ACTIONS:
        return f'action=tag 的 tag_mode 取值必须是 {"/".join(TAG_MODES)} 之一'
    error = require_string_list(merged.get('tags'), 'tags', action)
    if error:
        return error
    tc_id = merged['tc_id']
    tags = list(merged['tags'])
    merged.clear()
    merged['body'] = {
        'action': TAG_MODE_ACTIONS[tag_mode],
        'ids': [tc_id],
        'tags': tags,
    }
    return None


def resolve(arguments: Optional[Dict[str, Any]]
            ) -> Tuple[Optional[dict], Optional[Dict[str, Any]], Optional[str]]:
    """解析 ``testcase_write`` 调用为 ``(目标工具项, 合并参数, 错误文本)``。"""
    return resolve_domain(ACTIONS, arguments, label='testcase_write',
                          tools=INTERNAL_TOOLS, prepare=_prepare)


__all__ = [
    'ACTIONS', 'ACTION_NAMES', 'INTERNAL_TOOLS', 'TAG_MODE_ACTIONS', 'TAG_MODES',
    'TESTCASE_BATCH_TOOL', 'resolve',
]
