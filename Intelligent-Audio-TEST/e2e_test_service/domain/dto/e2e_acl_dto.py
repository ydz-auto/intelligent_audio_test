from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TestResultDTO:
    """TestResult DTO"""
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
    case_id: Optional[str] = None
    status: Optional[str] = None
    execution_status: Optional[str] = None
    evaluation_status: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class AudioDTO:
    """音频 DTO"""
    id: Optional[int] = None
    name: Optional[str] = None
    file_path: Optional[str] = None
    duration: Optional[float] = None
    audio_type: Optional[str] = None
    sample_rate: Optional[int] = None
    deleted: Optional[bool] = None
    annotations: Any = None


@dataclass
class DeviceDTO:
    """设备 DTO"""
    id: Optional[int] = None
    name: Optional[str] = None
    system: Optional[str] = None
    keywords: Optional[str] = None
    serial_number: Optional[str] = None
    ip: Optional[str] = None
    needs_prompt_audio: Optional[bool] = None
    prompt_config: Any = None


@dataclass
class DimensionResultDTO:
    """维度评估结果 DTO"""
    id: Optional[int] = None
    result_id: Optional[int] = None
    dimension_id: Optional[int] = None
    dimension_name: Optional[str] = None
    round_number: Optional[int] = None
    score: Optional[float] = None
    evaluation_status: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CollectedResultDTO:
    """采集/转换/提取结果 DTO（collect_results / convert_results / extract_archive_results / get_final_results 通用）

    result_data 持有算法专属的动态结构字段（因算法类型不同而异）。
    """
    task_id: Optional[str] = None
    test_case_id: Optional[str] = None
    device_id: Optional[int] = None
    device_sn: Optional[str] = None
    round_number: Optional[int] = None
    result_type: Optional[str] = None
    success: Optional[bool] = None
    raw_results: Any = None
    adjusted_reference_params: Any = None
    result_data: Any = None
    error_message: Optional[str] = None


@dataclass
class PlaybackResultDTO:
    """播放结果 DTO（play_round 返回）

    audio_timelines 持有时间线列表（动态结构）。
    """
    task_id: Optional[str] = None
    test_case_id: Optional[str] = None
    round_number: Optional[int] = None
    success: Optional[bool] = None
    audio_timelines: Any = None
    result_data: Any = None
    error_message: Optional[str] = None


@dataclass
class DriverScanDTO:
    """设备扫描结果 DTO"""
    device_id: Optional[int] = None
    device_name: Optional[str] = None
    system: Optional[str] = None
    keywords: Optional[str] = None
    serial_number: Optional[str] = None
    ip: Optional[str] = None
    status: Optional[str] = None
    extra: Any = None


@dataclass
class PhysicalDeviceDTO:
    """物理播放设备 DTO"""
    device_index: Optional[int] = None
    device_name: Optional[str] = None
    unique_id: Optional[str] = None
    channels: Optional[int] = None
    extra: Any = None


@dataclass
class PlayStatusDTO:
    """播放状态 DTO"""
    task_id: Optional[str] = None
    is_playing: Optional[bool] = None
    active_players: Any = None
    extra: Any = None


@dataclass
class ReextractResultDTO:
    """重新提取结果 DTO"""
    task_id: Optional[str] = None
    test_case_id: Optional[str] = None
    success: Optional[bool] = None
    result_data: Any = None
    error_message: Optional[str] = None


@dataclass
class RegisteredKeywordsDTO:
    """已注册驱动关键字 DTO"""
    keywords: Any = None


@dataclass
class TaskDeviceDTO:
    """任务-设备关联 DTO"""
    task_id: Optional[int] = None
    device_id: Optional[int] = None
    device_sn: Optional[str] = None
    device_name: Optional[str] = None
    needs_prompt_audio: Optional[bool] = None
    prompt_audio_path: Optional[str] = None
    prompt_audio_name: Optional[str] = None
    extra: Any = None
