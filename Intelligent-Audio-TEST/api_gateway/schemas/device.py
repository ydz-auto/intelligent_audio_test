from typing import Any, Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class DeviceListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    keyword: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None, alias='type')
    algorithm_type: Optional[str] = Field(None)


class DeviceStatusQuery(APIModel):
    ids: Optional[List[int]] = Field(None)


class DeviceCreateSchema(APIModel):
    name: str = Field(..., validation_alias='deviceName')
    model: str = Field(...)
    type: str = Field(..., validation_alias='deviceType')
    system: str = Field(...)
    system_version: str = Field(...)
    app_name: str = Field(...)
    app_version: str = Field(...)
    description: Optional[str] = Field(None)
    location: Optional[str] = Field(None)
    max_audio_duration: Optional[int] = Field(None)
    needs_prompt_audio: Optional[bool] = Field(None)
    prompt_config: Optional[Dict[str, Any]] = Field(None)
    connection_type: Optional[str] = Field(None)
    keywords: Optional[str] = Field(None)
    serial_number: Optional[str] = Field(None)
    ip: Optional[str] = Field(None)
    status: Optional[str] = Field('offline')
    supported_algorithms: Optional[List[str]] = Field(None)


class DeviceUpdateSchema(APIModel):
    name: Optional[str] = Field(None)
    model: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    system: Optional[str] = Field(None)
    system_version: Optional[str] = Field(None)
    app_name: Optional[str] = Field(None)
    app_version: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    location: Optional[str] = Field(None)
    max_audio_duration: Optional[int] = Field(None)
    needs_prompt_audio: Optional[bool] = Field(None)
    prompt_config: Optional[Dict[str, Any]] = Field(None)
    connection_type: Optional[str] = Field(None)
    keywords: Optional[str] = Field(None)
    serial_number: Optional[str] = Field(None)
    ip: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    supported_algorithms: Optional[List[str]] = Field(None)


class DeviceItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    model: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    system: Optional[str] = Field(None)
    system_version: Optional[str] = Field(None)
    app_name: Optional[str] = Field(None)
    app_version: Optional[str] = Field(None)
    location: Optional[str] = Field(None)
    max_audio_duration: Optional[int] = Field(None)
    needs_prompt_audio: Optional[bool] = Field(None)
    prompt_config: Optional[Dict[str, Any]] = Field(None)
    connection_type: Optional[str] = Field(None)
    keywords: Optional[str] = Field(None)
    serial_number: Optional[str] = Field(None)
    ip: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    last_online_at: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)
    driver_name: Optional[str] = Field(None)
    supported_algorithms: Optional[List[str]] = Field(None)


class DeviceListData(PaginatedData[DeviceItem]):
    pass


class DeviceStatusItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)
    last_online_at: Optional[str] = Field(None)


class DeviceStatusListData(APIModel):
    items: List[DeviceStatusItem] = Field(...)
    total: int = Field(...)


class DeviceScanItem(APIModel):
    serial: str = Field(...)
    model: Optional[str] = Field(None)
    system: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    is_registered: Optional[bool] = Field(None)
    id: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    system_version: Optional[str] = Field(None)
    app_name: Optional[str] = Field(None)
    app_version: Optional[str] = Field(None)
    ip: Optional[str] = Field(None)


class DeviceTestData(APIModel):
    id: int = Field(...)
    status: str = Field(...)
    wakeup_command: Optional[str] = Field(None)


class DeviceHealthItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    status: Optional[str] = Field(None)
    last_online_at: Optional[str] = Field(None)
    model: Optional[str] = Field(None)
    system: Optional[str] = Field(None)


class DeviceHealthCheckRequest(APIModel):
    device_ids: Optional[List[int]] = Field(None)
