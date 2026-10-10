# -*- coding: utf-8 -*-
"""数字域 RMS→SPL 映射（API 灵敏度域）请求 schema（UC-0902）

区别于 schemas/spl.py（设备 SPLMapping，物理域）：
本文件对应 api_test_service.api_rms_spl_mappings（被测 API 1:N）。
"""
from typing import Any, Dict, Optional

from pydantic import Field

from api_gateway.schemas.base import APIModel


class RmsSplMappingCreateRequest(APIModel):
    api_id: int = Field(...)
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    vendor: Optional[str] = Field(None)
    protocol: Optional[str] = Field(None)
    reference_spl: Optional[float] = Field(None)
    reference_gain_linear: Optional[float] = Field(None)
    calibration_status: Optional[str] = Field(None)
    calibration_data: Optional[Dict[str, Any]] = Field(None)
    min_gain_linear: Optional[float] = Field(None)
    max_gain_linear: Optional[float] = Field(None)


class RmsSplMappingUpdateRequest(APIModel):
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    vendor: Optional[str] = Field(None)
    protocol: Optional[str] = Field(None)
    reference_spl: Optional[float] = Field(None)
    reference_gain_linear: Optional[float] = Field(None)
    calibration_status: Optional[str] = Field(None)
    calibration_data: Optional[Dict[str, Any]] = Field(None)
    min_gain_linear: Optional[float] = Field(None)
    max_gain_linear: Optional[float] = Field(None)


class RmsSplCalibrateRequest(APIModel):
    calibration_data: Dict[str, Any] = Field(..., description='{"points": [{target_spl, gain_linear, rms_dbfs}, ...]}')


class RmsSplSetDefaultRequest(APIModel):
    mapping_id: Optional[int] = Field(None, description='为空/0 表示清除默认映射')
