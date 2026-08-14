from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from pydantic import Field, field_validator, AliasChoices, model_validator, ConfigDict

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class ReportAudioItem(APIModel):
    id: Optional[int] = Field(None)
    filename: Optional[str] = Field(None)
    duration: Optional[float] = Field(None)
    url: Optional[str] = Field(None)
    spl: Optional[float] = Field(None)
    play_order: Optional[int] = Field(None)
    playback_device_id: Optional[int] = Field(None)
    playback_device_name: Optional[str] = Field(None)
    label: Optional[str] = Field(None)
    timeline_start: Optional[float] = Field(None)
    timeline_end: Optional[float] = Field(None)


class ReportTestCaseItem(APIModel):
    id: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    tags: List[Any] = Field(default_factory=list)
    audios: List[ReportAudioItem] = Field(default_factory=list)
    metrics: List[Any] = Field(default_factory=list)
    asr: Optional[Dict[str, Any]] = Field(None)
    translation: Optional[Dict[str, Any]] = Field(None)
    results: List[Any] = Field(default_factory=list)
    logs: Optional[str] = Field(None)

if TYPE_CHECKING:
    pass


class TestCaseAudioConfigItem(APIModel):
    id: Optional[int] = Field(None)
    audio_id: Optional[Union[int, str]] = Field(None)
    audio_name: Optional[str] = Field(None)
    spl: Optional[float] = Field(None)
    playback_device_id: Optional[Union[int, str]] = Field(None)
    playback_device_name: Optional[str] = Field(None)
    play_order: Optional[int] = Field(None)

    @field_validator('spl', mode='before')
    @classmethod
    def _empty_spl_to_none(cls, v):
        if v == '' or v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


class TestCaseBackgroundNoiseItem(APIModel):
    audio_id: Optional[Union[int, str]] = Field(None)
    spl: Optional[float] = Field(None)
    device_ids: Optional[List[Union[int, str]]] = Field(None)
    loop: Optional[bool] = Field(True)


class TestCaseDimensionItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    weight: Optional[float] = Field(None)
    threshold: Optional[float] = Field(None)
    test_type: Optional[str] = Field(None)


class RoundConfigItem(APIModel):
    """单轮配置项 — 只含结构性字段

    算法参数和参考参数不在 config.rounds[] 中：
      - algorithm_params → test_cases.algorithm_params 独立列（按轮分组 [{round_number, params}]）
      - reference_params → test_cases.reference_params 独立列（按轮分组 [{round_number, reference_params_path}]）
    """
    model_config = ConfigDict(extra='allow')

    # === 结构性字段 ===
    round_number: Optional[int] = Field(1)
    audios: Optional[List[TestCaseAudioConfigItem]] = Field(default_factory=list)
    background_noise: Optional[TestCaseBackgroundNoiseItem] = Field(None)
    evaluation: Optional[Dict[str, Any]] = Field(None)


class TestCaseConfig(APIModel):
    """测试用例配置 — 只含结构性配置
    config = { rounds, dimensions, background_noise, source_audio, auto_generated }
    算法参数和参考参数在独立列，不在 config 中
    """
    model_config = ConfigDict(extra='allow')
    rounds: Optional[List[RoundConfigItem]] = Field(default_factory=list)
    dimensions: Optional[List[TestCaseDimensionItem]] = Field(default_factory=list)
    background_noise: Optional[Dict[str, Any]] = Field(None)
    source_audio: Optional[str] = Field(None)
    auto_generated: Optional[bool] = Field(False)


class TestCaseListItem(APIModel):
    id: str = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    group_id: Optional[str] = Field(None)
    group_name: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    tags: List[str] = Field(default_factory=list)
    config: TestCaseConfig = Field(default_factory=TestCaseConfig)
    algorithm_params: Optional[Any] = Field(None)
    reference_params: Optional[Any] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)
    total_duration: Optional[float] = Field(None)


class TestCaseListData(PaginatedData[TestCaseListItem]):
    pass


class TestCaseDimensionBrief(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    type: Optional[str] = Field(None)


class TestCaseDetailData(APIModel):
    id: str = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    group_id: Optional[str] = Field(None)
    group_name: Optional[str] = Field(None)
    group: Optional[Dict[str, Any]] = Field(None)
    type: Optional[str] = Field(None)
    config: TestCaseConfig = Field(default_factory=TestCaseConfig)
    algorithm_params: Optional[Any] = Field(None)
    reference_params: Optional[Any] = Field(None)
    tags: List[str] = Field(default_factory=list)
    audios: List[TestCaseAudioConfigItem] = Field(default_factory=list)
    dimensions: List[TestCaseDimensionBrief] = Field(default_factory=list)
    algorithm_type: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)
    total_duration: Optional[float] = Field(None)


