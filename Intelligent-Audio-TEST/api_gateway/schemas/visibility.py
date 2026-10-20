# -*- coding: utf-8 -*-
"""数据可见性（INT-423/466）共享端点请求体。"""
from typing import Optional

from pydantic import Field

from api_gateway.schemas.base import APIModel


class VisibilityUpdateRequest(APIModel):
    """`PATCH /{id}/visibility` 请求体：目标可见性值。"""
    visibility: str = Field(..., description='shared / private')


class VisibilityUpdateData(APIModel):
    id: Optional[object] = Field(None, description='资源 ID（task_id / tc_id / group_id / tag_id / report_id / dim_id）')
    visibility: Optional[str] = Field(None)
