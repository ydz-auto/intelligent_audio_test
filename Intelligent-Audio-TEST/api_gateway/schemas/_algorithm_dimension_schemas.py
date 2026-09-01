# -*- coding: utf-8 -*-
"""算法维度关联与参数映射 Schema

评估维度参数 CRUD、算法维度关联、参数映射 CRUD 及维度关联请求 Schema。
"""
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from api_gateway.schemas.base import APIModel


# ========== 评估维度参数 ==========

class EvaluationDimensionParamCreate(APIModel):
    """创建评估维度参数请求"""
    dimension_id: int = Field(..., description='关联评估维度ID')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    field_type: str = Field(default='text', description='字段类型：text, audio, number, boolean, json, timestamp')
    param_direction: str = Field(default='input', description='参数方向：input, output')
    field_path: Optional[str] = Field(None, description='结果提取路径（output专用）')
    agg_role: Optional[str] = Field(None, description='聚合角色（output专用）：numerator/denominator/value')
    required: bool = Field(default=True, description='是否必填')
    default_value: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0, ge=0, description='界面排序')


class EvaluationDimensionParamUpdate(APIModel):
    """更新评估维度参数请求"""
    param_name: Optional[str] = Field(None, max_length=100)
    label: Optional[str] = Field(None, max_length=100)
    field_type: Optional[str] = Field(None)
    param_direction: Optional[str] = Field(None)
    field_path: Optional[str] = Field(None)
    agg_role: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)


class EvaluationDimensionParamItem(APIModel):
    """评估维度参数项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    dimension_id: int
    dimension_name: Optional[str]
    param_code: str
    param_name: Optional[str]
    label: Optional[str]
    field_type: str
    param_direction: str
    field_path: Optional[str]
    agg_role: Optional[str]
    required: bool
    default_value: Optional[Any]
    help_text: Optional[str]
    ui_order: int


class EvaluationDimensionParamListResponse(APIModel):
    """评估维度参数列表响应"""
    data: List['EvaluationDimensionParamItem']
    total: int


# ========== 算法维度关联 ==========

class AlgorithmDimensionRelationCreate(APIModel):
    """创建算法维度关联请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    dimension_id: int = Field(..., description='关联评估维度ID')
    is_default: bool = Field(default=False, description='是否默认评估维度')
    weight: float = Field(default=1.0, ge=0, description='权重')


class AlgorithmDimensionRelationUpdate(APIModel):
    """更新算法维度关联请求"""
    is_default: Optional[bool] = Field(None)
    weight: Optional[float] = Field(None, ge=0)


class AlgorithmDimensionRelationItem(APIModel):
    """算法维度关联项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    algorithm_type: str
    dimension_id: int
    is_default: bool
    weight: float


class AlgorithmDimensionRelationListResponse(APIModel):
    """算法维度关联列表响应"""
    data: List['AlgorithmDimensionRelationItem']
    total: int


# ========== 维度关联请求（统一入口） ==========

class AssociateDimensionsRequest(APIModel):
    """关联评估维度请求"""
    dimensions: List[Dict[str, Any]] = Field(default=[])


class DimensionRelationCreateRequest(APIModel):
    """创建维度关联请求"""
    algorithm_type: str = Field(...)
    dimension_id: int = Field(...)
    is_default: bool = Field(default=False)
    weight: float = Field(default=1.0)


class DimensionRelationUpdateRequest(APIModel):
    """更新维度关联请求"""
    algorithm_type: Optional[str] = Field(None)
    weight: Optional[float] = Field(None, ge=0)
    is_default: Optional[bool] = Field(None)
    dimension_id: Optional[int] = Field(None)


# ========== 参数映射 ==========

class ParamMappingCreate(APIModel):
    """创建参数映射请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    source_type: str = Field(..., description='源类型：device, api')
    source_param: str = Field(..., min_length=1, max_length=50, description='源参数代码')
    source_direction: str = Field(default='output', description='源参数方向：input, output')
    dimension_id: int = Field(..., description='目标评估维度ID')
    target_param: str = Field(..., min_length=1, max_length=50, description='目标评估维度参数代码')
    transform_type: str = Field(default='none', description='转换类型：none, uppercase, lowercase, json_parse, base64')


class ParamMappingUpdate(APIModel):
    """更新参数映射请求"""
    source_type: Optional[str] = Field(None)
    source_param: Optional[str] = Field(None)
    source_direction: Optional[str] = Field(None)
    dimension_id: Optional[int] = Field(None)
    target_param: Optional[str] = Field(None)
    transform_type: Optional[str] = Field(None)


class ParamMappingItem(APIModel):
    """参数映射项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    algorithm_type: str
    source_type: str
    source_param: str
    source_direction: str
    dimension_id: int
    dimension_name: Optional[str]
    target_param: str
    transform_type: str


class ParamMappingListResponse(APIModel):
    """参数映射列表响应"""
    data: List[ParamMappingItem]
    total: int


# ========== 映射请求（统一入口） ==========

class MappingCreateRequest(APIModel):
    """创建参数映射请求"""
    algorithm_type: str = Field(...)
    source_type: str = Field(...)
    source_param: str = Field(...)
    source_direction: str = Field(default='output')
    dimension_id: Optional[int] = Field(None)
    target_param: str = Field(...)
    transform_type: str = Field(default='none')


class MappingUpdateRequest(APIModel):
    """更新参数映射请求"""
    source_type: Optional[str] = Field(None)
    source_param: Optional[str] = Field(None)
    source_direction: Optional[str] = Field(None)
    dimension_id: Optional[int] = Field(None)
    target_param: Optional[str] = Field(None)
    transform_type: Optional[str] = Field(None)


class AlgorithmMappingListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
    source_type: Optional[str] = Field(None)
    dimension_id: Optional[int] = Field(None)
