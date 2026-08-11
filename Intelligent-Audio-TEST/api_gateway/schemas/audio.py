from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData
from api_gateway.schemas.testcase import AlgorithmParamItem, RoundConfigItem


class TagListData(APIModel):
    items: List[str] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


class AudioItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    original_filename: Optional[str] = Field(None, alias='originalFilename', validation_alias='originalFilename')
    file_path: Optional[str] = Field(None, alias='filePath', validation_alias='filePath')
    duration: Optional[float] = Field(None, alias='duration', validation_alias='duration')
    size: Optional[int] = Field(None, alias='size', validation_alias='size')
    sample_rate: Optional[float] = Field(None, alias='sampleRate', validation_alias='sampleRate')
    channels: Optional[int] = Field(None, alias='channels', validation_alias='channels')
    bitrate: Optional[int] = Field(None, alias='bitrate', validation_alias='bitrate')
    format: Optional[str] = Field(None, alias='format', validation_alias='format')
    audio_type: Optional[str] = Field(None, alias='audioType', validation_alias='audioType')
    asr_text: Optional[str] = Field(None, alias='asrText', validation_alias='asrText')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    source_language: Optional[str] = Field(None, alias='sourceLanguage', validation_alias='sourceLanguage')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')
    annotations: List[Dict] = Field(default_factory=list, alias='annotations', validation_alias='annotations')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class AudioListStats(APIModel):
    total_files: int = Field(..., alias='totalFiles', validation_alias='totalFiles')
    total_size: str = Field(..., alias='totalSize', validation_alias='totalSize')
    total_duration: str = Field(..., alias='totalDuration', validation_alias='totalDuration')
    today_uploads: int = Field(..., alias='todayUploads', validation_alias='todayUploads')


class AudioListData(PaginatedData[AudioItem]):
    stats: AudioListStats = Field(..., alias='stats', validation_alias='stats')


class AudioIdsData(APIModel):
    ids: List[int] = Field(..., alias='ids', validation_alias='ids')
    total: int = Field(..., alias='total', validation_alias='total')


class InitUploadTaskRequest(APIModel):
    pass


# ========== 前端直传 OSS 相关 schemas ==========

class PresignUploadRequest(APIModel):
    """请求预签名上传 URL（前端直传 OSS）"""
    filename: str = Field(..., alias='filename', validation_alias='filename')
    file_size: int = Field(0, alias='fileSize', validation_alias='fileSize')
    md5: Optional[str] = Field(None, alias='md5', validation_alias='md5')
    # 分片大小（字节），默认 5MB（S3 最小分片大小）
    chunk_size: Optional[int] = Field(5 * 1024 * 1024, alias='chunkSize', validation_alias='chunkSize')
    # 是否是 WAV（WAV 直传 audios bucket，非 WAV 传 raw-chunks bucket）
    is_wav: Optional[bool] = Field(False, alias='isWav', validation_alias='isWav')
    # 原始目录结构（来自浏览器 webkitRelativePath），用于保留本地目录结构
    # 如 "test_data/noise/sample.wav"，OSS key 会存成 "direct/test_data/noise/sample.wav"
    relative_path: Optional[str] = Field(None, alias='relativePath', validation_alias='relativePath')


class PresignPartRequest(APIModel):
    """请求单个分片的预签名上传 URL"""
    upload_id: str = Field(..., alias='uploadId', validation_alias='uploadId')
    part_number: int = Field(..., alias='partNumber', validation_alias='partNumber')


class CompleteDirectUploadRequest(APIModel):
    """前端直传完成后登记 DB（WAV 场景，无需后端转码）"""
    oss_key: str = Field(..., alias='ossKey', validation_alias='ossKey')
    upload_id: Optional[str] = Field(None, alias='uploadId', validation_alias='uploadId')
    parts: Optional[List[Dict]] = Field(default_factory=list, alias='parts', validation_alias='parts')
    filename: str = Field(..., alias='filename', validation_alias='filename')
    md5: Optional[str] = Field(None, alias='md5', validation_alias='md5')
    file_size: int = Field(0, alias='fileSize', validation_alias='fileSize')
    sample_rate: Optional[int] = Field(44100, alias='sampleRate', validation_alias='sampleRate')
    bits_per_sample: Optional[int] = Field(16, alias='bitsPerSample', validation_alias='bitsPerSample')
    duration: Optional[float] = Field(0.0, alias='duration', validation_alias='duration')
    # 测试用例相关（同 MergeChunksRequest 的部分字段）
    tags: Optional[List[str]] = Field(default_factory=list, alias='tags', validation_alias='tags')
    audio_type: Optional[str] = Field('dry', alias='audioType', validation_alias='audioType')
    asr_text: Optional[str] = Field('', alias='asrText', validation_alias='asrText')


