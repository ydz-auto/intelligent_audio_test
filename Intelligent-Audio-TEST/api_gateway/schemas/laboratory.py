# -*- coding: utf-8 -*-
"""api_gateway 实验室（Laboratory）Schemas —— 契约对照设计文档 §5.1/§5.4.1 与父卡 §4.1

字段以 snake_case 定义（APIModel 序列化输出 snake_case，请求体兼容 camelCase）。
status 用 shared.models.common_enums.LabStatus 枚举校验，拒绝魔法字符串。
"""
from typing import List, Optional

from pydantic import Field, AliasChoices, field_validator

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData
from shared.models.common_enums import LabStatus


class LaboratoryItem(APIModel):
    """实验室列表/详情项（含 gRPC 聚合三计数）"""
    id: int = Field(...)
    code: str = Field(...)
    name: str = Field(...)
    building: Optional[str] = Field(None)
    floor: Optional[str] = Field(None)
    room_number: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: str = Field(...)
    device_count: int = Field(0)
    playback_device_count: int = Field(0)
    test_case_count: int = Field(0)


class LaboratoryListData(PaginatedData[LaboratoryItem]):
    pass


class LaboratorySummaryData(APIModel):
    """实验室资源统计（设计文档 §5.1 summary）"""
    device_count: int = Field(0)
    playback_device_count: int = Field(0)
    test_case_count: int = Field(0)


class LaboratoryIdData(APIModel):
    id: int = Field(...)


class LaboratoryCreateRequest(APIModel):
    code: str = Field(...)
    name: str = Field(...)
    building: Optional[str] = Field(None)
    floor: Optional[str] = Field(None)
    room_number: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: LabStatus = Field(LabStatus.ACTIVE)


class LaboratoryUpdateRequest(APIModel):
    code: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    building: Optional[str] = Field(None)
    floor: Optional[str] = Field(None)
    room_number: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[LabStatus] = Field(None)


class LaboratoryListQuery(APIModel):
    status: Optional[LabStatus] = Field(None)
    page: int = Field(1)
    per_page: Optional[int] = Field(
        None,
        validation_alias=AliasChoices('per_page', 'perPage', 'page_size', 'pageSize'),
    )

    @field_validator('page', mode='before')
    @classmethod
    def _coerce_page(cls, v):
        return int(v) if v is not None and str(v).isdigit() else v

    @field_validator('per_page', mode='before')
    @classmethod
    def _coerce_per_page(cls, v):
        if v is None:
            return None
        return int(v) if str(v).isdigit() else v


class LaboratoryResourcesQuery(APIModel):
    """子资源列表查询（devices/playback_devices/test_cases）"""
    page: int = Field(1)
    per_page: Optional[int] = Field(
        None,
        validation_alias=AliasChoices('per_page', 'perPage', 'page_size', 'pageSize'),
    )
    keyword: Optional[str] = Field(None)
    # test_cases 专属：算法类型过滤（设计文档 §5.4.2）
    algorithm_type: Optional[str] = Field(None)
