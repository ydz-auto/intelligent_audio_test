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
from shared.agent_tools.pagination import check_page_bounds
from shared.agent_tools.rest_target import rest_target as build_rest_target
from shared.models.common_enums import (
    AlarmMetricType,
    AlarmSeverity,
    AlarmStatus,
    CalibrationStatus,
    DeviceGroupType,
    DeviceOperation,
    DeviceStatusEventType,
)

DEVICE_READ = ('device:read',)
DEVICE_CONTROL = ('device:control',)
SPL_READ = ('spl:read',)
SPL_CREATE = ('spl:create',)
SPL_UPDATE = ('spl:update',)
SPL_DELETE = ('spl:delete',)
SPL_TEST_TONE = ('spl:test_tone',)
DIGITAL_SPL_READ = ('digital_spl:read',)
DIGITAL_SPL_CREATE = ('digital_spl:create',)
DIGITAL_SPL_UPDATE = ('digital_spl:update',)
DIGITAL_SPL_DELETE = ('digital_spl:delete',)

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
    return build_rest_target(name, description, permissions, 'GET', path,
                             path_params=path_params,
                             query_params=query_params, schema=schema)


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

    # 分页边界与其余查询类意图工具同源（INT-2552）：网关对 page<1 / 超大
    # per_page 不报错，工具层必须拦（Schema 的 minimum / maximum 同源）。
    bounds_error = check_page_bounds(action, merged)
    if bounds_error:
        return bounds_error

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


# ========================================================================
# 写侧（INT-2467）：device_control（DESTRUCTIVE）+ spl_calibrate（WRITE）
# ========================================================================
#
# 与只读侧同一约束：设备写动作映射共享 MCP 注册表的 ``device_*`` 写工具；
# SPL 物理域 / 数字域没有对外 MCP 工具（§6.2 冻结 207 项），以 Agent 专用
# REST 目标声明，只经 ``spl_calibrate`` 暴露。执行前一律走 INT-2466 的
# 提案 + 审批 + 幂等：本模块只解析目标请求，不产生副作用。

# 设备控制动作 → 共享 MCP 注册表的写工具名。
# ``install`` / ``uninstall`` 是 ``install-app`` / ``uninstall-app`` 的意图别名
# （动作名不带 app 后缀，参数里给安装包 / 包名）。
DEVICE_CONTROL_ACTIONS: Dict[str, str] = {
    'connect': 'device_connect',
    'disconnect': 'device_disconnect',
    'reboot': 'device_reboot',
    'shutdown': 'device_shutdown',
    'install': 'device_install_app',
    'uninstall': 'device_uninstall_app',
    'scan': 'device_scan',
    'batch': 'device_batch_action',
}

# 动作支持的可选参数（动作独立白名单）
DEVICE_CONTROL_PARAMS: Dict[str, Tuple[str, ...]] = {
    'connect': ('params',),
    'disconnect': ('params',),
    'reboot': ('params',),
    'shutdown': ('params',),
    'install': ('params',),
    'uninstall': ('params',),
    'scan': (),
    'batch': ('operation', 'device_ids', 'params', 'idempotency_key'),
}

DEVICE_CONTROL_REQUIRED: Dict[str, Tuple[str, ...]] = {
    'connect': ('device_id',),
    'disconnect': ('device_id',),
    'reboot': ('device_id',),
    'shutdown': ('device_id',),
    'install': ('device_id', 'params'),
    'uninstall': ('device_id', 'params'),
    'scan': (),
    'batch': ('operation', 'device_ids'),
}

# 批量动作白名单：与 device_service ``DeviceOperation`` 对齐（不含
# ``health_check``——它是只读探测，不放在破坏性批量里）。
DEVICE_BATCH_OPERATIONS: Tuple[str, ...] = tuple(
    v.value for v in DeviceOperation)

# 安装 / 卸载的参数必填键（device_service executor 直接按这两个键取值，
# 缺参数会以 400 失败；工具层先拦下，避免生成注定失败的提案）。
DEVICE_INSTALL_PARAM_KEYS: Tuple[str, ...] = ('file_path',)
DEVICE_UNINSTALL_PARAM_KEYS: Tuple[str, ...] = ('package_name',)

DEVICE_CONTROL_ACTION_PERMISSIONS: Dict[str, Tuple[str, ...]] = {
    action: DEVICE_CONTROL for action in DEVICE_CONTROL_ACTIONS}


