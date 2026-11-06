# -*- coding: utf-8 -*-
"""算法分组 Schema

算法分组的创建/更新请求与分组项/列表响应 Schema。
"""
from typing import List, Optional

from pydantic import Field

from api_gateway.schemas.base import APIModel


class AlgorithmGroupCreate(APIModel):
    """创建算法分组请求"""
    name: str = Field(..., min_length=1, max_length=100, description='分组名称')
    description: Optional[str] = Field(None)
    icon: Optional[str] = Field(None, max_length=200, description='图标URL')
    display_order: int = Field(default=0, ge=0, description='排序权重')


class AlgorithmGroupUpdate(APIModel):
    """更新算法分组请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None)
    icon: Optional[str] = Field(None, max_length=200)
    display_order: Optional[int] = Field(None, ge=0)


class AlgorithmGroupItem(APIModel):
    """算法分组项"""
    id: int
    name: str
    description: Optional[str]
    icon: Optional[str]
    display_order: int
    algorithm_count: int
    created_at: Optional[str]
    updated_at: Optional[str]


class AlgorithmGroupListResponse(APIModel):
    """算法分组列表响应"""
    data: List[AlgorithmGroupItem]
    total: int
