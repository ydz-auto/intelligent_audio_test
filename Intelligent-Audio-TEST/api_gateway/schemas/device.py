from typing import Any, Dict, List, Optional
from pydantic import Field, ConfigDict, AliasChoices

from shared.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class DeviceListQuery(APIModel):
    page: int = Field(1, alias='page', validation_alias='page')
    per_page: int = Field(10, alias='perPage', validation_alias='perPage')
    keyword: Optional[str] = Field(None, alias='keyword', validation_alias='keyword')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    device_type: Optional[str] = Field(None, alias='type', validation_alias='type')
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')


class DeviceStatusQuery(APIModel):
    ids: Optional[List[int]] = Field(None, alias='ids', validation_alias='ids')


class DeviceCreateSchema(APIModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(..., validation_alias=AliasChoices('name', 'deviceName'))
    model: str = Field(..., validation_alias=AliasChoices('model'))
    type: str = Field(..., validation_alias=AliasChoices('type', 'deviceType'))
    system: str = Field(..., validation_alias=AliasChoices('system'))
    system_version: str = Field(..., validation_alias=AliasChoices('systemVersion', 'system_version'))
    app_name: str = Field(..., validation_alias=AliasChoices('appName', 'app_name'))
    app_version: str = Field(..., validation_alias=AliasChoices('appVersion', 'app_version'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('description'))
    location: Optional[str] = Field(None, validation_alias=AliasChoices('location'))
    max_audio_duration: Optional[int] = Field(None, validation_alias=AliasChoices('maxAudioDuration', 'max_audio_duration'))
    needs_prompt_audio: Optional[bool] = Field(None, validation_alias=AliasChoices('needsPromptAudio', 'needs_prompt_audio'))
    prompt_config: Optional[Dict[str, Any]] = Field(None, validation_alias=AliasChoices('promptConfig', 'prompt_config'))
    connection_type: Optional[str] = Field(None, validation_alias=AliasChoices('connectionType', 'connection_type'))
    keywords: Optional[str] = Field(None, validation_alias='keywords')
    serial_number: Optional[str] = Field(None, validation_alias=AliasChoices('serialNumber', 'serial_number'))
    ip: Optional[str] = Field(None, validation_alias='ip')
    status: Optional[str] = Field('offline', validation_alias='status')
    supported_algorithms: Optional[List[str]] = Field(None, validation_alias=AliasChoices('supportedAlgorithms', 'supported_algorithms'))


class DeviceUpdateSchema(APIModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: Optional[str] = Field(None, validation_alias='name')
    model: Optional[str] = Field(None, validation_alias='model')
    type: Optional[str] = Field(None, validation_alias='type')
    system: Optional[str] = Field(None, validation_alias='system')
    system_version: Optional[str] = Field(None, validation_alias=AliasChoices('systemVersion', 'system_version'))
    app_name: Optional[str] = Field(None, validation_alias=AliasChoices('appName', 'app_name'))
    app_version: Optional[str] = Field(None, validation_alias=AliasChoices('appVersion', 'app_version'))
    description: Optional[str] = Field(None, validation_alias='description')
    location: Optional[str] = Field(None, validation_alias='location')
    max_audio_duration: Optional[int] = Field(None, validation_alias=AliasChoices('maxAudioDuration', 'max_audio_duration'))
    needs_prompt_audio: Optional[bool] = Field(None, validation_alias=AliasChoices('needsPromptAudio', 'needs_prompt_audio'))
    prompt_config: Optional[Dict[str, Any]] = Field(None, validation_alias=AliasChoices('promptConfig', 'prompt_config'))
    connection_type: Optional[str] = Field(None, validation_alias=AliasChoices('connectionType', 'connection_type'))
    keywords: Optional[str] = Field(None, validation_alias='keywords')
    serial_number: Optional[str] = Field(None, validation_alias=AliasChoices('serialNumber', 'serial_number'))
    ip: Optional[str] = Field(None, validation_alias='ip')
    status: Optional[str] = Field(None, validation_alias='status')
    supported_algorithms: Optional[List[str]] = Field(None, validation_alias=AliasChoices('supportedAlgorithms', 'supported_algorithms'))


class DeviceItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    system: Optional[str] = Field(None, alias='system', validation_alias='system')
    system_version: Optional[str] = Field(None, alias='systemVersion', validation_alias='systemVersion')
    app_name: Optional[str] = Field(None, alias='appName', validation_alias='appName')
    app_version: Optional[str] = Field(None, alias='appVersion', validation_alias='appVersion')
    location: Optional[str] = Field(None, alias='location', validation_alias='location')
    max_audio_duration: Optional[int] = Field(None, alias='maxAudioDuration', validation_alias='maxAudioDuration')
    needs_prompt_audio: Optional[bool] = Field(None, alias='needsPromptAudio', validation_alias='needsPromptAudio')
    prompt_config: Optional[Dict[str, Any]] = Field(None, alias='promptConfig', validation_alias='promptConfig')
    connection_type: Optional[str] = Field(None, alias='connectionType', validation_alias='connectionType')
    keywords: Optional[str] = Field(None, alias='keywords', validation_alias='keywords')
    serial_number: Optional[str] = Field(None, alias='serialNumber', validation_alias='serialNumber')
    ip: Optional[str] = Field(None, alias='ip', validation_alias='ip')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    last_online_at: Optional[str] = Field(None, alias='lastOnlineAt', validation_alias='lastOnlineAt')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')
    driver_name: Optional[str] = Field(None, alias='driverName', validation_alias='driverName')
    supported_algorithms: Optional[List[str]] = Field(None, alias='supportedAlgorithms', validation_alias='supportedAlgorithms')


class DeviceListData(PaginatedData[DeviceItem]):
    pass


class DeviceStatusItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    last_online_at: Optional[str] = Field(None, alias='lastOnlineAt', validation_alias='lastOnlineAt')


class DeviceStatusListData(APIModel):
    items: List[DeviceStatusItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


class DeviceScanItem(APIModel):
    serial: str = Field(..., alias='serial', validation_alias='serial')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    system: Optional[str] = Field(None, alias='system', validation_alias='system')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    is_registered: Optional[bool] = Field(None, alias='isRegistered', validation_alias='isRegistered')
    id: Optional[str] = Field(None, alias='id', validation_alias='id')
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    system_version: Optional[str] = Field(None, alias='systemVersion', validation_alias='systemVersion')
    app_name: Optional[str] = Field(None, alias='appName', validation_alias='appName')
    app_version: Optional[str] = Field(None, alias='appVersion', validation_alias='appVersion')
    ip: Optional[str] = Field(None, alias='ip', validation_alias='ip')


class DeviceTestData(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    status: str = Field(..., alias='status', validation_alias='status')
    wakeup_command: Optional[str] = Field(None, alias='wakeupCommand', validation_alias='wakeupCommand')


class DeviceHealthItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    last_online_at: Optional[str] = Field(None, alias='lastOnlineAt', validation_alias='lastOnlineAt')
    model: Optional[str] = Field(None, alias='model', validation_alias='model')
    system: Optional[str] = Field(None, alias='system', validation_alias='system')


class DeviceHealthCheckRequest(APIModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    device_ids: Optional[List[int]] = Field(None, validation_alias=AliasChoices('deviceIds', 'device_ids'))