class TestCasePreviewData(APIModel):
    test_case_id: str = Field(...)
    preview_task_id: Optional[str] = Field(None)
    status: str = Field(...)
    message: Optional[str] = Field(None)
    duration: Optional[float] = Field(None)
    playback_mode: Optional[str] = Field('backend')
    audio_id: Optional[Union[int, str]] = Field(None)
    audio_stream_url: Optional[str] = Field(None)
    # 多轮音频连续播放
    audio_stream_urls: Optional[List[str]] = Field(None)


class TestCaseStopPreviewData(APIModel):
    test_case_id: str = Field(...)
    status: str = Field(...)
    message: Optional[str] = Field(None)


class TestCaseStatsData(APIModel):
    total_count: int = Field(...)
    by_group: Dict[str, int] = Field(default_factory=dict)
    recent_updates: List[Dict[str, Any]] = Field(default_factory=list)


class TagListData(APIModel):
    items: List[str] = Field(...)


class TagCategoryItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    color: Optional[str] = Field(None)
    sort_order: int = Field(0)
    tag_count: int = Field(0)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class TagCategoryListData(APIModel):
    items: List[TagCategoryItem] = Field(...)
    total: int = Field(...)


class TagCategoryCreateSchema(APIModel):
    name: str = Field(...)
    description: Optional[str] = Field(None)
    color: Optional[str] = Field(None)
    sort_order: Optional[int] = Field(0)


class TagCategoryUpdateSchema(APIModel):
    id: Optional[int] = Field(None)
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    color: Optional[str] = Field(None)
    sort_order: Optional[int] = Field(None)


class TagItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    color: Optional[str] = Field(None)
    category_id: Optional[int] = Field(None)
    category_name: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class TagDetailListData(APIModel):
    items: List[TagItem] = Field(...)
    total: int = Field(...)


class TagCreateSchema(APIModel):
    name: str = Field(...)
    description: Optional[str] = Field(None)
    color: Optional[str] = Field(None)
    category_id: Optional[int] = Field(None)


class TagUpdateSchema(APIModel):
    id: Optional[int] = Field(None)
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    color: Optional[str] = Field(None)
    category_id: Optional[int] = Field(None)


class TestCaseExportJsonData(APIModel):
    test_cases: List["TestCaseExportItem"] = Field(...)
    exported_at: str = Field(...)
    total_count: int = Field(...)


class TestCaseImportResult(APIModel):
    imported_count: int = Field(...)
    errors: List[Any] = Field(default_factory=list)


class TestCaseExportTagItem(APIModel):
    tag_id: int = Field(...)
    tag_name: str = Field(...)


class TestCaseExportAudioItem(APIModel):
    audio_id: Optional[int] = Field(None)
    audio_name: Optional[str] = Field(None)
    spl: Optional[float] = Field(None)
    playback_device_id: Optional[int] = Field(None)
    playback_device_name: Optional[str] = Field(None)
    play_order: Optional[int] = Field(None)


class TestCaseExportItem(APIModel):
    id: str = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    group: Optional[str] = Field(None)
    group_id: Optional[str] = Field(None)
    tags: List[str] = Field(default_factory=list)
    tag_items: List[TestCaseExportTagItem] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    dimension_ids: List[int] = Field(default_factory=list)
    playback_devices: List[str] = Field(default_factory=list)
    audios: List[TestCaseExportAudioItem] = Field(default_factory=list)
    audio_details: Optional[str] = Field(None)
    noise_name: Optional[str] = Field(None)
    noise_spl: Optional[Any] = Field(None)
    noise_audio_id: Optional[int] = Field(None)
    config: Dict[str, Any] = Field(default_factory=dict)
    raw_config: Optional[str] = Field(None)


class TestCaseAudioConfigRequest(APIModel):
    audio_id: Optional[int] = Field(None)
    spl: Optional[float] = Field(None)
    playback_device_id: Optional[int] = Field(None)
    play_order: Optional[int] = Field(None)


class TestCaseBackgroundNoiseRequest(APIModel):
    audio_id: Optional[int] = Field(None)
    spl: Optional[float] = Field(None)
    device_ids: Optional[List[Union[int, str]]] = Field(None)


