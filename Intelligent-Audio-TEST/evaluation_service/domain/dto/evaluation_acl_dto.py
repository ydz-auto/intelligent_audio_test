# -*- coding: utf-8 -*-
"""evaluation_service ACL 层 DTO 定义。

对应 task_service / algorithm_service gRPC 返回的数据结构，
作为防腐层向上层（domain/services）返回的 dataclass DTO，
替代裸 dict，提升类型安全与可维护性。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TestResultDTO:
    """TestResult DTO（对应 task_service 返回的 test_result dict）"""
    id: Optional[int] = None
    task_id: Optional[int] = None
    test_case_id: Optional[str] = None
    device_id: Optional[int] = None
    api_id: Optional[int] = None
    algorithm_result: Any = None
    result_data: Any = None
    execution_status: Optional[str] = None
    evaluation_status: Optional[str] = None
    response_time: Optional[float] = None
    error_message: Optional[str] = None
    result_data_path: Optional[str] = None


@dataclass
class TaskCaseDTO:
    """TaskCase DTO"""
    id: Optional[int] = None
    task_id: Optional[int] = None
    test_case_id: Optional[str] = None
    status: Optional[str] = None
    execution_status: Optional[str] = None
    evaluation_status: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class TaskDTO:
    """Task DTO"""
    id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    config: Any = None


@dataclass
class DimensionParamDTO:
    """评估维度参数 DTO"""
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
class DimensionRelationDTO:
    """维度关联 DTO"""
    id: Optional[int] = None
    algorithm_type: Optional[str] = None
    dimension_id: Optional[int] = None
    is_default: Optional[bool] = None
    weight: Optional[float] = None


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
class TestCaseDetailDTO:
    """测试用例详情 DTO"""
    id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    config: Any = None
    algorithm_type: Optional[str] = None
    reference_params: Any = None


@dataclass
class TaskDeviceDTO:
    """任务-设备关联 DTO"""
    task_id: Optional[int] = None
    device_id: Optional[int] = None
    device_sn: Optional[str] = None
    device_name: Optional[str] = None
    extra: Any = None


@dataclass
class TaskApiDTO:
    """任务-API 关联 DTO"""
    task_id: Optional[int] = None
    api_id: Optional[int] = None
    api_name: Optional[str] = None
    extra: Any = None
