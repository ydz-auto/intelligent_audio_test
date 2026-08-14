# -*- coding: utf-8 -*-
"""task_service / api_test_service / evaluation_service config 跨域 ACL 仓储接口。

所有方法返回 CommandResultDTO，封装 gRPC 信封 {success, message, data, code}。
应用服务通过属性访问 (result.success / result.data) 替代 dict.get()。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from api_gateway.domain.dto import CommandResultDTO


class ApiConfigAclRepository(ABC):
    """api_test_service.APITestService 实体 ACL 接口。"""

    @abstractmethod
    def get_all(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_one(self, api_id) -> CommandResultDTO: ...

    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, api_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, api_id) -> CommandResultDTO: ...

    @abstractmethod
    def test_connection(self, api_id) -> CommandResultDTO: ...

    @abstractmethod
    def stop_test(self, api_id) -> CommandResultDTO: ...


class TaskConfigAclRepository(ABC):
    """task_service.TaskConfigService 实体 ACL 接口。"""

    # ---- 写操作 ----
    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, task_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, task_id) -> CommandResultDTO: ...

    @abstractmethod
    def update_cases(self, task_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def batch_action(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def merge(self, data) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def list_tasks(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_task_detail(self, task_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_task_progress(self, task_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_task_stats(self, task_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_case_detail(self, task_id, case_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_case_results(self, task_id, case_id) -> CommandResultDTO: ...

    # ---- 生命周期操作 ----
    @abstractmethod
    def start(self, task_id) -> CommandResultDTO: ...

    @abstractmethod
    def retry(self, task_id) -> CommandResultDTO: ...

    @abstractmethod
    def control(self, task_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def stop(self, task_id) -> CommandResultDTO: ...

    @abstractmethod
    def reextract(self, task_id, data) -> CommandResultDTO: ...


class TestCaseConfigAclRepository(ABC):
    """task_service.TestCaseConfigService 实体 ACL 接口。"""

    # ---- 写操作 ----
    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, tc_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, tc_id) -> CommandResultDTO: ...

    @abstractmethod
    def copy(self, tc_id) -> CommandResultDTO: ...

    @abstractmethod
    def batch_action(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_ref_params(self, tc_id, round_number, data) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def list_testcases(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_testcase_detail(self, tc_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_testcase_stats(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_testcase_tags(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_testcase_ref_params(self, tc_id, round_number) -> CommandResultDTO: ...


class TagConfigAclRepository(ABC):
    """task_service.TagConfigService 实体 ACL 接口。"""

    # ---- 分类写操作 ----
    @abstractmethod
    def create_category(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_category(self, category_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_category(self, category_id) -> CommandResultDTO: ...

    # ---- 标签写操作 ----
    @abstractmethod
    def create_tag(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_tag(self, tag_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_tag(self, tag_id) -> CommandResultDTO: ...

    @abstractmethod
    def batch_update_category(self, data) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def list_categories(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_category(self, category_id) -> CommandResultDTO: ...

    @abstractmethod
    def list_tags(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def list_tag_names(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_tag(self, tag_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_tags_by_category(self) -> CommandResultDTO: ...


class AlgorithmConfigAclRepository(ABC):
    """task_service.AlgorithmConfigService 实体 ACL 接口。"""

    # ---- 算法写操作 ----
    @abstractmethod
    def create_algorithm(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_algorithm(self, algo_type, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_algorithm(self, algo_type) -> CommandResultDTO: ...

    # ---- 参数写操作 ----
    @abstractmethod
    def create_param(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_param(self, param_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_param(self, param_id) -> CommandResultDTO: ...

    # ---- 映射写操作 ----
    @abstractmethod
    def create_mapping(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_mapping(self, mapping_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_mapping(self, mapping_id) -> CommandResultDTO: ...

    # ---- 用例参数写操作 ----
    @abstractmethod
    def create_case_param(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_case_param(self, param_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_case_param(self, param_id) -> CommandResultDTO: ...

    # ---- 参考参数写操作 ----
    @abstractmethod
    def create_reference_param(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_reference_param(self, param_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_reference_param(self, param_id) -> CommandResultDTO: ...

    # ---- 维度关联写操作 ----
    @abstractmethod
    def associate_dimensions(self, algo_type, data) -> CommandResultDTO: ...

    @abstractmethod
    def create_dimension_relation(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_dimension_relation(self, relation_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_dimension_relation(self, relation_id) -> CommandResultDTO: ...

    # ---- 批量操作 ----
    @abstractmethod
    def import_algorithms(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def bulk_delete(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def extract_params(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def reload_config(self) -> CommandResultDTO: ...

    # ---- 分组写操作 ----
    @abstractmethod
    def create_group(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_group(self, group_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_group(self, group_id) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def list_algorithms(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_algorithm_options(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_algorithm(self, algo_type) -> CommandResultDTO: ...

    @abstractmethod
    def list_params(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_param(self, param_id) -> CommandResultDTO: ...

    @abstractmethod
    def list_mappings(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def list_case_params(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_case_param(self, param_id) -> CommandResultDTO: ...

    @abstractmethod
    def list_reference_params(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_form_schema(self, algo_type) -> CommandResultDTO: ...

    @abstractmethod
    def get_algorithm_dimensions(self, algo_type) -> CommandResultDTO: ...

    @abstractmethod
    def get_dimension_params(self, dimension_id) -> CommandResultDTO: ...

    @abstractmethod
    def list_groups(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_group(self, group_id) -> CommandResultDTO: ...


class EvaluationConfigAclRepository(ABC):
    """evaluation_service.EvaluationConfigService 维度 ACL 接口。"""

    # ---- 分类写操作 ----
    @abstractmethod
    def create_category(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_category(self, cat_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_category(self, cat_id) -> CommandResultDTO: ...

    # ---- 维度写操作 ----
    @abstractmethod
    def create_dimension(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_dimension(self, dim_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def calculate_score(self, dim_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_dimension(self, dim_id) -> CommandResultDTO: ...

    @abstractmethod
    def batch_action(self, data) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def list_categories(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_dimension_options(self, algorithm_type=None) -> CommandResultDTO: ...

    @abstractmethod
    def list_dimensions(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def health_check(self, dim_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_dimension_by_ids(self, dim_ids) -> CommandResultDTO: ...


class SplConfigAclRepository(ABC):
    """spl_config_service SPL 映射配置 ACL 接口。"""

    # ---- 写操作 ----
    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, mapping_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, mapping_id) -> CommandResultDTO: ...

    @abstractmethod
    def calibrate(self, mapping_id) -> CommandResultDTO: ...

    @abstractmethod
    def play_test_tone(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def stop_test_tone(self, data) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def get_all(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_one(self, mapping_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_history(self, mapping_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_calibration_data(self, mapping_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_stats(self) -> CommandResultDTO: ...

    @abstractmethod
    def get_by_device(self, device_id) -> CommandResultDTO: ...
