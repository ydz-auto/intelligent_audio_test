from typing import Any, Dict, List, Optional, Union
from pydantic import Field, field_validator, AliasChoices

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class CategoryItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    icon: Optional[str] = Field(None, alias='icon', validation_alias='icon')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class CategoryListData(APIModel):
    items: List[CategoryItem] = Field(..., alias='items', validation_alias='items')
    total: int = Field(..., alias='total', validation_alias='total')


def parse_rule_field(v):
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        import json
        try:
            return json.loads(v)
        except:
            return v
    return v


class DimensionInput(APIModel):
    name: Optional[str] = Field(None, validation_alias=AliasChoices('name', 'dimensionName', 'dimension_name'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('description', 'dimensionDescription', 'dimension_description'))
    keywords: Optional[str] = Field(None, validation_alias='keywords')
    dimension_type: Optional[str] = Field(None, validation_alias=AliasChoices('dimension_type', 'dimensionType'))
    parent_dimension_id: Optional[int] = Field(None, validation_alias=AliasChoices('parent_dimension_id', 'parentDimensionId'))
    task_type_code: Optional[str] = Field(None, validation_alias=AliasChoices('task_type_code', 'taskTypeCode'))
    category_id: Optional[int] = Field(None, validation_alias=AliasChoices('category_id', 'categoryId'))
    api_url: Optional[str] = Field(None, validation_alias=AliasChoices('api_url', 'apiUrl'))
    api_endpoints: Optional[Any] = Field(None, validation_alias=AliasChoices('api_endpoints', 'apiEndpoints'))
    api_settings: Optional[Dict[str, Any]] = Field(None, validation_alias=AliasChoices('api_settings', 'apiSettings'))
    api_status: Optional[str] = Field(None, alias='api_status', validation_alias='apiStatus')
    score_unit: Optional[str] = Field(None, alias='score_unit', validation_alias='scoreUnit')
    statistic_method: Optional[str] = Field(None, alias='statistic_method', validation_alias='statisticMethod')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    result_type: Optional[int] = Field(None, alias='result_type', validation_alias='resultType')
    result_min: Optional[float] = Field(None, alias='result_min', validation_alias='resultMin')
    result_max: Optional[float] = Field(None, alias='result_max', validation_alias='resultMax')
    decimal_places: Optional[int] = Field(None, alias='decimal_places', validation_alias='decimalPlaces')
    weight: Optional[int] = Field(None, alias='weight', validation_alias='weight')
    estimated_exec_time: Optional[int] = Field(None, alias='estimated_exec_time', validation_alias='estimatedExecTime')
    rule: Optional[Union[Dict[str, Any], str]] = Field(None, alias='rule', validation_alias='rule')
    required_inputs: Optional[Any] = Field(None, alias='required_inputs', validation_alias='requiredInputs')
    output_fields: Optional[Any] = Field(None, alias='output_fields', validation_alias='outputFields')
    associated_algorithms: Optional[List[Dict[str, Any]]] = Field(None, alias='associated_algorithms', validation_alias='associatedAlgorithms')
    status: Optional[bool] = Field(None, alias='status', validation_alias='status')

    @field_validator('rule', mode='before')
    @classmethod
    def parse_rule(cls, v):
        return parse_rule_field(v)


class DimensionCreateInput(DimensionInput):
    # 创建时提供默认值
    dimension_type: Optional[str] = Field('main', validation_alias=AliasChoices('dimension_type', 'dimensionType'))
    statistic_method: Optional[str] = Field('average', alias='statistic_method', validation_alias='statisticMethod')
    type: Optional[str] = Field('auto', alias='type', validation_alias='type')
    result_type: Optional[int] = Field(1, alias='result_type', validation_alias='resultType')
    result_min: Optional[float] = Field(0, alias='result_min', validation_alias='resultMin')
    result_max: Optional[float] = Field(100, alias='result_max', validation_alias='resultMax')
    decimal_places: Optional[int] = Field(2, alias='decimal_places', validation_alias='decimalPlaces')
    weight: Optional[int] = Field(5, alias='weight', validation_alias='weight')
    estimated_exec_time: Optional[int] = Field(5, alias='estimated_exec_time', validation_alias='estimatedExecTime')
    status: Optional[bool] = Field(True, alias='status', validation_alias='status')


DimensionUpdateInput = DimensionInput


class DimensionItem(APIModel):
    id: int = Field(..., alias='id', validation_alias='id')
    name: str = Field(..., alias='name', validation_alias='name')
    description: Optional[str] = Field(None, alias='description', validation_alias='description')
    keywords: Optional[str] = Field(None, alias='keywords', validation_alias='keywords')
    dimension_type: Optional[str] = Field('main', alias='dimensionType', validation_alias='dimensionType')
    parent_dimension_id: Optional[int] = Field(None, alias='parentDimensionId', validation_alias='parentDimensionId')
    task_type_code: Optional[str] = Field(None, alias='taskTypeCode', validation_alias='taskTypeCode')
    category_id: Optional[int] = Field(None, alias='categoryId', validation_alias='categoryId')
    api_url: Optional[str] = Field(None, alias='apiUrl', validation_alias='apiUrl')
    api_endpoints: Optional[Any] = Field(None, alias='apiEndpoints', validation_alias='apiEndpoints')
    api_settings: Optional[Dict[str, Any]] = Field(None, alias='apiSettings', validation_alias='apiSettings')
    api_status: Optional[str] = Field(None, alias='apiStatus', validation_alias='apiStatus')
    score_unit: Optional[str] = Field(None, alias='scoreUnit', validation_alias='scoreUnit')
    type: Optional[str] = Field(None, alias='type', validation_alias='type')
    result_type: Optional[int] = Field(None, alias='resultType', validation_alias='resultType')
    result_min: Optional[float] = Field(None, alias='resultMin', validation_alias='resultMin')
    result_max: Optional[float] = Field(None, alias='resultMax', validation_alias='resultMax')
    decimal_places: Optional[int] = Field(None, alias='decimalPlaces', validation_alias='decimalPlaces')
    weight: Optional[int] = Field(None, alias='weight', validation_alias='weight')
    estimated_exec_time: Optional[int] = Field(None, alias='estimatedExecTime', validation_alias='estimatedExecTime')
    rule: Optional[Union[Dict[str, Any], str]] = Field(None, alias='rule', validation_alias='rule')
    required_inputs: Optional[Any] = Field(None, alias='requiredInputs', validation_alias='requiredInputs')
    output_fields: Optional[Any] = Field(None, alias='outputFields', validation_alias='outputFields')
    statistic_method: Optional[str] = Field('average', alias='statisticMethod', validation_alias='statisticMethod')
    associated_algorithms: Optional[List[Dict[str, Any]]] = Field(None, alias='associatedAlgorithms', validation_alias='associatedAlgorithms')
    status: Optional[bool] = Field(None, alias='status', validation_alias='status')
    created_at: Optional[str] = Field(None, alias='createdAt', validation_alias='createdAt')
    updated_at: Optional[str] = Field(None, alias='updatedAt', validation_alias='updatedAt')


class DimensionListData(PaginatedData[DimensionItem]):
    pass


class HealthCheckResultItem(APIModel):
    url: str = Field(..., alias='url', validation_alias='url')
    status: str = Field(..., alias='status', validation_alias='status')
    status_code: Optional[int] = Field(None, alias='statusCode', validation_alias='statusCode')
    response_time: Optional[str] = Field(None, alias='responseTime', validation_alias='responseTime')
    message: Optional[str] = Field(None, alias='message', validation_alias='message')
    error: Optional[str] = Field(None, alias='error', validation_alias='error')


class DimensionHealthCheckData(APIModel):
    results: List[HealthCheckResultItem] = Field(..., alias='results', validation_alias='results')
    overall_status: str = Field(..., alias='overallStatus', validation_alias='overallStatus')


class ScoreData(APIModel):
    score: float = Field(..., alias='score', validation_alias='score')


class DimensionImportResult(APIModel):
    imported: int = Field(..., alias='imported', validation_alias='imported')
    updated: int = Field(..., alias='updated', validation_alias='updated')


class CategoryCreateInput(APIModel):
    name: str = Field(..., validation_alias=AliasChoices('name', 'categoryName'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('description', 'categoryDescription'))
    icon: Optional[str] = Field('default-icon', validation_alias=AliasChoices('icon', 'categoryIcon'))


class CategoryUpdateInput(APIModel):
    name: Optional[str] = Field(None, validation_alias=AliasChoices('name', 'categoryName'))
    description: Optional[str] = Field(None, validation_alias=AliasChoices('description', 'categoryDescription'))
    icon: Optional[str] = Field(None, validation_alias=AliasChoices('icon', 'categoryIcon'))


class ScoreCalculateInput(APIModel):
    value: Union[int, float, str] = Field(..., validation_alias=AliasChoices('value', 'testValue', 'test_value'))


class BatchActionInput(APIModel):
    ids: Optional[List[int]] = Field(None, validation_alias=AliasChoices('ids', 'itemIds', 'item_ids'))
    action: str = Field(..., validation_alias=AliasChoices('action', 'batchAction'))


class FileImportInput(APIModel):
    update_existing: bool = Field(False, validation_alias=AliasChoices('update_existing', 'updateExisting'))


class TaskReevaluateInput(APIModel):
    task_id: int = Field(..., validation_alias=AliasChoices('task_id', 'taskId'))
    reevaluate_type: str = Field('all', validation_alias=AliasChoices('reevaluate_type', 'reevaluateType'))
    reextract_device_output: bool = Field(False, validation_alias=AliasChoices('reextract_device_output', 'reextractDeviceOutput'))


class TaskReevaluateResult(APIModel):
    total_cases: int = Field(..., alias='totalCases', validation_alias='totalCases')
    queued_cases: int = Field(..., alias='queuedCases', validation_alias='queuedCases')
    reextracted_cases: int = Field(0, alias='reextractedCases', validation_alias='reextractedCases')
    message: str = Field(..., alias='message', validation_alias='message')

