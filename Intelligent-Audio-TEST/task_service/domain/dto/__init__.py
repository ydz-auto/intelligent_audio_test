# -*- coding: utf-8 -*-
"""task_service 领域 DTO（Data Transfer Object）。

微服务拆分后，ACL 仓储层通过 gRPC 调用 algorithm_service，
返回的不再是 ORM PO 对象，而是 dict。
本模块定义与 dict 同构的 dataclass DTO，由 ACL 仓储负责 dict→DTO 转换，
应用层统一用 DTO 属性访问，避免 dict 键访问与属性访问混用。
"""
from task_service.domain.dto.task_acl_dto import (
    AlgorithmDefinitionDTO,
    AlgorithmGroupDTO,
    DeviceParamDTO,
    ApiParamDTO,
    CaseParamDTO,
    ReferenceParamDTO,
    ParamMappingDTO,
    DimensionRelationDTO,
    DimensionParamDTO,
    DimensionDTO,
    CreateAckDTO,
)

__all__ = [
    'AlgorithmDefinitionDTO',
    'AlgorithmGroupDTO',
    'DeviceParamDTO',
    'ApiParamDTO',
    'CaseParamDTO',
    'ReferenceParamDTO',
    'ParamMappingDTO',
    'DimensionRelationDTO',
    'DimensionParamDTO',
    'DimensionDTO',
    'CreateAckDTO',
]
