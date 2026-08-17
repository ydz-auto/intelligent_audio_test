# -*- coding: utf-8 -*-
"""
算法配置 Schema 定义

定义算法配置相关的请求/响应 Schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, AliasChoices

from backend.schemas.base import APIModel


class AlgorithmReferenceParam(BaseModel):
    """参考参数"""
    id: Optional[int] = Field(None, validation_alias='id')
    code: str = Field(validation_alias='code', alias='code')
    name: str = Field(validation_alias='name', alias='name')
    type: str = Field(default='text', validation_alias='type')
    help_text: Optional[str] = Field('', validation_alias='helpText')

    model_config = {'populate_by_name': True}


class AlgorithmDefinitionCreate(BaseModel):
    """创建算法定义请求"""
    type: str = Field(..., min_length=1, max_length=50, description='算法类型代码', validation_alias='type')
    name: str = Field(..., min_length=1, max_length=100, description='算法显示名称', validation_alias='name')
    category: Optional[str] = Field(None, max_length=50, description='分类', validation_alias='category')
    description: Optional[str] = Field(None, validation_alias='description')
    status: str = Field(default='online', description='状态', validation_alias='status')
    icon: Optional[str] = Field(None, max_length=200, description='图标URL', validation_alias='icon')
    display_order: int = Field(default=0, ge=0, description='排序权重', validation_alias='displayOrder')
    group_id: Optional[int] = Field(None, description='分组ID', validation_alias='groupId')
    device_params: Optional[List[Dict[str, Any]]] = Field(None, description='设备参数', validation_alias='deviceParams')
    api_params: Optional[List[Dict[str, Any]]] = Field(None, description='API参数', validation_alias='apiParams')
    case_params: Optional[List[Dict[str, Any]]] = Field(None, description='用例专属参数', validation_alias='caseParams')
    mappings: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None, description='参数映射', validation_alias='mappings')
    associated_dimensions: Optional[List[Dict[str, Any]]] = Field(None, description='关联评估维度', validation_alias='associatedDimensions')
    reference_params: Optional[List[Dict[str, Any]]] = Field(None, description='参考参数', validation_alias='referenceParams')

    model_config = {'populate_by_name': True}


class AlgorithmDefinitionUpdate(BaseModel):
    """更新算法定义请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, validation_alias='name')
    category: Optional[str] = Field(None, max_length=50, validation_alias='category')
    description: Optional[str] = Field(None, validation_alias='description')
    status: Optional[str] = Field(None, validation_alias='status')
    icon: Optional[str] = Field(None, max_length=200, validation_alias='icon')
    display_order: Optional[int] = Field(None, ge=0, validation_alias='displayOrder')
    group_id: Optional[int] = Field(None, validation_alias='groupId')
    device_params: Optional[List[Dict[str, Any]]] = Field(None, validation_alias='deviceParams')
    api_params: Optional[List[Dict[str, Any]]] = Field(None, validation_alias='apiParams')
    case_params: Optional[List[Dict[str, Any]]] = Field(None, validation_alias='caseParams')
    mappings: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None, validation_alias='mappings')
    associated_dimensions: Optional[List[Dict[str, Any]]] = Field(None, validation_alias='associatedDimensions')

    model_config = {'populate_by_name': True}