def _prop(description: str, *, required: bool = False,
          kind: str = 'string', enum: Sequence[str] = ()) -> dict:
    """写目标的扁平参数声明（``rest_target`` 据此推导 required）。"""
    prop: Dict[str, Any] = {'type': kind, 'description': description}
    if required:
        prop['required'] = True
    if enum:
        prop['enum'] = list(enum)
    return prop


def _write_target(name: str, description: str, permissions: Sequence[str],
                  method: str, path: str, *, path_params: Sequence[str] = (),
                  schema: Optional[Dict[str, Any]] = None) -> dict:
    return build_rest_target(name, description, permissions, method, path,
                             path_params=path_params, schema=schema)


# SPL 映射 / 校准的公共字段（物理域 SPLMappingCreateRequest /
# SPLMappingUpdateRequest，数字域 RmsSplMapping*Request 有各自的子集）。
_SPL_MAPPING_FIELDS: Dict[str, Any] = {
    'name': _prop('映射名称', required=True),
    'description': _prop('描述'),
    'device_id': _prop('播放设备 ID（与 device_type 至少给一个；这是播放设备，不是被测设备）',
                       kind='integer'),
    'device_type': _prop('设备类型（与 device_id 至少给一个）'),
    'distance': _prop('测试距离（米，默认 1.0）', kind='number'),
    'target_spl': _prop('目标声压级', kind='number'),
    'digital_gain': _prop('数字增益', kind='number'),
    'test_frequency': _prop('测试频率（Hz，默认 1000）', kind='integer'),
    'calibration_status': _prop('校准状态（以接口返回为准）',
                                enum=CALIBRATION_STATUS_VALUES),
    'calibration_data': _prop(
        '校准点集：物理域 {points: [{spl, gain_offset, digital_gain, '
        'base_level, final_level}]}', kind='object'),
}
_SPL_MAPPING_UPDATE_FIELDS: Dict[str, Any] = dict(
    _SPL_MAPPING_FIELDS, name=_prop('映射名称'),
    is_current=_prop('是否设为当前映射', kind='boolean'))

_DIGITAL_SPL_MAPPING_FIELDS: Dict[str, Any] = {
    'api_id': _prop('被测 API ID（创建必填；走请求体，不是路径参数）',
                    kind='integer', required=True),
    'name': _prop('映射名称'),
    'description': _prop('描述'),
    'vendor': _prop('厂商（以被测 API 配置为准）'),
    'protocol': _prop('协议（以被测 API 配置为准）'),
    'reference_spl': _prop('参考声压级', kind='number'),
    'reference_gain_linear': _prop('参考增益（线性）', kind='number'),
    'calibration_status': _prop('校准状态（以接口返回为准）',
                                enum=CALIBRATION_STATUS_VALUES),
    'calibration_data': _prop(
        '校准点集 {points: [{target_spl, gain_linear, rms_dbfs}]}；'
        'rms_dbfs 必填主输入，gain_linear 由后端推导', kind='object'),
    'min_gain_linear': _prop('最小增益（线性）', kind='number'),
    'max_gain_linear': _prop('最大增益（线性）', kind='number'),
}
_DIGITAL_SPL_MAPPING_UPDATE_FIELDS: Dict[str, Any] = {
    key: value for key, value in _DIGITAL_SPL_MAPPING_FIELDS.items()
    if key != 'api_id'
}

