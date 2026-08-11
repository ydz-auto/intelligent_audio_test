# -*- coding: utf-8 -*-
"""参数/映射/维度关联写操作命令（CQRS - Command 侧）。

归属：algorithm_service.application.commands

说明：
- 所有命令均为 frozen dataclass，作为写操作的输入契约。
- 命令只承载"做什么"的意图，不携带领域对象，不包含业务逻辑。
- 实际处理由 handlers/algorithm_param_handlers.py 的
  AlgorithmParamCommandHandler 完成。
- 命令字段与 servicers.py 对应 gRPC 方法的请求参数对齐，
  便于 servicer 将 request 转为命令后委托 handler。

命令清单：
- 设备/API 参数：CreateParamCommand / UpdateParamCommand / DeleteParamCommand
                  / FindParamByCodeCommand
- 用例参数：CreateCaseParamCommand / UpdateCaseParamCommand / DeleteCaseParamCommand
            / FindCaseParamByCodeCommand / ReviveCaseParamCommand
- 参考参数：CreateReferenceParamCommand / UpdateReferenceParamCommand
            / DeleteReferenceParamCommand / FindReferenceParamCommand
- 参数映射：CreateMappingCommand / UpdateMappingCommand / DeleteMappingCommand
- 维度关联：CreateDimensionRelationCommand / UpdateDimensionRelationAttrsCommand
            / DeleteDimensionRelationCommand
            / SoftDeleteAlgorithmDimensionRelationsCommand
- 导入/批量：CreateImportDeviceParamCommand / BulkDeleteAlgorithmsCommand
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ========== 设备/API 参数命令 ==========

@dataclass(frozen=True)
class CreateParamCommand:
    """创建设备参数或 API 参数命令。

    - data: 参数字段集合（algorithm_type / param_code / param_name / label
            / param_type / direction / required / default_value
            / validation_rules / help_text / ui_order / hidden）
    - param_type_source: 参数来源（device/api）
    """

    data: Dict[str, Any]
    param_type_source: str = "device"


@dataclass(frozen=True)
class UpdateParamCommand:
    """更新设备参数或 API 参数命令。

    - param_id: 参数ID
    - data: 待更新字段集合
    - param_type_source: 参数来源（device/api，空值时自动探测）
    """

    param_id: int
    data: Dict[str, Any]
    param_type_source: str = ""


@dataclass(frozen=True)
class DeleteParamCommand:
    """软删除设备参数或 API 参数命令。

    - param_id: 参数ID
    - param_type_source: 参数来源（device/api，空值时自动探测）
    """

    param_id: int
    param_type_source: str = ""


@dataclass(frozen=True)
class FindParamByCodeCommand:
    """按 算法/参数代码/方向 查找设备或 API 参数命令。

    - algorithm_type: 算法类型代码
    - param_code: 参数代码
    - direction: 参数方向（input/output）
    - param_type_source: 参数来源（device/api）
    """

    algorithm_type: str
    param_code: str
    direction: str
    param_type_source: str = "device"


# ========== 用例参数命令 ==========

@dataclass(frozen=True)
class CreateCaseParamCommand:
    """创建用例专属参数命令。

    - data: 参数字段集合（algorithm_type / param_code / param_name / label
            / param_type / required / default_value / help_text / ui_order
            / hidden / scope / min_value / max_value / step / unit）
    """

    data: Dict[str, Any]


@dataclass(frozen=True)
class UpdateCaseParamCommand:
    """更新用例专属参数命令。

    - param_id: 参数ID
    - data: 待更新字段集合
    """

    param_id: int
    data: Dict[str, Any]


@dataclass(frozen=True)
class DeleteCaseParamCommand:
    """软删除用例专属参数命令。

    - param_id: 参数ID
    """

    param_id: int


@dataclass(frozen=True)
class FindCaseParamByCodeCommand:
    """按 算法/参数代码 查找用例参数命令（可包含软删项）。

    - algorithm_type: 算法类型代码
    - param_code: 参数代码
    - include_deleted: 是否包含已软删项
    """

    algorithm_type: str
    param_code: str
    include_deleted: bool = False


@dataclass(frozen=True)
class ReviveCaseParamCommand:
    """恢复软删除的用例参数并更新字段命令。

    - param_id: 参数ID
    - data: 待更新字段集合
    """

    param_id: int
    data: Dict[str, Any]


# ========== 参考参数命令 ==========

@dataclass(frozen=True)
class CreateReferenceParamCommand:
    """创建参考参数命令。

    - data: 参数字段集合（algorithm_type / code / name / param_type
            / annotation_code / annotation_format / field_path
            / merge_mode / help_text）
    """

    data: Dict[str, Any]


@dataclass(frozen=True)
class UpdateReferenceParamCommand:
    """更新参考参数命令。

    - param_id: 参数ID
    - data: 待更新字段集合
    """

    param_id: int
    data: Dict[str, Any]


@dataclass(frozen=True)
class DeleteReferenceParamCommand:
    """软删除参考参数命令。

    - param_id: 参数ID
    """

    param_id: int


@dataclass(frozen=True)
class FindReferenceParamCommand:
    """按 算法/code 查找参考参数命令。

    - algorithm_type: 算法类型代码
    - code: 参数代码
    """

    algorithm_type: str
    code: str


# ========== 参数映射命令 ==========

@dataclass(frozen=True)
class CreateMappingCommand:
    """创建参数映射命令。

    - data: 映射字段集合（algorithm_type / source_type / source_param
            / source_direction / dimension_id / target_param / transform_type）
    """

    data: Dict[str, Any]


@dataclass(frozen=True)
class UpdateMappingCommand:
    """更新参数映射命令。

    - mapping_id: 映射ID
    - data: 待更新字段集合
    """

    mapping_id: int
    data: Dict[str, Any]


@dataclass(frozen=True)
class DeleteMappingCommand:
    """软删除参数映射命令。

    - mapping_id: 映射ID
    """

    mapping_id: int


# ========== 维度关联命令 ==========

@dataclass(frozen=True)
class CreateDimensionRelationCommand:
    """创建维度关联命令。

    - data: 关联字段集合（algorithm_type / dimension_id / is_default / weight）
    """

    data: Dict[str, Any]


@dataclass(frozen=True)
class UpdateDimensionRelationAttrsCommand:
    """更新维度关联属性命令。

    - relation_id: 关联ID
    - data: 待更新字段集合（weight / is_default / dimension_id）
    """

    relation_id: int
    data: Dict[str, Any]


@dataclass(frozen=True)
class DeleteDimensionRelationCommand:
    """软删除维度关联命令。

    - relation_id: 关联ID
    """

    relation_id: int


@dataclass(frozen=True)
class SoftDeleteAlgorithmDimensionRelationsCommand:
    """按算法批量软删除维度关联命令。

    - algorithm_type: 算法类型代码
    """

    algorithm_type: str


# ========== 导入/批量命令 ==========

@dataclass(frozen=True)
class CreateImportDeviceParamCommand:
    """导入场景下创建设备参数命令（仅 add，由调用方控制 flush/commit）。

    - data: 参数字段集合（algorithm_type / code / name / label / type
            / required / default_value / ui_order / hidden）
    """

    data: Dict[str, Any]


@dataclass(frozen=True)
class BulkDeleteAlgorithmsCommand:
    """批量软删除算法定义命令。

    - algorithm_types: 算法类型代码列表
    """

    algorithm_types: List[str] = field(default_factory=list)
