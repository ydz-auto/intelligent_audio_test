# -*- coding: utf-8 -*-
"""算法基础定义 Schema

算法定义的创建/更新请求与详情/列表/表单等响应 Schema。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from api_gateway.schemas.base import APIModel


class AlgorithmReferenceParam(APIModel):
    """参考参数"""
    id: Optional[int] = Field(None)
    code: str = Field()
    name: str = Field()
    type: str = Field(default='text')
    help_text: Optional[str] = Field('')


class AlgorithmDefinitionCreate(APIModel):
    """创建算法定义请求"""
    type: str = Field(..., min_length=1, max_length=50, description='算法类型代码')
    name: str = Field(..., min_length=1, max_length=100, description='算法显示名称')
    category: Optional[str] = Field(None, max_length=50, description='分类')
    description: Optional[str] = Field(None)
    status: str = Field(default='online', description='状态')
    icon: Optional[str] = Field(None, max_length=200, description='图标URL')
    display_order: int = Field(default=0, ge=0, description='排序权重')
    group_id: Optional[int] = Field(None, description='分组ID')
    device_params: Optional[List[Dict[str, Any]]] = Field(None, description='设备参数')
    api_params: Optional[List[Dict[str, Any]]] = Field(None, description='API参数')
    case_params: Optional[List[Dict[str, Any]]] = Field(None, description='用例专属参数')
    mappings: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None, description='参数映射')
    associated_dimensions: Optional[List[Dict[str, Any]]] = Field(None, description='关联评估维度')
    reference_params: Optional[List[Dict[str, Any]]] = Field(None, description='参考参数')


class AlgorithmDefinitionUpdate(APIModel):
    """更新算法定义请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    icon: Optional[str] = Field(None, max_length=200)
    display_order: Optional[int] = Field(None, ge=0)
    group_id: Optional[int] = Field(None)
    device_params: Optional[List[Dict[str, Any]]] = Field(None)
    api_params: Optional[List[Dict[str, Any]]] = Field(None)
    case_params: Optional[List[Dict[str, Any]]] = Field(None)
    mappings: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None)
    associated_dimensions: Optional[List[Dict[str, Any]]] = Field(None)


class AlgorithmDefinitionSaveRequest(APIModel):
    """算法定义全量保存请求（INT-589，聚合事务 + 乐观锁）。

    - id: 定义ID（None → 新建；有值 → 按 id 更新）
    - expected_updated_at: 乐观锁版本（更新路径必填，取自最近一次
      AlgorithmDetailResponse.updated_at）；并发覆盖返回 CONFLICT
    - 六类子实体随定义整体落库（幂等，不产生重复子实体）
    """
    id: Optional[int] = Field(None, description='算法定义ID（新建为空）')
    type: Optional[str] = Field(None, max_length=50, description='算法类型代码（新建必填）')
    algorithm_type: Optional[str] = Field(None, max_length=50, description='算法类型代码（与 type 二选一）')
    name: str = Field(..., min_length=1, max_length=100, description='算法显示名称')
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None)
    status: Optional[str] = Field('online', description='状态：online/offline/draft')
    icon: Optional[str] = Field(None, max_length=200)
    display_order: Optional[int] = Field(0, ge=0)
    group_id: Optional[int] = Field(None)
    expected_updated_at: Optional[str] = Field(None, description='乐观锁版本（更新必填）')
    device_params: Optional[List[Dict[str, Any]]] = Field(None)
    api_params: Optional[List[Dict[str, Any]]] = Field(None)
    case_params: Optional[List[Dict[str, Any]]] = Field(None)
    reference_params: Optional[List[Dict[str, Any]]] = Field(None)
    mappings: Optional[Any] = Field(None, description='参数映射（平铺列表或按 source 分组的 dict）')
    associated_dimensions: Optional[List[Dict[str, Any]]] = Field(None, description='关联评估维度')


class AlgorithmDetailResponse(APIModel):
    """算法详情响应"""
    id: int
    type: str
    name: str
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    status: str
    icon: Optional[str] = None
    display_order: int
    device_params: Optional[List[Dict[str, Any]]] = Field(None)
    api_params: Optional[List[Dict[str, Any]]] = Field(None)
    case_params: Optional[List[Dict[str, Any]]] = Field(None)
    params: Optional[List[Dict[str, Any]]] = Field(None)
    mappings: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None)
    associated_dimensions: Optional[List[Dict[str, Any]]] = Field(None)
    dimension_relations: Optional[List[Dict[str, Any]]] = Field(None)
    reference_params: Optional[List[Dict[str, Any]]] = Field(None)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AlgorithmListResponse(APIModel):
    """算法列表响应"""
    data: List[AlgorithmDetailResponse]
    total: int


class AlgorithmFormSchemaResponse(APIModel):
    """算法表单 Schema 响应（用于前端动态表单）"""
    algorithm_type: str = Field()
    algorithm_name: str = Field()
    category: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    groups: List[Dict[str, Any]] = Field()
    fields: List[Dict[str, Any]] = Field()


class AlgorithmParamsResponse(APIModel):
    """算法参数列表响应"""
    parameters: List[Dict[str, Any]]


class AlgorithmOptionsResponse(APIModel):
    """算法选项列表响应（下拉框用）"""
    algorithms: List[Dict[str, Any]]


class AlgorithmAssociateDimensionsRequest(APIModel):
    """关联评估维度请求"""
    dimension_ids: List[int] = Field(..., description='维度ID列表')
    is_default: bool = Field(default=False, description='是否默认')
    weight: float = Field(default=1.0, ge=0, description='权重')


class ReloadConfigResponse(APIModel):
    """重新加载配置响应"""
    success: bool = Field()
    message: str = Field()
    reload_time: Optional[datetime] = Field(None)


class AlgorithmImportRequest(APIModel):
    """导入算法配置请求"""
    algorithms: List[Dict[str, Any]] = Field()


class BulkDeleteRequest(APIModel):
    """批量删除请求"""
    algorithm_types: List[str] = Field(..., description='要删除的算法类型列表')


class AlgorithmDeleteResponse(APIModel):
    """删除算法响应"""
    deleted_types: List[str]
    message: str