class AlgorithmParamCreate(BaseModel):
    """创建算法参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型', validation_alias='algorithmType')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码', validation_alias='paramCode')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称', validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(..., description='参数类型', validation_alias='paramType')
    required: bool = Field(default=False, validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue', alias='defaultValue')
    options_source: Optional[str] = Field(None, description='选项来源', validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, validation_alias='optionsField', alias='optionsField')
    options_label_field: Optional[str] = Field(None, validation_alias='optionsLabelField', alias='optionsLabelField')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules', alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText', alias='helpText')
    component: Optional[str] = Field(None, description='前端组件')
    ui_order: int = Field(default=0, ge=0, validation_alias='uiOrder', alias='uiOrder')
    ui_group: str = Field(default='basic', max_length=50, validation_alias='uiGroup', alias='uiGroup')
    hidden: bool = Field(default=False)

    model_config = {'populate_by_name': True}


class AlgorithmParamUpdate(BaseModel):
    """更新算法参数请求"""
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称', validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: Optional[str] = Field(None, validation_alias='paramType')
    required: Optional[bool] = Field(None, validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    options_source: Optional[str] = Field(None, validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, validation_alias='optionsField')
    options_label_field: Optional[str] = Field(None, validation_alias='optionsLabelField')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: Optional[int] = Field(None, validation_alias='uiOrder')
    ui_group: Optional[str] = Field(None, validation_alias='uiGroup')
    hidden: Optional[bool] = Field(None, validation_alias='hidden')

    model_config = {'populate_by_name': True}


class ParamMappingCreate(BaseModel):
    """创建参数映射请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    component_type: str = Field(..., description='组件类型')
    direction: str = Field(default='input', description='方向：input, output')
    field_type: str = Field(default='text', description='字段类型：text, audio, number, boolean, json')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    source_param: str = Field(..., min_length=1, max_length=50, description='源参数')
    target_key: str = Field(..., min_length=1, max_length=50, description='目标参数')
    transform_type: str = Field(default='none', description='转换类型')

    model_config = {'populate_by_name': True}


class ParamMappingUpdate(BaseModel):
    """更新参数映射请求"""
    component_type: Optional[str] = None
    direction: Optional[str] = None
    field_type: Optional[str] = None
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    source_param: Optional[str] = None
    target_key: Optional[str] = None
    transform_type: Optional[str] = None

    model_config = {'populate_by_name': True}


class AlgorithmDimensionRelationCreate(BaseModel):
    """创建算法维度关联请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    dimension_id: int = Field(..., description='维度ID')
    is_default: bool = Field(default=False)
    weight: float = Field(default=1.0, ge=0)


class AlgorithmDetailResponse(BaseModel):
    """算法详情响应"""
    model_config = {'populate_by_name': True}

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
    device_params: Optional[List[Dict[str, Any]]] = Field(None, alias='deviceParams', validation_alias='deviceParams')
    api_params: Optional[List[Dict[str, Any]]] = Field(None, alias='apiParams', validation_alias='apiParams')
    case_params: Optional[List[Dict[str, Any]]] = Field(None, alias='caseParams', validation_alias='caseParams')
    params: Optional[List[Dict[str, Any]]] = Field(None, alias='params', validation_alias='params')
    mappings: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None, alias='mappings', validation_alias='mappings')
    associated_dimensions: Optional[List[Dict[str, Any]]] = Field(None, alias='associatedDimensions', validation_alias='associatedDimensions')
    dimension_relations: Optional[List[Dict[str, Any]]] = Field(None, alias='dimensionRelations', validation_alias='dimensionRelations')
    reference_params: Optional[List[Dict[str, Any]]] = Field(None, alias='referenceParams', validation_alias='referenceParams')
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AlgorithmListResponse(BaseModel):
    """算法列表响应"""
    data: List[AlgorithmDetailResponse]
    total: int


class AlgorithmFormSchemaResponse(BaseModel):
    """算法表单 Schema 响应（用于前端动态表单）"""
    algorithm_type: str = Field(validation_alias='algorithmType', alias='algorithmType')
    algorithm_name: str = Field(validation_alias='algorithmName', alias='algorithmName')
    category: Optional[str] = Field(None, validation_alias='category', alias='category')
    description: Optional[str] = Field(None, validation_alias='description', alias='description')
    groups: List[Dict[str, Any]] = Field(validation_alias='groups', alias='groups')
    fields: List[Dict[str, Any]] = Field(validation_alias='fields', alias='fields')


class AlgorithmParamsResponse(BaseModel):
    """算法参数列表响应"""
    parameters: List[Dict[str, Any]]


class AlgorithmOptionsResponse(BaseModel):
    """算法选项列表响应（下拉框用）"""
    algorithms: List[Dict[str, Any]]


class AlgorithmAssociateDimensionsRequest(BaseModel):
    """关联评估维度请求"""
    dimension_ids: List[int] = Field(..., description='维度ID列表', validation_alias='dimensionIds')
    is_default: bool = Field(default=False, description='是否默认', validation_alias='isDefault')
    weight: float = Field(default=1.0, ge=0, description='权重', validation_alias='weight')

    model_config = {'populate_by_name': True}


class ReloadConfigResponse(BaseModel):
    """重新加载配置响应"""
    success: bool = Field(validation_alias='success', alias='success')
    message: str = Field(validation_alias='message', alias='message')
    reload_time: Optional[datetime] = Field(None, validation_alias='reloadTime', alias='reloadTime')


class AlgorithmImportRequest(BaseModel):
    """导入算法配置请求"""
    algorithms: List[Dict[str, Any]] = Field(validation_alias='algorithms', alias='algorithms')


class BulkDeleteRequest(BaseModel):
    """批量删除请求"""
    algorithm_types: List[str] = Field(..., description='要删除的算法类型列表', validation_alias='algorithmTypes')


class AlgorithmDeleteResponse(BaseModel):
    """删除算法响应"""
    deleted_types: List[str]
    message: str


# ========== 算法分组 ==========

class AlgorithmGroupCreate(BaseModel):
    """创建算法分组请求"""
    name: str = Field(..., min_length=1, max_length=100, description='分组名称', validation_alias='name')
    description: Optional[str] = Field(None, validation_alias='description')
    icon: Optional[str] = Field(None, max_length=200, description='图标URL', validation_alias='icon')
    display_order: int = Field(default=0, ge=0, description='排序权重', validation_alias='displayOrder')

    model_config = {'populate_by_name': True}


class AlgorithmGroupUpdate(BaseModel):
    """更新算法分组请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, validation_alias='name')
    description: Optional[str] = Field(None, validation_alias='description')
    icon: Optional[str] = Field(None, max_length=200, validation_alias='icon')
    display_order: Optional[int] = Field(None, ge=0, validation_alias='displayOrder')

    model_config = {'populate_by_name': True}


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


