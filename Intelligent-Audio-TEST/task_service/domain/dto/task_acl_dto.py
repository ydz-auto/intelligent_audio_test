# -*- coding: utf-8 -*-
"""task_service ACL DTO 定义。

供 task_service/infrastructure/acl 下的仓储使用，
将 gRPC 返回的 dict 转换为 dataclass DTO。

每个 DTO 对应 algorithm_service gRPC 返回的一种实体 dict，
字段与 PO to_dict() 输出键完全一致。

所有字段均使用 Optional + 默认值 None，因为 gRPC 返回的 dict
可能缺少部分键（如旧数据无 group_name）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AlgorithmDefinitionDTO:
    """算法定义 DTO（对应 AlgorithmDefinition.to_dict()）"""
    id: Optional[int] = None
    type: Optional[str] = None
    name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    icon: Optional[str] = None
    display_order: Optional[int] = None
    created_at: Any = None
    updated_at: Any = None


@dataclass
class AlgorithmGroupDTO:
    """算法分组 DTO（对应 AlgorithmGroup.to_dict()）"""
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    display_order: Optional[int] = None
    algorithm_count: Optional[int] = None
    created_at: Any = None
    updated_at: Any = None


@dataclass
class DeviceParamDTO:
    """设备参数 DTO（对应 AlgorithmDeviceParam.to_dict()）"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    param_code: Optional[str] = None
    param_name: Optional[str] = None
    label: Optional[str] = None
    param_type: Optional[str] = None
    direction: Optional[str] = None
    required: Optional[bool] = None
    default_value: Any = None
    validation: Any = None
    help_text: Optional[str] = None
    ui_order: Optional[int] = None
    hidden: Optional[bool] = None


@dataclass
class ApiParamDTO:
    """API 参数 DTO（与 DeviceParamDTO 同构）"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    param_code: Optional[str] = None
    param_name: Optional[str] = None
    label: Optional[str] = None
    param_type: Optional[str] = None
    direction: Optional[str] = None
    required: Optional[bool] = None
    default_value: Any = None
    validation: Any = None
    help_text: Optional[str] = None
    ui_order: Optional[int] = None
    hidden: Optional[bool] = None


@dataclass
class CaseParamDTO:
    """用例专属参数 DTO（对应 CaseAlgorithmParam.to_dict()）"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    param_code: Optional[str] = None
    param_name: Optional[str] = None
    label: Optional[str] = None
    param_type: Optional[str] = None
    required: Optional[bool] = None
    default_value: Any = None
    help_text: Optional[str] = None
    ui_order: Optional[int] = None
    hidden: Optional[bool] = None
    scope: Optional[str] = None
    min_value: Any = None
    max_value: Any = None
    step: Any = None
    unit: Optional[str] = None
    annotation_code: Optional[str] = None
    field_path: Optional[str] = None


@dataclass
class ReferenceParamDTO:
    """参考参数 DTO（对应 AlgorithmReferenceParam.to_dict()）"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    annotation_code: Optional[str] = None
    annotation_format: Optional[str] = None
    field_path: Optional[str] = None
    merge_mode: Optional[str] = None
    help_text: Optional[str] = None
    created_at: Any = None
    updated_at: Any = None


@dataclass
class ParamMappingDTO:
    """参数映射 DTO（对应 ParamMapping.to_dict()）"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    source: Optional[str] = None
    source_param: Optional[str] = None
    source_direction: Optional[str] = None
    dimension_id: Optional[int] = None
    target_param: Optional[str] = None
    transform_type: Optional[str] = None


@dataclass
class DimensionRelationDTO:
    """维度关联 DTO（对应 AlgorithmDimensionRelation.to_dict()）"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    dimension_id: Optional[int] = None
    is_default: Optional[bool] = None
    weight: Optional[float] = None


@dataclass
class DimensionParamDTO:
    """评估维度参数 DTO（对应 EvaluationDimensionParam.to_dict()）"""
    id: Optional[int] = None
    dimension_id: Optional[int] = None
    param_code: Optional[str] = None
    param_name: Optional[str] = None
    label: Optional[str] = None
    field_type: Optional[str] = None
    param_direction: Optional[str] = None
    field_path: Optional[str] = None
    agg_role: Optional[str] = None
    output_role: Optional[str] = None
    visible_in_report: Optional[bool] = None
    required: Optional[bool] = None
    default_value: Any = None
    help_text: Optional[str] = None
    ui_order: Optional[int] = None


@dataclass
class DimensionDTO:
    """跨域 Dimension DTO（来自 evaluation_service，精简 4 键）"""
    id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None


@dataclass
class CreateAckDTO:
    """精简 ack DTO（create_algorithm_definition / create_group 等返回）"""
    id: Optional[int] = None
    name: Optional[str] = None
    created: Optional[bool] = None
    added: Optional[bool] = None
