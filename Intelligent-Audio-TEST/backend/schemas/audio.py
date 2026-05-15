from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import Field

from backend.schemas.base import APIModel
from backend.schemas.common import PaginatedData
from backend.schemas.testcase import AlgorithmParamItem


class DirectionItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    source_language: str = Field(..., alias='sourceLanguage', validation_alias='sourceLanguage')
    target_language: str = Field(..., alias='targetLanguage', validation_alias='targetLanguage')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')


class DirectionListData(APIModel):
    items: List[DirectionItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


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


class RegisterUploadFileRequest(APIModel):
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    files: Optional[List[Dict]] = Field(default_factory=list, alias='files', validation_alias='files')


class AudioAlgorithmRelationItem(APIModel):
    algorithm_type: str = Field(..., alias='algorithmType', validation_alias='algorithmType')
    is_primary: bool = Field(default=False, alias='isPrimary', validation_alias='isPrimary')
    weight: float = Field(default=1.0)
    params: Optional[Dict] = Field(default=None)


class MergeChunksRequest(APIModel):
    file_id: str = Field(..., alias='fileId', validation_alias='fileId')
    task_id: str = Field(..., alias='taskId', validation_alias='taskId')
    create_test_case: Optional[bool] = Field(False, alias='createTestCase', validation_alias='createTestCase')
    test_types: Optional[List[str]] = Field(default_factory=lambda: ['api'], alias='testTypes', validation_alias='testTypes')
    dimensions: Optional[Dict] = Field(default_factory=dict, alias='dimensions', validation_alias='dimensions')
    default_playback_device_id: Optional[int] = Field(None, alias='defaultPlaybackDeviceId', validation_alias='defaultPlaybackDeviceId')
    default_spl: Optional[float] = Field(65.0, alias='defaultSpl', validation_alias='defaultSpl')
    noise_spl: Optional[float] = Field(60.0, alias='noiseSpl', validation_alias='noiseSpl')
    noise_audio_id: Optional[int] = Field(None, alias='noiseAudioId', validation_alias='noiseAudioId')
    test_case_group_name: Optional[str] = Field(None, alias='testCaseGroupName', validation_alias='testCaseGroupName')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    algorithm_params: Optional[List[AlgorithmParamItem]] = Field(None, alias='algorithmParams', validation_alias='algorithmParams')
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

    def get_algorithm_params_dict(self) -> Optional[List[Dict[str, Any]]]:
        if not self.algorithm_params:
            return None
        return [p.model_dump() for p in self.algorithm_params]


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
