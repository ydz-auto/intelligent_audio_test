from typing import Any, Dict, List, Optional
from pydantic import Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class CalibrationPointSchema(APIModel):
    spl: Optional[float] = Field(None)
    gain_offset: Optional[float] = Field(None)
    digital_gain: Optional[float] = Field(None)
    base_level: Optional[float] = Field(None)
    final_level: Optional[float] = Field(None)


class CalibrationDataSchema(APIModel):
    points: List[CalibrationPointSchema] = Field(default_factory=list)


class SPLMappingQueryRequest(APIModel):
    keyword: Optional[str] = Field(None)
    search: Optional[str] = Field(None)
    calibration_status: Optional[str] = Field(None)
    page: Optional[int] = Field(1)
    per_page: Optional[int] = Field(10)
    device_id: Optional[int] = Field(None)


class SPLMappingCreateRequest(APIModel):
    name: str = Field(...)
    description: Optional[str] = Field(None)
    device_id: Optional[int] = Field(None)
    device_type: Optional[str] = Field(None)
    distance: Optional[float] = Field(1.0)
    target_spl: Optional[float] = Field(None)
    digital_gain: Optional[float] = Field(None)
    test_frequency: Optional[int] = Field(1000)
    calibration_status: Optional[str] = Field(None)
    calibration_data: Optional[Dict[str, Any]] = Field(None)


class SPLMappingUpdateRequest(APIModel):
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    device_id: Optional[int] = Field(None)
    device_type: Optional[str] = Field(None)
    distance: Optional[float] = Field(None)
    target_spl: Optional[float] = Field(None)
    digital_gain: Optional[float] = Field(None)
    test_frequency: Optional[int] = Field(None)
    calibration_status: Optional[str] = Field(None)
    calibration_data: Optional[Dict[str, Any]] = Field(None)
    is_current: Optional[bool] = Field(None)


class PlayTestToneRequest(APIModel):
    gain_value: Optional[float] = Field(50)
    gain_offset: Optional[float] = Field(None)
    target_spl: Optional[float] = Field(65)
    unique_id: Optional[str] = Field(None)


class StopTestToneRequest(APIModel):
    unique_id: Optional[str] = Field(None)


class SplMappingItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    device_id: Optional[int] = Field(None)
    device: Optional[Dict[str, Any]] = Field(None)
    device_name: Optional[str] = Field(None)
    device_model: Optional[str] = Field(None)
    device_type: Optional[str] = Field(None)
    distance: Optional[float] = Field(None)
    target_spl: Optional[float] = Field(None)
    digital_gain: Optional[float] = Field(None)
    calibration_status: Optional[str] = Field(None)
    test_frequency: Optional[int] = Field(None)
    calibration_data: Optional[Dict[str, Any]] = Field(None)
    is_current: Optional[bool] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class SplMappingListData(PaginatedData[SplMappingItem]):
    pass


class SplHistoryItem(APIModel):
    id: int = Field(...)
    calibration_data: Optional[Dict[str, Any]] = Field(None)
    distance: Optional[float] = Field(None)
    test_frequency: Optional[int] = Field(None)
    created_at: Optional[str] = Field(None)


class SplHistoryData(APIModel):
    items: List[SplHistoryItem] = Field(...)
    total: int = Field(...)


class SplStatsData(APIModel):
    total: int = Field(...)
    calibrated: int = Field(...)
    uncalibrated: int = Field(...)
    associated_devices: int = Field(...)


class SplByDeviceItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    device_id: Optional[int] = Field(None)
    device_type: Optional[str] = Field(None)
    distance: Optional[float] = Field(None)
    target_spl: Optional[float] = Field(None)
    calibration_status: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class SplByDeviceData(APIModel):
    items: List[SplByDeviceItem] = Field(...)
    total: int = Field(...)


class TestToneDeviceItem(APIModel):
    device: Any = Field(...)
    gain_db: float = Field(...)
    final_dbfs: float = Field(...)
    target_spl: float = Field(...)


class PlayTestToneData(APIModel):
    devices: List[TestToneDeviceItem] = Field(...)
    duration: float = Field(...)


class StopTestToneData(APIModel):
    stopped_count: int = Field(...)


class SplCalibrationResult(APIModel):
    id: int = Field(...)
    calibration_status: str = Field(...)
