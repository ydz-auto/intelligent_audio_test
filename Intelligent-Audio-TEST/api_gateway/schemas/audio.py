from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, Union
from pydantic import BeforeValidator, Field, field_validator

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData
from api_gateway.schemas.testcase import AlgorithmParamItem, RoundConfigItem


class TagListData(PaginatedData[str]):
    """音频标签名列表（INT-297 信封统一）"""


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
    # INT-423/466：资源可见性与归属人（前端徽标 + 路由层 owner 校验）
    visibility: Optional[str] = Field(None)
    created_by_user_id: Optional[int] = Field(None)


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
    # 分片大小（字节），默认 5MB：这是 OSS Multipart 的分片长度（S3 协议要求
    # 除末片外每片 ≥5MiB），分片内容由浏览器直传 OSS，不经网关→audio_service
    # 的 gRPC 通道，故不受 gRPC 报文上限约束（与 INT-1522 的分片上传路径不同）。
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
    # case 级背景噪声（rounds 外层），优先级高于轮次级 background_noise
    background_noise: Optional[Any] = Field(None)


class MergeChunksRequest(APIModel):
    file_id: str = Field(...)
    task_id: str = Field(...)
    create_test_case: Optional[bool] = Field(False)
    # 前端直传 OSS 模式：非 WAV 文件分片直传 raw-chunks bucket 后，merge 从 OSS 拉取
    oss_upload_id: Optional[str] = Field(None)
    oss_key: Optional[str] = Field(None)
    oss_parts: Optional[List[Dict]] = Field(None)
    is_direct_oss: Optional[bool] = Field(False)
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
    """格式转换请求（INT-782 附加参数：目标采样率/声道数/位深度/比特率）。

    全部附加参数可选，不传时保持原行为（仅转换格式）。支持范围见
    接口实现文档 AudioImport §1.5：校验采样率/声道数/位深在支持范围内。
    """
    format: str = Field(...)
    sample_rate: Optional[int] = Field(None, description='目标采样率 (Hz)，支持 8000-192000')
    channels: Optional[int] = Field(None, description='目标声道数，支持 1-8')
    bit_depth: Optional[int] = Field(None, description='目标位深度 (bit)，支持 8/16/24/32')
    bitrate: Optional[Union[int, str]] = Field(None, description='目标比特率 (kbps)，如 128 或 "128k"')

    @field_validator('sample_rate')
    def _check_sample_rate(cls, v):
        if v is not None and not (8000 <= v <= 192000):
            raise ValueError('目标采样率需在 8000-192000 Hz 范围内')
        return v

    @field_validator('channels')
    def _check_channels(cls, v):
        if v is not None and not (1 <= v <= 8):
            raise ValueError('目标声道数需在 1-8 之间')
        return v

    @field_validator('bit_depth')
    def _check_bit_depth(cls, v):
        if v is not None and v not in (8, 16, 24, 32):
            raise ValueError('目标位深度仅支持 8/16/24/32 bit')
        return v

    @field_validator('bitrate', mode='before')
    def _check_bitrate(cls, v):
        if v is None:
            return v
        if isinstance(v, bool):
            raise ValueError('目标比特率不能为布尔值')
        if isinstance(v, (int, float)):
            if v <= 0:
                raise ValueError('目标比特率需为正整数 (kbps)')
            return int(v)
        s = str(v).strip().lower()
        # 纯数字按 kbps 解释；允许 k/m 后缀（如 "128k"、"1m"）
        body = s[:-1] if s and s[-1] in 'km' else s
        if not body.replace('.', '', 1).isdigit():
            raise ValueError('目标比特率需为数字或以 k/m 结尾的数值字符串 (kbps)')
        return s


