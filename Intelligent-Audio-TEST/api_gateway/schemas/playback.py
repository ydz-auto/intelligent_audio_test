from typing import Any, List, Optional
from pydantic import Field, AliasChoices

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class PlaybackDeviceItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    model: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None)
    sample_rate: Optional[int] = Field(None)
    channel_index: Optional[int] = Field(None)
    device_unique_id: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    current_spl_mapping_id: Optional[int] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class PlaybackDeviceListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    keyword: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None, validation_alias=AliasChoices('type', 'device_type', 'deviceType'))


class PlaybackDeviceListData(PaginatedData[PlaybackDeviceItem]):
    pass


class PlaybackScanItem(APIModel):
    name: Optional[str] = Field(None)
    model: Optional[str] = Field(None)
    device_unique_id: Optional[str] = Field(None)
    channel_index: Optional[int] = Field(None)
    sample_rate: Optional[int] = Field(None)
    type: Optional[str] = Field(None)
    status: Optional[str] = Field(None)


class PlaybackTestData(APIModel):
    device: Any = Field(...)
    audio: Any = Field(...)
    status: str = Field(...)
    device_index: Optional[int] = Field(None)
    channel_index: Optional[int] = Field(None)
    gain: Optional[float] = Field(None)


class PlaybackStatusItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    unique_id: str = Field(...)
    status: str = Field(...)
    device_index: Optional[int] = Field(None)


class PlaybackCreateSchema(APIModel):
    name: str = Field(...)
    model: str = Field(...)
    device_type: str = Field(...)
    sample_rate: int = Field(...)
    device_unique_id: str = Field(...)
    channel_index: Optional[int] = Field(0)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field('online')


class PlaybackUpdateSchema(APIModel):
    name: Optional[str] = Field(None)
    model: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None)
    sample_rate: Optional[int] = Field(None)
    channel_index: Optional[int] = Field(None)
    device_unique_id: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    current_spl_mapping_id: Optional[int] = Field(None)


class PlaybackTestSchema(APIModel):
    audio_id: Optional[int] = Field(None)
    spl: Optional[float] = Field(None)


class PlaybackAssociateSplSchema(APIModel):
    spl_mapping_id: int = Field(...)
