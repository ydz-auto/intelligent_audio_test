# -*- coding: utf-8 -*-
"""api_gateway 实验室（Laboratory）Schemas —— INT-655 契约（设计文档 §5.1/§5.4.1）

字段以 snake_case 定义（APIModel 序列化输出 snake_case，请求体兼容 camelCase）。
status 用 shared.models.common_enums.LaboratoryStatus 枚举校验，拒绝魔法字符串。

注（集成合并，INT-680）：文件同时保留 INT-493/537 旧实现的只读侧 schema 类
（LaboratoryResourcesQuery / LaboratoryCreateRequest / LaboratoryUpdateRequest /
LaboratoryIdData），供旧应用层服务（api_gateway/application/services/laboratory/）
在替换过渡期内保持可导入；新路由（INT-655）不消费这些旧类。
"""
from typing import List, Optional

from pydantic import Field, AliasChoices, field_validator

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData
from shared.models.common_enums import LaboratoryStatus, LabStatus


class LaboratoryListQuery(APIModel):
    page: int = Field(1)
    per_page: int = Field(10)
    keyword: Optional[str] = Field(None)
    status: Optional[str] = Field(None)

    @field_validator('status', mode='before')
    @classmethod
    def _validate_status(cls, value):
        """status 枚举校验：空/未知值 → None（不过滤）；非法显式值 → ValidationError → 400"""
        if value is None or value == '':
            return None
        try:
            return LaboratoryStatus(value).value
        except ValueError:
            raise ValueError(f"状态 status 非法: {value!r}，合法值: {[s.value for s in LaboratoryStatus]}")


class LaboratoryItem(APIModel):
    id: int = Field(...)
    code: str = Field(...)
    name: str = Field(...)
    building: Optional[str] = Field(None)
    floor: Optional[str] = Field(None)
    room_number: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    device_count: int = Field(0)
    playback_device_count: int = Field(0)
    test_case_count: int = Field(0)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class LaboratoryListData(PaginatedData[LaboratoryItem]):
    pass


class LaboratoryCreateSchema(APIModel):
    code: str = Field(...)
    name: str = Field(...)
    building: Optional[str] = Field(None)
    floor: Optional[str] = Field(None)
    room_number: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field('active')

    @field_validator('status', mode='before')
    @classmethod
    def _validate_status(cls, value):
        if value is None or value == '':
            return LaboratoryStatus.ACTIVE.value
        try:
            return LaboratoryStatus(value).value
        except ValueError:
            raise ValueError(f"状态 status 非法: {value!r}，合法值: {[s.value for s in LaboratoryStatus]}")


class LaboratoryUpdateSchema(APIModel):
    code: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    building: Optional[str] = Field(None)
    floor: Optional[str] = Field(None)
    room_number: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)

    @field_validator('status', mode='before')
    @classmethod
    def _validate_status(cls, value):
        if value is None or value == '':
            return None
        try:
            return LaboratoryStatus(value).value
        except ValueError:
            raise ValueError(f"状态 status 非法: {value!r}，合法值: {[s.value for s in LaboratoryStatus]}")


class LaboratorySummaryData(APIModel):
    device_count: int = Field(0)
    playback_device_count: int = Field(0)
    test_case_count: int = Field(0)


# ============ 以下为 INT-493/INT-537 旧实现保留的 schema（过渡期可导入） ============


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
