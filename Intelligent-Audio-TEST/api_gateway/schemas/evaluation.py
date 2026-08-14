from typing import Any, Dict, List, Optional, Union
from pydantic import Field, field_validator, AliasChoices

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class CategoryItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    icon: Optional[str] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class CategoryListData(APIModel):
    items: List[CategoryItem] = Field(...)
    total: int = Field(...)


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
    keywords: Optional[str] = Field(None)
    dimension_type: Optional[str] = Field(None)
    parent_dimension_id: Optional[int] = Field(None)
    task_type_code: Optional[str] = Field(None)
    category_id: Optional[int] = Field(None)
    api_url: Optional[str] = Field(None)
    api_endpoints: Optional[Any] = Field(None)
    api_settings: Optional[Dict[str, Any]] = Field(None)
    api_status: Optional[str] = Field(None)
    score_unit: Optional[str] = Field(None)
    statistic_method: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    result_type: Optional[int] = Field(None)
    result_min: Optional[float] = Field(None)
    result_max: Optional[float] = Field(None)
    decimal_places: Optional[int] = Field(None)
    weight: Optional[int] = Field(None)
    estimated_exec_time: Optional[int] = Field(None)
    rule: Optional[Union[Dict[str, Any], str]] = Field(None)
    required_inputs: Optional[Any] = Field(None)
    output_fields: Optional[Any] = Field(None)
    associated_algorithms: Optional[List[Dict[str, Any]]] = Field(None)
    status: Optional[bool] = Field(None)

    @field_validator('rule', mode='before')
    @classmethod
    def parse_rule(cls, v):
        return parse_rule_field(v)


class DimensionCreateInput(DimensionInput):
    # 创建时提供默认值
    dimension_type: Optional[str] = Field('main')
    statistic_method: Optional[str] = Field('average')
    type: Optional[str] = Field('auto')
    result_type: Optional[int] = Field(1)
    result_min: Optional[float] = Field(0)
    result_max: Optional[float] = Field(100)
    decimal_places: Optional[int] = Field(2)
    weight: Optional[int] = Field(5)
    estimated_exec_time: Optional[int] = Field(5)
    status: Optional[bool] = Field(True)


DimensionUpdateInput = DimensionInput


class DimensionItem(APIModel):
    id: int = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    keywords: Optional[str] = Field(None)
    dimension_type: Optional[str] = Field('main')
    parent_dimension_id: Optional[int] = Field(None)
    task_type_code: Optional[str] = Field(None)
    category_id: Optional[int] = Field(None)
    api_url: Optional[str] = Field(None)
    api_endpoints: Optional[Any] = Field(None)
    api_settings: Optional[Dict[str, Any]] = Field(None)
    api_status: Optional[str] = Field(None)
    score_unit: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    result_type: Optional[int] = Field(None)
    result_min: Optional[float] = Field(None)
    result_max: Optional[float] = Field(None)
    decimal_places: Optional[int] = Field(None)
    weight: Optional[int] = Field(None)
    estimated_exec_time: Optional[int] = Field(None)
    rule: Optional[Union[Dict[str, Any], str]] = Field(None)
    required_inputs: Optional[Any] = Field(None)
    output_fields: Optional[Any] = Field(None)
    statistic_method: Optional[str] = Field('average')
    associated_algorithms: Optional[List[Dict[str, Any]]] = Field(None)
    status: Optional[bool] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class DimensionListData(PaginatedData[DimensionItem]):
    pass


class HealthCheckResultItem(APIModel):
    url: str = Field(...)
    status: str = Field(...)
    status_code: Optional[int] = Field(None)
    response_time: Optional[str] = Field(None)
    message: Optional[str] = Field(None)
    error: Optional[str] = Field(None)


class DimensionHealthCheckData(APIModel):
    results: List[HealthCheckResultItem] = Field(...)
    overall_status: str = Field(...)


class ScoreData(APIModel):
    score: float = Field(...)


class DimensionImportResult(APIModel):
    imported: int = Field(...)
    updated: int = Field(...)


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
    total_cases: int = Field(...)
    queued_cases: int = Field(...)
    reextracted_cases: int = Field(0)
    message: str = Field(...)