class AudioProcessRequest(APIModel):
    """音频处理请求（INT-820 §3.3.2 处理：降噪/增益/剪辑）。

    mode 默认 new：生成新文件并创建新音频记录；overwrite：更新原记录 file_path。
    """
    operation: str = Field(...)
    mode: Optional[str] = Field('new')
    gain_db: Optional[float] = Field(0.0)
    start_ms: Optional[int] = Field(0)
    end_ms: Optional[int] = Field(None)


class BatchActionRequest(APIModel):
    audio_ids: List[int] = Field(...)
    action: str = Field(...)
    tags: Optional[List[str]] = Field(default_factory=list)
    # INT-818：批量移动/复制/重命名/改属性扩展字段（React 弹窗 targetFolder /
    # renameRule / property 语义一一对应；旧 Vue extraParams 透传兼容——
    # extra="ignore" 下未声明字段不报错，camelCase 由 alias_generator 同时接受）
    target_folder: Optional[str] = Field(None, description='move/copy 目标文件夹（如 test_data/dry）')
    rename_rule: Optional[str] = Field(None, description='rename 统一命名规则前缀（自动追加序号）')
    property: Optional[str] = Field(None, description='modify-properties 属性名（metadata / audio-type / spl）')
    property_value: Optional[Any] = Field(None, description='modify-properties 属性值（metadata 为字段字典，audio-type 为类型值）')


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


class PlaybackHistoryItem(APIModel):
    """音频播放历史条目（INT-782#2；字段与 React audio-playback-history-dialog 期望一致）"""
    id: int = Field(...)
    audio_id: int = Field(...)
    testcase_id: Optional[str] = Field(None)
    testcase_name: Optional[str] = Field(None)
    device_id: Optional[str] = Field(None)
    device_name: str = Field(...)
    result: str = Field('success')
    duration: Optional[float] = Field(None)
    source: str = Field('preview')
    played_at: Optional[str] = Field(None)


class PlaybackHistoryListData(PaginatedData[PlaybackHistoryItem]):
    """播放历史分页列表（INT-297 信封统一）"""


class PlaybackHistoryQuery(APIModel):
    """播放历史分页查询参数"""
    page: int = Field(1)
    per_page: int = Field(10)


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


def _normalize_tags_param(value):
    """tags 入参归一化（INT-1525）。

    GET 单值（tags=a）经 query 取值后是 str，POST 既可能是 str 列表也可能是
    `{name, mode}` dict 列表；统一交给 Pydantic 按 `List[Union[str, dict]]` 校验，
    避免单值 str 在 List[str] 上直接 422。
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return value


TagsFilter = Annotated[
    Optional[List[Union[str, Dict[str, Any]]]],
    BeforeValidator(_normalize_tags_param),
]


class AudioListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    keyword: Optional[str] = Field(None)
    format: Optional[str] = Field(None)
    audio_type: Optional[str] = Field(None)
    folder: Optional[str] = Field(None)
    sample_rate: Optional[str] = Field(None)
    duration: Optional[str] = Field(None)
    tags: TagsFilter = Field(default_factory=list)
    direction: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)


class AudioIdQuery(APIModel):
    keyword: Optional[str] = Field(None)
    format: Optional[str] = Field(None)
    audio_type: Optional[str] = Field(None)
    sample_rate: Optional[str] = Field(None)
    duration: Optional[str] = Field(None)
    tags: TagsFilter = Field(default_factory=list)
    direction: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)


class AudioStreamQuery(APIModel):
    task_type: str = Field('api')


class AudioStreamByPathQuery(APIModel):
    path: str = Field(...)


class AudioDownloadQuery(APIModel):
    """本地存储降级模式的音频下载参数（stream 预签名回退地址）"""
    # path 缺失时由 service 手动返回 400（避免 schema 直接抛 500）
    path: Optional[str] = Field('')


class AudioUploadProgressQuery(APIModel):
    task_id: Optional[str] = Field(None)


class AudioPresignPartQuery(APIModel):
    oss_key: Optional[str] = Field(None)
    category: str = Field('raw_chunks')
