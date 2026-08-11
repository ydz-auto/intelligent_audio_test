# -*- coding: utf-8 -*-
"""report_service ACL DTO 定义。

供 report_service/infrastructure/acl 下的仓储使用，
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
class TestResultDTO:
    """TestResult DTO（task_service.TaskDataService 返回）"""
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
    round_number: Optional[int] = None


@dataclass
class TaskDeviceDTO:
    """任务-设备关联 DTO（GetTaskDevices 返回）"""
    task_id: Optional[int] = None
    device_id: Optional[int] = None
    device_sn: Optional[str] = None
    device_name: Optional[str] = None
    needs_prompt_audio: Optional[bool] = None
    prompt_audio_path: Optional[str] = None
    prompt_audio_name: Optional[str] = None
    result_data: Any = None


@dataclass
class TaskApiDTO:
    """任务-API 关联 DTO（GetTaskApis 返回）"""
    task_id: Optional[int] = None
    api_id: Optional[int] = None
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
class DimensionResultDTO:
    """维度评估结果 DTO（EvaluationDataService.GetDimensionResultsByResultIds items）"""
    id: Optional[int] = None
    result_id: Optional[int] = None
    test_result_id: Optional[int] = None
    dimension_id: Optional[int] = None
    dimension_name: Optional[str] = None
    dimension_value: Any = None
    round_number: Optional[int] = None
    score: Optional[float] = None
    api_raw_response: Any = None
    evaluation_status: Optional[str] = None
    error_message: Optional[str] = None
    result_data: Any = None


@dataclass
class DimensionDTO:
    """维度配置 DTO（EvaluationConfigService.ListDimensions / GetDimensionByIds）"""
    id: Optional[int] = None
    name: Optional[str] = None
    weight: Optional[float] = None
    score_unit: Optional[str] = None
    decimal_places: Optional[int] = None
    statistic_method: Optional[str] = None
    status: Optional[bool] = None
    deleted: Optional[bool] = None
    category_id: Optional[int] = None
    result_data: Any = None


@dataclass
class DimensionParamDTO:
    """维度参数 DTO（AlgorithmConfigService.GetDimensionParams items）"""
    id: Optional[int] = None
    param_code: Optional[str] = None
    field_path: Optional[str] = None
    field_type: Optional[str] = None
    agg_role: Optional[str] = None
    output_role: Optional[str] = None
    visible_in_report: Optional[bool] = None
    param_direction: Optional[str] = None
    dimension_id: Optional[int] = None
    result_data: Any = None


@dataclass
class TestCaseDTO:
    """测试用例 DTO（TestCaseConfigService.ListTestCases items）"""
    id: Optional[int] = None
    name: Optional[str] = None
    test_type: Optional[str] = None
    algorithm_type: Optional[str] = None
    config: Any = None
    result_data: Any = None


@dataclass
class TagCategoryDTO:
    """标签分类 DTO（TagConfigService.GetTagCategory）"""
    id: Optional[int] = None
    name: Optional[str] = None
    result_data: Any = None


@dataclass
class DeviceDTO:
    """设备 DTO（DeviceConfigService.GetDevice）"""
    id: Optional[int] = None
    name: Optional[str] = None
    system: Optional[str] = None
    keywords: Optional[str] = None
    serial_number: Optional[str] = None
    ip: Optional[str] = None
    device_type: Optional[str] = None
    result_data: Any = None


@dataclass
class PlaybackDeviceDTO:
    """播放设备 DTO（PlaybackConfigService.GetPlaybackDevice）"""
    id: Optional[int] = None
    name: Optional[str] = None
    device_type: Optional[str] = None
    serial_number: Optional[str] = None
    ip: Optional[str] = None
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
class ApiConfigDTO:
    """被测 API 配置 DTO（APITestService.GetAPIConfig）"""
    id: Optional[int] = None
    name: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    status: Optional[str] = None
    algorithm_type: Optional[str] = None
    config: Any = None
    result_data: Any = None


@dataclass
class TaskMergeRelationDTO:
    """任务合并关系 DTO（get_task_merge_relations items）"""
    id: Optional[int] = None
    merged_task_id: Optional[int] = None
    source_task_id: Optional[int] = None
    result_data: Any = None


@dataclass
class AlgoNormalizedParamsDTO:
    """规范化算法参数 DTO（AlgorithmQueryService.NormalizeAlgorithmParams 返回）。

    返回值为动态键值 dict（如 overlap_time / overlap_rate 等），
    无固定 schema，result_data 保留完整负载供 dto_to_dict 还原。
    """
    result_data: Any = None


@dataclass
class AlgoReferenceParamsDTO:
    """报告参考参数 DTO（AlgorithmQueryService.GetReferenceParamsForReport 返回）。

    返回值为动态键值 dict（code → {type, value, segments, text, json}），
    无固定 schema，result_data 保留完整负载供 dto_to_dict 还原。
    """
    result_data: Any = None
