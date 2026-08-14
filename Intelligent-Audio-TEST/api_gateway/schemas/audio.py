from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData
from api_gateway.schemas.testcase import AlgorithmParamItem, RoundConfigItem


class TagListData(APIModel):
    items: List[str] = Field(...)
    total: int = Field(...)


class AudioItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    original_filename: Optional[str] = Field(None)
    file_path: Optional[str] = Field(None)
    duration: Optional[float] = Field(None)
    size: Optional[int] = Field(None)
    sample_rate: Optional[float] = Field(None)
    channels: Optional[int] = Field(None)
    bitrate: Optional[int] = Field(None)
    format: Optional[str] = Field(None)
    audio_type: Optional[str] = Field(None)
    asr_text: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    source_language: Optional[str] = Field(None)
    tags: List[str] = Field(default_factory=list)
    annotations: List[Dict] = Field(default_factory=list)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class AudioListStats(APIModel):
    total_files: int = Field(...)
    total_size: str = Field(...)
    total_duration: str = Field(...)
    today_uploads: int = Field(...)


class AudioListData(PaginatedData[AudioItem]):
    stats: AudioListStats = Field(...)


class AudioIdsData(APIModel):
    ids: List[int] = Field(...)
    total: int = Field(...)


class InitUploadTaskRequest(APIModel):
    pass


# ========== 前端直传 OSS 相关 schemas ==========

class PresignUploadRequest(APIModel):
    """请求预签名上传 URL（前端直传 OSS）"""
    filename: str = Field(...)
    file_size: int = Field(0)
    md5: Optional[str] = Field(None)
    # 分片大小（字节），默认 5MB（S3 最小分片大小）
    chunk_size: Optional[int] = Field(5 * 1024 * 1024)
    # 是否是 WAV（WAV 直传 audios bucket，非 WAV 传 raw-chunks bucket）
    is_wav: Optional[bool] = Field(False)
    # 原始目录结构（来自浏览器 webkitRelativePath），用于保留本地目录结构
    # 如 "test_data/noise/sample.wav"，OSS key 会存成 "direct/test_data/noise/sample.wav"
    relative_path: Optional[str] = Field(None)


class PresignPartRequest(APIModel):
    """请求单个分片的预签名上传 URL"""
    upload_id: str = Field(...)
    part_number: int = Field(...)


class CompleteDirectUploadRequest(APIModel):
    """前端直传完成后登记 DB（WAV 场景，无需后端转码）"""
    oss_key: str = Field(...)
    upload_id: Optional[str] = Field(None)
    parts: Optional[List[Dict]] = Field(default_factory=list)
    filename: str = Field(...)
    md5: Optional[str] = Field(None)
    file_size: int = Field(0)
    sample_rate: Optional[int] = Field(44100)
    bits_per_sample: Optional[int] = Field(16)
    duration: Optional[float] = Field(0.0)
    # 测试用例相关（同 MergeChunksRequest 的部分字段）
    tags: Optional[List[str]] = Field(default_factory=list)
    audio_type: Optional[str] = Field('dry')
    asr_text: Optional[str] = Field('')


class RegisterUploadFileRequest(APIModel):
    task_id: str = Field(...)
    files: Optional[List[Dict]] = Field(default_factory=list)


class AudioAlgorithmRelationItem(APIModel):
    algorithm_type: str = Field(...)
    is_primary: bool = Field(default=False)
    weight: float = Field(default=1.0)
    params: Optional[Dict] = Field(default=None)


class TestCaseUploadConfig(APIModel):
    """上传时携带的测试用例配置，支持多轮 rounds 架构。

    字段全部 optional，不传时由 _create_test_case_from_audio 降级为平面 config。
    """
    rounds: Optional[List[RoundConfigItem]] = Field(None)
    # dimensions 接受 dict 或 list，由 _create_test_case_from_audio 统一处理
    dimensions: Optional[Any] = Field(None)
    group_name: Optional[str] = Field(None)
    inherit_tags: Optional[bool] = Field(True)
    # 算法参数：接受 list（标准 [{field_code, field_value}]）或 dict（{field_code: field_value}），由 controller 归一化
    algorithm_params: Optional[Any] = Field(None)


