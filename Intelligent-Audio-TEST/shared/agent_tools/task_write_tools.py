# -*- coding: utf-8 -*-
"""任务域写意图工具 ``task_run`` 的动作表（INT-2468，M2）。

| 动作 | 目标接口 | 权限 | 风险 |
|---|---|---|---|
| ``create`` | ``POST /api/v1/tasks``（``task_create``） | ``task:create`` | WRITE |
| ``start`` | ``POST /api/v1/tasks/{task_id}/start``（``task_start``） | ``task:execute`` | WRITE |
| ``stop`` | ``POST /api/v1/tasks/{task_id}/stop``（``task_stop``） | ``task:execute`` | WRITE |
| ``retry`` | ``POST /api/v1/tasks/{task_id}/retry``（``task_retry``） | ``task:execute`` | WRITE |
| ``merge`` | ``POST /api/v1/tasks/merge``（``task_merge``） | ``task:merge`` | WRITE |
| ``reextract`` | ``POST /api/v1/tasks/{task_id}/reextract``（``task_reextract``） | ``task:reextract`` | WRITE |

口径与幂等：

- ``start`` / ``stop`` 在 task_service 侧就是幂等的：已在 ``running`` / ``queued``
  时 start 返回成功并说明「已在运行中 / 队列中」，不会重复建任务或重复执行
  （``task_service/application/task/task_lifecycle_service.py``）；工具层原样
  转述接口文案，不自己判定「是否算启动成功」。
- 同一 tool_call 的重复执行由 M2 基座（INT-2466）的审批幂等键领取一次，
  工具层不生成第二套幂等键。
- ``reextract`` 的网关实现**要求 JSON body**（``TaskReextractInput`` 的
  ``task_id`` 在 body 里），而 MCP 注册项只声明了路径参数；本工具在归一阶段
  注入 ``body={task_id, execution_status?, evaluation_status?}``，否则网关拿不到
  必填 ``task_id`` 直接 400。
- ``merge`` 至少两个任务（服务端约束），且源任务必须已完成（未完成返回
  「任务 'X' 未完成，无法合并」，实测）；``retry`` 的 ``case_ids`` 与
  ``mode=selected`` 必须成对出现，否则会被服务端按整任务语义静默执行（不是用户
  要的范围）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.agent_tools.write_support import (
    WriteAction, require_body, require_positive_int, require_string_list,
    resolve_domain,
)

# 任务重执行范围（shared.models.common_enums.RetryScopeMode 的接口取值）
RETRY_MODES: Tuple[str, ...] = ('selected', 'failed_only', 'all')

# 重新提取的状态取值（shared.utils.status_constants.ExecutionStatus /
# EvaluationStatus；缺省按网关默认 COMPLETED）
EXECUTION_STATUS_DEFAULT = 'completed'
EXECUTION_STATUS_VALUES: Tuple[str, ...] = (
    'pending', 'queued', 'running', 'completed', 'stopped', 'failed', 'skipped')
EVALUATION_STATUS_VALUES: Tuple[str, ...] = (
    'pending', 'queued', 'running', 'calculating', 'completed', 'stopped',
    'failed', 'skipped')

# 合并至少两个任务（task_crud_service.merge 的硬约束）
MERGE_MIN_TASKS = 2

ACTIONS: Dict[str, WriteAction] = {
    'create': WriteAction(
        tool='task_create', params=('body',), required=('body',),
        permissions=('task:create',)),
    'start': WriteAction(
        tool='task_start', params=('task_id',), required=('task_id',),
        permissions=('task:execute',)),
    'stop': WriteAction(
        tool='task_stop', params=('task_id',), required=('task_id',),
        permissions=('task:execute',)),
    'retry': WriteAction(
        tool='task_retry', params=('task_id', 'body'), required=('task_id',),
        permissions=('task:execute',)),
    'merge': WriteAction(
        tool='task_merge', params=('body',), required=('body',),
        permissions=('task:merge',)),
    'reextract': WriteAction(
        tool='task_reextract',
        params=('task_id', 'execution_status', 'evaluation_status'),
        required=('task_id',), permissions=('task:reextract',)),
}

ACTION_NAMES: Tuple[str, ...] = tuple(ACTIONS)


def _prepare_retry(merged: Dict[str, Any]) -> Optional[str]:
    body = merged.get('body')
    if body is None:
        return None
    if not isinstance(body, dict) or not body:
        return 'action=retry 的 body 必须是非空对象（case_ids / mode）'
    unknown = sorted(set(body) - {'case_ids', 'mode'})
    if unknown:
        return (f'action=retry 的 body 不支持字段：{"、".join(unknown)}'
                '（只支持 case_ids / mode）')
    mode = body.get('mode')
    if mode is not None and mode not in RETRY_MODES:
        return f'action=retry 的 body.mode 取值必须是 {"/".join(RETRY_MODES)} 之一'
    case_ids = body.get('case_ids')
    if case_ids is not None:
        error = require_string_list(case_ids, 'body.case_ids', 'retry')
        if error:
            return error
        if mode != 'selected':
            return ('action=retry 指定 case_ids 时必须同时给 body.mode=selected'
                    '（缺省 mode=all 会按整任务重跑，不是所选用例）')
    elif mode == 'selected':
        return 'action=retry 的 body.mode=selected 时 case_ids 不能为空'
    return None


def _prepare_merge(merged: Dict[str, Any]) -> Optional[str]:
    error = require_body(merged, action='merge', required_fields=())
    if error:
        return error
    body = merged['body']
    unknown = sorted(set(body) - {'task_ids'})
    if unknown:
        return (f'action=merge 的 body 不支持字段：{"、".join(unknown)}'
                '（网关 TaskMergeRequest 只接受 task_ids，'
                '其余字段会被静默丢弃）')
    task_ids = body.get('task_ids')
    if not isinstance(task_ids, list) or not task_ids:
        return 'action=merge 的 body.task_ids 必须是非空整数数组'
    normalized: list = []
    for value in task_ids:
        error = require_positive_int(value, 'body.task_ids[]', 'merge')
        if error:
            return error
        if value in normalized:
            return f'action=merge 的 body.task_ids 含重复任务：{value}'
        normalized.append(value)
    if len(normalized) < MERGE_MIN_TASKS:
        return f'action=merge 至少需要 {MERGE_MIN_TASKS} 个任务，当前 {len(normalized)} 个'
    return None


def _prepare_reextract(merged: Dict[str, Any]) -> Optional[str]:
    execution_status = merged.get('execution_status') or EXECUTION_STATUS_DEFAULT
    if execution_status not in EXECUTION_STATUS_VALUES:
        return (f'action=reextract 的 execution_status 取值必须是 '
                f'{"/".join(EXECUTION_STATUS_VALUES)} 之一')
    evaluation_status = merged.get('evaluation_status')
    if evaluation_status is not None and \
            evaluation_status not in EVALUATION_STATUS_VALUES:
        return (f'action=reextract 的 evaluation_status 取值必须是 '
                f'{"/".join(EVALUATION_STATUS_VALUES)} 之一')
    body: Dict[str, Any] = {
        'task_id': merged['task_id'],
        'execution_status': execution_status,
    }
    if evaluation_status is not None:
        body['evaluation_status'] = evaluation_status
    merged.pop('execution_status', None)
    merged.pop('evaluation_status', None)
    merged['body'] = body
    return None


def _prepare(action: str, merged: Dict[str, Any]) -> Optional[str]:
    """动作级归一：ID / 正文校验 + 网关必需但 MCP 未声明的 body 注入。"""
    if action == 'create':
        return require_body(merged, action=action, required_fields=('name',))
    if action in ('start', 'stop', 'reextract'):
        error = require_positive_int(merged.get('task_id'), 'task_id', action)
        if error:
            return error
        return _prepare_reextract(merged) if action == 'reextract' else None
    if action == 'retry':
        error = require_positive_int(merged.get('task_id'), 'task_id', action)
        return error or _prepare_retry(merged)
    # action == 'merge'
    return _prepare_merge(merged)


def resolve(arguments: Optional[Dict[str, Any]]
            ) -> Tuple[Optional[dict], Optional[Dict[str, Any]], Optional[str]]:
    """解析 ``task_run`` 调用为 ``(目标工具项, 合并参数, 错误文本)``。"""
    return resolve_domain(ACTIONS, arguments, label='task_run',
                          prepare=_prepare)


__all__ = [
    'ACTIONS', 'ACTION_NAMES', 'EVALUATION_STATUS_VALUES',
    'EXECUTION_STATUS_DEFAULT', 'EXECUTION_STATUS_VALUES', 'MERGE_MIN_TASKS',
    'RETRY_MODES', 'resolve',
]
