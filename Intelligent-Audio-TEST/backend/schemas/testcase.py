from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from pydantic import Field, field_validator, AliasChoices, model_validator, ConfigDict
from pydantic.alias_generators import to_camel

from backend.schemas.base import APIModel
from backend.schemas.common import PaginatedData

if TYPE_CHECKING:
    pass


class TranslationDirectionItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    source_language: str = Field(..., alias='sourceLanguage', validation_alias='sourceLanguage')
    target_language: str = Field(..., alias='targetLanguage', validation_alias='targetLanguage')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')


class TestCaseAudioConfigItem(APIModel):
    id: Optional[int] = Field(None, alias='id', validation_alias='id')
    audio_id: Optional[Union[int, str]] = Field(None, alias='audioId', validation_alias=AliasChoices('audio_id', 'audioId'))
    audio_name: Optional[str] = Field(None, alias='audioName', validation_alias='audioName')
    test_type: Optional[str] = Field(None, alias='testType', validation_alias=AliasChoices('test_type', 'testType'))
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    playback_device_id: Optional[Union[int, str]] = Field(None, alias='playbackDeviceId', validation_alias=AliasChoices('playback_device_id', 'playbackDeviceId'))
    play_order: Optional[int] = Field(None, alias='playOrder', validation_alias=AliasChoices('play_order', 'playOrder'))


class TestCaseBackgroundNoiseItem(APIModel):
    audio_id: Optional[Union[int, str]] = Field(None, alias='audioId', validation_alias=AliasChoices('audio_id', 'audioId'))
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    device_ids: Optional[List[Union[int, str]]] = Field(None, alias='deviceIds', validation_alias=AliasChoices('device_ids', 'deviceIds'))


class TestCaseDimensionItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    weight: Optional[float] = Field(None, alias='weight', validation_alias='weight')
    threshold: Optional[float] = Field(None, alias='threshold', validation_alias='threshold')


class TestCaseDimensionsConfig(APIModel):
    api: Optional[List[TestCaseDimensionItem]] = Field(None, alias='api', validation_alias='api')
    e2e: Optional[List[TestCaseDimensionItem]] = Field(None, alias='e2e', validation_alias='e2e')


class TestCaseConfig(APIModel):
    audios: Optional[List[TestCaseAudioConfigItem]] = Field(None, alias='audios', validation_alias='audios')
    background_noise: Optional[TestCaseBackgroundNoiseItem] = Field(None, alias='backgroundNoise', validation_alias=AliasChoices('background_noise', 'backgroundNoise'))
    dimensions: Optional[TestCaseDimensionsConfig] = Field(None, alias='dimensions', validation_alias='dimensions')
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')