class TestCaseDimensionItemRequest(APIModel):
    id: Optional[int] = Field(None)
    name: Optional[str] = Field(None)
    display_name: Optional[str] = Field(None)
    weight: Optional[float] = Field(None)
    threshold: Optional[float] = Field(None)


class AlgorithmParamItem(APIModel):
    """算法参数项 — {field_code, field_value}

    field_value 类型由 case_algorithm_params 表的 param_type 定义决定，
    Schema 层不限制具体类型，支持 str/int/float/bool/list/dict 等。
    """
    model_config = ConfigDict(extra='allow')

    field_code: Optional[str] = Field(None)
    field_value: Optional[Any] = Field(None)

    @staticmethod
    def convert_params(params) -> Optional[List['AlgorithmParamItem']]:
        if not params:
            return None
        if isinstance(params, list):
            result = []
            for item in params:
                if isinstance(item, dict):
                    field_value = item.get('field_value')
                    result.append(AlgorithmParamItem(
                        field_code=item.get('field_code'),
                        field_value=field_value
                    ))
                elif isinstance(item, AlgorithmParamItem):
                    result.append(item)
            return result if result else None
        elif isinstance(params, dict):
            result = []
            for key, value in params.items():
                result.append(AlgorithmParamItem(
                    field_code=key,
                    field_value=value
                ))
            return result if result else None
        return params


class ReferenceParamItem(APIModel):
    model_config = ConfigDict(extra='allow')

    code: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    value: Optional[Union[str, Dict[str, Any], List[Any]]] = Field(None)
    annotation_code: Optional[str] = Field(None)
    annotation_format: Optional[str] = Field(None)

    @staticmethod
    def convert_params(params) -> Optional[List['ReferenceParamItem']]:
        if not params:
            return None
        if isinstance(params, list):
            result = []
            for item in params:
                if isinstance(item, dict):
                    result.append(ReferenceParamItem(
                        code=item.get('code'),
                        type=item.get('type'),
                        value=item.get('value'),
                        annotation_code=item.get('annotation_code'),
                        annotation_format=item.get('annotation_format')
                    ))
                elif isinstance(item, ReferenceParamItem):
                    result.append(item)
            return result if result else None
        return params


class TestCaseCreateSchema(APIModel):
    name: str = Field(..., validation_alias=AliasChoices('name', 'caseName', 'case_name'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('description', 'Description'))
    group_id: Optional[str] = Field(None, validation_alias=AliasChoices('group_id', 'groupId'))
    group: Optional[str] = Field(None)
    test_type: Optional[str] = Field('api')
    config: Optional[Dict[str, Any]] = Field(None)
    tags: Optional[List[str]] = Field(None)
    background_noise_id: Optional[int] = Field(None)
    background_noise_spl: Optional[float] = Field(None)
    audios: Optional[List[TestCaseAudioConfigRequest]] = Field(None)
    dimensions: Optional[Any] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    # 按轮分组：[{round_number, params:[{field_code, field_value}]}]，兼容旧平面格式 [{field_code, field_value}]
    algorithm_params: Optional[Any] = Field(None)
    # 按轮分组：[{round_number, reference_params_path}]，兼容旧格式
    reference_params: Optional[Any] = Field(None)

    @field_validator('algorithm_params', mode='before')
    @classmethod
    def coerce_dict_to_list(cls, v):
        if isinstance(v, dict):
            # 旧 dict 格式 → 平面 list（向后兼容）
            return [
                {'field_code': k, 'field_value': val}
                for k, val in v.items()
            ]
        return v

    def get_algorithm_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        """返回按轮分组的 algorithm_params

        新格式：[{round_number, params:[{field_code, field_value}]}]
        旧格式（平面 [{field_code, field_value}]）会被包装为 round_number=1 的单轮
        """
        if not self.algorithm_params:
            return None
        # 检测格式：新格式第一个元素有 round_number 键
        if isinstance(self.algorithm_params, list) and self.algorithm_params:
            first = self.algorithm_params[0]
            if isinstance(first, dict) and 'round_number' in first:
                # 新格式，直接返回
                return self.algorithm_params
            if isinstance(first, dict) and 'params' in first and 'field_code' not in first:
                # 新格式（params 键）
                return self.algorithm_params
        # 旧格式（平面 [{field_code, field_value}]） → 包装为 round_number=1
        result = []
        for p in self.algorithm_params:
            if isinstance(p, dict):
                item = dict(p)
                # field_value 保持原始类型（list/dict/str/number）
                result.append(item)
        if result:
            return [{'round_number': 1, 'params': result}]
        return None

    def get_reference_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        """返回按轮分组的 reference_params"""
        if not self.reference_params:
            return None
        if isinstance(self.reference_params, list):
            return self.reference_params
        return None


class TestCasePreviewRequest(APIModel):
    offset: Optional[float] = Field(0)
    preview_type: Optional[str] = Field(None)
    playback_mode: Optional[str] = Field('backend')

    @field_validator('offset', mode='before')
    @classmethod
    def convert_offset_to_int(cls, v):
        if v is None:
            return 0
        return int(v)

    @field_validator('playback_mode', mode='before')
    @classmethod
    def validate_playback_mode(cls, v):
        if v is None:
            return 'backend'
        if v not in ['frontend', 'backend']:
            return 'backend'
        return v


class TestCaseBatchActionRequest(APIModel):
    ids: List[str] = Field(...)
    action: str = Field(...)
    target_group_id: Optional[str] = Field(None)
    algorithm_params: Optional[Dict[str, Any]] = Field(None)
    playback_devices: Optional[Dict[str, Any]] = Field(None)
    spl: Optional[Union[float, Dict[str, Any]]] = Field(None)
    noise_spl: Optional[float] = Field(None)
    noise_audio_id: Optional[Union[int, str]] = Field(None)
    noise_device_ids: Optional[List[Union[int, str]]] = Field(None)
    group_name: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)
    dimensions: Optional[List[Dict[str, Any]]] = Field(None)
    old_tag_name: Optional[str] = Field(None)
    new_tag_name: Optional[str] = Field(None)


