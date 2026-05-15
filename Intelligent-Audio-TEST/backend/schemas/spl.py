from typing import Any, Dict, List, Optional
from pydantic import Field

from backend.schemas.base import APIModel
from backend.schemas.common import PaginatedData


class CalibrationPointSchema(APIModel):
    spl: Optional[float] = Field(None, alias='spl', validation_alias='spl')
    gain_offset: Optional[float] = Field(None, alias='gainOffset', validation_alias='gainOffset')
    digital_gain: Optional[float] = Field(None, alias='digitalGain', validation_alias='digitalGain')
    base_level: Optional[float] = Field(None, alias='baseLevel', validation_alias='baseLevel')
    final_level: Optional[float] = Field(None, alias='finalLevel', validation_alias='finalLevel')


class CalibrationDataSchema(APIModel):
    points: List[CalibrationPointSchema] = Field(default_factory=list, alias='points', validation_alias='points')


class SPLMappingQueryRequest(APIModel):
    keyword: Optional[str] = Field(None, alias='keyword', validation_alias='keyword')
    search: Optional[str] = Field(None, alias='search', validation_alias='search')
    calibration_status: Optional[str] = Field(None, alias='calibrationStatus', validation_alias='calibrationStatus')
    page: Optional[int] = Field(1, alias='page', validation_alias='page')
    per_page: Optional[int] = Field(10, alias='perPage', validation_alias='perPage')
    device_id: Optional[int] = Field(None, alias='deviceId', validation_alias='deviceId')


class SPLMappingCreateRequest(APIModel):
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    device_id: Optional[int] = Field(None, alias='deviceId', validation_alias='deviceId')
    device_type: Optional[str] = Field(None, alias='deviceType', validation_alias='deviceType')
    distance: Optional[float] = Field(1.0, alias='distance', validation_alias='distance')
    target_spl: Optional[float] = Field(None, alias='targetSpl', validation_alias='targetSpl')
    digital_gain: Optional[float] = Field(None, alias='digitalGain', validation_alias='digitalGain')
    test_frequency: Optional[int] = Field(1000, alias='testFrequency', validation_alias='testFrequency')
    calibration_status: Optional[str] = Field(None, alias='calibrationStatus', validation_alias='calibrationStatus')
    calibration_data: Optional[Dict[str, Any]] = Field(None, alias='calibrationData', validation_alias='calibrationData')


class SPLMappingUpdateRequest(APIModel):
    name: Optional[str] = Field(None, alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    device_id: Optional[int] = Field(None, alias='deviceId', validation_alias='deviceId')
    device_type: Optional[str] = Field(None, alias='deviceType', validation_alias='deviceType')
    distance: Optional[float] = Field(None, alias='distance', validation_alias='distance')
    target_spl: Optional[float] = Field(None, alias='targetSpl', validation_alias='targetSpl')
    digital_gain: Optional[float] = Field(None, alias='digitalGain', validation_alias='digitalGain')
    test_frequency: Optional[int] = Field(None, alias='testFrequency', validation_alias='testFrequency')
    calibration_status: Optional[str] = Field(None, alias='calibrationStatus', validation_alias='calibrationStatus')
    calibration_data: Optional[Dict[str, Any]] = Field(None, alias='calibrationData', validation_alias='calibrationData')
    is_current: Optional[bool] = Field(None, alias='isCurrent', validation_alias='isCurrent')


class PlayTestToneRequest(APIModel):
    gain_value: Optional[float] = Field(50, alias='gainValue', validation_alias='gainValue')
    gain_offset: Optional[float] = Field(None, alias='gainOffset', validation_alias='gainOffset')
    target_spl: Optional[float] = Field(65, alias='targetSpl', validation_alias='targetSpl')
    unique_id: Optional[str] = Field(None, alias='uniqueId', validation_alias='uniqueId')


class StopTestToneRequest(APIModel):
    unique_id: Optional[str] = Field(None, alias='uniqueId', validation_alias='uniqueId')


class SplMappingItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    device_id: Optional[int] = Field(None, alias='deviceId', validation_alias='deviceId')
    device: Optional[Dict[str, Any]] = Field(None, alias='device', validation_alias='device')
    device_name: Optional[str] = Field(None, alias='deviceName', validation_alias='deviceName')
    device_model: Optional[str] = Field(None, alias='deviceModel', validation_alias='deviceModel')
    device_type: Optional[str] = Field(None, alias='deviceType', validation_alias='deviceType')
    distance: Optional[float] = Field(None, alias='distance', validation_alias='distance')
    target_spl: Optional[float] = Field(None, alias='targetSpl', validation_alias='targetSpl')
    digital_gain: Optional[float] = Field(None, alias='digitalGain', validation_alias='digitalGain')
    calibration_status: Optional[str] = Field(None, alias='calibrationStatus', validation_alias='calibrationStatus')
    test_frequency: Optional[int] = Field(None, alias='testFrequency', validation_alias='testFrequency')
    calibration_data: Optional[Dict[str, Any]] = Field(None, alias='calibrationData', validation_alias='calibrationData')
    is_current: Optional[bool] = Field(None, alias='isCurrent', validation_alias='isCurrent')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class SplMappingListData(PaginatedData[SplMappingItem]):
    pass


class SplHistoryItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    calibration_data: Optional[Dict[str, Any]] = Field(None, alias='calibrationData', validation_alias='calibrationData')
    distance: Optional[float] = Field(None, alias='distance', validation_alias='distance')
    test_frequency: Optional[int] = Field(None, alias='testFrequency', validation_alias='testFrequency')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')


class SplHistoryData(APIModel):
    items: List[SplHistoryItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


class SplStatsData(APIModel):
    total: int = Field(..., alias='total', validation_alias='total')
    calibrated: int = Field(..., alias='calibrated', validation_alias='calibrated')
    uncalibrated: int = Field(..., alias='uncalibrated', validation_alias='uncalibrated')
    associated_devices: int = Field(..., alias='associatedDevices', validation_alias='associatedDevices')


class SplByDeviceItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    device_id: Optional[int] = Field(None, alias='deviceId', validation_alias='deviceId')
    device_type: Optional[str] = Field(None, alias='deviceType', validation_alias='deviceType')
    distance: Optional[float] = Field(None, alias='distance', validation_alias='distance')
    target_spl: Optional[float] = Field(None, alias='targetSpl', validation_alias='targetSpl')
    calibration_status: Optional[str] = Field(None, alias='calibrationStatus', validation_alias='calibrationStatus')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class SplByDeviceData(APIModel):
    items: List[SplByDeviceItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


class TestToneDeviceItem(APIModel):
    device: Any = Field(..., alias='device', validation_alias='device')
    gain_db: float = Field(..., alias='gainDb', validation_alias='gainDb')
    final_dbfs: float = Field(..., alias='finalDbfs', validation_alias='finalDbfs')
    target_spl: float = Field(..., alias='targetSpl', validation_alias='targetSpl')


class PlayTestToneData(APIModel):
    devices: List[TestToneDeviceItem] = Field(..., alias='devices', validation_alias='devices')
    duration: float = Field(..., alias='duration', validation_alias='duration')


class StopTestToneData(APIModel):
    stopped_count: int = Field(..., alias='stoppedCount', validation_alias='stoppedCount')


class SplCalibrationResult(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    calibration_status: str = Field(..., alias='calibrationStatus', validation_alias='calibrationStatus')
