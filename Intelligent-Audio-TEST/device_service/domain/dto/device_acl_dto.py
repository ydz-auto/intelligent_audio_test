# -*- coding: utf-8 -*-
"""device_service ACL DTO 定义。

供 device_service/infrastructure/acl 下的仓储使用，
将 gRPC 返回的 dict 转换为 dataclass DTO。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class FieldMappingDTO:
    """字段映射 DTO"""
    code: Optional[str] = None
    source_param: Optional[str] = None
    transform: Optional[str] = None
    component_type: Optional[str] = None
    dimension_id: Optional[int] = None


@dataclass
class DeviceParamDTO:
    """设备参数 DTO"""
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
class ParamMappingDTO:
    """参数映射 DTO"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    source: Optional[str] = None
    source_param: Optional[str] = None
    source_direction: Optional[str] = None
    dimension_id: Optional[int] = None
    target_param: Optional[str] = None
    transform_type: Optional[str] = None


@dataclass
class ReferenceParamDTO:
    """参考参数值 DTO

    对应 algorithm_service 生成的参考参数（generate_reference_params /
    get_all_reference_params 返回的 list[dict] 元素）。
    已知字段：code / type / value / annotation_code / annotation_format / round_number。
    其余动态键收纳到 result_data。
    """
    code: Optional[str] = None
    type: Optional[str] = None
    value: Any = None
    annotation_code: Optional[str] = None
    annotation_format: Optional[str] = None
    round_number: Optional[int] = None
    result_data: Any = None