class RegisterUploadFileRequest(APIModel):
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    files: Optional[List[Dict]] = Field(default_factory=list, alias='files', validation_alias='files')


class AudioAlgorithmRelationItem(APIModel):
    algorithm_type: str = Field(..., alias='algorithmType', validation_alias='algorithmType')
    is_primary: bool = Field(default=False, alias='isPrimary', validation_alias='isPrimary')
    weight: float = Field(default=1.0)
    params: Optional[Dict] = Field(default=None)


class TestCaseUploadConfig(APIModel):
    """上传时携带的测试用例配置，支持多轮 rounds 架构。

    字段全部 optional，不传时由 _create_test_case_from_audio 降级为平面 config。
    """
    rounds: Optional[List[RoundConfigItem]] = Field(None, alias='rounds', validation_alias='rounds')
    # dimensions 接受 dict 或 list，由 _create_test_case_from_audio 统一处理
    dimensions: Optional[Any] = Field(None, alias='dimensions', validation_alias='dimensions')
    group_name: Optional[str] = Field(None, alias='groupName', validation_alias='groupName')
    inherit_tags: Optional[bool] = Field(True, alias='inheritTags', validation_alias='inheritTags')
    # 算法参数：接受 list（标准 [{field_code, field_value}]）或 dict（{field_code: field_value}），由 controller 归一化
    algorithm_params: Optional[Any] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')


class MergeChunksRequest(APIModel):
    file_id: str = Field(..., alias='fileId', validation_alias='fileId')
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    create_test_case: Optional[bool] = Field(False, alias='createTestCase', validation_alias='createTestCase')
    # 前端直传 OSS 模式：非 WAV 文件分片直传 raw-chunks bucket 后，merge 从 OSS 拉取
    oss_upload_id: Optional[str] = Field(None, alias='ossUploadId', validation_alias='ossUploadId')
    oss_key: Optional[str] = Field(None, alias='ossKey', validation_alias='ossKey')
    oss_parts: Optional[List[Dict]] = Field(None, alias='ossParts', validation_alias='ossParts')
    is_direct_oss: Optional[bool] = Field(False, alias='isDirectOss', validation_alias='isDirectOss')
    test_types: Optional[List[str]] = Field(default_factory=lambda: ['api'], alias='testTypes', validation_alias='testTypes')
    # dimensions 接受 dict 或 list，由 _create_test_case_from_audio 统一处理
    dimensions: Optional[Any] = Field(default_factory=dict, alias='dimensions', validation_alias='dimensions')
    default_playback_device_id: Optional[int] = Field(None, alias='defaultPlaybackDeviceId', validation_alias='defaultPlaybackDeviceId')
    default_spl: Optional[float] = Field(65.0, alias='defaultSpl', validation_alias='defaultSpl')
    noise_spl: Optional[float] = Field(60.0, alias='noiseSpl', validation_alias='noiseSpl')
    noise_audio_id: Optional[int] = Field(None, alias='noiseAudioId', validation_alias='noiseAudioId')
    test_case_group_name: Optional[str] = Field(None, alias='testCaseGroupName', validation_alias='testCaseGroupName')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    # algorithm_params 接受 list 或 dict，由 controller 归一化
    algorithm_params: Optional[Any] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
    algorithm_relations: Optional[List[AudioAlgorithmRelationItem]] = Field(None, alias='algorithmRelations', validation_alias='algorithmRelations')
    description: Optional[str] = Field('', alias='description', validation_alias='description')
    tags: Optional[List[str]] = Field(default_factory=list, alias='tags', validation_alias='tags')
    prompt_device_id: Optional[int] = Field(None, alias='promptDeviceId', validation_alias='promptDeviceId')
    prompt_source_language: Optional[str] = Field(None, alias='promptSourceLanguage', validation_alias='promptSourceLanguage')
    prompt_target_language: Optional[str] = Field(None, alias='promptTargetLanguage', validation_alias='promptTargetLanguage')
    prompt_translation_direction: Optional[str] = Field(None, alias='promptTranslationDirection', validation_alias='promptTranslationDirection')
    prompt_algorithm_type: Optional[str] = Field(None, alias='promptAlgorithmType', validation_alias='promptAlgorithmType')
    annotations: Optional[List[Dict]] = Field(default_factory=list, alias='annotations', validation_alias='annotations')
    audio_type: Optional[str] = Field('dry', alias='audioType', validation_alias='audioType')
    asr_text: Optional[str] = Field('', alias='asrText', validation_alias='asrText')
    playback_device_id: Optional[int] = Field(None, alias='playbackDeviceId', validation_alias='playbackDeviceId')
    group_name_type: Optional[str] = Field('root', alias='groupNameType', validation_alias='groupNameType')
    custom_group_name: Optional[str] = Field('', alias='customGroupName', validation_alias='customGroupName')
    inherit_tags: Optional[bool] = Field(True, alias='inheritTags', validation_alias='inheritTags')
    # 多轮上传配置：前端解析文件夹后构建的完整 rounds 配置
    test_case_config: Optional[TestCaseUploadConfig] = Field(None, alias='testCaseConfig', validation_alias='testCaseConfig')

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
    url: str = Field(..., alias='url', validation_alias='url')
    relative_path: Optional[str] = Field(None, alias='relativePath', validation_alias='relativePath')
    audio_type: Optional[str] = Field('dry', alias='audioType', validation_alias='audioType')


