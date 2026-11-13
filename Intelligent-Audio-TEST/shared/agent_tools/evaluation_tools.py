# -*- coding: utf-8 -*-
"""评估域写意图工具分组（INT-2469，M2，方案 §6.1 / §6.2）。

``evaluation_manage`` 覆盖评估维度 / 分类的写动作、维度可见性切换与触发重评估。
动作 → 目标 REST 的映射、动作级权限、body 字段白名单与条件必填全部收敛在本模块，
``intent_tools`` 只做注册与透传（与 ``device_tools`` 同构，避免两套口径）。

为什么分类更新 / 删除写在本模块而不进 ``mcp_registry.TOOLS``：

- ``mcp_registry.TOOLS`` 是外部 MCP ``tools/list`` 的 1:1 契约（207 条，
  INT-2453 / INT-2465 钉住并有快照测试），本卡只扩内部 Agent 能力，不外扩外部清单；
- 网关已有 ``PUT /api/v1/evaluation/categories/{cat_id}`` 与
  ``DELETE /api/v1/evaluation/categories/{cat_id}``，但外部 MCP 表未登记。
  这里以**Agent 专用写目标**声明（字段与 MCP 注册项同形），复用
  ``mcp_registry.build_path`` / ``build_body`` 的请求拼装，不复制第二套构造器。

写路径不落业务副作用：提案 + 审批由 Loop 的审批服务（INT-2466）统一负责，本模块
只回答「这个动作落到哪个接口、要什么权限、参数合不合法、审批人该看到什么」。
删除动作后端是**级联软删**（``_soft_delete_tree`` / 分类 ``deleted=True``），
重复执行不会物理删除数据。

字段名 / 参数名一律以网关真实路由与 ``api_gateway/schemas/evaluation.py`` 为准；
可见性二值、重评估类型 / 范围取值与评估服务侧常量对齐，不在这里写字面量之外的枚举。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.agent_tools.mcp_registry import get_tool as get_mcp_tool
from shared.agent_tools.mcp_registry import tool_entry

DIM_MANAGE = 'evaluation:dim_manage'
CATEGORY_MANAGE = 'evaluation:category_manage'
EVALUATION_EXECUTE = 'evaluation:execute'
EVALUATION_SHARE = 'evaluation:share'

# 写动作 → 目标工具名。前 6 项在 ``mcp_registry``，后 2 项是本模块的
# Agent 专用写目标（外部 MCP 未登记），见模块 docstring。
EVALUATION_MANAGE_ACTIONS: Dict[str, str] = {
    'dimension_create': 'evaluation_dimension_create',
    'dimension_update': 'evaluation_dimension_update',
    'dimension_delete': 'evaluation_dimension_delete',
    'dimension_visibility': 'evaluation_dimension_set_visibility',
    'category_create': 'evaluation_category_create',
    'category_update': 'evaluation_category_update',
    'category_delete': 'evaluation_category_delete',
    'reevaluate': 'evaluation_task_reevaluate',
}

# 动作级权限（OR 语义）：工具级声明只表达可见性，调用时按 action 收窄，
# 避免「持有 dimension 管理权限」的用户删除分类 / 触发重评估。
EVALUATION_MANAGE_PERMISSIONS: Dict[str, Tuple[str, ...]] = {
    'dimension_create': (DIM_MANAGE,),
    'dimension_update': (DIM_MANAGE,),
    'dimension_delete': (DIM_MANAGE,),
    'dimension_visibility': (EVALUATION_SHARE,),
    'category_create': (CATEGORY_MANAGE,),
    'category_update': (CATEGORY_MANAGE,),
    'category_delete': (CATEGORY_MANAGE,),
    'reevaluate': (EVALUATION_EXECUTE,),
}

# 目标对象 ID 参数（动作级条件必填）：动作 → 参数名
EVALUATION_MANAGE_ID_PARAMS: Dict[str, str] = {
    'dimension_update': 'dim_id',
    'dimension_delete': 'dim_id',
    'dimension_visibility': 'dim_id',
    'category_update': 'cat_id',
    'category_delete': 'cat_id',
}

# 网关 APIModel 基类 ``extra='ignore'``：不认识的 body 字段被静默丢弃。
# 工具层先白名单拦下「传了但不会生效」的字段，避免模型以为改成功了。
DIMENSION_BODY_FIELDS: Tuple[str, ...] = (
    'name', 'description', 'keywords', 'dimension_type', 'parent_dimension_id',
    'task_type_code', 'category_id', 'api_url', 'api_endpoints', 'api_settings',
    'api_status', 'score_unit', 'statistic_method', 'agg_denominator',
    'exclude_rounds', 'type', 'result_type', 'result_min', 'result_max',
    'decimal_places', 'weight', 'sort_order', 'estimated_exec_time', 'rule',
    'required_inputs', 'output_fields', 'associated_algorithms', 'status',
    'visibility',
)
CATEGORY_BODY_FIELDS: Tuple[str, ...] = (
    'name', 'description', 'icon', 'visibility')
REEVALUATE_BODY_FIELDS: Tuple[str, ...] = (
    'task_id', 'reevaluate_type', 'reextract_device_output',
    'case_ids', 'dimension_ids', 'mode')

# 动作 → 允许的 body 字段（None = 该动作不收 body）
EVALUATION_MANAGE_BODY_FIELDS: Dict[str, Optional[Tuple[str, ...]]] = {
    'dimension_create': DIMENSION_BODY_FIELDS,
    'dimension_update': DIMENSION_BODY_FIELDS,
    'dimension_delete': None,
    'dimension_visibility': None,
    'category_create': CATEGORY_BODY_FIELDS,
    'category_update': CATEGORY_BODY_FIELDS,
    'category_delete': None,
    'reevaluate': REEVALUATE_BODY_FIELDS,
}

# body 中条件必填的字段：创建类必须有名称，重评估必须指定任务。
EVALUATION_MANAGE_BODY_REQUIRED: Dict[str, Tuple[str, ...]] = {
    'dimension_create': ('name',),
    'category_create': ('name',),
    'reevaluate': ('task_id',),
}

# 可见性二值（网关 VisibilityUpdateRequest / parse_visibility）
VISIBILITY_VALUES: Tuple[str, ...] = ('shared', 'private')

# 重评估类型 / 范围模式：与 evaluation_service.revaluation 侧常量一致。
# ``selected`` 空 case_ids 会被评估服务拒绝（INT-302），本层不替它兜底成全量。
REEVALUATE_TYPES: Tuple[str, ...] = ('all', 'failed')
REEVALUATE_MODES: Tuple[str, ...] = ('all', 'failed_only', 'selected')

# Agent 专用写目标：网关已有、外部 MCP 表未登记的分类写路由。
# 与 ``mcp_registry`` 同形，复用同一 ``build_path`` / ``build_body`` 构造器。
EVALUATION_WRITE_TOOLS = [
    tool_entry(
        'evaluation_category_update', '修改评估分类',
        {'cat_id': {'type': 'integer', 'description': '分类 ID', 'required': True},
         'body': {'type': 'object', 'description': '分类修改字段'}},
        [CATEGORY_MANAGE], 'PUT',
        '/api/v1/evaluation/categories/{cat_id}', path_params=['cat_id']),
    tool_entry(
        'evaluation_category_delete', '删除评估分类（软删）',
        {'cat_id': {'type': 'integer', 'description': '分类 ID', 'required': True}},
        [CATEGORY_MANAGE], 'DELETE',
        '/api/v1/evaluation/categories/{cat_id}', path_params=['cat_id']),
]

_WRITE_TOOL_BY_NAME: Dict[str, dict] = {
    tool['name']: tool for tool in EVALUATION_WRITE_TOOLS}


def get_tool(name: str) -> Optional[dict]:
    """按名取本模块的 Agent 专用写目标；非本模块工具返回 None。"""
    return _WRITE_TOOL_BY_NAME.get(name)


def _lookup(action: str) -> Optional[dict]:
    """动作 → 目标工具定义：MCP 注册表优先，其次本模块写目标。"""
    name = EVALUATION_MANAGE_ACTIONS[action]
    return get_mcp_tool(name) or get_tool(name)


def action_permissions(action: Any) -> Optional[Tuple[str, ...]]:
    """动作所需权限；非法动作返回 None（由解析层给出明确的 action 错误）。"""
    return EVALUATION_MANAGE_PERMISSIONS.get(action)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _check_body(action: str, body: Any) -> Optional[str]:
    """body 字段白名单 / 条件必填 / 类型校验；返回错误文本或 None。"""
    allowed = EVALUATION_MANAGE_BODY_FIELDS[action]
    if allowed is None:
        if body is not None:
            return f'action={action} 不接受 body'
        return None
    if body is None:
        return f'action={action} 缺少必填参数：body'
    if not isinstance(body, dict):
        return f'action={action} 的 body 必须是对象'
    unknown = sorted(key for key in body if key not in allowed)
    if unknown:
        return (f'action={action} 的 body 不支持字段：{"、".join(unknown)}'
                '（网关会静默忽略这些字段）')
    for name in EVALUATION_MANAGE_BODY_REQUIRED.get(action, ()):
        if body.get(name) is None:
            return f'action={action} 的 body 缺少必填字段：{name}'
    visibility = body.get('visibility')
    if visibility is not None and visibility not in VISIBILITY_VALUES:
        return 'body.visibility 取值必须是 shared / private 之一'
    if action == 'reevaluate':
        if not _positive_int(body.get('task_id')):
            return f'action=reevaluate 的 body.task_id 必须是正整数：{body.get("task_id")}'
        reevaluate_type = body.get('reevaluate_type')
        if reevaluate_type is not None and reevaluate_type not in REEVALUATE_TYPES:
            return (f'body.reevaluate_type 取值必须是 '
                    f'{"/".join(REEVALUATE_TYPES)} 之一')
        mode = body.get('mode')
        if mode is not None and mode not in REEVALUATE_MODES:
            return f'body.mode 取值必须是 {"/".join(REEVALUATE_MODES)} 之一'
        case_ids = body.get('case_ids')
        if mode == 'selected' and not case_ids:
            return 'body.mode=selected 时 case_ids 不能为空'
    return None


def validate_arguments(arguments: Dict[str, Any]) -> Optional[str]:
    """动作级参数校验：路径必填、可见性、body 白名单与条件必填。"""
    if not isinstance(arguments, dict):
        return '工具参数必须是对象'
    action = arguments.get('action')
    if action not in EVALUATION_MANAGE_ACTIONS:
        return f'action 取值必须是 {"/".join(EVALUATION_MANAGE_ACTIONS)} 之一'
    allowed_keys = {'action', 'dim_id', 'cat_id', 'visibility', 'body'}
    unknown = sorted(key for key in arguments if key not in allowed_keys)
    if unknown:
        return f'不支持参数：{"、".join(unknown)}'
    id_param = EVALUATION_MANAGE_ID_PARAMS.get(action)
    if id_param and not _positive_int(arguments.get(id_param)):
        return f'action={action} 缺少必填参数：{id_param}'
    visibility = arguments.get('visibility')
    if action == 'dimension_visibility':
        if visibility is None:
            return 'action=dimension_visibility 缺少必填参数：visibility'
        if visibility not in VISIBILITY_VALUES:
            return '参数 visibility 取值必须是 shared / private 之一'
    elif visibility is not None:
        return f'action={action} 不接受 visibility（可见性改用 dimension_visibility 动作）'
    return _check_body(action, arguments.get('body'))


def resolve_call(arguments: Dict[str, Any]
                 ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把 ``evaluation_manage`` 调用解析为 ``(目标工具, 合并参数, 错误文本)``。"""
    error = validate_arguments(arguments or {})
    if error:
        return None, None, error
    action = arguments['action']
    tool = _lookup(action)
    if tool is None:  # pragma: no cover - 注册表内部一致性防御
        return None, None, f'工具映射失效：evaluation_manage.{action}'
    merged = {key: value for key, value in arguments.items() if key != 'action'}
    return tool, merged, None


