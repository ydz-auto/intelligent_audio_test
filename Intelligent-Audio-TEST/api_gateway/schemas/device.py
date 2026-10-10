from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

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


# ==================== INT-80 设备操作/批量 ====================

class DeviceControlRequest(APIModel):
    """设备操作请求（connect/disconnect/reboot/shutdown/install_app/uninstall_app）"""
    params: Optional[Dict[str, Any]] = Field(None)
    idempotency_key: Optional[str] = Field(None)


class DeviceBatchActionRequest(APIModel):
    """设备批量操作请求（动作白名单见 shared DeviceOperation）"""
    action: str = Field(...)
    device_ids: List[int] = Field(default_factory=list)
    params: Optional[Dict[str, Any]] = Field(None)
    idempotency_key: Optional[str] = Field(None)


class DeviceStatusHistoryQuery(APIModel):
    device_ids: Optional[List[int]] = Field(None)
    event_type: Optional[str] = Field(None)
    start_time: Optional[str] = Field(None)
    end_time: Optional[str] = Field(None)
    page: int = Field(1)
    per_page: int = Field(50)

    @field_validator('device_ids', mode='before')
    @classmethod
    def _split_comma_ids(cls, value):
        """query 形态兼容：device_ids=1,2（URLSearchParams 数组序列化）与 1&device_ids=2 均可"""
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(',') if p.strip()]
            return [int(p) for p in parts] if parts else None
        return value


# ==================== INT-80 设备分组 ====================

class DeviceGroupListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(100)
    keyword: Optional[str] = Field(None)
    group_type: Optional[str] = Field(None)


class DeviceGroupCreateSchema(APIModel):
    name: str = Field(...)
    description: Optional[str] = Field(None)
    group_type: Optional[str] = Field('test')
    device_ids: Optional[List[int]] = Field(None)


class DeviceGroupUpdateSchema(APIModel):
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    group_type: Optional[str] = Field(None)


class DeviceGroupMembersRequest(APIModel):
    device_ids: List[int] = Field(...)


class DeviceGroupDeleteQuery(APIModel):
    cascade: bool = Field(False)


# ==================== INT-80 监控告警 ====================

class AlarmRuleListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(50)
    metric_type: Optional[str] = Field(None)
    enabled: Optional[bool] = Field(None)


class AlarmRuleCreateSchema(APIModel):
    name: str = Field(...)
    metric_type: str = Field(...)
    threshold_value: float = Field(...)
    severity: Optional[str] = Field('warning')
    notify_email: Optional[bool] = Field(True)
    enabled: Optional[bool] = Field(True)


class AlarmRuleUpdateSchema(APIModel):
    name: Optional[str] = Field(None)
    metric_type: Optional[str] = Field(None)
    threshold_value: Optional[float] = Field(None)
    severity: Optional[str] = Field(None)
    notify_email: Optional[bool] = Field(None)
    enabled: Optional[bool] = Field(None)


class AlarmListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(50)
    status: Optional[str] = Field(None)
    severity: Optional[str] = Field(None)
    device_id: Optional[int] = Field(None)


class AlarmAcknowledgeRequest(APIModel):
    acknowledged_by: Optional[str] = Field(None)