class TestCaseListItem(APIModel):
    id: str = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    group_id: Optional[str] = Field(None, alias='groupId', validation_alias='groupId')
    group_name: Optional[str] = Field(None, alias='groupName', validation_alias='groupName')
    type: Optional[Any] = Field(None, alias='type', validation_alias='type')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')
    config: TestCaseConfig = Field(default_factory=TestCaseConfig, alias='config', validation_alias='config')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[List[AlgorithmParamItem]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
    reference_params: Optional[List[ReferenceParamItem]] = Field(None, alias='referenceParams', validation_alias='referenceParams')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')
    total_duration: Optional[float] = Field(None, alias='totalDuration', validation_alias='totalDuration')
    api_duration: Optional[float] = Field(None, alias='apiDuration', validation_alias='apiDuration')
    e2e_duration: Optional[float] = Field(None, alias='e2eDuration', validation_alias='e2eDuration')


class TestCaseListData(PaginatedData[TestCaseListItem]):
    pass


class TestCaseDimensionBrief(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')


class TestCaseDetailData(APIModel):
    id: str = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    group_id: Optional[str] = Field(None, alias='groupId', validation_alias='groupId')
    group_name: Optional[str] = Field(None, alias='groupName', validation_alias='groupName')
    group: Optional[Dict[str, Any]] = Field(None, alias='group', validation_alias='group')
    type: Optional[Any] = Field(None, alias='type', validation_alias='type')
    config: TestCaseConfig = Field(default_factory=TestCaseConfig, alias='config', validation_alias='config')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')
    audios: List[TestCaseAudioConfigItem] = Field(default_factory=list, alias='audios', validation_alias='audios')
    dimensions: List[TestCaseDimensionBrief] = Field(default_factory=list, alias='dimensions', validation_alias='dimensions')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[List[AlgorithmParamItem]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
    reference_params: Optional[List[ReferenceParamItem]] = Field(None, alias='referenceParams', validation_alias='referenceParams')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')
    total_duration: Optional[float] = Field(None, alias='totalDuration', validation_alias='totalDuration')
    api_duration: Optional[float] = Field(None, alias='apiDuration', validation_alias='apiDuration')
    e2e_duration: Optional[float] = Field(None, alias='e2eDuration', validation_alias='e2eDuration')


class TestCasePreviewData(APIModel):
    test_case_id: str = Field(..., alias='testCaseId', validation_alias='testCaseId')
    preview_task_id: Optional[str] = Field(None, alias='previewTaskId', validation_alias='previewTaskId')
    status: str = Field(..., alias='status', validation_alias='status')
    message: Optional[str] = Field(None, alias='message', validation_alias='message')
    duration: Optional[float] = Field(None, alias='duration', validation_alias='duration')


class TestCaseStopPreviewData(APIModel):
    test_case_id: str = Field(..., alias='testCaseId', validation_alias='testCaseId')
    status: str = Field(..., alias='status', validation_alias='status')
    message: Optional[str] = Field(None, alias='message', validation_alias='message')


class TestCaseStatsData(APIModel):
    total_count: int = Field(..., alias='totalCount', validation_alias='totalCount')
    by_group: Dict[str, int] = Field(default_factory=dict, alias='byGroup', validation_alias='byGroup')
    recent_updates: List[Dict[str, Any]] = Field(default_factory=list, alias='recentUpdates', validation_alias='recentUpdates')


class TagListData(APIModel):
    items: List[str] = Field(..., alias='items', validation_alias='items')


class TagCategoryItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    color: Optional[str] = Field(None, alias='color', validation_alias='color')
    sort_order: int = Field(0, alias='sortOrder', validation_alias=AliasChoices('sort_order', 'sortOrder'))
    tag_count: int = Field(0, alias='tagCount', validation_alias=AliasChoices('tag_count', 'tagCount'))
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class TagCategoryListData(APIModel):
    items: List[TagCategoryItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


class TagCategoryCreateSchema(APIModel):
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    color: Optional[str] = Field(None, alias='color', validation_alias='color')
    sort_order: Optional[int] = Field(0, alias='sortOrder', validation_alias=AliasChoices('sort_order', 'sortOrder'))


class TagCategoryUpdateSchema(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    color: Optional[str] = Field(None, alias='color', validation_alias='color')
    sort_order: Optional[int] = Field(None, alias='sortOrder', validation_alias=AliasChoices('sort_order', 'sortOrder'))


class TagItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    color: Optional[str] = Field(None, alias='color', validation_alias='color')
    category_id: Optional[int] = Field(None, alias='categoryId', validation_alias=AliasChoices('category_id', 'categoryId'))
    category_name: Optional[str] = Field(None, alias='categoryName', validation_alias=AliasChoices('category_name', 'categoryName'))
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class TagDetailListData(APIModel):
    items: List[TagItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


class TagCreateSchema(APIModel):
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    color: Optional[str] = Field(None, alias='color', validation_alias='color')
    category_id: Optional[int] = Field(None, alias='categoryId', validation_alias=AliasChoices('category_id', 'categoryId'))


class TagUpdateSchema(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    color: Optional[str] = Field(None, alias='color', validation_alias='color')
    category_id: Optional[int] = Field(None, alias='categoryId', validation_alias=AliasChoices('category_id', 'categoryId'))


class TestCaseExportJsonData(APIModel):
    test_cases: List["TestCaseExportItem"] = Field(..., alias='testCases', validation_alias='testCases')
    exported_at: str = Field(..., alias='exportedAt', validation_alias='exportedAt')
    total_count: int = Field(..., alias='totalCount', validation_alias='totalCount')


class TestCaseImportResult(APIModel):
    imported_count: int = Field(..., alias='importedCount', validation_alias='importedCount')
    errors: List[Any] = Field(default_factory=list, alias='errors', validation_alias='errors')


class TestCaseExportTagItem(APIModel):
    tag_id: int = Field(..., alias='tagId', validation_alias='tagId')
    tag_name: str = Field(..., alias='tagName', validation_alias='tagName')


class TestCaseExportAudioItem(APIModel):
    audio_id: Optional[int] = Field(None, alias='audioId', validation_alias='audioId')
    audio_name: Optional[str] = Field(None, alias='audioName', validation_alias='audioName')
    test_type: Optional[str] = Field(None, alias='testType', validation_alias='testType')
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    playback_device_id: Optional[int] = Field(None, alias='playbackDeviceId', validation_alias='playbackDeviceId')
    playback_device_name: Optional[str] = Field(None, alias='playbackDeviceName', validation_alias='playbackDeviceName')
    play_order: Optional[int] = Field(None, alias='playOrder', validation_alias='playOrder')


class ReportAudioItem(APIModel):
    id: Optional[int] = Field(None, alias='id', validation_alias='id')
    filename: Optional[str] = Field(None, alias='filename', validation_alias='filename')
    duration: Optional[float] = Field(None, alias='duration', validation_alias='duration')
    url: Optional[str] = Field(None, alias='url', validation_alias='url')
    test_type: Optional[str] = Field(None, alias='testType', validation_alias='testType')
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    play_order: Optional[int] = Field(None, alias='playOrder', validation_alias='playOrder')
    playback_device_id: Optional[int] = Field(None, alias='playbackDeviceId', validation_alias='playbackDeviceId')
    playback_device_name: Optional[str] = Field(None, alias='playbackDeviceName', validation_alias='playbackDeviceName')
    label: Optional[str] = Field(None, alias='label', validation_alias='label')


class ReportTestCaseItem(APIModel):
    id: Optional[str] = Field(None, alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    category: Optional[str] = Field(None, alias='category', validation_alias='category')
    tags: List[Any] = Field(default_factory=list, alias='tags', validation_alias='tags')
    audios: List[ReportAudioItem] = Field(default_factory=list, alias='audios', validation_alias='audios')
    metrics: List[Any] = Field(default_factory=list, alias='metrics', validation_alias='metrics')
    asr: Optional[Dict[str, Any]] = Field(None, alias='asr', validation_alias='asr')
    translation: Optional[Dict[str, Any]] = Field(None, alias='translation', validation_alias='translation')
    results: List[Any] = Field(default_factory=list, alias='results', validation_alias='results')
    logs: Optional[str] = Field(None, alias='logs', validation_alias='logs')


class TestCaseExportItem(APIModel):
    id: str = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    group: Optional[str] = Field(None, alias='group', validation_alias='group')
    group_id: Optional[str] = Field(None, alias='groupId', validation_alias='groupId')
    tags: List[str] = Field(default_factory=list, alias='tags', validation_alias='tags')
    tag_items: List[TestCaseExportTagItem] = Field(default_factory=list, alias='tagItems', validation_alias='tagItems')
    api_dimensions: List[str] = Field(default_factory=list, alias='apiDimensions', validation_alias='apiDimensions')
    e2e_dimensions: List[str] = Field(default_factory=list, alias='e2eDimensions', validation_alias='e2eDimensions')
    api_dimension_ids: List[int] = Field(default_factory=list, alias='apiDimensionIds', validation_alias='apiDimensionIds')
    e2e_dimension_ids: List[int] = Field(default_factory=list, alias='e2eDimensionIds', validation_alias='e2eDimensionIds')
    playback_devices: List[str] = Field(default_factory=list, alias='playbackDevices', validation_alias='playbackDevices')
    audios: List[TestCaseExportAudioItem] = Field(default_factory=list, alias='audios', validation_alias='audios')
    audio_details: Optional[str] = Field(None, alias='audioDetails', validation_alias='audioDetails')
    noise_name: Optional[str] = Field(None, alias='noiseName', validation_alias='noiseName')
    noise_spl: Optional[Any] = Field(None, alias='noiseSpl', validation_alias='noiseSpl')
    noise_audio_id: Optional[int] = Field(None, alias='noiseAudioId', validation_alias='noiseAudioId')
    config: Dict[str, Any] = Field(default_factory=dict, alias='config', validation_alias='config')
    raw_config: Optional[str] = Field(None, alias='rawConfig', validation_alias='rawConfig')


class TestCaseAudioConfigRequest(APIModel):
    audio_id: Optional[int] = Field(None, alias='audioId', validation_alias=AliasChoices('audio_id', 'audioId'))
    test_type: Optional[str] = Field(None, alias='testType', validation_alias=AliasChoices('test_type', 'testType'))
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    playback_device_id: Optional[int] = Field(None, alias='playbackDeviceId', validation_alias=AliasChoices('playback_device_id', 'playbackDeviceId'))
    play_order: Optional[int] = Field(None, alias='playOrder', validation_alias=AliasChoices('play_order', 'playOrder'))


class TestCaseBackgroundNoiseRequest(APIModel):
    audio_id: Optional[int] = Field(None, alias='audioId', validation_alias=AliasChoices('audio_id', 'audioId'))
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    device_ids: Optional[List[Union[int, str]]] = Field(None, alias='deviceIds', validation_alias=AliasChoices('device_ids', 'deviceIds'))


class TestCaseDimensionItemRequest(APIModel):
    id: Optional[int] = Field(None, alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    display_name: Optional[str] = Field(None, alias='displayName', validation_alias=AliasChoices('display_name', 'displayName'))
    weight: Optional[float] = Field(None, alias='weight', validation_alias='weight')
    threshold: Optional[float] = Field(None, alias='threshold', validation_alias='threshold')


class TestCaseDimensionsRequest(APIModel):
    api: Optional[List[TestCaseDimensionItemRequest]] = Field(None, alias='api', validation_alias='api')
    e2e: Optional[List[TestCaseDimensionItemRequest]] = Field(None, alias='e2e', validation_alias='e2e')


class AlgorithmParamItem(APIModel):
    model_config = ConfigDict(extra='allow')

    field_code: Optional[str] = Field(None, alias='fieldCode', validation_alias=AliasChoices('field_code', 'fieldCode'))
    field_value: Optional[Union[str, int, float]] = Field(None, alias='fieldValue', validation_alias=AliasChoices('field_value', 'fieldValue'))

    @staticmethod
    def convert_params(params) -> Optional[List['AlgorithmParamItem']]:
        if not params:
            return None
        if isinstance(params, list):
            result = []
            for item in params:
                if isinstance(item, dict):
                    result.append(AlgorithmParamItem(
                        field_code=item.get('field_code'),
                        field_value=item.get('field_value')
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

    code: Optional[str] = Field(None, alias='code', validation_alias=AliasChoices('code', 'code'))
    type: Optional[str] = Field(None, alias='type', validation_alias=AliasChoices('type', 'type'))
    api: Optional[Union[str, Dict[str, Any], List[Any]]] = Field(None, alias='api', validation_alias=AliasChoices('api', 'api'))
    e2e: Optional[Union[str, Dict[str, Any], List[Any]]] = Field(None, alias='e2e', validation_alias=AliasChoices('e2e', 'e2e'))
    annotation_code: Optional[str] = Field(None, alias='annotationCode', validation_alias=AliasChoices('annotation_code', 'annotationCode'))
    annotation_format: Optional[str] = Field(None, alias='annotationFormat', validation_alias=AliasChoices('annotation_format', 'annotationFormat'))

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
                        api=item.get('api'),
                        e2e=item.get('e2e'),
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
    group: Optional[str] = Field(None, alias='group', validation_alias='group')
    config: Optional[Dict[str, Any]] = Field(None, alias='config', validation_alias='config')
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')
    background_noise_id: Optional[int] = Field(None, alias='backgroundNoiseId', validation_alias=AliasChoices('background_noise_id', 'backgroundNoiseId'))
    background_noise_spl: Optional[float] = Field(None, alias='backgroundNoiseSpl', validation_alias=AliasChoices('background_noise_spl', 'backgroundNoiseSpl'))
    audios: Optional[List[TestCaseAudioConfigRequest]] = Field(None, alias='audios', validation_alias='audios')
    dimensions: Optional[Any] = Field(None, alias='dimensions', validation_alias='dimensions')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias=AliasChoices('algorithm_type', 'algorithmType'))
    algorithm_params: Optional[List[AlgorithmParamItem]] = Field(None, alias='algorithmParams', validation_alias=AliasChoices('algorithm_params', 'algorithmParams'))
    reference_params: Optional[List[ReferenceParamItem]] = Field(None, alias='referenceParams', validation_alias=AliasChoices('reference_params', 'referenceParams'))

    def get_algorithm_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        if not self.algorithm_params:
            return None
        return [p.model_dump() for p in self.algorithm_params]

    def get_reference_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        if not self.reference_params:
            return None
        return [p.model_dump() for p in self.reference_params]


class TestCasePreviewRequest(APIModel):
    offset: Optional[float] = Field(0, alias='offset', validation_alias='offset')
    preview_type: Optional[str] = Field(None, alias='previewType', validation_alias=AliasChoices('preview_type', 'previewType'))

    @field_validator('offset', mode='before')
    @classmethod
    def convert_offset_to_int(cls, v):
        if v is None:
            return 0
        return int(v)


class TestCaseBatchActionRequest(APIModel):
    ids: List[str] = Field(..., alias='ids', validation_alias='ids')
    action: str = Field(..., alias='action', validation_alias='action')
    target_group_id: Optional[str] = Field(None, alias='targetGroupId', validation_alias=AliasChoices('target_group_id', 'targetGroupId'))
    algorithm_params: Optional[Dict[str, Any]] = Field(None, alias='algorithmParams', validation_alias=AliasChoices('algorithm_params', 'algorithmParams'))
    playback_devices: Optional[Dict[str, Any]] = Field(None, alias='playbackDevices', validation_alias=AliasChoices('playback_devices', 'playbackDevices'))
    spl: Optional[Union[float, Dict[str, Any]]] = Field(None, alias='spl', validation_alias=AliasChoices('spl', 'spl'))
    noise_spl: Optional[float] = Field(None, alias='noiseSpl', validation_alias=AliasChoices('noise_spl', 'noiseSpl'))
    noise_audio_id: Optional[Union[int, str]] = Field(None, alias='noiseAudioId', validation_alias=AliasChoices('noise_audio_id', 'noiseAudioId'))
    noise_device_ids: Optional[List[Union[int, str]]] = Field(None, alias='noiseDeviceIds', validation_alias=AliasChoices('noise_device_ids', 'noiseDeviceIds'))
    group_name: Optional[str] = Field(None, alias='groupName', validation_alias=AliasChoices('group_name', 'groupName'))
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')
    dimensions: Optional[List[Dict[str, Any]]] = Field(None, alias='dimensions', validation_alias='dimensions')
    test_type: Optional[str] = Field(None, alias='testType', validation_alias=AliasChoices('test_type', 'testType'))
    old_tag_name: Optional[str] = Field(None, alias='oldTagName', validation_alias=AliasChoices('old_tag_name', 'oldTagName'))
    new_tag_name: Optional[str] = Field(None, alias='newTagName', validation_alias=AliasChoices('new_tag_name', 'newTagName'))


class TestCaseExportRequest(APIModel):
    ids: List[str] = Field(default_factory=list, alias='ids', validation_alias='ids')
    format: Optional[str] = Field('json', alias='format', validation_alias='format')
    include_deleted: Optional[bool] = Field(False, alias='includeDeleted', validation_alias=AliasChoices('include_deleted', 'includeDeleted'))


class TestCaseImportRequest(APIModel):
    file_name: Optional[str] = Field(None, alias='fileName', validation_alias=AliasChoices('file_name', 'fileName'))
    file_content: Optional[str] = Field(None, alias='fileContent', validation_alias=AliasChoices('file_content', 'fileContent'))
    group_id: Optional[str] = Field(None, alias='groupId', validation_alias=AliasChoices('group_id', 'groupId'))
    overwrite: Optional[bool] = Field(False, alias='overwrite', validation_alias='overwrite')


class TestCaseUpdateSchema(APIModel):
    id: Optional[str] = Field(None, alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias=AliasChoices('name', 'Name'))
    description: Optional[str] = Field(None, alias='description', validation_alias=AliasChoices('description', 'Description'))
    group_id: Optional[str] = Field(None, alias='groupId', validation_alias=AliasChoices('group_id', 'groupId'))
    group: Optional[str] = Field(None, alias='group', validation_alias='group')
    config: Optional[Dict[str, Any]] = Field(None, alias='config', validation_alias='config')
    tags: Optional[List[str]] = Field(None, alias='tags', validation_alias='tags')
    background_noise_id: Optional[int] = Field(None, alias='backgroundNoiseId', validation_alias=AliasChoices('background_noise_id', 'backgroundNoiseId'))
    background_noise_spl: Optional[float] = Field(None, alias='backgroundNoiseSpl', validation_alias=AliasChoices('background_noise_spl', 'backgroundNoiseSpl'))
    audios: Optional[List[TestCaseAudioConfigRequest]] = Field(None, alias='audios', validation_alias='audios')
    dimensions: Optional[Any] = Field(None, alias='dimensions', validation_alias='dimensions')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias=AliasChoices('algorithm_type', 'algorithmType'))
    algorithm_params: Optional[List[AlgorithmParamItem]] = Field(None, alias='algorithmParams', validation_alias=AliasChoices('algorithm_params', 'algorithmParams'))
    reference_params: Optional[List[ReferenceParamItem]] = Field(None, alias='referenceParams', validation_alias=AliasChoices('reference_params', 'referenceParams'))

    def get_algorithm_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        if not self.algorithm_params:
            return None
        return [p.model_dump() for p in self.algorithm_params]

    def get_reference_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        if not self.reference_params:
            return None
        return [p.model_dump() for p in self.reference_params]

