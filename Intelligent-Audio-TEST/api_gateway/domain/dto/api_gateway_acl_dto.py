# -*- coding: utf-8 -*-
"""api_gateway ACL DTO 定义。

供 api_gateway/infrastructure/acl 下的仓储使用，将各 config 服务 gRPC
返回的 ``{success, message, data, code}`` 信封中的 ``data`` 负载，以及
audio/playback/spl/device 等只读代理返回的 raw dict/list，转换为 dataclass DTO。

每个 DTO 声明常用类型字段并携带 ``result_data: Any`` 保留原始动态负载，
经 ``shared.utils.dto_utils.dto_to_dict`` 可还原完整 dict。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AudioDTO:
    """音频 DTO（audio_config_service.get_one / get_by_ids / get_by_md5）"""
    id: Optional[int] = None
    name: Optional[str] = None
    file_path: Optional[str] = None
    duration: Optional[float] = None
    audio_type: Optional[str] = None
    sample_rate: Optional[int] = None
    deleted: Optional[bool] = None
    annotations: Any = None
    result_data: Any = None


@dataclass
class AudioInfoDTO:
    """音频信息 DTO（audio_service.get_audio_info）"""
    duration: Optional[float] = None
    audio_type: Optional[str] = None
    sample_rate: Optional[int] = None
    result_data: Any = None


@dataclass
class PhysicalDeviceDTO:
    """物理播放设备 DTO（audio_service.get_all_physical_devices）"""
    device_index: Optional[int] = None
    device_name: Optional[str] = None
    unique_id: Optional[str] = None
    channels: Optional[int] = None
    result_data: Any = None


@dataclass
class PlayStatusDTO:
    """播放状态 DTO（audio_service.active_players）"""
    task_id: Optional[str] = None
    is_playing: Optional[bool] = None
    active_players: Any = None
    result_data: Any = None


@dataclass
class SplMeasureResultDTO:
    """SPL 测量结果 DTO（spl_service.measure_spl）"""
    gain: Optional[float] = None
    spl: Optional[float] = None
    result_data: Any = None


@dataclass
class PlaybackPreviewResultDTO:
    """播放预览/执行结果 DTO（playback_orchestrator.preview / play_round）"""
    task_id: Optional[str] = None
    test_case_id: Optional[str] = None
    round_number: Optional[int] = None
    success: Optional[bool] = None
    audio_timelines: Any = None
    result_data: Any = None


@dataclass
class DeviceDTO:
    """设备 DTO（device_config_service.get_one / get_all）"""
    id: Optional[int] = None
    name: Optional[str] = None
    system: Optional[str] = None
    keywords: Optional[str] = None
    serial_number: Optional[str] = None
    ip: Optional[str] = None
    device_type: Optional[str] = None
    status: Optional[str] = None
    result_data: Any = None


@dataclass
class DriverScanDTO:
    """设备扫描结果 DTO（device_driver_factory._DriverProxy.scan）"""
    device_id: Optional[int] = None
    device_name: Optional[str] = None
    system: Optional[str] = None
    keywords: Optional[str] = None
    serial_number: Optional[str] = None
    ip: Optional[str] = None
    status: Optional[str] = None
    result_data: Any = None


@dataclass
class RegisteredKeywordsDTO:
    """已注册驱动关键字 DTO（device_driver_factory.get_registered_keywords）"""
    keywords: Any = None
    result_data: Any = None


@dataclass
class PlaybackDeviceDTO:
    """播放设备 DTO（playback_config_service.get_one / get_all）"""
    id: Optional[int] = None
    name: Optional[str] = None
    device_type: Optional[str] = None
    serial_number: Optional[str] = None
    ip: Optional[str] = None
    result_data: Any = None


@dataclass
class SplMappingDTO:
    """SPL 映射 DTO（spl_config_service.get_one / get_all）"""
    id: Optional[int] = None
    name: Optional[str] = None
    device_id: Optional[int] = None
    calibration_status: Optional[str] = None
    result_data: Any = None


@dataclass
class ApiConfigDTO:
    """被测 API 配置 DTO（api_config_service.get_one / get_all）"""
    id: Optional[int] = None
    name: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    status: Optional[str] = None
    algorithm_type: Optional[str] = None
    config: Any = None
    result_data: Any = None


@dataclass
class TaskDTO:
    """任务 DTO（task_config_service.list_tasks / get_task_detail）"""
    id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    algorithm_type: Optional[str] = None
    config: Any = None
    result_data: Any = None


@dataclass
class TestCaseDTO:
    """测试用例 DTO（testcase_config_service.list_testcases / get_testcase_detail）"""
    id: Optional[int] = None
    name: Optional[str] = None
    test_type: Optional[str] = None
    algorithm_type: Optional[str] = None
    config: Any = None
    result_data: Any = None


@dataclass
class TagCategoryDTO:
    """标签分类 DTO（tag_config_service.list_categories / get_category）"""
    id: Optional[int] = None
    name: Optional[str] = None
    result_data: Any = None


@dataclass
class TagDTO:
    """标签 DTO（tag_config_service.list_tags / get_tag）"""
    id: Optional[int] = None
    name: Optional[str] = None
    category_id: Optional[int] = None
    result_data: Any = None


@dataclass
class AlgorithmDTO:
    """算法 DTO（algorithm_config_service.list_algorithms / get_algorithm）"""
    algorithm_type: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    group_id: Optional[int] = None
    result_data: Any = None


@dataclass
class AlgorithmGroupDTO:
    """算法分组 DTO（algorithm_config_service.list_groups / get_group）"""
    id: Optional[int] = None
    name: Optional[str] = None
    result_data: Any = None


@dataclass
class ParamDTO:
    """算法参数 DTO（algorithm_config_service.list_params / get_param）"""
    id: Optional[int] = None
    param_code: Optional[str] = None
    field_path: Optional[str] = None
    field_type: Optional[str] = None
    param_type: Optional[str] = None
    result_data: Any = None


@dataclass
class DimensionDTO:
    """维度 DTO（evaluation_config_service.list_dimensions / get_dimension_by_ids）"""
    id: Optional[int] = None
    name: Optional[str] = None
    weight: Optional[float] = None
    score_unit: Optional[str] = None
    decimal_places: Optional[int] = None
    statistic_method: Optional[str] = None
    status: Optional[bool] = None
    category_id: Optional[int] = None
    result_data: Any = None


# ==================== runtime / 执行类 DTO ====================


@dataclass
class ExecutionResultDTO:
    """任务执行结果 DTO（execution_engine.start_task / control_task / remove_from_queue）"""
    success: Optional[bool] = None
    message: Optional[str] = None
    result_data: Any = None


@dataclass
class ReevaluationResultDTO:
    """重新评估结果 DTO（_ReevaluationExecutorProxy.submit / _reevaluate_multi_round / _reevaluate_single）"""
    success: Optional[bool] = None
    message: Optional[str] = None
    result_data: Any = None


@dataclass
class DeviceIndexDTO:
    """物理设备索引 DTO（audio_service.get_device_index）"""
    device_index: Optional[int] = None
    result_data: Any = None


@dataclass
class AudioCommandResultDTO:
    """音频命令结果 DTO（audio_service.play_audio / stop_task_audio_by_pattern）"""
    success: Optional[bool] = None
    result_data: Any = None


@dataclass
class SplGainDTO:
    """SPL 转增益结果 DTO（spl_service.spl_to_gain）"""
    gain: Optional[float] = None
    result_data: Any = None


@dataclass
class SplCommandResultDTO:
    """SPL 命令结果 DTO（spl_service.start_spl / stop_spl）"""
    success: Optional[bool] = None
    result_data: Any = None


@dataclass
class PlaybackCommandResultDTO:
    """播放命令结果 DTO（playback_orchestrator.play_voiceprint）"""
    success: Optional[bool] = None
    result_data: Any = None


@dataclass
class CommandResultDTO:
    """通用命令结果 DTO，封装 gRPC 信封 {success, message, data, code}。

    供所有 ACL 仓储方法返回，应用服务通过属性访问替代 dict.get()。
    兼容 dict-like .get() 调用以简化迁移。
    """
    success: bool = False
    message: Optional[str] = None
    data: Any = None
    code: Optional[int] = None

    def get(self, key, default=None):
        """Dict-like access for backward compatibility with .get() calls."""
        val = getattr(self, key, None)
        return val if val is not None else default
