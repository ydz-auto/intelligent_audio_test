# -*- coding: utf-8 -*-
"""设备与 SPL 域只读意图工具分组（INT-2459，方案 §6.1 / §6.2）。

``device_query`` 覆盖两个只读子集：

1. **被测设备**：动作直接映射共享 MCP 注册表里的 ``device_*`` GET 工具
   （与外部 MCP 同一份 Schema / 路径构造，不复制）；
2. **SPL**：§6.1 没有独立的 SPL 只读意图工具（只有写工具 ``spl_calibrate``），
   也没有对外 MCP 工具（外部 ``tools/list`` 冻结在 205 项，见 §6.2）。
   SPL 只读端点在本模块以**Agent 专用 REST 目标**声明（字段与 MCP 注册项同形），
   只经 ``device_query`` 暴露；``tool_search`` 通过 ``device_query`` 的 L1 描述
   命中。执行者不得自造工具名（如 ``spl_query`` / ``digital_spl_query``）。

为什么 SPL 端点不写进 ``mcp_registry.TOOLS``：那是外部 MCP 的 1:1 契约，
本卡只扩内部 Agent 能力，不改外部工具清单。``build_path`` / ``build_body``
仍复用 ``mcp_registry`` 的共享构造器，不另写一套请求拼装。

字段名 / 参数名一律以网关真实路由与 ``api_gateway/schemas`` 为准
（``device_bp.py`` / ``spl_bp.py`` / ``digital_spl_bp.py``），取值枚举取自
``shared.models.common_enums``，不在这里写字面量。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from shared.agent_tools import mcp_registry
from shared.models.common_enums import (
    AlarmMetricType,
    AlarmSeverity,
    AlarmStatus,
    CalibrationStatus,
    DeviceGroupType,
    DeviceStatusEventType,
)

DEVICE_READ = ('device:read',)
SPL_READ = ('spl:read',)
DIGITAL_SPL_READ = ('digital_spl:read',)

# 设备只读动作 → 共享 MCP 注册表的 GET 工具名
DEVICE_QUERY_ACTIONS: Dict[str, str] = {
    'list': 'device_list',
    'detail': 'device_get',
    'groups': 'device_group_list',
    'group': 'device_group_get',
    'status': 'device_status_list',
    # 带 device_id 时改投单设备端点（见 ``rest_target``）
    'status_history': 'device_status_history',
    'alarms': 'device_alarm_list',
    'alarm_rules': 'device_alarm_rule_list',
    'serials': 'device_serials',
    'driver_keywords': 'device_driver_keywords',
}


def _rest_target(name: str, description: str, permissions: Sequence[str],
                 path: str, *, path_params: Sequence[str] = (),
                 query_params: Sequence[str] = (),
                 schema: Optional[Dict[str, Any]] = None) -> dict:
    """构造 Agent 专用只读 REST 目标（与 MCP 注册项同形，供共享构造器使用）。"""
    properties = dict(schema or {})
    input_schema: Dict[str, Any] = {
        'type': 'object', 'properties': properties,
        'additionalProperties': True,
    }
    required = [key for key, value in properties.items()
                if isinstance(value, dict) and value.get('required')]
    if required:
        input_schema['required'] = required
    return {
        'name': name,
        'description': description,
        'inputSchema': input_schema,
        'permissions': list(permissions),
        'method': 'GET',
        'path': path,
        'path_params': list(path_params),
        'query_params': list(query_params),
    }


# SPL 只读动作 → Agent 专用 REST 目标（物理域 /api/v1/spl + 数字域 /api/v1/digital-spl）
DEVICE_SPL_TARGETS: Dict[str, dict] = {
    'spl_mappings': _rest_target(
        'spl_mapping_list', '列出 SPL 映射（物理域，可按关键词 / 校准状态 / 播放设备过滤）',
        SPL_READ, '/api/v1/spl',
        query_params=['page', 'per_page', 'keyword', 'calibration_status',
                      'device_id']),
    'spl_mapping': _rest_target(
        'spl_mapping_get', '获取 SPL 映射详情（含校准状态与最新校准点集）',
        SPL_READ, '/api/v1/spl/{mapping_id}',
        path_params=['mapping_id']),
    'spl_stats': _rest_target(
        'spl_mapping_stats', 'SPL 映射统计（总数 / 已校准 / 未校准 / 关联设备数）',
        SPL_READ, '/api/v1/spl/stats'),
    'spl_by_device': _rest_target(
        'spl_mapping_by_device', '按播放设备列出 SPL 映射',
        SPL_READ, '/api/v1/spl/by-device/{device_id}',
        path_params=['device_id']),
    'spl_history': _rest_target(
        'spl_mapping_history', 'SPL 校准历史（按映射 ID，全量不分页）',
        SPL_READ, '/api/v1/spl/{mapping_id}/history',
        path_params=['mapping_id']),
    'spl_calibration_data': _rest_target(
        'spl_mapping_calibration_data', 'SPL 最新校准点集（每行一个测试音校准点）',
        SPL_READ, '/api/v1/spl/{mapping_id}/calibration-data',
        path_params=['mapping_id']),
    'digital_spl_mappings': _rest_target(
        'digital_spl_mapping_list', '列出数字域 RMS→SPL 映射（可按被测 API / 校准状态过滤）',
        DIGITAL_SPL_READ, '/api/v1/digital-spl',
        query_params=['page', 'per_page', 'api_id', 'calibration_status']),
    'digital_spl_mapping': _rest_target(
        'digital_spl_mapping_get', '获取数字域 RMS→SPL 映射详情（含校准点集）',
        DIGITAL_SPL_READ, '/api/v1/digital-spl/{mapping_id}',
        path_params=['mapping_id']),
    'digital_spl_by_api': _rest_target(
        'digital_spl_mapping_by_api', '按被测 API 列出数字域 RMS→SPL 映射',
        DIGITAL_SPL_READ, '/api/v1/digital-spl/by-api/{api_id}',
        path_params=['api_id']),
}

# 全部动作（动作顺序 = Schema enum 顺序：设备在前、SPL 在后）
DEVICE_QUERY_ACTION_NAMES: Tuple[str, ...] = (
    tuple(DEVICE_QUERY_ACTIONS) + tuple(DEVICE_SPL_TARGETS))

# 动作支持的可选参数白名单（动作独立口径）。
# 网关查询 Schema 基类 ``extra='ignore'``：不认识的参数被静默丢弃，不报错。
# 工具层必须拦下「传了但不会生效」的参数，否则模型会把全量 / 默认过滤
# 当成目标结果（INT-2529 同类教训）。
DEVICE_QUERY_PARAMS: Dict[str, Tuple[str, ...]] = {
    'list': ('page', 'per_page', 'keyword', 'status', 'device_type',
             'algorithm_type', 'lab_id'),
    'detail': (),
    'groups': ('page', 'per_page', 'keyword', 'group_type'),
    'group': (),
    'status': ('ids',),
    'status_history': ('device_id', 'device_ids', 'event_type',
                       'start_time', 'end_time', 'page', 'per_page'),
    'alarms': ('page', 'per_page', 'status', 'severity', 'device_id'),
    'alarm_rules': ('page', 'per_page', 'metric_type', 'enabled'),
    'serials': (),
    'driver_keywords': (),
    'spl_mappings': ('page', 'per_page', 'keyword', 'calibration_status',
                     'device_id'),
    'spl_mapping': (),
    'spl_stats': (),
    'spl_by_device': (),
    'spl_history': (),
    'spl_calibration_data': (),
    'digital_spl_mappings': ('page', 'per_page', 'api_id',
                             'calibration_status'),
    'digital_spl_mapping': (),
    'digital_spl_by_api': (),
}

# 动作的必填参数（参数 Schema 无法表达的条件必填）
DEVICE_QUERY_REQUIRED: Dict[str, Tuple[str, ...]] = {
    'detail': ('device_id',),
    'group': ('group_id',),
    'spl_mapping': ('mapping_id',),
    'spl_history': ('mapping_id',),
    'spl_calibration_data': ('mapping_id',),
    'spl_by_device': ('device_id',),
    'digital_spl_mapping': ('mapping_id',),
    'digital_spl_by_api': ('api_id',),
}

# 动作级权限：device_query 横跨三个权限域，工具级 permissions 是并集（OR 语义
# 只用于「工具可见性」），真正的授权按动作收窄，避免持有 device:read 的用户
# 直接读 SPL 映射（或反之）。
DEVICE_QUERY_ACTION_PERMISSIONS: Dict[str, Tuple[str, ...]] = {
    **{action: DEVICE_READ for action in DEVICE_QUERY_ACTIONS},
    **{action: SPL_READ for action in (
        'spl_mappings', 'spl_mapping', 'spl_stats', 'spl_by_device',
        'spl_history', 'spl_calibration_data')},
    **{action: DIGITAL_SPL_READ for action in (
        'digital_spl_mappings', 'digital_spl_mapping', 'digital_spl_by_api')},
}

# 工具级权限 = 三个域的并集（tool_search / Skill 可见性按 OR 判定）
DEVICE_QUERY_PERMISSIONS: Tuple[str, ...] = (
    DEVICE_READ + SPL_READ + DIGITAL_SPL_READ)

# 查询串数组：网关 request.args 适配器只取最后一个值，重复参数会丢元素，
# 必须按服务端契约序列化成逗号分隔字符串（DeviceStatusQuery / DeviceStatusHistoryQuery）。
_CSV_ARRAY_PARAMS: Tuple[str, ...] = ('ids', 'device_ids')
_BOOL_PARAMS: Tuple[str, ...] = ('enabled',)

# 枚举取值（事实源 shared.models.common_enums）
GROUP_TYPE_VALUES: Tuple[str, ...] = tuple(v.value for v in DeviceGroupType)
ALARM_STATUS_VALUES: Tuple[str, ...] = tuple(v.value for v in AlarmStatus)
ALARM_SEVERITY_VALUES: Tuple[str, ...] = tuple(v.value for v in AlarmSeverity)
ALARM_METRIC_VALUES: Tuple[str, ...] = tuple(v.value for v in AlarmMetricType)
STATUS_EVENT_TYPE_VALUES: Tuple[str, ...] = tuple(
    v.value for v in DeviceStatusEventType)
CALIBRATION_STATUS_VALUES: Tuple[str, ...] = tuple(
    v.value for v in CalibrationStatus)


def action_permissions(action: Optional[str]) -> Optional[Tuple[str, ...]]:
    """动作级权限；未知动作返回 None。"""
    return DEVICE_QUERY_ACTION_PERMISSIONS.get(action or '')


def rest_target(action: str, merged: Dict[str, Any]) -> Optional[dict]:
    """动作 → 目标工具定义（设备动作取 MCP 注册表，SPL 动作取本模块目标）。"""
    name = DEVICE_QUERY_ACTIONS.get(action)
    if name == 'device_status_history' and merged.get('device_id') is not None:
        name = 'device_get_status_history'
    if name is not None:
        return mcp_registry.get_tool(name)
    return DEVICE_SPL_TARGETS.get(action)


def normalize_arguments(action: str, merged: Dict[str, Any]) -> Optional[str]:
    """按动作校验 / 归一参数，返回错误文本或 None。"""
    allowed = set(DEVICE_QUERY_PARAMS.get(action, ()))
    allowed |= set(DEVICE_QUERY_REQUIRED.get(action, ()))
    unknown = sorted(name for name in merged if name not in allowed)
    if unknown:
        return f'action={action} 不支持参数：{"、".join(unknown)}'

    # status_history 两个入口互斥：单设备端点会忽略 device_ids，全量端点不接受
    # device_id；同时传会让模型把「某一台」当成「全部」。
    if action == 'status_history' and merged.get('device_id') is not None \
            and merged.get('device_ids') is not None:
        return ('参数 device_id 与 device_ids 不能同时使用：'
                '查单设备用 device_id，查全量（或按 id 列表）用 device_ids')

    # 告警状态只有三个取值；传错值服务端会返回空列表，模型会误判「没有告警」。
    status = merged.get('status')
    if action == 'alarms' and status is not None \
            and status not in ALARM_STATUS_VALUES:
        return (f'参数 status 取值必须是 {"/".join(ALARM_STATUS_VALUES)} 之一'
                '（告警状态）')

    for name in ('page', 'per_page'):
        if merged.get(name) is None:
            continue
        value = merged[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return f'参数 {name} 必须是 ≥1 的整数'

    for name in _CSV_ARRAY_PARAMS:
        if merged.get(name) is None:
            continue
        value = merged[name]
        if not isinstance(value, (list, tuple)):
            return f'参数 {name} 必须是整数数组'
        if not value:
            # 空数组在服务端等价于「不过滤」，会让模型把全量当成过滤结果
            return f'参数 {name} 不能为空数组（不传表示不过滤）'
        for item in value:
            if isinstance(item, bool) or not isinstance(item, int):
                return f'参数 {name} 必须是整数数组'
        merged[name] = ','.join(str(item) for item in value)

    for name in _BOOL_PARAMS:
        if merged.get(name) is None:
            continue
        value = merged[name]
        if not isinstance(value, bool):
            return f'参数 {name} 必须是布尔值'
        merged[name] = 'true' if value else 'false'
    return None


def resolve_call(arguments: Dict[str, Any]
                 ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把 ``device_query`` 调用解析为 ``(目标工具, 合并参数, 错误文本)``。"""
    action = arguments.get('action')
    if action not in DEVICE_QUERY_ACTION_PERMISSIONS:
        return None, None, (
            f'action 取值必须是 {"/".join(DEVICE_QUERY_ACTION_NAMES)} 之一')
    missing = [name for name in DEVICE_QUERY_REQUIRED.get(action, ())
               if arguments.get(name) is None]
    if missing:
        return None, None, f'action={action} 缺少必填参数：{"、".join(missing)}'
    merged = {key: value for key, value in arguments.items()
              if key != 'action' and value is not None}
    error = normalize_arguments(action, merged)
    if error:
        return None, None, error
    target = rest_target(action, merged)
    if target is None:  # pragma: no cover - 模块内映射一致性防御
        return None, None, f'工具映射失效：device_query.{action}'
    return target, merged, None


__all__ = [
    'ALARM_METRIC_VALUES', 'ALARM_SEVERITY_VALUES', 'ALARM_STATUS_VALUES',
    'CALIBRATION_STATUS_VALUES', 'DEVICE_QUERY_ACTIONS',
    'DEVICE_QUERY_ACTION_NAMES', 'DEVICE_QUERY_ACTION_PERMISSIONS',
    'DEVICE_QUERY_PARAMS', 'DEVICE_QUERY_PERMISSIONS', 'DEVICE_QUERY_REQUIRED',
    'DEVICE_READ', 'DEVICE_SPL_TARGETS', 'DIGITAL_SPL_READ',
    'GROUP_TYPE_VALUES', 'SPL_READ', 'STATUS_EVENT_TYPE_VALUES',
    'action_permissions', 'normalize_arguments', 'resolve_call', 'rest_target',
]
