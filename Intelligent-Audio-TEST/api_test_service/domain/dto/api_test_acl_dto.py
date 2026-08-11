# -*- coding: utf-8 -*-
"""api_test_service ACL DTO 定义。

供 api_test_service/infrastructure/acl 下的仓储使用，
将 gRPC 返回的 raw dict 转换为 dataclass DTO。

每个 DTO 声明常用类型字段并携带 ``result_data: Any`` 保留原始动态负载，
经 ``shared.utils.dto_utils.dto_to_dict`` 可还原完整 dict（兼容历史调用方）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TaskDTO:
    """Task DTO（task_service.TaskDataService.GetTaskById 返回）"""
    id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    algorithm_type: Optional[str] = None
    config: Any = None
    result_data: Any = None


@dataclass
class TaskCaseDTO:
    """TaskCase 关联 DTO（GetTaskCaseByIds 返回的 items）"""
    id: Optional[int] = None
    task_id: Optional[int] = None
    case_id: Optional[str] = None
    test_case_id: Optional[str] = None
    status: Optional[str] = None
    execution_status: Optional[str] = None
    evaluation_status: Optional[str] = None
    error_message: Optional[str] = None
    result_data: Any = None


@dataclass
class TaskApiDTO:
    """任务-API 关联 DTO（GetTaskApis 返回）"""
    task_id: Optional[int] = None
    api_id: Optional[int] = None
    result_data: Any = None


@dataclass
class TestCaseDetailDTO:
    """测试用例详情 DTO（TestCaseConfigService.GetTestCaseDetail）"""
    id: Optional[int] = None
    name: Optional[str] = None
    test_type: Optional[str] = None
    algorithm_type: Optional[str] = None
    config: Any = None
    result_data: Any = None


@dataclass
class AudioDTO:
    """音频 DTO（AudioConfigService.GetAudio）"""
    id: Optional[int] = None
    name: Optional[str] = None
    file_path: Optional[str] = None
    duration: Optional[float] = None
    audio_type: Optional[str] = None
    sample_rate: Optional[int] = None
    asr_text: Optional[str] = None
    deleted: Optional[bool] = None
    annotations: Any = None
    result_data: Any = None


@dataclass
class AdapterRoundResultDTO:
    """adapter SendRound 返回结果 DTO"""
    output_content: Optional[str] = None
    output: Optional[str] = None
    output_audio_path: Optional[str] = None
    response_metrics: Any = None
    result_data: Any = None


@dataclass
class AlgoFieldMappingsDTO:
    """算法字段映射 DTO（algo_get_field_mappings 返回）"""
    original: Any = None
    result_data: Any = None


@dataclass
class AlgoParamDTO:
    """算法参数 DTO（algo_get_device_params / algo_get_api_params items）"""
    id: Optional[int] = None
    param_code: Optional[str] = None
    field_path: Optional[str] = None
    field_type: Optional[str] = None
    param_type: Optional[str] = None
    ui_group: Optional[str] = None
    source_direction: Optional[str] = None
    result_data: Any = None


@dataclass
class AlgoParamMappingDTO:
    """算法参数映射 DTO（algo_get_param_mapping items）"""
    id: Optional[int] = None
    param_code: Optional[str] = None
    field_path: Optional[str] = None
    source_direction: Optional[str] = None
    component_type: Optional[str] = None
    result_data: Any = None


@dataclass
class ExtractedCaseParamsDTO:
    """algo_extract_case_all_params 返回 DTO"""
    evaluation: Any = None
    result_data: Any = None