class AlgorithmGroupListResponse(BaseModel):
    """算法分组列表响应"""
    data: List[AlgorithmGroupItem]
    total: int


# ========== 设备参数 ==========

class AlgorithmDeviceParamCreate(BaseModel):
    """创建设备参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型', validation_alias='algorithmType')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码', validation_alias='paramCode')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称', validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(..., description='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json', validation_alias='paramType')
    direction: str = Field(default='input', description='方向：input, output', validation_alias='direction')
    required: bool = Field(default=False, description='是否必填', validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    options_source: Optional[str] = Field(None, description='选项来源：NULL=静态, translation_directions=翻译方向表, languages=语言表', validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, description='选项值字段', validation_alias='optionsField')
    options_label_field: Optional[str] = Field(None, description='选项显示字段', validation_alias='optionsLabelField')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: int = Field(default=0, ge=0, description='界面排序', validation_alias='uiOrder')
    hidden: bool = Field(default=False, description='是否隐藏', validation_alias='hidden')

    model_config = {'populate_by_name': True}


class AlgorithmDeviceParamUpdate(BaseModel):
    """更新设备参数请求"""
    param_code: Optional[str] = Field(None, max_length=50, validation_alias='paramCode')
    param_name: Optional[str] = Field(None, max_length=100, validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, validation_alias='label')
    param_type: Optional[str] = Field(None, validation_alias='paramType')
    direction: Optional[str] = Field(None, validation_alias='direction')
    required: Optional[bool] = Field(None, validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    options_source: Optional[str] = Field(None, validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, validation_alias='optionsField')
    options_label_field: Optional[str] = Field(None, validation_alias='optionsLabelField')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: Optional[int] = Field(None, validation_alias='uiOrder')
    hidden: Optional[bool] = Field(None, validation_alias='hidden')

    model_config = {'populate_by_name': True}


class AlgorithmDeviceParamItem(BaseModel):
    """设备参数项"""
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

    class Config:
        from_attributes = True


class AlgorithmDeviceParamListResponse(BaseModel):
    """设备参数列表响应"""
    data: List[AlgorithmDeviceParamItem]
    total: int


# ========== API 参数 ==========

class AlgorithmApiParamCreate(BaseModel):
    """创建API参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型', validation_alias='algorithmType')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码', validation_alias='paramCode')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称', validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(..., description='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json', validation_alias='paramType')
    direction: str = Field(default='input', description='方向：input, output', validation_alias='direction')
    required: bool = Field(default=False, description='是否必填', validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    options_source: Optional[str] = Field(None, description='选项来源', validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, description='选项值字段', validation_alias='optionsField')
    options_label_field: Optional[str] = Field(None, description='选项显示字段', validation_alias='optionsLabelField')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: int = Field(default=0, ge=0, description='界面排序', validation_alias='uiOrder')
    hidden: bool = Field(default=False, description='是否隐藏', validation_alias='hidden')

    model_config = {'populate_by_name': True}


class AlgorithmApiParamUpdate(BaseModel):
    """更新API参数请求"""
    param_code: Optional[str] = Field(None, max_length=50, validation_alias='paramCode')
    param_name: Optional[str] = Field(None, max_length=100, validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, validation_alias='label')
    param_type: Optional[str] = Field(None, validation_alias='paramType')
    direction: Optional[str] = Field(None, validation_alias='direction')
    required: Optional[bool] = Field(None, validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    options_source: Optional[str] = Field(None, validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, validation_alias='optionsField')
    options_label_field: Optional[str] = Field(None, validation_alias='optionsLabelField')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: Optional[int] = Field(None, validation_alias='uiOrder')
    hidden: Optional[bool] = Field(None, validation_alias='hidden')

    model_config = {'populate_by_name': True}


class AlgorithmApiParamItem(BaseModel):
    """API参数项"""
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

    class Config:
        from_attributes = True


class AlgorithmApiParamListResponse(BaseModel):
    """API参数列表响应"""
    data: List[AlgorithmApiParamItem]
    total: int


# ========== 用例专属参数 ==========

class CaseAlgorithmParamCreate(BaseModel):
    """创建用例专属参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型', validation_alias='algorithmType')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码', validation_alias='paramCode')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称', validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(default='text', description='参数类型：text, number, textarea, slider, switch, audio_select, device_select, json', validation_alias='paramType')
    required: bool = Field(default=False, description='是否必填', validation_alias='required')
    default_value: Optional[str] = Field(None, description='默认值（JSON格式）', validation_alias='defaultValue')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: int = Field(default=0, ge=0, description='界面排序', validation_alias='uiOrder')
    hidden: bool = Field(default=False, description='是否隐藏', validation_alias='hidden')
    scope: str = Field(default='common', max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')
    min_value: Optional[float] = Field(None, description='最小值 (slider/number)', validation_alias='minValue')
    max_value: Optional[float] = Field(None, description='最大值 (slider/number)', validation_alias='maxValue')
    step: Optional[float] = Field(None, description='步长 (slider/number)', validation_alias='step')
    unit: Optional[str] = Field(None, max_length=20, description='单位显示 (如 cm, dB, s)', validation_alias='unit')

    model_config = {'populate_by_name': True}


class CaseAlgorithmParamUpdate(BaseModel):
    """更新用例专属参数请求"""
    param_name: Optional[str] = Field(None, max_length=100, validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, validation_alias='label')
    param_type: Optional[str] = Field(None, validation_alias='paramType')
    required: Optional[bool] = Field(None, validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: Optional[int] = Field(None, validation_alias='uiOrder')
    hidden: Optional[bool] = Field(None, validation_alias='hidden')
    scope: Optional[str] = Field(None, max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')
    min_value: Optional[float] = Field(None, description='最小值 (slider/number)', validation_alias='minValue')
    max_value: Optional[float] = Field(None, description='最大值 (slider/number)', validation_alias='maxValue')
    step: Optional[float] = Field(None, description='步长 (slider/number)', validation_alias='step')
    unit: Optional[str] = Field(None, max_length=20, description='单位显示 (如 cm, dB, s)', validation_alias='unit')

    model_config = {'populate_by_name': True}


# ========== 评估维度参数 ==========

class EvaluationDimensionParamCreate(BaseModel):
    """创建评估维度参数请求"""
    dimension_id: int = Field(..., description='关联评估维度ID', validation_alias='dimensionId')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码', validation_alias='paramCode')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称', validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    field_type: str = Field(default='text', description='字段类型：text, audio, number, boolean, json', validation_alias='fieldType')
    param_direction: str = Field(default='input', description='参数方向：input, output', validation_alias='paramDirection')
    field_path: Optional[str] = Field(None, description='结果提取路径（output专用）', validation_alias='fieldPath')
    agg_role: Optional[str] = Field(None, description='聚合角色（output专用）：numerator/denominator/value/pass_le/pass_ge/pass_eq', validation_alias='aggRole')
    required: bool = Field(default=True, description='是否必填', validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    pass_threshold: Optional[float] = Field(None, description='达标阈值/目标值（pass_rate策略专用）', validation_alias='passThreshold')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: int = Field(default=0, ge=0, description='界面排序', validation_alias='uiOrder')

    model_config = {'populate_by_name': True}


class EvaluationDimensionParamUpdate(BaseModel):
    """更新评估维度参数请求"""
    param_name: Optional[str] = Field(None, max_length=100, validation_alias='paramName')
    label: Optional[str] = Field(None, max_length=100, validation_alias='label')
    field_type: Optional[str] = Field(None, validation_alias='fieldType')
    param_direction: Optional[str] = Field(None, validation_alias='paramDirection')
    field_path: Optional[str] = Field(None, validation_alias='fieldPath')
    agg_role: Optional[str] = Field(None, validation_alias='aggRole')
    required: Optional[bool] = Field(None, validation_alias='required')
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    pass_threshold: Optional[float] = Field(None, description='达标阈值/目标值（pass_rate策略专用）', validation_alias='passThreshold')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: Optional[int] = Field(None, validation_alias='uiOrder')

    model_config = {'populate_by_name': True}


class EvaluationDimensionParamItem(BaseModel):
    """评估维度参数项"""
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
    pass_threshold: Optional[float]
    help_text: Optional[str]
    ui_order: int

    class Config:
        from_attributes = True


class EvaluationDimensionParamListResponse(BaseModel):
    """评估维度参数列表响应"""
    data: List[EvaluationDimensionParamItem]
    total: int


# ========== 参数映射 ==========

class ParamMappingCreate(BaseModel):
    """创建参数映射请求"""
    algorithm_type: str = Field(..., description='关联算法类型', validation_alias='algorithmType')
    source_type: str = Field(..., description='源类型：device, api', validation_alias='sourceType')
    source_param: str = Field(..., min_length=1, max_length=50, description='源参数代码', validation_alias='sourceParam')
    source_direction: str = Field(default='output', description='源参数方向：input, output', validation_alias='sourceDirection')
    dimension_id: int = Field(..., description='目标评估维度ID', validation_alias='dimensionId')
    target_param: str = Field(..., min_length=1, max_length=50, description='目标评估维度参数代码', validation_alias='targetParam')
    transform_type: str = Field(default='none', description='转换类型：none, uppercase, lowercase, json_parse, base64', validation_alias='transformType')


class ParamMappingUpdate(BaseModel):
    """更新参数映射请求"""
    source_type: Optional[str] = Field(None, validation_alias='sourceType')
    source_param: Optional[str] = Field(None, validation_alias='sourceParam')
    source_direction: Optional[str] = Field(None, validation_alias='sourceDirection')
    dimension_id: Optional[int] = Field(None, validation_alias='dimensionId')
    target_param: Optional[str] = Field(None, validation_alias='targetParam')
    transform_type: Optional[str] = Field(None, validation_alias='transformType')

    model_config = {'populate_by_name': True}


class ParamMappingItem(BaseModel):
    """参数映射项"""
    id: int
    algorithm_type: str
    source_type: str
    source_param: str
    source_direction: str
    dimension_id: int
    dimension_name: Optional[str]
    target_param: str
    transform_type: str

    class Config:
        from_attributes = True


class ParamMappingListResponse(BaseModel):
    """参数映射列表响应"""
    data: List[ParamMappingItem]
    total: int


# ========== 算法维度关联 ==========

class AlgorithmDimensionRelationCreate(BaseModel):
    """创建算法维度关联请求"""
    algorithm_type: str = Field(..., description='关联算法类型', validation_alias='algorithmType')
    dimension_id: int = Field(..., description='关联评估维度ID', validation_alias='dimensionId')
    is_default: bool = Field(default=False, description='是否默认评估维度', validation_alias='isDefault')
    weight: float = Field(default=1.0, ge=0, description='权重', validation_alias='weight')

    model_config = {'populate_by_name': True}


class AlgorithmDimensionRelationUpdate(BaseModel):
    """更新算法维度关联请求"""
    is_default: Optional[bool] = Field(None, validation_alias='isDefault')
    weight: Optional[float] = Field(None, ge=0, validation_alias='weight')

    model_config = {'populate_by_name': True}


class AlgorithmDimensionRelationItem(BaseModel):
    """算法维度关联项"""
    id: int
    algorithm_type: str
    dimension_id: int
    is_default: bool
    weight: float

    class Config:
        from_attributes = True


class AlgorithmDimensionRelationListResponse(BaseModel):
    """算法维度关联列表响应"""
    data: List[AlgorithmDimensionRelationItem]
    total: int


class ParamCreateRequest(BaseModel):
    """创建参数请求"""
    algorithm_type: str = Field(..., validation_alias='algorithmType')
    param_code: str = Field(..., validation_alias='paramCode')
    param_name: Optional[str] = Field(None, validation_alias='paramName')
    label: Optional[str] = Field(None)
    param_type: str = Field(default='text', validation_alias='paramType')
    direction: str = Field(default='input')
    required: bool = Field(default=False)
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: int = Field(default=0, validation_alias='uiOrder')
    hidden: bool = Field(default=False)
    param_type_source: Optional[str] = Field(default='device', validation_alias='paramTypeSource')

    model_config = {'populate_by_name': True}


class ParamUpdateRequest(BaseModel):
    """更新参数请求"""
    param_code: Optional[str] = Field(None, validation_alias='paramCode')
    param_name: Optional[str] = Field(None, validation_alias='paramName')
    label: Optional[str] = Field(None)
    param_type: Optional[str] = Field(None, validation_alias='paramType')
    direction: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    validation_rules: Optional[str] = Field(None, validation_alias='validationRules')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: Optional[int] = Field(None, validation_alias='uiOrder')
    hidden: Optional[bool] = Field(None)

    model_config = {'populate_by_name': True}


class MappingCreateRequest(BaseModel):
    """创建参数映射请求"""
    algorithm_type: str = Field(..., validation_alias='algorithmType')
    source_type: str = Field(..., validation_alias='sourceType')
    source_param: str = Field(..., validation_alias='sourceParam')
    source_direction: str = Field(default='output', validation_alias='sourceDirection')
    dimension_id: Optional[int] = Field(None, validation_alias='dimensionId')
    target_param: str = Field(..., validation_alias='targetParam')
    transform_type: str = Field(default='none', validation_alias='transformType')

    model_config = {'populate_by_name': True}


class MappingUpdateRequest(BaseModel):
    """更新参数映射请求"""
    source_type: Optional[str] = Field(None, validation_alias='sourceType')
    source_param: Optional[str] = Field(None, validation_alias='sourceParam')
    source_direction: Optional[str] = Field(None, validation_alias='sourceDirection')
    dimension_id: Optional[int] = Field(None, validation_alias='dimensionId')
    target_param: Optional[str] = Field(None, validation_alias='targetParam')
    transform_type: Optional[str] = Field(None, validation_alias='transformType')

    model_config = {'populate_by_name': True}


class CaseParamCreateRequest(BaseModel):
    """创建用例专属参数请求"""
    algorithm_type: str = Field(..., validation_alias='algorithmType')
    param_code: str = Field(..., validation_alias='paramCode')
    param_name: Optional[str] = Field(None, validation_alias='paramName')
    label: Optional[str] = Field(None)
    param_type: str = Field(default='text', validation_alias='paramType')
    required: bool = Field(default=False)
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    options_source: Optional[str] = Field(None, validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, validation_alias='optionsField')
    options_label_field: Optional[str] = Field(None, validation_alias='optionsLabelField')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: int = Field(default=0, validation_alias='uiOrder')
    hidden: bool = Field(default=False)
    scope: str = Field(default='common', max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')

    model_config = {'populate_by_name': True}


class CaseParamUpdateRequest(BaseModel):
    """更新用例专属参数请求"""
    param_name: Optional[str] = Field(None, validation_alias='paramName')
    label: Optional[str] = Field(None)
    param_type: Optional[str] = Field(None, validation_alias='paramType')
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None, validation_alias='defaultValue')
    options_source: Optional[str] = Field(None, validation_alias='optionsSource')
    options_field: Optional[str] = Field(None, validation_alias='optionsField')
    options_label_field: Optional[str] = Field(None, validation_alias='optionsLabelField')
    help_text: Optional[str] = Field(None, validation_alias='helpText')
    ui_order: Optional[int] = Field(None, validation_alias='uiOrder')
    hidden: Optional[bool] = Field(None)
    scope: Optional[str] = Field(None, max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')

    model_config = {'populate_by_name': True}


class ReferenceParamCreateRequest(BaseModel):
    """创建参考参数请求"""
    algorithm_type: str = Field(..., validation_alias='algorithmType')
    code: str = Field(...)
    name: Optional[str] = Field(None)
    type: str = Field(default='text')
    annotation_code: Optional[str] = Field(None, validation_alias='annotationCode')
    annotation_format: Optional[str] = Field(None, validation_alias='annotationFormat')
    field_path: Optional[str] = Field(None, validation_alias='fieldPath')
    merge_mode: Optional[str] = Field(None, validation_alias='mergeMode')
    help_text: Optional[str] = Field(None, validation_alias='helpText')

    model_config = {'populate_by_name': True}


class ReferenceParamUpdateRequest(BaseModel):
    """更新参考参数请求"""
    algorithm_type: Optional[str] = Field(None, validation_alias='algorithmType')
    code: Optional[str] = Field(None)
    name: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    annotation_code: Optional[str] = Field(None, validation_alias='annotationCode')
    annotation_format: Optional[str] = Field(None, validation_alias='annotationFormat')
    field_path: Optional[str] = Field(None, validation_alias='fieldPath')
    merge_mode: Optional[str] = Field(None, validation_alias='mergeMode')
    help_text: Optional[str] = Field(None, validation_alias='helpText')

    model_config = {'populate_by_name': True}


class AssociateDimensionsRequest(BaseModel):
    """关联评估维度请求"""
    dimensions: List[Dict[str, Any]] = Field(default=[])

    model_config = {'populate_by_name': True}


class DimensionRelationCreateRequest(BaseModel):
    """创建维度关联请求"""
    algorithm_type: str = Field(..., validation_alias='algorithmType')
    dimension_id: int = Field(..., validation_alias='dimensionId')
    is_default: bool = Field(default=False, validation_alias='isDefault')
    weight: float = Field(default=1.0)

    model_config = {'populate_by_name': True}


class DimensionRelationUpdateRequest(BaseModel):
    """更新维度关联请求"""
    algorithm_type: Optional[str] = Field(None, validation_alias='algorithmType')
    weight: Optional[float] = Field(None, ge=0)
    is_default: Optional[bool] = Field(None, validation_alias='isDefault')
    dimension_id: Optional[int] = Field(None, validation_alias='dimensionId')

    model_config = {'populate_by_name': True}


class ExtractParamsRequest(BaseModel):
    """提取用例算法参数请求"""
    case_config: Dict[str, Any] = Field(default={}, validation_alias='caseConfig')

    model_config = {'populate_by_name': True}


class AlgorithmListQuery(APIModel):
    status: Optional[str] = Field(None, alias='status', validation_alias='status')
    group_id: Optional[int] = Field(None, alias='groupId', validation_alias='groupId')


class AlgorithmParamListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    param_type: str = Field('device', alias='paramType', validation_alias='paramType')


class AlgorithmMappingListQuery(APIModel):
    algorithm_type: Optional[str] = Field(None, alias='algorithmType', validation_alias='algorithmType')
    source_type: Optional[str] = Field(None, alias='sourceType', validation_alias='sourceType')
    dimension_id: Optional[int] = Field(None, alias='dimensionId', validation_alias='dimensionId')