def proposal_diff(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """审批人可见的字段级变更预览（比通用 REST 请求预览更可读）。

    只做「这次要改什么」的事实转述：目标对象、字段、可见性、重评估范围；
    不预判后端结果，也不把目标当前值编造出来（没有回源，就不写 before 值）。
    """
    action = (arguments or {}).get('action')
    if action not in EVALUATION_MANAGE_ACTIONS:
        return None
    diff: Dict[str, Any] = {
        'kind': 'evaluation_config',
        'operation': action,
        'target_table': 'evaluation_category' if action.startswith('category')
        else ('task' if action == 'reevaluate' else 'evaluation_dimension'),
        'request': EVALUATION_MANAGE_ACTIONS[action],
    }
    if action.startswith('dimension'):
        if arguments.get('dim_id') is not None:
            diff['dim_id'] = arguments['dim_id']
    elif action.startswith('category'):
        if arguments.get('cat_id') is not None:
            diff['cat_id'] = arguments['cat_id']
    if action == 'dimension_visibility':
        diff['visibility'] = arguments.get('visibility')
    body = arguments.get('body')
    if isinstance(body, dict):
        diff['changes'] = dict(body)
        if action == 'reevaluate':
            diff['scope'] = {
                'mode': body.get('mode') or 'all',
                'case_ids': list(body.get('case_ids') or []),
                'dimension_ids': list(body.get('dimension_ids') or []),
            }
    if action.endswith('_delete'):
        diff['effect'] = '软删除（可追溯；不物理删除数据）'
    elif action == 'reevaluate':
        diff['effect'] = '提交重新评估队列（只重算评估结论，不重跑执行）'
    return diff


__all__ = [
    'CATEGORY_BODY_FIELDS', 'CATEGORY_MANAGE', 'DIM_MANAGE',
    'DIMENSION_BODY_FIELDS', 'EVALUATION_EXECUTE', 'EVALUATION_MANAGE_ACTIONS',
    'EVALUATION_MANAGE_BODY_FIELDS', 'EVALUATION_MANAGE_BODY_REQUIRED',
    'EVALUATION_MANAGE_ID_PARAMS', 'EVALUATION_MANAGE_PERMISSIONS',
    'EVALUATION_SHARE', 'EVALUATION_WRITE_TOOLS', 'REEVALUATE_BODY_FIELDS',
    'REEVALUATE_MODES', 'REEVALUATE_TYPES', 'VISIBILITY_VALUES',
    'action_permissions', 'get_tool', 'proposal_diff', 'resolve_call',
    'validate_arguments',
]