# SPL 写动作 → Agent 专用 REST 目标
SPL_CALIBRATE_TARGETS: Dict[str, dict] = {
    # ---- 物理域 /api/v1/spl ----
    'mapping_create': _write_target(
        'spl_mapping_create', '创建 SPL 映射（物理域）', SPL_CREATE,
        'POST', '/api/v1/spl', schema=_SPL_MAPPING_FIELDS),
    'mapping_update': _write_target(
        'spl_mapping_update', '修改 SPL 映射（物理域）', SPL_UPDATE,
        'PUT', '/api/v1/spl/{mapping_id}', path_params=['mapping_id'],
        schema=dict(_SPL_MAPPING_UPDATE_FIELDS,
                    mapping_id=_prop('映射 ID', kind='integer', required=True))),
    'mapping_delete': _write_target(
        'spl_mapping_delete', '删除 SPL 映射（物理域）', SPL_DELETE,
        'DELETE', '/api/v1/spl/{mapping_id}', path_params=['mapping_id'],
        schema={'mapping_id': _prop('映射 ID', kind='integer', required=True)}),
    'calibrate': _write_target(
        'spl_mapping_calibrate', '执行 SPL 校准（按映射测量并写入校准点集）',
        SPL_CREATE, 'POST', '/api/v1/spl/{mapping_id}/calibrate',
        path_params=['mapping_id'],
        schema={'mapping_id': _prop('映射 ID', kind='integer', required=True)}),
    'test_tone': _write_target(
        'spl_test_tone', '播放测试音（后端扬声器 / 指定设备）', SPL_TEST_TONE,
        'POST', '/api/v1/spl/test-tone',
        schema={'gain_value': _prop('增益（默认 50）', kind='number'),
                'gain_offset': _prop('增益偏移', kind='number'),
                'target_spl': _prop('目标声压（默认 65）', kind='number'),
                'unique_id': _prop('目标设备唯一标识（不传用后端扬声器）')}),
    'test_tone_stop': _write_target(
        'spl_test_tone_stop', '停止测试音', SPL_TEST_TONE,
        'POST', '/api/v1/spl/test-tone/stop',
        schema={'unique_id': _prop('目标设备唯一标识（不传停止全部）')}),
    # ---- 数字域 /api/v1/digital-spl ----
    'digital_mapping_create': _write_target(
        'digital_spl_mapping_create', '创建数字域 RMS→SPL 映射', DIGITAL_SPL_CREATE,
        'POST', '/api/v1/digital-spl', schema=_DIGITAL_SPL_MAPPING_FIELDS),
    'digital_mapping_update': _write_target(
        'digital_spl_mapping_update', '修改数字域 RMS→SPL 映射',
        DIGITAL_SPL_UPDATE, 'PUT', '/api/v1/digital-spl/{mapping_id}',
        path_params=['mapping_id'],
        schema=dict(_DIGITAL_SPL_MAPPING_UPDATE_FIELDS,
                    mapping_id=_prop('映射 ID', kind='integer', required=True))),
    'digital_mapping_delete': _write_target(
        'digital_spl_mapping_delete', '删除数字域 RMS→SPL 映射',
        DIGITAL_SPL_DELETE, 'DELETE', '/api/v1/digital-spl/{mapping_id}',
        path_params=['mapping_id'],
        schema={'mapping_id': _prop('映射 ID', kind='integer', required=True)}),
    'digital_calibrate': _write_target(
        'digital_spl_mapping_calibrate', '提交数字域校准点集（RMS→SPL 映射）',
        DIGITAL_SPL_CREATE, 'POST', '/api/v1/digital-spl/{mapping_id}/calibrate',
        path_params=['mapping_id'],
        schema={'mapping_id': _prop('映射 ID', kind='integer', required=True),
                'calibration_data': _prop(
                    '校准点集 {points: [{target_spl, gain_linear, rms_dbfs}]}',
                    required=True, kind='object')}),
    'digital_set_default': _write_target(
        'digital_spl_mapping_set_default', '设置 / 清除被测 API 的默认数字映射',
        DIGITAL_SPL_UPDATE, 'POST',
        '/api/v1/digital-spl/by-api/{api_id}/set-default',
        path_params=['api_id'],
        schema={'api_id': _prop('被测 API ID', kind='integer', required=True),
                'mapping_id': _prop('映射 ID（为空 / 0 表示清除默认）',
                                    kind='integer')}),
}

# SPL 写动作的可选参数白名单 = 目标 Schema 的字段（去掉路径参数）
SPL_CALIBRATE_PARAMS: Dict[str, Tuple[str, ...]] = {
    action: tuple(name for name in target['inputSchema']['properties']
                  if name not in target['path_params'])
    for action, target in SPL_CALIBRATE_TARGETS.items()
}
SPL_CALIBRATE_REQUIRED: Dict[str, Tuple[str, ...]] = {
    action: tuple(target['inputSchema'].get('required') or ())
    for action, target in SPL_CALIBRATE_TARGETS.items()
}