class MergeChunksRequest(APIModel):
    file_id: str = Field(...)
    task_id: str = Field(...)
    create_test_case: Optional[bool] = Field(False)
    # 前端直传 OSS 模式：非 WAV 文件分片直传 raw-chunks bucket 后，merge 从 OSS 拉取
    oss_upload_id: Optional[str] = Field(None)
    oss_key: Optional[str] = Field(None)
    oss_parts: Optional[List[Dict]] = Field(None)
    is_direct_oss: Optional[bool] = Field(False)
    test_types: Optional[List[str]] = Field(default_factory=lambda: ['api'])
    # dimensions 接受 dict 或 list，由 _create_test_case_from_audio 统一处理
    dimensions: Optional[Any] = Field(default_factory=dict)
    default_playback_device_id: Optional[int] = Field(None)
    default_spl: Optional[float] = Field(65.0)
    noise_spl: Optional[float] = Field(60.0)
    noise_audio_id: Optional[int] = Field(None)
    test_case_group_name: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    # algorithm_params 接受 list 或 dict，由 controller 归一化
    algorithm_params: Optional[Any] = Field(None)
    algorithm_relations: Optional[List[AudioAlgorithmRelationItem]] = Field(None)
    description: Optional[str] = Field('')
    tags: Optional[List[str]] = Field(default_factory=list)
    prompt_device_id: Optional[int] = Field(None)
    prompt_source_language: Optional[str] = Field(None)
    prompt_target_language: Optional[str] = Field(None)
    prompt_translation_direction: Optional[str] = Field(None)
    prompt_algorithm_type: Optional[str] = Field(None)
    annotations: Optional[List[Dict]] = Field(default_factory=list)
    audio_type: Optional[str] = Field('dry')
    asr_text: Optional[str] = Field('')
    playback_device_id: Optional[int] = Field(None)
    group_name_type: Optional[str] = Field('root')
    custom_group_name: Optional[str] = Field('')
    inherit_tags: Optional[bool] = Field(True)
    # 多轮上传配置：前端解析文件夹后构建的完整 rounds 配置
    test_case_config: Optional[TestCaseUploadConfig] = Field(None)

    def get_algorithm_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        """归一化算法参数为 [{field_code, field_value}] 列表格式。

        接受两种输入：
        - list: [{field_code, field_value}, ...] 或 [AlgorithmParamItem, ...]
        - dict: {field_code: field_value, ...}
        """
        if not self.algorithm_params:
            return None
        ap = self.algorithm_params
        # dict 格式：{field_code: field_value}
        if isinstance(ap, dict):
            return [{'field_code': k, 'field_value': v} for k, v in ap.items()]
        # list 格式
        if isinstance(ap, list):
            result = []
            for item in ap:
                if hasattr(item, 'model_dump'):
                    result.append(item.model_dump())
                elif isinstance(item, dict):
                    # 兼容 {field_code, field_value} 和 {fieldCode, fieldValue}
                    fc = item.get('field_code') or item.get('fieldCode')
                    fv = item.get('field_value', item.get('fieldValue'))
                    if fc is not None:
                        result.append({'field_code': fc, 'field_value': fv})
                    else:
                        result.append(item)
            return result if result else None
        return None


class URLImportRequest(APIModel):
    url: str = Field(...)
    relative_path: Optional[str] = Field(None)
    audio_type: Optional[str] = Field('dry')


class ConvertFormatRequest(APIModel):
    format: str = Field(...)


class BatchActionRequest(APIModel):
    audio_ids: List[int] = Field(...)
    action: str = Field(...)
    tags: Optional[List[str]] = Field(default_factory=list)


class BatchPlaybackRequest(APIModel):
    playback_device_id: Optional[int] = Field(None)
    playback_device_ids: Optional[List[int]] = Field(None)
    device_unique_ids: Optional[List[str]] = Field(None)
    spl: Optional[float] = Field(None)
    offset: Optional[float] = Field(0)


class UpdateMetadataRequest(APIModel):
    name: Optional[str] = Field(None)
    audio_type: Optional[str] = Field(None)
    asr_text: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    source_language: Optional[str] = Field(None)
    tags: Optional[str] = Field(None)
    annotations: Optional[List[Dict]] = Field(default_factory=list)


class AudioItemWithAlgorithms(AudioItem):
    algorithms: List[AudioAlgorithmRelationItem] = Field(default_factory=list)


class UpdateAudioAlgorithmsRequest(APIModel):
    algorithms: List[AudioAlgorithmRelationItem] = Field(...)


class BatchUpdateAudioAlgorithmsRequest(APIModel):
    audio_ids: List[int] = Field(...)
    algorithms: List[AudioAlgorithmRelationItem] = Field(...)


class BatchAnnotationItem(APIModel):
    audio_id: int = Field(...)
    annotations: List[Dict] = Field(default_factory=list)


class BatchUpdateAnnotationsRequest(APIModel):
    items: List[BatchAnnotationItem] = Field(default_factory=list)
    algorithm_type: Optional[str] = Field(None)
    refresh_test_cases: Optional[bool] = Field(True)
