# -*- coding: utf-8 -*-
"""
算法配置 Schema 定义

定义算法配置相关的请求/响应 Schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import Field, ConfigDict

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


class ParamMappingCreate(APIModel):
    """创建参数映射请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    component_type: str = Field(..., description='组件类型')
    direction: str = Field(default='input', description='方向：input, output')
    field_type: str = Field(default='text', description='字段类型：text, audio, number, boolean, json')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    source_param: str = Field(..., min_length=1, max_length=50, description='源参数')
    target_key: str = Field(..., min_length=1, max_length=50, description='目标参数')
    transform_type: str = Field(default='none', description='转换类型')


class ParamMappingUpdate(APIModel):
    """更新参数映射请求"""
    component_type: Optional[str] = None
    direction: Optional[str] = None
    field_type: Optional[str] = None
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    source_param: Optional[str] = None
    target_key: Optional[str] = None
    transform_type: Optional[str] = None


class AlgorithmDimensionRelationCreate(APIModel):
    """创建算法维度关联请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    dimension_id: int = Field(..., description='维度ID')
    is_default: bool = Field(default=False)
    weight: float = Field(default=1.0, ge=0)


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


# ========== 算法分组 ==========

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


# ========== API 参数 ==========

class AlgorithmApiParamCreate(APIModel):
    """创建API参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(..., description='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction: str = Field(default='input', description='方向：input, output')
    required: bool = Field(default=False, description='是否必填')
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None, description='选项来源')
    options_field: Optional[str] = Field(None, description='选项值字段')
    options_label_field: Optional[str] = Field(None, description='选项显示字段')
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0, ge=0, description='界面排序')
    hidden: bool = Field(default=False, description='是否隐藏')


class AlgorithmApiParamUpdate(APIModel):
    """更新API参数请求"""
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


class AlgorithmApiParamItem(APIModel):
    """API参数项"""
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


class AlgorithmApiParamListResponse(APIModel):
    """API参数列表响应"""
    data: List[AlgorithmApiParamItem]
    total: int


# ========== 用例专属参数 ==========

class CaseAlgorithmParamCreate(APIModel):
    """创建用例专属参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(default='text', description='参数类型：text, number, textarea, slider, switch, audio_select, device_select, json')
    required: bool = Field(default=False, description='是否必填')
    default_value: Optional[str] = Field(None, description='默认值（JSON格式）')
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0, ge=0, description='界面排序')
    hidden: bool = Field(default=False, description='是否隐藏')
    scope: str = Field(default='common', max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')
    min_value: Optional[float] = Field(None, description='最小值 (slider/number)')
    max_value: Optional[float] = Field(None, description='最大值 (slider/number)')
    step: Optional[float] = Field(None, description='步长 (slider/number)')
    unit: Optional[str] = Field(None, max_length=20, description='单位显示 (如 cm, dB, s)')


class CaseAlgorithmParamUpdate(APIModel):
    """更新用例专属参数请求"""
    param_name: Optional[str] = Field(None, max_length=100)
    label: Optional[str] = Field(None, max_length=100)
    param_type: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    hidden: Optional[bool] = Field(None)
    scope: Optional[str] = Field(None, max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')
    min_value: Optional[float] = Field(None, description='最小值 (slider/number)')
    max_value: Optional[float] = Field(None, description='最大值 (slider/number)')
    step: Optional[float] = Field(None, description='步长 (slider/number)')
    unit: Optional[str] = Field(None, max_length=20, description='单位显示 (如 cm, dB, s)')


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
    data: List[EvaluationDimensionParamItem]
    total: int


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
    data: List[AlgorithmDimensionRelationItem]
    total: int


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


class CaseParamCreateRequest(APIModel):
    """创建用例专属参数请求"""
    algorithm_type: str = Field(...)
    param_code: str = Field(...)
    param_name: Optional[str] = Field(None)
    label: Optional[str] = Field(None)
    param_type: str = Field(default='text')
    required: bool = Field(default=False)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None)
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0)
    hidden: bool = Field(default=False)
    scope: str = Field(default='common', max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')


class CaseParamUpdateRequest(APIModel):
    """更新用例专属参数请求"""
    param_name: Optional[str] = Field(None)
    label: Optional[str] = Field(None)
    param_type: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None)
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    hidden: Optional[bool] = Field(None)
    scope: Optional[str] = Field(None, max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')


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


class ExtractParamsRequest(APIModel):
    """提取用例算法参数请求"""
    case_config: Dict[str, Any] = Field(default={})


class AlgorithmListQuery(APIModel):
    status: Optional[str] = Field(None)
    group_id: Optional[int] = Field(None)


class AlgorithmParamListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
    param_type: str = Field('device')


class AlgorithmMappingListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
    source_type: Optional[str] = Field(None)
    dimension_id: Optional[int] = Field(None)


class AlgorithmCaseParamListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
    scope: Optional[str] = Field(None)


class AlgorithmReferenceParamListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None)