# SPL 写动作横跨物理域 / 数字域与不同动作语义（校准是 create、删除是 delete），
# 按动作收窄权限；工具级声明只表达可见性（并集）。
SPL_CALIBRATE_ACTION_PERMISSIONS: Dict[str, Tuple[str, ...]] = {
    'mapping_create': SPL_CREATE,
    'mapping_update': SPL_UPDATE,
    'mapping_delete': SPL_DELETE,
    'calibrate': SPL_CREATE,
    'test_tone': SPL_TEST_TONE,
    'test_tone_stop': SPL_TEST_TONE,
    'digital_mapping_create': DIGITAL_SPL_CREATE,
    'digital_mapping_update': DIGITAL_SPL_UPDATE,
    'digital_mapping_delete': DIGITAL_SPL_DELETE,
    'digital_calibrate': DIGITAL_SPL_CREATE,
    'digital_set_default': DIGITAL_SPL_UPDATE,
}
SPL_CALIBRATE_PERMISSIONS: Tuple[str, ...] = (
    SPL_CREATE + SPL_UPDATE + SPL_DELETE + SPL_TEST_TONE
    + DIGITAL_SPL_CREATE + DIGITAL_SPL_UPDATE + DIGITAL_SPL_DELETE)


def write_action_permissions(tool: str, action: Optional[str]
                             ) -> Optional[Tuple[str, ...]]:
    """写工具的动作级权限；未知动作返回 ``None``（调用方按工具级回落）。"""
    if tool == 'device_control':
        return DEVICE_CONTROL_ACTION_PERMISSIONS.get(action or '')
    if tool == 'spl_calibrate':
        return SPL_CALIBRATE_ACTION_PERMISSIONS.get(action or '')
    return None


def _normalize_device_control(action: str,
                              merged: Dict[str, Any]) -> Optional[str]:
    """设备控制动作的参数校验（写前拦下注定 400 的调用）。"""
    params = merged.get('params')
    if params is not None and not isinstance(params, dict):
        return '参数 params 必须是对象'
    if action in ('install', 'uninstall'):
        keys = (DEVICE_INSTALL_PARAM_KEYS if action == 'install'
                else DEVICE_UNINSTALL_PARAM_KEYS)
        missing = [key for key in keys if not (params or {}).get(key)]
        if missing:
            return (f'action={action} 的 params 缺少必填键：{"、".join(missing)}'
                    f'（{" / ".join(keys)}）')
    if action == 'batch':
        operation = merged.get('operation')
        if operation not in DEVICE_BATCH_OPERATIONS:
            return (f'参数 operation 取值必须是 '
                    f'{"/".join(DEVICE_BATCH_OPERATIONS)} 之一')
        device_ids = merged.get('device_ids')
        if not isinstance(device_ids, list) or not device_ids:
            return '参数 device_ids 必须是非空整数数组'
        if any(not _positive_int(value) for value in device_ids):
            return '参数 device_ids 只能包含正整数设备 ID'
    if action == 'scan':
        if params:
            return 'action=scan 不接受 params（扫描无参数）'
    return None


def _normalize_spl_calibrate(action: str,
                             merged: Dict[str, Any]) -> Optional[str]:
    """SPL 写动作的参数校验：创建映射要求 device_id / device_type 至少一个。"""
    if action == 'mapping_create':
        if merged.get('device_id') is None and not merged.get('device_type'):
            return 'action=mapping_create 需要 device_id 与 device_type 至少一个'
    if action in ('calibrate', 'mapping_update', 'mapping_delete',
                  'digital_calibrate', 'digital_mapping_update',
                  'digital_mapping_delete') and merged.get('mapping_id') is None:
        return f'action={action} 缺少必填参数：mapping_id'
    if action == 'digital_calibrate' and \
            not isinstance(merged.get('calibration_data'), dict):
        return 'action=digital_calibrate 的 calibration_data 必须是对象'
    return None