class TestCaseExportRequest(APIModel):
    ids: List[str] = Field(default_factory=list)
    format: Optional[str] = Field('json')
    include_deleted: Optional[bool] = Field(False)


class TestCaseImportRequest(APIModel):
    file_name: Optional[str] = Field(None)
    file_content: Optional[str] = Field(None)
    group_id: Optional[str] = Field(None)
    overwrite: Optional[bool] = Field(False)


class TestCaseUpdateSchema(APIModel):
    id: Optional[str] = Field(None)
    name: Optional[str] = Field(None, validation_alias=AliasChoices('name', 'Name'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('description', 'Description'))
    group_id: Optional[str] = Field(None, validation_alias=AliasChoices('group_id', 'groupId'))
    group: Optional[str] = Field(None)
    test_type: Optional[str] = Field(None)
    config: Optional[Dict[str, Any]] = Field(None)
    tags: Optional[List[str]] = Field(None)
    background_noise_id: Optional[int] = Field(None)
    background_noise_spl: Optional[float] = Field(None)
    audios: Optional[List[TestCaseAudioConfigRequest]] = Field(None)
    dimensions: Optional[Any] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    # 按轮分组：[{round_number, params:[{field_code, field_value}]}]，兼容旧平面格式
    algorithm_params: Optional[Any] = Field(None)
    # 按轮分组：[{round_number, reference_params_path}]
    reference_params: Optional[Any] = Field(None)

    @field_validator('algorithm_params', mode='before')
    @classmethod
    def coerce_dict_to_list(cls, v):
        if isinstance(v, dict):
            return [
                {'field_code': k, 'field_value': val}
                for k, val in v.items()
            ]
        return v

    def get_algorithm_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        """返回按轮分组的 algorithm_params"""
        if not self.algorithm_params:
            return None
        if isinstance(self.algorithm_params, list) and self.algorithm_params:
            first = self.algorithm_params[0]
            if isinstance(first, dict) and 'round_number' in first:
                return self.algorithm_params
            if isinstance(first, dict) and 'params' in first and 'field_code' not in first:
                return self.algorithm_params
        result = []
        for p in self.algorithm_params:
            if isinstance(p, dict):
                item = dict(p)
                # field_value 保持原始类型（list/dict/str/number）
                # 历史遗留：旧代码用 str() 转换，会导致 list/dict 变成 Python repr 字符串，无法 JSON 解析
                # 现在原样保留，JSON 列原生支持 list/dict
                result.append(item)
        if result:
            return [{'round_number': 1, 'params': result}]
        return None

    def get_reference_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        if not self.reference_params:
            return None
        if isinstance(self.reference_params, list):
            return self.reference_params
        return None
