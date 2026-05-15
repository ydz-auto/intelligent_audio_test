from typing import Any, List, Optional
from pydantic import Field

from backend.schemas.base import APIModel
from backend.schemas.common import PaginatedData


class PlaybackDeviceItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    device_type: Optional[str] = Field(None, alias='deviceType', validation_alias='deviceType')
    sample_rate: Optional[int] = Field(None, alias='sampleRate', validation_alias='sampleRate')
    channel_index: Optional[int] = Field(None, alias='channelIndex', validation_alias='channelIndex')
    device_unique_id: Optional[str] = Field(None, alias='deviceUniqueId', validation_alias='deviceUniqueId')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    current_spl_mapping_id: Optional[int] = Field(None, alias='currentSplMappingId', validation_alias='currentSplMappingId')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class PlaybackDeviceListData(PaginatedData[PlaybackDeviceItem]):
    pass


class PlaybackScanItem(APIModel):
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    device_unique_id: Optional[str] = Field(None, alias='deviceUniqueId', validation_alias='deviceUniqueId')
    channel_index: Optional[int] = Field(None, alias='channelIndex', validation_alias='channelIndex')
    sample_rate: Optional[int] = Field(None, alias='sampleRate', validation_alias='sampleRate')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')


class PlaybackTestData(APIModel):
    device: Any = Field(..., alias='device', validation_alias='device')
    audio: Any = Field(..., alias='audio', validation_alias='audio')
    status: str = Field(..., alias='status', validation_alias='status')
    device_index: Optional[int] = Field(None, alias='deviceIndex', validation_alias='deviceIndex')
    channel_index: Optional[int] = Field(None, alias='channelIndex', validation_alias='channelIndex')
    gain: Optional[float] = Field(None, alias='gain', validation_alias='gain')


class PlaybackStatusItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    unique_id: str = Field(..., alias='uniqueId', validation_alias='uniqueId')
    status: str = Field(..., alias='status', validation_alias='status')
    device_index: Optional[int] = Field(None, alias='deviceIndex', validation_alias='deviceIndex')


class PlaybackCreateSchema(APIModel):
    name: str = Field(..., alias='name', validation_alias='name')
    model: str = Field(..., alias='model', validation_alias='model')
    device_type: str = Field(..., alias='deviceType', validation_alias='deviceType')
    sample_rate: int = Field(..., alias='sampleRate', validation_alias='sampleRate')
    device_unique_id: str = Field(..., alias='deviceUniqueId', validation_alias='deviceUniqueId')
    channel_index: Optional[int] = Field(0, alias='channelIndex', validation_alias='channelIndex')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: Optional[str] = Field('online', alias='status', validation_alias='status')


class PlaybackUpdateSchema(APIModel):
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    device_type: Optional[str] = Field(None, alias='deviceType', validation_alias='deviceType')
    sample_rate: Optional[int] = Field(None, alias='sampleRate', validation_alias='sampleRate')
    channel_index: Optional[int] = Field(None, alias='channelIndex', validation_alias='channelIndex')
    device_unique_id: Optional[str] = Field(None, alias='deviceUniqueId', validation_alias='deviceUniqueId')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    current_spl_mapping_id: Optional[int] = Field(None, alias='currentSplMappingId', validation_alias='currentSplMappingId')


class PlaybackTestSchema(APIModel):
    audio_id: Optional[int] = Field(None, alias='audioId', validation_alias='audioId')
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')


class PlaybackAssociateSplSchema(APIModel):
    spl_mapping_id: int = Field(..., alias='splMappingId', validation_alias='splMappingId')