def resolve_control_call(arguments: Dict[str, Any]
                         ) -> Tuple[Optional[dict], Optional[dict], Optional[str]]:
    """把 ``device_control`` 调用解析为 ``(目标工具, 合并参数, 错误文本)``。

    ``batch`` 的意图参数 ``operation`` 在 REST 契约里叫 ``action``（
    DeviceBatchActionRequest），这里做一次显式改名；其余动作参数原样透传。
    """
    action = arguments.get('action')
    if action not in DEVICE_CONTROL_ACTIONS:
        return None, None, (
            f'action 取值必须是 {"/".join(DEVICE_CONTROL_ACTIONS)} 之一')
    missing = [name for name in DEVICE_CONTROL_REQUIRED.get(action, ())
               if arguments.get(name) is None]
    if missing:
        return None, None, f'action={action} 缺少必填参数：{"、".join(missing)}'
    allowed = set(DEVICE_CONTROL_PARAMS.get(action, ())) \
        | set(DEVICE_CONTROL_REQUIRED.get(action, ()))
    merged = {key: value for key, value in arguments.items()
              if key != 'action' and value is not None}
    unknown = sorted(name for name in merged if name not in allowed)
    if unknown:
        return None, None, (
            f'action={action} 不支持参数：{"、".join(unknown)}'
            '（服务端会静默忽略这些字段）')
    error = _normalize_device_control(action, merged)
    if error:
        return None, None, error

    target = mcp_registry.get_tool(DEVICE_CONTROL_ACTIONS[action])
    if target is None:  # pragma: no cover - 注册表内部一致性防御
        return None, None, f'工具映射失效：device_control.{action}'
    if action == 'batch':
        body = {'action': merged['operation'],
                'device_ids': list(merged['device_ids'])}
        for key in ('params', 'idempotency_key'):
            if merged.get(key) is not None:
                body[key] = merged[key]
        return target, {'body': body}, None
    if action == 'scan':
        return target, {}, None
    rest_args: Dict[str, Any] = {'device_id': merged['device_id']}
    if merged.get('params'):
        rest_args['params'] = merged['params']
    return target, rest_args, None


def resolve_spl_calibrate_call(arguments: Dict[str, Any]
                               ) -> Tuple[Optional[dict], Optional[dict],
                                          Optional[str]]:
    """把 ``spl_calibrate`` 调用解析为 ``(目标工具, 合并参数, 错误文本)``。"""
    action = arguments.get('action')
    if action not in SPL_CALIBRATE_TARGETS:
        return None, None, (
            f'action 取值必须是 {"/".join(SPL_CALIBRATE_TARGETS)} 之一')
    missing = [name for name in SPL_CALIBRATE_REQUIRED.get(action, ())
               if arguments.get(name) is None]
    if missing:
        return None, None, f'action={action} 缺少必填参数：{"、".join(missing)}'
    allowed = set(SPL_CALIBRATE_PARAMS.get(action, ())) \
        | set(SPL_CALIBRATE_REQUIRED.get(action, ()))
    merged = {key: value for key, value in arguments.items()
              if key != 'action' and value is not None}
    unknown = sorted(name for name in merged if name not in allowed)
    if unknown:
        return None, None, (
            f'action={action} 不支持参数：{"、".join(unknown)}'
            '（服务端会静默忽略这些字段）')
    error = _normalize_spl_calibrate(action, merged)
    if error:
        return None, None, error
    target = SPL_CALIBRATE_TARGETS[action]
    return target, merged, None


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


__all__ = [
    'ALARM_METRIC_VALUES', 'ALARM_SEVERITY_VALUES', 'ALARM_STATUS_VALUES',
    'CALIBRATION_STATUS_VALUES', 'DEVICE_BATCH_OPERATIONS',
    'DEVICE_CONTROL', 'DEVICE_CONTROL_ACTIONS',
    'DEVICE_CONTROL_ACTION_PERMISSIONS', 'DEVICE_CONTROL_PARAMS',
    'DEVICE_CONTROL_REQUIRED', 'DEVICE_INSTALL_PARAM_KEYS',
    'DEVICE_QUERY_ACTIONS', 'DEVICE_QUERY_ACTION_NAMES',
    'DEVICE_QUERY_ACTION_PERMISSIONS', 'DEVICE_QUERY_PARAMS',
    'DEVICE_QUERY_PERMISSIONS', 'DEVICE_QUERY_REQUIRED', 'DEVICE_READ',
    'DEVICE_SPL_TARGETS', 'DEVICE_UNINSTALL_PARAM_KEYS',
    'DIGITAL_SPL_CREATE', 'DIGITAL_SPL_DELETE', 'DIGITAL_SPL_READ',
    'DIGITAL_SPL_UPDATE', 'GROUP_TYPE_VALUES', 'SPL_CALIBRATE_ACTION_PERMISSIONS',
    'SPL_CALIBRATE_PARAMS', 'SPL_CALIBRATE_PERMISSIONS',
    'SPL_CALIBRATE_REQUIRED', 'SPL_CALIBRATE_TARGETS', 'SPL_CREATE',
    'SPL_DELETE', 'SPL_READ', 'SPL_TEST_TONE', 'SPL_UPDATE',
    'STATUS_EVENT_TYPE_VALUES', 'action_permissions', 'normalize_arguments',
    'resolve_call', 'resolve_control_call', 'resolve_spl_calibrate_call',
    'rest_target', 'write_action_permissions',
]
