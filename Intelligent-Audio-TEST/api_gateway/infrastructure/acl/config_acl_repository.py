# -*- coding: utf-8 -*-
"""config 服务 ACL 仓储 — 委托 grpc_proxies 实现。

覆盖 api_config / task_config / testcase_config / tag_config /
algorithm_config / evaluation_config 各 config 服务的实体只读查询，
从 {success, message, data, code} 信封提取 data 并应用
dict_to_dto / dict_list_to_dto 转换为 dataclass DTO。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from api_gateway.domain.dto import (
    AlgorithmDTO, AlgorithmGroupDTO, ApiConfigDTO, DimensionDTO, ParamDTO,
    TagCategoryDTO, TagDTO, TaskDTO, TestCaseDTO,
)
from api_gateway.domain.repositories.acl.config_acl_repository import (
    AlgorithmConfigAclRepository,
    ApiConfigAclRepository,
    EvaluationConfigAclRepository,
    TagConfigAclRepository,
    TaskConfigAclRepository,
    TestCaseConfigAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


def _envelope_data(envelope):
    if isinstance(envelope, dict):
        return envelope.get('data')
    return None


def _items(payload):
    if isinstance(payload, dict):
        return payload.get('items', []) or payload.get('list', [])
    if isinstance(payload, list):
        return payload
    return []


class ApiConfigAclRepositoryImpl(ApiConfigAclRepository):
    """api_test_service.APITestService 实体 ACL 实现。"""

    def get_api(self, api_id) -> Optional[ApiConfigDTO]:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        data = _envelope_data(api_config_service.get_one(api_id))
        return _attach(dict_to_dto(data, ApiConfigDTO), data)

    def list_apis(self, **kwargs) -> List[ApiConfigDTO]:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        data = _envelope_data(api_config_service.get_all(**kwargs))
        return [_attach(dict_to_dto(d, ApiConfigDTO), d) for d in _items(data) if isinstance(d, dict)]


class TaskConfigAclRepositoryImpl(TaskConfigAclRepository):
    """task_service.TaskConfigService 实体 ACL 实现。"""

    def list_tasks(self, **kwargs) -> List[TaskDTO]:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        data = _envelope_data(task_config_service.list_tasks(**kwargs))
        return [_attach(dict_to_dto(d, TaskDTO), d) for d in _items(data) if isinstance(d, dict)]

    def get_task_detail(self, task_id) -> Optional[TaskDTO]:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        data = _envelope_data(task_config_service.get_task_detail(task_id))
        return _attach(dict_to_dto(data, TaskDTO), data)


class TestCaseConfigAclRepositoryImpl(TestCaseConfigAclRepository):
    """task_service.TestCaseConfigService 实体 ACL 实现。"""

    def list_testcases(self, **kwargs) -> List[TestCaseDTO]:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        data = _envelope_data(testcase_config_service.list_testcases(**kwargs))
        return [_attach(dict_to_dto(d, TestCaseDTO), d) for d in _items(data) if isinstance(d, dict)]

    def get_testcase_detail(self, tc_id) -> Optional[TestCaseDTO]:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        data = _envelope_data(testcase_config_service.get_testcase_detail(tc_id))
        return _attach(dict_to_dto(data, TestCaseDTO), data)


class TagConfigAclRepositoryImpl(TagConfigAclRepository):
    """task_service.TagConfigService 实体 ACL 实现。"""

    def list_tag_categories(self, **kwargs) -> List[TagCategoryDTO]:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        data = _envelope_data(tag_config_service.list_categories(**kwargs))
        return [_attach(dict_to_dto(d, TagCategoryDTO), d) for d in _items(data) if isinstance(d, dict)]

    def get_tag_category(self, category_id) -> Optional[TagCategoryDTO]:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        data = _envelope_data(tag_config_service.get_category(category_id))
        return _attach(dict_to_dto(data, TagCategoryDTO), data)

    def list_tags(self, **kwargs) -> List[TagDTO]:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        data = _envelope_data(tag_config_service.list_tags(**kwargs))
        return [_attach(dict_to_dto(d, TagDTO), d) for d in _items(data) if isinstance(d, dict)]

    def get_tag(self, tag_id) -> Optional[TagDTO]:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        data = _envelope_data(tag_config_service.get_tag(tag_id))
        return _attach(dict_to_dto(data, TagDTO), data)


class AlgorithmConfigAclRepositoryImpl(AlgorithmConfigAclRepository):
    """task_service.AlgorithmConfigService 实体 ACL 实现。"""

    def list_algorithms(self, **kwargs) -> List[AlgorithmDTO]:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        data = _envelope_data(algorithm_config_service.list_algorithms(**kwargs))
        return [_attach(dict_to_dto(d, AlgorithmDTO), d) for d in _items(data) if isinstance(d, dict)]

    def get_algorithm(self, algo_type) -> Optional[AlgorithmDTO]:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        data = _envelope_data(algorithm_config_service.get_algorithm(algo_type))
        return _attach(dict_to_dto(data, AlgorithmDTO), data)

    def list_algorithm_groups(self) -> List[AlgorithmGroupDTO]:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        data = _envelope_data(algorithm_config_service.list_groups())
        return [_attach(dict_to_dto(d, AlgorithmGroupDTO), d) for d in _items(data) if isinstance(d, dict)]

    def list_params(self, algorithm_type, param_type) -> List[ParamDTO]:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        data = _envelope_data(algorithm_config_service.list_params(algorithm_type, param_type))
        return [_attach(dict_to_dto(d, ParamDTO), d) for d in _items(data) if isinstance(d, dict)]


class EvaluationConfigAclRepositoryImpl(EvaluationConfigAclRepository):
    """evaluation_service.EvaluationConfigService 维度 ACL 实现。"""

    def list_dimensions(self, **kwargs) -> List[DimensionDTO]:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        data = _envelope_data(evaluation_config_service.list_dimensions(**kwargs))
        return [_attach(dict_to_dto(d, DimensionDTO), d) for d in _items(data) if isinstance(d, dict)]

    def get_dimension_by_ids(self, dim_ids) -> List[DimensionDTO]:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        data = _envelope_data(evaluation_config_service.get_dimension_by_ids(dim_ids))
        # get_dimension_by_ids 在 proxy 端已重塑为 {str(id): dim} 映射
        if isinstance(data, dict):
            return [_attach(dict_to_dto(d, DimensionDTO), d)
                    for d in data.values() if isinstance(d, dict)]
        return [_attach(dict_to_dto(d, DimensionDTO), d) for d in _items(data) if isinstance(d, dict)]
