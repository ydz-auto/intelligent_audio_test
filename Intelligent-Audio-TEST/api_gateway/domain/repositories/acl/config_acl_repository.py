# -*- coding: utf-8 -*-
"""task_service / api_test_service / evaluation_service config 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from api_gateway.domain.dto import (
    AlgorithmDTO, AlgorithmGroupDTO, ApiConfigDTO, DimensionDTO, ParamDTO,
    TagCategoryDTO, TagDTO, TaskDTO, TestCaseDTO,
)


class ApiConfigAclRepository(ABC):
    """api_test_service.APITestService 实体查询接口。"""

    @abstractmethod
    def get_api(self, api_id) -> Optional[ApiConfigDTO]:
        ...

    @abstractmethod
    def list_apis(self, **kwargs) -> List[ApiConfigDTO]:
        ...


class TaskConfigAclRepository(ABC):
    """task_service.TaskConfigService 实体查询接口。"""

    @abstractmethod
    def list_tasks(self, **kwargs) -> List[TaskDTO]:
        ...

    @abstractmethod
    def get_task_detail(self, task_id) -> Optional[TaskDTO]:
        ...


class TestCaseConfigAclRepository(ABC):
    """task_service.TestCaseConfigService 实体查询接口。"""

    @abstractmethod
    def list_testcases(self, **kwargs) -> List[TestCaseDTO]:
        ...

    @abstractmethod
    def get_testcase_detail(self, tc_id) -> Optional[TestCaseDTO]:
        ...


class TagConfigAclRepository(ABC):
    """task_service.TagConfigService 实体查询接口。"""

    @abstractmethod
    def list_tag_categories(self, **kwargs) -> List[TagCategoryDTO]:
        ...

    @abstractmethod
    def get_tag_category(self, category_id) -> Optional[TagCategoryDTO]:
        ...

    @abstractmethod
    def list_tags(self, **kwargs) -> List[TagDTO]:
        ...

    @abstractmethod
    def get_tag(self, tag_id) -> Optional[TagDTO]:
        ...


class AlgorithmConfigAclRepository(ABC):
    """task_service.AlgorithmConfigService 实体查询接口。"""

    @abstractmethod
    def list_algorithms(self, **kwargs) -> List[AlgorithmDTO]:
        ...

    @abstractmethod
    def get_algorithm(self, algo_type) -> Optional[AlgorithmDTO]:
        ...

    @abstractmethod
    def list_algorithm_groups(self) -> List[AlgorithmGroupDTO]:
        ...

    @abstractmethod
    def list_params(self, algorithm_type, param_type) -> List[ParamDTO]:
        ...


class EvaluationConfigAclRepository(ABC):
    """evaluation_service.EvaluationConfigService 维度查询接口。"""

    @abstractmethod
    def list_dimensions(self, **kwargs) -> List[DimensionDTO]:
        ...

    @abstractmethod
    def get_dimension_by_ids(self, dim_ids) -> List[DimensionDTO]:
        ...
