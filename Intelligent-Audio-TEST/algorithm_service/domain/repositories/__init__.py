# -*- coding: utf-8 -*-
"""algorithm_service.domain.repositories — 仓储接口（ACL 抽象层）。

导出所有 domain 仓储 ABC，供 infrastructure/persistence 继承。
"""
from algorithm_service.domain.repositories.algorithm_repositories import (
    IAlgorithmGroupRepository,
    IAlgorithmDefinitionRepository,
    IAlgorithmDefinitionQueryRepository,
    IAlgorithmGroupQueryRepository,
    IDeviceParamRepository,
    IDimensionParamRepository,
    IDimensionRelationQueryRepository,
    IParamMappingQueryRepository,
)
from algorithm_service.domain.repositories.param_repositories import (
    IAlgorithmParamRepository,
    ICaseParamRepository,
    IReferenceParamRepository,
    IMappingRepository,
    IDimensionRelationRepository,
)

__all__ = [
    'IAlgorithmGroupRepository',
    'IAlgorithmDefinitionRepository',
    'IAlgorithmDefinitionQueryRepository',
    'IAlgorithmGroupQueryRepository',
    'IDeviceParamRepository',
    'IDimensionParamRepository',
    'IDimensionRelationQueryRepository',
    'IParamMappingQueryRepository',
    'IAlgorithmParamRepository',
    'ICaseParamRepository',
    'IReferenceParamRepository',
    'IMappingRepository',
    'IDimensionRelationRepository',
]
