# -*- coding: utf-8 -*-
"""算法域写意图工具 ``algorithm_manage`` 的动作表（INT-2470，M2）。

动作与目标 REST（全部是网关既有写接口 ``api_gateway/routes/algorithm_bp.py``，
不新增端点、不改后端）：

| 动作 | 目标接口 | 权限 | 风险 |
|---|---|---|---|
| ``definition_create`` | ``POST /api/v1/algorithm/definitions`` | ``algorithm:definition_manage`` | WRITE |
| ``definition_update`` | ``PUT /api/v1/algorithm/definitions/{algo_type}`` | ``algorithm:definition_manage`` | WRITE |
| ``definition_save`` | ``PUT /api/v1/algorithm/definitions/save``（聚合保存 + 乐观锁） | ``algorithm:definition_manage`` | WRITE |
| ``definition_delete`` | ``DELETE /api/v1/algorithm/definitions/{algo_type}`` | ``algorithm:definition_manage`` | **DESTRUCTIVE** |
| ``param_create`` | ``POST /api/v1/algorithm/params``（设备 / API 两种作用域） | ``algorithm:param_manage`` | WRITE |
| ``param_update`` | ``PUT /api/v1/algorithm/params/{param_id}`` | ``algorithm:param_manage`` | WRITE |
| ``param_delete`` | ``DELETE /api/v1/algorithm/params/{param_id}`` | ``algorithm:param_manage`` | **DESTRUCTIVE** |
| ``reference_param_create`` | ``POST /api/v1/algorithm/reference-params`` | ``algorithm:param_manage`` | WRITE |
| ``reference_param_update`` | ``PUT /api/v1/algorithm/reference-params/{param_id}`` | ``algorithm:param_manage`` | WRITE |
| ``reference_param_delete`` | ``DELETE /api/v1/algorithm/reference-params/{param_id}`` | ``algorithm:param_manage`` | **DESTRUCTIVE** |
| ``mapping_create`` | ``POST /api/v1/algorithm/mappings`` | ``algorithm:param_manage`` | WRITE |
| ``mapping_update`` | ``PUT /api/v1/algorithm/mappings/{mapping_id}`` | ``algorithm:param_manage`` | WRITE |
| ``mapping_delete`` | ``DELETE /api/v1/algorithm/mappings/{mapping_id}`` | ``algorithm:param_manage`` | **DESTRUCTIVE** |
| ``import`` | ``POST /api/v1/algorithm/import`` | ``algorithm:definition_manage`` | WRITE |
| ``reload`` | ``POST /api/v1/algorithm/reload``（热重载） | ``algorithm:definition_manage`` | WRITE |

口径与边界：

- **权限按动作收窄**：定义 / 导入 / 热重载要 ``algorithm:definition_manage``；
  参数 / 参考参数 / 映射要 ``algorithm:param_manage``（与网关路由
  ``require_permission`` 逐条一致）。映射以 ``param_manage`` 为准 ——
  ``mcp_registry`` 的 ``algorithm_mapping_*`` 声明的是 ``definition_manage``，
  那是外部 MCP 1:1 契约的历史口径；网关实际路由（``post_mapping`` /
  ``put_mapping`` / ``delete_mapping_by_id``）校验 ``param_manage``，
  工具层按真实路由收窄，避免「有 definition_manage 的模型被网关 403」。
- **只做映射，不复制 Schema**：目标工具项取自 ``mcp_registry``（对外 207 项
  单源），执行期请求拼装复用同一 ``build_path`` / ``build_body``。
- **body 字段白名单**：网关写接口的 pydantic 基类 ``extra='ignore'``，下游
  （``task_service`` / ``algorithm_service``）也会静默忽略未映射字段。传了
  不生效的字段会让模型以为「改成功了」，因此本层按真实可写字段直接拒绝。
  参数更新的白名单取两端实现的**交集**（``options_source`` 等字段在更新路径
  不生效，故只在创建时允许）。
- **作用域判别**：``param_create`` 显式归一 ``param_type_source``（缺省
  ``device``）并校验：``api`` 必须带 ``api_id``（算法类型级 API 默认层已废弃，
  不带 ``api_id`` 的 API 参数在读取路径看不见）；设备 / API 两种作用域的
  字段集合互斥，混传直接拒绝。
- **删除是软删**：定义 / 参数 / 参考参数 / 映射的 DELETE 都是 ``deleted=true``，
  不发生物理删除；即便如此仍按 ``DESTRUCTIVE`` 提案（审批端二次确认），
  因为被删配置会立刻影响后续执行与评估。
- **热重载**：只从数据库重建算法配置缓存并广播失效通知，**不改任何配置
  数据**，因此可重复执行且结果一致；失败不静默 —— 网关的 reload 信封有两层
  ``success``，外层恒为 ``True``（``task_service.reload_config`` 在 gRPC
  重载失败时也返回 200 + ``reload_time=None``），因此工具层另按载荷断言
  （``validate_result``）：内层 ``success`` 不是 ``True`` 或 ``reload_time``
  为空即 ``UPSTREAM_ERROR``。热重载不校验业务规则，也不替代「保存 / 发布」。
- **导入是只增不改**：``import`` 对已存在的 ``type`` 不更新定义；同一次导入里
  的 ``params`` 按设备参数追加。模型侧不要用它做「覆盖导入」。
- **幂等**：同一 tool_call 的重复执行由 M2 基座（INT-2466）的审批幂等键
  领取一次；本模块不另生成幂等键，避免两套口径。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from shared.agent_tools import contract as platform_contract_catalog
from shared.agent_tools.write_support import (
    RISK_DESTRUCTIVE, WriteAction, require_body, require_positive_int,
    require_text, resolve_domain,
)

DEFINITION_MANAGE = 'algorithm:definition_manage'
PARAM_MANAGE = 'algorithm:param_manage'

# 工具级权限 = 可见性并集；调用时按动作收窄（``permissions_for``）。
MANAGE_PERMISSIONS: Tuple[str, ...] = (DEFINITION_MANAGE, PARAM_MANAGE)

# ------------------------------------------------------------------ 动作表

ACTIONS: Dict[str, WriteAction] = {
    # ---- 算法定义 ----
    'definition_create': WriteAction(
        tool='algorithm_definition_create', params=('body',),
        required=('body',), permissions=(DEFINITION_MANAGE,)),
    'definition_update': WriteAction(
        tool='algorithm_definition_update', params=('algo_type', 'body'),
        required=('algo_type', 'body'), permissions=(DEFINITION_MANAGE,)),
    'definition_save': WriteAction(
        tool='algorithm_definition_save', params=('body',),
        required=('body',), permissions=(DEFINITION_MANAGE,)),
    'definition_delete': WriteAction(
        tool='algorithm_definition_delete', params=('algo_type',),
        required=('algo_type',), permissions=(DEFINITION_MANAGE,),
        risk=RISK_DESTRUCTIVE),
    # ---- 设备 / API 参数 ----
    'param_create': WriteAction(
        tool='algorithm_param_create', params=('body',),
        required=('body',), permissions=(PARAM_MANAGE,)),
    'param_update': WriteAction(
        tool='algorithm_param_update', params=('param_id', 'body'),
        required=('param_id', 'body'), permissions=(PARAM_MANAGE,)),
    'param_delete': WriteAction(
        tool='algorithm_param_delete', params=('param_id',),
        required=('param_id',), permissions=(PARAM_MANAGE,),
        risk=RISK_DESTRUCTIVE),
    # ---- 参考参数 ----
    'reference_param_create': WriteAction(
        tool='algorithm_reference_param_create', params=('body',),
        required=('body',), permissions=(PARAM_MANAGE,)),
    'reference_param_update': WriteAction(
        tool='algorithm_reference_param_update', params=('param_id', 'body'),
        required=('param_id', 'body'), permissions=(PARAM_MANAGE,)),
    'reference_param_delete': WriteAction(
        tool='algorithm_reference_param_delete', params=('param_id',),
        required=('param_id',), permissions=(PARAM_MANAGE,),
        risk=RISK_DESTRUCTIVE),
    # ---- 参数映射 ----
    'mapping_create': WriteAction(
        tool='algorithm_mapping_create', params=('body',),
        required=('body',), permissions=(PARAM_MANAGE,)),
    'mapping_update': WriteAction(
        tool='algorithm_mapping_update', params=('mapping_id', 'body'),
        required=('mapping_id', 'body'), permissions=(PARAM_MANAGE,)),
    'mapping_delete': WriteAction(
        tool='algorithm_mapping_delete', params=('mapping_id',),
        required=('mapping_id',), permissions=(PARAM_MANAGE,),
        risk=RISK_DESTRUCTIVE),
    # ---- 导入 / 热重载 ----
    'import': WriteAction(
        tool='algorithm_import', params=('body',),
        required=('body',), permissions=(DEFINITION_MANAGE,)),
    'reload': WriteAction(
        tool='algorithm_reload', params=(), permissions=(DEFINITION_MANAGE,)),
}

ACTION_NAMES: Tuple[str, ...] = tuple(ACTIONS)

# 删 / 改 / 查三类的动作分组（proposal_diff 与 Skill 文案共用）。
DELETE_ACTIONS: Tuple[str, ...] = tuple(
    action for action, spec in ACTIONS.items() if spec.risk == RISK_DESTRUCTIVE)

# 动作 → 落库目标表（审批预览用；参数按作用域区分两张表）。
TARGET_TABLES: Dict[str, str] = {
    'definition_create': 'algorithm_definitions',
    'definition_update': 'algorithm_definitions',
    'definition_save': 'algorithm_definitions（含子实体表）',
    'definition_delete': 'algorithm_definitions',
    'param_create': 'algorithm_device_params / algorithm_api_params',
    'param_update': 'algorithm_device_params / algorithm_api_params',
    'param_delete': 'algorithm_device_params / algorithm_api_params',
    'reference_param_create': 'algorithm_reference_params',
    'reference_param_update': 'algorithm_reference_params',
    'reference_param_delete': 'algorithm_reference_params',
    'mapping_create': 'param_mappings',
    'mapping_update': 'param_mappings',
    'mapping_delete': 'param_mappings',
    'import': 'algorithm_definitions + algorithm_device_params',
    'reload': '（缓存重建，不写业务表）',
}

# ------------------------------------------------------------------ 枚举

# 网关 create_param 的判别键取值（``param_type_source``）。
PARAM_TYPE_SOURCES: Tuple[str, ...] = platform_contract_catalog.ALGORITHM_PARAM_TYPE_VALUES

# 映射来源的合法取值。算法服务侧白名单（``algorithm_param_handlers`` /
# ``config_cache`` 的 ``_VALID_MAPPING_SOURCES``）是 case / reference /
# device / api 四个；``contract.ALGORITHM_MAPPING_SOURCE_VALUES`` 只是读取
# 侧的作用域过滤口径（device / api），写侧不能用它收窄，否则建不出
# 用例 / 参考参数来源的映射。
MAPPING_SOURCE_VALUES: Tuple[str, ...] = ('case', 'reference', 'device', 'api')

# 参数方向（两张参数表与映射行的 ``source_direction`` 同一取值）。
DIRECTION_VALUES: Tuple[str, ...] = ('input', 'output')

# ------------------------------------------------------------------ body 白名单
# 逐字段对应网关 pydantic schema（``api_gateway/schemas/_algorithm_*``）；
# 更新路径再按服务端真实可写字段收窄（见模块 docstring）。

DEFINITION_CREATE_FIELDS: Tuple[str, ...] = (
    'type', 'name', 'category', 'description', 'status', 'icon',
    'display_order', 'group_id', 'device_params', 'api_params',
    'case_params', 'mappings', 'associated_dimensions', 'reference_params',
)
# AlgorithmDefinitionUpdate 不含 type / reference_params：算法类型是路径键，
# 参考参数走 reference_param_* 动作。
DEFINITION_UPDATE_FIELDS: Tuple[str, ...] = (
    'name', 'category', 'description', 'status', 'icon', 'display_order',
    'group_id', 'device_params', 'api_params', 'case_params', 'mappings',
    'associated_dimensions',
)
# 全量保存（INT-589）：聚合事务 + 乐观锁。
DEFINITION_SAVE_FIELDS: Tuple[str, ...] = (
    'id', 'type', 'algorithm_type', 'name', 'category', 'description',
    'status', 'icon', 'display_order', 'group_id', 'expected_updated_at',
    'device_params', 'api_params', 'case_params', 'reference_params',
    'mappings', 'associated_dimensions',
)

# 参数创建：设备作用域与 API 作用域字段集合互斥（``device_id`` vs
# ``api_id`` / ``field_path``），``param_type_source`` 是判别键。
_PARAM_CREATE_COMMON: Tuple[str, ...] = (
    'algorithm_type', 'param_code', 'param_name', 'label', 'param_type',
    'direction', 'required', 'default_value', 'options_source',
    'options_field', 'options_label_field', 'validation_rules', 'help_text',
    'ui_order', 'hidden', 'param_type_source',
)
PARAM_CREATE_DEVICE_FIELDS: Tuple[str, ...] = \
    _PARAM_CREATE_COMMON + ('device_id',)
PARAM_CREATE_API_FIELDS: Tuple[str, ...] = \
    _PARAM_CREATE_COMMON + ('api_id', 'field_path')

# 参数更新：两端实现的可写字段交集（``task_service`` 的
# ``updatable_fields`` ∩ ``algorithm_service`` 的列）。
# - 不含 options_*：更新路径两端都不生效（传了会被静默忽略）；
# - 不含 device_id / api_id / algorithm_type：作用域与归属不允许借更新搬移；
# - ``field_path`` 只对 API 参数行生效（设备参数表无该列），按行类型由服务端
#   决定，工具层不按作用域预判。
PARAM_UPDATE_FIELDS: Tuple[str, ...] = (
    'param_code', 'param_name', 'label', 'param_type', 'direction', 'required',
    'default_value', 'validation_rules', 'help_text', 'ui_order', 'hidden',
    'field_path',
)

REFERENCE_PARAM_CREATE_FIELDS: Tuple[str, ...] = (
    'algorithm_type', 'code', 'name', 'type', 'annotation_code',
    'annotation_format', 'field_path', 'merge_mode', 'help_text',
)
# 更新路径不接受 algorithm_type（服务端不搬家），传了会被静默忽略。
REFERENCE_PARAM_UPDATE_FIELDS: Tuple[str, ...] = (
    'code', 'name', 'type', 'annotation_code', 'annotation_format',
    'field_path', 'merge_mode', 'help_text',
)

MAPPING_CREATE_FIELDS: Tuple[str, ...] = (
    'algorithm_type', 'api_id', 'device_id', 'source_type', 'source_param',
    'source_direction', 'dimension_id', 'target_param', 'transform_type',
)
MAPPING_UPDATE_FIELDS: Tuple[str, ...] = (
    'api_id', 'device_id', 'source_type', 'source_param', 'source_direction',
    'dimension_id', 'target_param', 'transform_type',
)

IMPORT_BODY_FIELDS: Tuple[str, ...] = ('algorithms',)

# ------------------------------------------------------------------ 校验辅助


def _unknown_fields(action: str, body: Dict[str, Any],
                    allowed: Sequence[str]) -> Optional[str]:
    """动作不支持的 body 字段直接拒绝（网关 / 下游会静默忽略）。

    显式 ``None`` 视为「不设置」（与 ``_apply_update_fields`` 的 None 跳过
    同口径），不按未知字段拒绝；非空的未知字段才是「传了但不会生效」。
    """
    unknown = sorted(key for key in body
                     if key not in allowed and body[key] is not None)
    if not unknown:
        return None
    return (f'action={action} 的 body 不支持字段：{"、".join(unknown)}'
            f'（允许的字段：{"/".join(allowed)}）')


def _missing_fields(action: str, body: Dict[str, Any],
                    names: Sequence[str]) -> Optional[str]:
    """必填字段：``None`` / 空串 / 空数组 / 空对象都算缺失。"""
    missing = [name for name in names
               if body.get(name) in (None, '', [], {})]
    if not missing:
        return None
    return f'action={action} 的 body 缺少必填字段：{"、".join(missing)}'


def _check_status(action: str, body: Dict[str, Any]) -> Optional[str]:
    """定义状态只认接口值（未知值会被服务端静默落成 draft）。"""
    status = body.get('status')
    if status is None:
        return None
    if status not in platform_contract_catalog.ALGORITHM_STATUS_VALUES:
        return (f'action={action} 的 body.status 取值必须是 '
                f'{"/".join(platform_contract_catalog.ALGORITHM_STATUS_VALUES)} 之一')
    return None


def _check_direction(action: str, body: Dict[str, Any],
                     field: str) -> Optional[str]:
    value = body.get(field)
    if value is None or value in DIRECTION_VALUES:
        return None
    return (f'action={action} 的 body.{field} 取值必须是 '
            f'{"/".join(DIRECTION_VALUES)} 之一')


def _check_positive_id(action: str, body: Dict[str, Any],
                       field: str) -> Optional[str]:
    value = body.get(field)
    if value is None:
        return None
    return require_positive_int(value, f'body.{field}', action)


def _check_body(action: str, merged: Dict[str, Any],
                allowed: Sequence[str],
                required: Sequence[str] = ()) -> Tuple[
                    Optional[Dict[str, Any]], Optional[str]]:
    """通用 body 校验：对象 → 白名单 → 必填。"""
    error = require_body(merged, action=action)
    if error:
        return None, error
    body = merged['body']
    error = _unknown_fields(action, body, allowed) or \
        _missing_fields(action, body, required)
    if error:
        return None, error
    return body, None


# ------------------------------------------------------------------ 动作归一


def _prepare_definition_create(action: str,
                               merged: Dict[str, Any]) -> Optional[str]:
    body, error = _check_body(action, merged, DEFINITION_CREATE_FIELDS,
                              ('type', 'name'))
    if error:
        return error
    error = _check_status(action, body)
    if error:
        return error
    if body.get('group_id') is not None:
        return require_positive_int(body['group_id'], 'body.group_id', action)
    return None


def _prepare_definition_update(action: str,
                               merged: Dict[str, Any]) -> Optional[str]:
    error = require_text(merged.get('algo_type'), 'algo_type', action)
    if error:
        return error
    body, error = _check_body(action, merged, DEFINITION_UPDATE_FIELDS)
    if error:
        return error
    return _check_status(action, body)


def _prepare_definition_save(action: str,
                             merged: Dict[str, Any]) -> Optional[str]:
    body, error = _check_body(action, merged, DEFINITION_SAVE_FIELDS,
                              ('name',))
    if error:
        return error
    error = _check_status(action, body)
    if error:
        return error
    algorithm_id = body.get('id')
    if algorithm_id is not None:
        # 更新路径：服务端硬要求乐观锁版本（缺了抛 ValueError → 400），
        # 提案阶段就拦下，避免审批人批一条注定失败的提案。
        error = require_positive_int(algorithm_id, 'body.id', action)
        if error:
            return error
        if not str(body.get('expected_updated_at') or '').strip():
            return ('action=definition_save 的 body.id 有值时必须带 '
                    'expected_updated_at（乐观锁版本，取自定义详情 updated_at）')
    # 保存路径的算法类型：``algorithm_handlers.handle_save_definition`` 无条件
    # 校验 ``algorithm_type``（网关把 ``type`` 映射过去），新建与更新都必填。
    # 只在新建分支检查会让「更新缺类型」的提案通过、审批后才 422（INT-2470
    # 打回项 P3）。
    if not (str(body.get('type') or '').strip()
            or str(body.get('algorithm_type') or '').strip()):
        if algorithm_id is not None:
            return ('action=definition_save 的 body.id 有值时必须带 '
                    'body.type 或 body.algorithm_type（服务端保存时无条件校验；'
                    '取自定义详情的类型字段）')
        return 'action=definition_save 新建时必须带 body.type 或 body.algorithm_type'
    return None


def _prepare_param_create(action: str,
                          merged: Dict[str, Any]) -> Optional[str]:
    body = merged.get('body')
    if not isinstance(body, dict) or not body:
        return f'action={action} 的 body 必须是非空对象'
    source = body.get('param_type_source') or 'device'
    if source not in PARAM_TYPE_SOURCES:
        return (f'action={action} 的 body.param_type_source 取值必须是 '
                f'{"/".join(PARAM_TYPE_SOURCES)} 之一')
    # 显式回写判别键：网关 create_param 用它选 Schema 并回传给服务层，
    # 缺省值由本层固定，避免「传了 api_id 却按 device 建」。
    body['param_type_source'] = source
    allowed = (PARAM_CREATE_API_FIELDS if source == 'api'
               else PARAM_CREATE_DEVICE_FIELDS)
    error = _unknown_fields(action, body, allowed) or \
        _missing_fields(action, body, ('algorithm_type', 'param_code',
                                       'param_type'))
    if error:
        return error
    error = _check_direction(action, body, 'direction')
    if error:
        return error
    if source == 'api':
        # 算法类型级 API 默认层已废弃：不带 api_id 的 API 参数在读取路径
        # （param_type=api 必须带 api_id）永远看不见。
        if body.get('api_id') is None:
            return ('action=param_create 建 API 参数必须带 body.api_id'
                    '（API 实例作用域；先用 algorithm_query 的 params 查目标 API）')
        return require_positive_int(body['api_id'], 'body.api_id', action)
    return _check_positive_id(action, body, 'device_id')


def _prepare_param_update(action: str,
                          merged: Dict[str, Any]) -> Optional[str]:
    error = require_positive_int(merged.get('param_id'), 'param_id', action)
    if error:
        return error
    body, error = _check_body(action, merged, PARAM_UPDATE_FIELDS)
    if error:
        return error
    return _check_direction(action, body, 'direction')


def _prepare_param_delete(action: str,
                          merged: Dict[str, Any]) -> Optional[str]:
    return require_positive_int(merged.get('param_id'), 'param_id', action)


def _prepare_reference_create(action: str,
                              merged: Dict[str, Any]) -> Optional[str]:
    body, error = _check_body(action, merged,
                              REFERENCE_PARAM_CREATE_FIELDS,
                              ('algorithm_type', 'code'))
    return error


def _prepare_reference_update(action: str,
                              merged: Dict[str, Any]) -> Optional[str]:
    error = require_positive_int(merged.get('param_id'), 'param_id', action)
    if error:
        return error
    _body, error = _check_body(action, merged,
                               REFERENCE_PARAM_UPDATE_FIELDS)
    return error


def _prepare_mapping_create(action: str,
                            merged: Dict[str, Any]) -> Optional[str]:
    body, error = _check_body(
        action, merged, MAPPING_CREATE_FIELDS,
        ('algorithm_type', 'source_type', 'source_param', 'target_param'))
    if error:
        return error
    source_type = body.get('source_type')
    if source_type not in MAPPING_SOURCE_VALUES:
        return (f'action=mapping_create 的 body.source_type 取值必须是 '
                f'{"/".join(MAPPING_SOURCE_VALUES)} 之一')
    error = _check_direction(action, body, 'source_direction') or \
        _check_positive_id(action, body, 'device_id') or \
        _check_positive_id(action, body, 'api_id') or \
        _check_positive_id(action, body, 'dimension_id')
    if error:
        return error
    if source_type == 'api' and body.get('api_id') is None:
        return ('action=mapping_create 的 body.source_type=api 时必须带 '
                'body.api_id（API 实例作用域；算法类型级 API 映射层已废弃）')
    return None


def _prepare_mapping_update(action: str,
                            merged: Dict[str, Any]) -> Optional[str]:
    error = require_positive_int(merged.get('mapping_id'), 'mapping_id',
                                 action)
    if error:
        return error
    body, error = _check_body(action, merged, MAPPING_UPDATE_FIELDS)
    if error:
        return error
    source_type = body.get('source_type')
    if source_type is not None and source_type not in MAPPING_SOURCE_VALUES:
        return (f'action=mapping_update 的 body.source_type 取值必须是 '
                f'{"/".join(MAPPING_SOURCE_VALUES)} 之一')
    return _check_direction(action, body, 'source_direction') or \
        _check_positive_id(action, body, 'dimension_id')


def _prepare_delete_id_field(action: str, field: str):
    """只带路径 ID 的删除动作（定义 / 参考参数 / 映射）。"""
    def _prepare(_action: str, merged: Dict[str, Any]) -> Optional[str]:
        return require_positive_int(merged.get(field), field, action)
    return _prepare


def _prepare_definition_delete(action: str,
                               merged: Dict[str, Any]) -> Optional[str]:
    return require_text(merged.get('algo_type'), 'algo_type', action)


def _prepare_import(action: str, merged: Dict[str, Any]) -> Optional[str]:
    body, error = _check_body(action, merged, IMPORT_BODY_FIELDS)
    if error:
        return error
    algorithms = body.get('algorithms')
    if not isinstance(algorithms, list) or not algorithms:
        return 'action=import 的 body.algorithms 必须是非空数组'
    for index, item in enumerate(algorithms):
        if not isinstance(item, dict) or not item:
            return f'action=import 的 body.algorithms[{index}] 必须是非空对象'
        if not str(item.get('type') or '').strip():
            # 服务端对缺 type 的条目是静默跳过（不报错也不导入），
            # 放进提案会让审批人以为这些条目会被导入。
            return (f'action=import 的 body.algorithms[{index}] 缺少 type'
                    '（服务端会静默跳过该条目）')
        if item.get('params') is not None and not isinstance(
                item['params'], list):
            return f'action=import 的 body.algorithms[{index}].params 必须是数组'
    return None


def _prepare_reload(_action: str, _merged: Dict[str, Any]) -> Optional[str]:
    # 热重载不接收任何参数：``resolve_domain`` 已按动作白名单拒绝多余键。
    return None


_PREPARE_HOOKS: Dict[str, Any] = {
    'definition_create': _prepare_definition_create,
    'definition_update': _prepare_definition_update,
    'definition_save': _prepare_definition_save,
    'definition_delete': _prepare_definition_delete,
    'param_create': _prepare_param_create,
    'param_update': _prepare_param_update,
    'param_delete': _prepare_param_delete,
    'reference_param_create': _prepare_reference_create,
    'reference_param_update': _prepare_reference_update,
    'reference_param_delete': _prepare_delete_id_field(
        'reference_param_delete', 'param_id'),
    'mapping_create': _prepare_mapping_create,
    'mapping_update': _prepare_mapping_update,
    'mapping_delete': _prepare_delete_id_field(
        'mapping_delete', 'mapping_id'),
    'import': _prepare_import,
    'reload': _prepare_reload,
}


def _prepare(action: str, merged: Dict[str, Any]) -> Optional[str]:
    """动作级归一：校验 ID / body 字段 / 跨字段规则，返回错误文本或 None。"""
    hook = _PREPARE_HOOKS.get(action)
    return hook(action, merged) if hook is not None else None


def resolve(arguments: Optional[Dict[str, Any]]
            ) -> Tuple[Optional[dict], Optional[Dict[str, Any]],
                       Optional[str]]:
    """解析 ``algorithm_manage`` 调用为 ``(目标工具项, 合并参数, 错误文本)``。"""
    return resolve_domain(ACTIONS, arguments, label='algorithm_manage',
                          prepare=_prepare)


# ------------------------------------------------------------ 执行后校验

# 成功路径必定带重建时间（``algorithm_service`` 的 ReloadConfig 在缓存重建
# 成功后写入 ``_last_reload_time``），因此空 ``reload_time`` 就是「缓存没重建」。


def validate_result(action: str, payload: Any) -> Optional[str]:
    """执行后语义校验：HTTP 2xx 但实际未成功时返回错误文本。

    目前只有热重载需要：``POST /api/v1/algorithm/reload`` 的外层信封恒为
    ``success=True``，真实结果在内层 ``data``；``task_service.reload_config``
    在 gRPC 重载失败时仍返回 ``success=True`` + ``reload_time=None``，只看
    HTTP 状态会把「配置缓存没重建」报成成功（INT-2470 打回项 P2）。其余写动作
    的结果由接口幂等语义直接表达，不做额外断言。
    """
    if action != 'reload':
        return None
    if not isinstance(payload, dict):
        return '热重载返回非 JSON 对象，无法确认配置缓存已重建'
    data = payload.get('data')
    if not isinstance(data, dict):
        return '热重载响应缺少 data，无法确认配置缓存已重建'
    message = str(data.get('message') or payload.get('message') or '').strip()
    if data.get('success') is not True:
        return ('热重载未成功：' + (message or '接口返回 success=false')
                + '；不要当作已生效')
    if not str(data.get('reload_time') or '').strip():
        return ('热重载未完成：reload_time 为空（配置缓存未重建）'
                + (f'：{message}' if message else '')
                + '；请检查 algorithm_service 后重试，不要当作已生效')
    return None


# ------------------------------------------------------------------ 审批预览

# 审批人最需要看清的「这次改了什么」：大段子实体结构只给键名与条数，
# 不把整棵树塞进 diff。
_SUB_ENTITY_FIELDS: Tuple[str, ...] = (
    'device_params', 'api_params', 'case_params', 'reference_params',
    'mappings', 'associated_dimensions',
)


def _describe_effect(action: str) -> str:
    if action in DELETE_ACTIONS:
        return '软删除（deleted=true，可追溯；不物理删除数据）'
    if action == 'reload':
        return ('从数据库重建算法配置缓存并广播失效通知（不改配置数据；'
                '可重复执行，结果一致）')
    if action == 'import':
        return '按 type 导入算法定义（已存在的 type 不更新）+ 追加设备参数'
    if action == 'definition_save':
        return ('聚合保存：定义与五类子实体同事务落库（并发覆盖返回 CONFLICT，'
                '不会静默覆盖）')
    if action == 'param_create':
        return '新增参数行（设备作用域或 API 实例作用域）'
    if action == 'param_update':
        return '按 param_id 更新参数行（作用域 / 归属不变）'
    return '更新既有配置行'


def proposal_diff(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """审批人可见的字段级变更预览（比通用 REST 请求预览更可读）。

    只转述「这次要改什么」：动作、目标表、目标 ID、变更字段、影响面；
    不回源、不预判结果，也不编造目标当前值。
    """
    action = (arguments or {}).get('action')
    if action not in ACTIONS:
        return None
    diff: Dict[str, Any] = {
        'kind': 'algorithm_config',
        'operation': action,
        'target_table': TARGET_TABLES[action],
        'request': ACTIONS[action].tool,
    }
    algo_type = arguments.get('algo_type')
    if algo_type:
        diff['algo_type'] = algo_type
    for field in ('param_id', 'mapping_id'):
        if arguments.get(field) is not None:
            diff[field] = arguments[field]
    body = arguments.get('body')
    if isinstance(body, dict):
        changes = {key: value for key, value in body.items()
                   if key not in _SUB_ENTITY_FIELDS}
        if changes:
            diff['changes'] = changes
        sub_entities: Dict[str, Any] = {}
        for field in _SUB_ENTITY_FIELDS:
            value = body.get(field)
            if value is None:
                continue
            if isinstance(value, list):
                sub_entities[field] = {'count': len(value)}
            elif isinstance(value, dict):
                sub_entities[field] = {
                    'groups': sorted(value),
                    'count': sum(len(items or []) for items in value.values()
                                 if isinstance(items, list)),
                }
            else:
                sub_entities[field] = {'count': 0}
        if sub_entities:
            diff['sub_entities'] = sub_entities
        if action == 'param_create':
            diff['scope'] = body.get('param_type_source') or 'device'
        if action == 'import':
            algorithms = body.get('algorithms') or []
            diff['scope'] = {
                'algorithm_types': [item.get('type') for item in algorithms
                                    if isinstance(item, dict)],
                'count': len(algorithms),
            }
    diff['effect'] = _describe_effect(action)
    if action in DELETE_ACTIONS:
        diff['irreversible_by_tool'] = True
    return diff


__all__ = [
    'ACTIONS', 'ACTION_NAMES', 'DEFINITION_CREATE_FIELDS', 'DEFINITION_MANAGE',
    'DEFINITION_SAVE_FIELDS', 'DEFINITION_UPDATE_FIELDS', 'DELETE_ACTIONS',
    'DIRECTION_VALUES', 'IMPORT_BODY_FIELDS', 'MANAGE_PERMISSIONS',
    'MAPPING_CREATE_FIELDS', 'MAPPING_SOURCE_VALUES', 'MAPPING_UPDATE_FIELDS',
    'PARAM_CREATE_API_FIELDS', 'PARAM_CREATE_DEVICE_FIELDS', 'PARAM_MANAGE',
    'PARAM_TYPE_SOURCES', 'PARAM_UPDATE_FIELDS',
    'REFERENCE_PARAM_CREATE_FIELDS', 'REFERENCE_PARAM_UPDATE_FIELDS',
    'TARGET_TABLES', 'proposal_diff', 'resolve', 'validate_result',
]
