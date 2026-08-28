# -*- coding: utf-8 -*-
"""config 服务 ACL 仓储实现 — 委托 grpc_proxies 实现。

所有方法委托 grpc_proxies 单例完成 gRPC 调用，将返回的
{success, message, data, code} 信封封装为 CommandResultDTO。
"""
from __future__ import annotations

from api_gateway.domain.dto import CommandResultDTO
from api_gateway.domain.repositories.acl.config_acl_repository import (
    AlgorithmConfigAclRepository,
    ApiConfigAclRepository,
    EvaluationConfigAclRepository,
    SplConfigAclRepository,
    TagConfigAclRepository,
    TaskConfigAclRepository,
    TestCaseConfigAclRepository,
)


def _wrap(result) -> CommandResultDTO:
    """将 gRPC 返回的信封 dict 封装为 CommandResultDTO。"""
    if isinstance(result, dict):
        return CommandResultDTO(
            success=result.get('success', False),
            message=result.get('message'),
            data=result.get('data'),
            code=result.get('code'),
        )
    return CommandResultDTO(success=False, data=result)


class ApiConfigAclRepositoryImpl(ApiConfigAclRepository):
    """api_test_service.APITestService 实体 ACL 实现。"""

    def get_all(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        return _wrap(api_config_service.get_all(**kwargs))

    def get_one(self, api_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        return _wrap(api_config_service.get_one(api_id))

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        return _wrap(api_config_service.create(data))

    def update(self, api_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        return _wrap(api_config_service.update(api_id, data))

    def delete(self, api_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        return _wrap(api_config_service.delete(api_id))

    def test_connection(self, api_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        return _wrap(api_config_service.test_connection(api_id))

    def stop_test(self, api_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import api_config_service
        return _wrap(api_config_service.stop_test(api_id))


class TaskConfigAclRepositoryImpl(TaskConfigAclRepository):
    """task_service.TaskConfigService 实体 ACL 实现。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.create(data))

    def update(self, task_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.update(task_id, data))

    def delete(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.delete(task_id))

    def update_cases(self, task_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.update_cases(task_id, data))

    def batch_action(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.batch_action(data))

    def merge(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.merge(data))

    def list_tasks(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.list_tasks(**kwargs))

    def get_task_detail(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.get_task_detail(task_id))

    def get_task_progress(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.get_task_progress(task_id))

    def get_task_stats(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.get_task_stats(task_id))

    def get_case_detail(self, task_id, case_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.get_case_detail(task_id, case_id))

    def get_case_results(self, task_id, case_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.get_case_results(task_id, case_id))

    def start(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.start(task_id))

    def retry(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.retry(task_id))

    def control(self, task_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.control(task_id, data))

    def stop(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.stop(task_id))

    def reextract(self, task_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import task_config_service
        return _wrap(task_config_service.reextract(task_id, data))


class TestCaseConfigAclRepositoryImpl(TestCaseConfigAclRepository):
    """task_service.TestCaseConfigService 实体 ACL 实现。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.create(data))

    def update(self, tc_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.update(tc_id, data))

    def delete(self, tc_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.delete(tc_id))

    def copy(self, tc_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.copy(tc_id))

    def batch_action(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.batch_action(data))

    def update_ref_params(self, tc_id, round_number, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.update_ref_params(tc_id, round_number, data))

    def list_testcases(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.list_testcases(**kwargs))

    def get_testcase_detail(self, tc_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.get_testcase_detail(tc_id))

    def get_testcase_stats(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.get_testcase_stats())

    def get_testcase_tags(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.get_testcase_tags())

    def get_testcase_ref_params(self, tc_id, round_number) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.get_testcase_ref_params(tc_id, round_number))

    def fetch_case_ids(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import testcase_config_service
        return _wrap(testcase_config_service.fetch_case_ids(data))


class TagConfigAclRepositoryImpl(TagConfigAclRepository):
    """task_service.TagConfigService 实体 ACL 实现。"""

    def create_category(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.create_category(data))

    def update_category(self, category_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.update_category(category_id, data))

    def delete_category(self, category_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.delete_category(category_id))

    def create_tag(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.create_tag(data))

    def update_tag(self, tag_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.update_tag(tag_id, data))

    def delete_tag(self, tag_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.delete_tag(tag_id))

    def batch_update_category(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.batch_update_category(data))

    def list_categories(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.list_categories(**kwargs))

    def get_category(self, category_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.get_category(category_id))

    def list_tags(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.list_tags(**kwargs))

    def list_tag_names(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.list_tag_names(**kwargs))

    def get_tag(self, tag_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.get_tag(tag_id))

    def get_tags_by_category(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import tag_config_service
        return _wrap(tag_config_service.get_tags_by_category())


class AlgorithmConfigAclRepositoryImpl(AlgorithmConfigAclRepository):
    """task_service.AlgorithmConfigService 实体 ACL 实现。"""

    # ---- 算法写操作 ----
    def create_algorithm(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.create_algorithm(data))

    def update_algorithm(self, algo_type, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.update_algorithm(algo_type, data))

    def delete_algorithm(self, algo_type) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.delete_algorithm(algo_type))

    # ---- 参数写操作 ----
    def create_param(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.create_param(data))

    def update_param(self, param_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.update_param(param_id, data))

    def delete_param(self, param_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.delete_param(param_id))

    # ---- 映射写操作 ----
    def create_mapping(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.create_mapping(data))

    def update_mapping(self, mapping_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.update_mapping(mapping_id, data))

    def delete_mapping(self, mapping_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.delete_mapping(mapping_id))

    # ---- 用例参数写操作 ----
    def create_case_param(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.create_case_param(data))

    def update_case_param(self, param_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.update_case_param(param_id, data))

    def delete_case_param(self, param_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.delete_case_param(param_id))

    # ---- 参考参数写操作 ----
    def create_reference_param(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.create_reference_param(data))

    def update_reference_param(self, param_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.update_reference_param(param_id, data))

    def delete_reference_param(self, param_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.delete_reference_param(param_id))

    # ---- 维度关联写操作 ----
    def associate_dimensions(self, algo_type, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.associate_dimensions(algo_type, data))

    def create_dimension_relation(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.create_dimension_relation(data))

    def update_dimension_relation(self, relation_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.update_dimension_relation(relation_id, data))

    def delete_dimension_relation(self, relation_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.delete_dimension_relation(relation_id))

    # ---- 批量操作 ----
    def import_algorithms(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.import_algorithms(data))

    def bulk_delete(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.bulk_delete(data))

    def extract_params(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.extract_params(data))

    def reload_config(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.reload_config())

    # ---- 分组写操作 ----
    def create_group(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.create_group(data))

    def update_group(self, group_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.update_group(group_id, data))

    def delete_group(self, group_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.delete_group(group_id))

    # ---- 读操作 ----
    def list_algorithms(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.list_algorithms(**kwargs))

    def get_algorithm_options(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_algorithm_options())

    def get_algorithm(self, algo_type) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_algorithm(algo_type))

    def list_params(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.list_params(**kwargs))

    def get_param(self, param_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_param(param_id))

    def list_mappings(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.list_mappings(**kwargs))

    def list_case_params(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.list_case_params(**kwargs))

    def get_case_param(self, param_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_case_param(param_id))

    def list_reference_params(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.list_reference_params(**kwargs))

    def get_form_schema(self, algo_type) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_form_schema(algo_type))

    def get_algorithm_dimensions(self, algo_type) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_algorithm_dimensions(algo_type))

    def get_dimension_params(self, dimension_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_dimension_params(dimension_id))

    def list_groups(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.list_groups())

    def get_group(self, group_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import algorithm_config_service
        return _wrap(algorithm_config_service.get_group(group_id))


class EvaluationConfigAclRepositoryImpl(EvaluationConfigAclRepository):
    """evaluation_service.EvaluationConfigService 维度 ACL 实现。"""

    def create_category(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.create_category(data))

    def update_category(self, cat_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.update_category(cat_id, data))

    def delete_category(self, cat_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.delete_category(cat_id))

    def create_dimension(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.create_dimension(data))

    def update_dimension(self, dim_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.update_dimension(dim_id, data))

    def calculate_score(self, dim_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.calculate_score(dim_id, data))

    def delete_dimension(self, dim_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.delete_dimension(dim_id))

    def batch_action(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.batch_action(data))

    def list_categories(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.list_categories())

    def get_dimension_options(self, algorithm_type=None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.get_dimension_options(algorithm_type=algorithm_type))

    def list_dimensions(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.list_dimensions(**kwargs))

    def health_check(self, dim_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.health_check(dim_id))

    def get_dimension_by_ids(self, dim_ids) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_config_service
        return _wrap(evaluation_config_service.get_dimension_by_ids(dim_ids))


class SplConfigAclRepositoryImpl(SplConfigAclRepository):
    """spl_config_service SPL 映射配置 ACL 实现。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.create(data))

    def update(self, mapping_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.update(mapping_id, data))

    def delete(self, mapping_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.delete(mapping_id))

    def calibrate(self, mapping_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.calibrate(mapping_id))

    def play_test_tone(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.play_test_tone(data))

    def stop_test_tone(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.stop_test_tone(data))

    def get_all(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.get_all(**kwargs))

    def get_one(self, mapping_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.get_one(mapping_id))

    def get_history(self, mapping_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.get_history(mapping_id))

    def get_calibration_data(self, mapping_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.get_calibration_data(mapping_id))

    def get_stats(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.get_stats())

    def get_by_device(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import spl_config_service
        return _wrap(spl_config_service.get_by_device(device_id))
