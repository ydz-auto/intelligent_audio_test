# -*- coding: utf-8 -*-
"""算法参数 Schema（通用参数 / 设备参数 / 参考参数请求 / 列表查询）

算法参数创建/更新、设备参数 CRUD、参考参数请求及各类算法参数列表查询 Schema。
"""
from typing import Any, List, Optional

from pydantic import ConfigDict, Field

from api_gateway.schemas.base import APIModel


# ========== 通用算法参数 ==========

class AlgorithmParamCreate(APIModel):
    """创建算法参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(..., description='参数类型')
    required: bool = Field(default=False)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None, description='选项来源')
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    component: Optional[str] = Field(None, description='前端组件')
    ui_order: int = Field(default=0, ge=0)
    ui_group: str = Field(default='basic', max_length=50)
    hidden: bool = Field(default=False)


class AlgorithmParamUpdate(APIModel):
    """更新算法参数请求"""
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None)
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    ui_group: Optional[str] = Field(None)
    hidden: Optional[bool] = Field(None)


# ========== 设备参数 ==========

class AlgorithmDeviceParamCreate(APIModel):
    """创建设备参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(..., description='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction: str = Field(default='input', description='方向：input, output')
    required: bool = Field(default=False, description='是否必填')
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None, description='选项来源：NULL=静态, translation_directions=翻译方向表, languages=语言表')
    options_field: Optional[str] = Field(None, description='选项值字段')
    options_label_field: Optional[str] = Field(None, description='选项显示字段')
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0, ge=0, description='界面排序')
    hidden: bool = Field(default=False, description='是否隐藏')


class AlgorithmDeviceParamUpdate(APIModel):
    """更新设备参数请求"""
    param_code: Optional[str] = Field(None, max_length=50)
    param_name: Optional[str] = Field(None, max_length=100)
    label: Optional[str] = Field(None, max_length=100)
    param_type: Optional[str] = Field(None)
    direction: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None)
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    hidden: Optional[bool] = Field(None)


class AlgorithmDeviceParamItem(APIModel):
    """设备参数项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    algorithm_type: str
    param_code: str
    param_name: Optional[str]
    label: Optional[str]
    param_type: str
    direction: str
    required: bool
    default_value: Optional[Any]
    options_source: Optional[str]
    options_field: Optional[str]
    options_label_field: Optional[str]
    validation: Optional[Any]
    help_text: Optional[str]
    ui_order: int
    hidden: bool


class AlgorithmDeviceParamListResponse(APIModel):
    """设备参数列表响应"""
    data: List[AlgorithmDeviceParamItem]
    total: int


# ========== 参数请求（统一入口） ==========

class ParamCreateRequest(APIModel):
    """创建参数请求"""
    algorithm_type: str = Field(...)
    param_code: str = Field(...)
    param_name: Optional[str] = Field(None)
    label: Optional[str] = Field(None)
    param_type: str = Field(default='text')
    direction: str = Field(default='input')
    required: bool = Field(default=False)
    default_value: Optional[str] = Field(None)
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0)
    hidden: bool = Field(default=False)
    param_type_source: Optional[str] = Field(default='device')


class ParamUpdateRequest(APIModel):
    """更新参数请求"""
    param_code: Optional[str] = Field(None)
    param_name: Optional[str] = Field(None)
    label: Optional[str] = Field(None)
    param_type: Optional[str] = Field(None)
    direction: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    hidden: Optional[bool] = Field(None)


class ReferenceParamCreateRequest(APIModel):
    """创建参考参数请求"""
    algorithm_type: str = Field(...)
    code: str = Field(...)
    name: Optional[str] = Field(None)
    type: str = Field(default='text')
    annotation_code: Optional[str] = Field(None)
    annotation_format: Optional[str] = Field(None)
    field_path: Optional[str] = Field(None)
    merge_mode: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)


class ReferenceParamUpdateRequest(APIModel):
    """更新参考参数请求"""
    algorithm_type: Optional[str] = Field(None)
    code: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    annotation_code: Optional[str] = Field(None)
    annotation_format: Optional[str] = Field(None)
    field_path: Optional[str] = Field(None)
    merge_mode: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)


# ========== 列表查询 ==========

class AlgorithmListQuery(APIModel):
    status: Optional[str] = Field(None)
    group_id: Optional[int] = Field(None)


class AlgorithmParamListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
    param_type: str = Field('device')


class AlgorithmCaseParamListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
    scope: Optional[str] = Field(None)


class AlgorithmReferenceParamListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
