# -*- coding: utf-8 -*-
"""算法配置 Schema 定义

定义算法配置相关的请求/响应 Schema。

本模块为门面（Facade）：具体 Schema 按职责拆分至以下子模块，
所有历史导入路径 ``api_gateway.schemas.algorithm.X`` 保持兼容。
"""
from api_gateway.schemas._algorithm_definition_schemas import (
    AlgorithmAssociateDimensionsRequest,
    AlgorithmDeleteResponse,
    AlgorithmDefinitionCreate,
    AlgorithmDefinitionUpdate,
    AlgorithmDetailResponse,
    AlgorithmFormSchemaResponse,
    AlgorithmImportRequest,
    AlgorithmListResponse,
    AlgorithmOptionsResponse,
    AlgorithmParamsResponse,
    AlgorithmReferenceParam,
    BulkDeleteRequest,
    ReloadConfigResponse,
)
from api_gateway.schemas._algorithm_group_schemas import (
    AlgorithmGroupCreate,
    AlgorithmGroupItem,
    AlgorithmGroupListResponse,
    AlgorithmGroupUpdate,
)
from api_gateway.schemas._algorithm_param_schemas import (
    AlgorithmCaseParamListQuery,
    AlgorithmDeviceParamCreate,
    AlgorithmDeviceParamItem,
    AlgorithmDeviceParamListResponse,
    AlgorithmDeviceParamUpdate,
    AlgorithmListQuery,
    AlgorithmParamCreate,
    AlgorithmParamListQuery,
    AlgorithmParamUpdate,
    AlgorithmReferenceParamListQuery,
    ParamCreateRequest,
    ParamUpdateRequest,
    ReferenceParamCreateRequest,
    ReferenceParamUpdateRequest,
)
from api_gateway.schemas._algorithm_api_param_schemas import (
    AlgorithmApiParamCreate,
    AlgorithmApiParamItem,
    AlgorithmApiParamListResponse,
    AlgorithmApiParamUpdate,
    CaseAlgorithmParamCreate,
    CaseAlgorithmParamUpdate,
    CaseParamCreateRequest,
    CaseParamUpdateRequest,
    ExtractParamsRequest,
)
from api_gateway.schemas._algorithm_dimension_schemas import (
    AlgorithmDimensionRelationCreate,
    AlgorithmDimensionRelationItem,
    AlgorithmDimensionRelationListResponse,
    AlgorithmDimensionRelationUpdate,
    AlgorithmMappingListQuery,
    AssociateDimensionsRequest,
    DimensionRelationCreateRequest,
    DimensionRelationUpdateRequest,
    EvaluationDimensionParamCreate,
    EvaluationDimensionParamItem,
    EvaluationDimensionParamListResponse,
    EvaluationDimensionParamUpdate,
    MappingCreateRequest,
    MappingUpdateRequest,
    ParamMappingCreate,
    ParamMappingItem,
    ParamMappingListResponse,
    ParamMappingUpdate,
)

# 供 ``from api_gateway.schemas.algorithm import *`` 使用
__all__ = [
    # 算法定义
    'AlgorithmReferenceParam',
    'AlgorithmDefinitionCreate',
    'AlgorithmDefinitionUpdate',
    'AlgorithmDetailResponse',
    'AlgorithmListResponse',
    'AlgorithmFormSchemaResponse',
    'AlgorithmParamsResponse',
    'AlgorithmOptionsResponse',
    'AlgorithmAssociateDimensionsRequest',
    'ReloadConfigResponse',
    'AlgorithmImportRequest',
    'BulkDeleteRequest',
    'AlgorithmDeleteResponse',
    # 算法分组
    'AlgorithmGroupCreate',
    'AlgorithmGroupUpdate',
    'AlgorithmGroupItem',
    'AlgorithmGroupListResponse',
    # 通用算法参数
    'AlgorithmParamCreate',
    'AlgorithmParamUpdate',
    # 设备参数
    'AlgorithmDeviceParamCreate',
    'AlgorithmDeviceParamUpdate',
    'AlgorithmDeviceParamItem',
    'AlgorithmDeviceParamListResponse',
    # API 参数
    'AlgorithmApiParamCreate',
    'AlgorithmApiParamUpdate',
    'AlgorithmApiParamItem',
    'AlgorithmApiParamListResponse',
    # 用例专属参数
    'CaseAlgorithmParamCreate',
    'CaseAlgorithmParamUpdate',
    # 评估维度参数
    'EvaluationDimensionParamCreate',
    'EvaluationDimensionParamUpdate',
    'EvaluationDimensionParamItem',
    'EvaluationDimensionParamListResponse',
    # 参数映射
    'ParamMappingCreate',
    'ParamMappingUpdate',
    'ParamMappingItem',
    'ParamMappingListResponse',
    # 算法维度关联
    'AlgorithmDimensionRelationCreate',
    'AlgorithmDimensionRelationUpdate',
    'AlgorithmDimensionRelationItem',
    'AlgorithmDimensionRelationListResponse',
    # 参数请求（统一入口）
    'ParamCreateRequest',
    'ParamUpdateRequest',
    'MappingCreateRequest',
    'MappingUpdateRequest',
    'CaseParamCreateRequest',
    'CaseParamUpdateRequest',
    'ReferenceParamCreateRequest',
    'ReferenceParamUpdateRequest',
    'AssociateDimensionsRequest',
    'DimensionRelationCreateRequest',
    'DimensionRelationUpdateRequest',
    'ExtractParamsRequest',
    # 列表查询
    'AlgorithmListQuery',
    'AlgorithmParamListQuery',
    'AlgorithmMappingListQuery',
    'AlgorithmCaseParamListQuery',
    'AlgorithmReferenceParamListQuery',
]