class ConvertFormatRequest(APIModel):
    format: str = Field(..., alias='format', validation_alias='format')


class BatchActionRequest(APIModel):
    audio_ids: List[int] = Field(..., alias='audioIds', validation_alias='audioIds')
    action: str = Field(..., alias='action', validation_alias='action')
    tags: Optional[List[str]] = Field(default_factory=list, alias='tags', validation_alias='tags')


class BatchPlaybackRequest(APIModel):
    playback_device_id: Optional[int] = Field(None, alias='playbackDeviceId', validation_alias='playbackDeviceId')
    playback_device_ids: Optional[List[int]] = Field(None, alias='playbackDeviceIds', validation_alias='playbackDeviceIds')
    device_unique_ids: Optional[List[str]] = Field(None, alias='deviceUniqueIds', validation_alias='deviceUniqueIds')
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    offset: Optional[float] = Field(0, alias='offset', validation_alias='offset')


class UpdateMetadataRequest(APIModel):
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    audio_type: Optional[str] = Field(None, alias='audioType', validation_alias='audioType')
    asr_text: Optional[str] = Field(None, alias='asrText', validation_alias='asrText')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    source_language: Optional[str] = Field(None, alias='sourceLanguage', validation_alias='sourceLanguage')
    tags: Optional[str] = Field(None, alias='tags', validation_alias='tags')
    annotations: Optional[List[Dict]] = Field(default_factory=list, alias='annotations', validation_alias='annotations')


class AudioItemWithAlgorithms(AudioItem):
    algorithms: List[AudioAlgorithmRelationItem] = Field(default_factory=list, alias='algorithms', validation_alias='algorithms')


class UpdateAudioAlgorithmsRequest(APIModel):
    algorithms: List[AudioAlgorithmRelationItem] = Field(..., alias='algorithms', validation_alias='algorithms')


class BatchUpdateAudioAlgorithmsRequest(APIModel):
    audio_ids: List[int] = Field(..., alias='audioIds', validation_alias='audioIds')
    algorithms: List[AudioAlgorithmRelationItem] = Field(..., alias='algorithms', validation_alias='algorithms')


class BatchAnnotationItem(APIModel):
    audio_id: int = Field(..., alias='audioId', validation_alias='audioId')
    annotations: List[Dict] = Field(default_factory=list, alias='annotations', validation_alias='annotations')


class BatchUpdateAnnotationsRequest(APIModel):
    items: List[BatchAnnotationItem] = Field(default_factory=list, alias='items', validation_alias='items')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    refresh_test_cases: Optional[bool] = Field(True, alias='refreshTestCases', validation_alias='refreshTestCases')

