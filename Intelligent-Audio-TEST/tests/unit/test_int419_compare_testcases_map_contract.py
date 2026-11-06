# -*- coding: utf-8 -*-
"""INT-419 回归：对比报告生成 test_cases 字典被当列表迭代触发 AttributeError。

根因链路（issue 描述）：
1. _grpc_list_testcases_by_ids 契约返回 {id: dict} 映射（grpc_clients.py:206）；
2. _prepare_compare_data 把映射直接当列表使用，str 键被当用例传入
   extract_case_categories_and_tags（静默丢分组/标签）与
   _build_case_data_compare（AttributeError → 对比报告恒 400）。

修复：
- _prepare_compare_data 按契约归一为 dict 值列表（对齐 _get_task_test_cases 单任务路径）
- _build_case_data_compare / extract_case_categories_and_tags 兼容映射入参（防御）
- _get_source_cases 对 dict 形态 tasks 取 id（同链路的第二个 str/dict 误用：
  t.id 在 dict 上同样 AttributeError，test_cases 归一化后即暴露）

回归验证：真实执行 _prepare_compare_data 全链（仅打桩 gRPC helper），
断言不再崩溃且用例/分组/标签/对比矩阵正确落进 data_dict。
"""
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int419_compare_') + '/report.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.application.services.report_compare_generator_data_mixin import ReportCompareDataMixin
from report_service.application.services.report_compare_helpers import ReportCompareHelpers
import report_service.application.services.report_compare_generator_data_mixin as data_mixin_mod
import report_service.application.services.report_compare_helpers as rch
import report_service.application.services.report_query_builder as rqb
import report_service.application.services.report_helpers as rh
import report_service.application.services.report_utils.resource_mixin as resource_mixin_mod
import report_service.application.services.report_utils.metrics_mixin as metrics_mixin_mod


TASKS = [
    {'id': 1, 'name': '任务A', 'status': 'completed', 'config': {},
     'total_cases': 1, 'completed_cases': 1, 'failed_cases': 0,
     'started_at': '2026-10-01T10:00:00'},
    {'id': 2, 'name': '任务B', 'status': 'completed', 'config': {},
     'total_cases': 1, 'completed_cases': 1, 'failed_cases': 0,
     'started_at': '2026-10-01T11:00:00'},
]
RESULTS = [
    {'id': 101, 'task_id': 1, 'test_case_id': 'TC-1', 'device_id': 7,
     'execution_status': 'completed', 'created_at': '2026-10-01T10:00:01'},
    {'id': 102, 'task_id': 2, 'test_case_id': 'TC-1', 'device_id': 7,
     'execution_status': 'completed', 'created_at': '2026-10-01T11:00:01'},
]
# _grpc_list_testcases_by_ids 的真实返回契约：{id: dict} 映射
TESTCASE_MAP = {
    'TC-1': {'id': 'TC-1', 'name': '对比用例', 'config': {},
             'group': {'id': 'g1', 'name': '分组1'},
             'tags': [{'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': '标签分类X'}]},
}
DIMENSIONS = [{'id': 1, 'name': 'ASR得分', 'weight': 1.0,
               'score_unit': '%', 'decimal_places': 2}]
DIM_RESULTS = {101: [{'dimension_id': 1, 'dimension_value': 80.0}],
               102: [{'dimension_id': 1, 'dimension_value': 60.0}]}
DEVICE_7 = {'id': 7, 'name': 'dev-7', 'app_version': '1.0.0',
            'model': 'M', 'type': 'phone'}


@pytest.fixture()
def stub_grpc(monkeypatch):
    """对比链路全部 gRPC helper 打桩（契约为本 issue 的验证核心）。"""
    # 数据准备 Mixin 直接导入的 helper
    monkeypatch.setattr(data_mixin_mod, '_grpc_list_testcases_by_ids',
                        lambda ids: TESTCASE_MAP)
    # ReportCompareHelpers 模块级 helper
    monkeypatch.setattr(rch, '_grpc_list_dimensions_all', lambda: DIMENSIONS)
    monkeypatch.setattr(rch, '_grpc_get_dim_results', lambda ids: DIM_RESULTS)
    monkeypatch.setattr(rch, '_grpc_get_dimension_params', lambda dim_id: [])
    monkeypatch.setattr(rch, '_grpc_list_testcases_by_ids', lambda ids: TESTCASE_MAP)
    monkeypatch.setattr(rch, '_grpc_get_task_devices', lambda tid: [{'device_id': 7}])
    monkeypatch.setattr(rch, '_grpc_get_task_apis', lambda tid: [])
    monkeypatch.setattr(rch, '_grpc_get_devices_by_ids', lambda ids: {7: DEVICE_7})
    monkeypatch.setattr(rch, '_grpc_get_apis_by_ids', lambda ids: {})
    monkeypatch.setattr(rch, '_grpc_algo_get_reference_params_for_report',
                        lambda config: {})
    # ReportQueryBuilder.get_dimension_results_batch
    monkeypatch.setattr(rqb, '_grpc_get_dim_results', lambda ids: DIM_RESULTS)
    # ReportHelpers（extract_dimension_values 无映射表时按 result_id 兜底查询）
    monkeypatch.setattr(rh, '_grpc_get_dim_results', lambda ids: DIM_RESULTS)
    # ReportUtils.resource_mixin / metrics_mixin（get_resource_name / device_api_stats）
    monkeypatch.setattr(resource_mixin_mod, '_grpc_get_device', lambda did: DEVICE_7)
    monkeypatch.setattr(metrics_mixin_mod, '_grpc_get_device', lambda did: DEVICE_7)
    monkeypatch.setattr(metrics_mixin_mod, '_grpc_list_testcases_by_ids',
                        lambda ids: TESTCASE_MAP)
    monkeypatch.setattr(metrics_mixin_mod, '_grpc_get_dimension_params',
                        lambda dim_id: [])
    # _get_source_cases 读取已存报告：隔离库无报告 → 恒 None（落 source_cases=cases 兜底）
    monkeypatch.setattr(rch.report_repository, 'get_report_by_task_id_raw',
                        lambda task_id: None)
    return TESTCASE_MAP


class TestComparePrepareDataContract:
    """_prepare_compare_data 按 {id: dict} 契约消费用例映射，不再崩溃。"""

    def test_prepare_compare_data_consumes_testcase_mapping(self, stub_grpc):
        """真实执行全链：修复前 _build_case_data_compare 对 str 键 AttributeError。"""
        data_dict, error = ReportCompareDataMixin._prepare_compare_data(
            TASKS, [1, 2], RESULTS)

        assert error is None, f'对比数据准备应成功，实际 error={error}'
        # 契约归一：data_dict["test_cases"] 为 dict 值列表（非映射、非 str 键）
        assert isinstance(data_dict["test_cases"], list)
        assert all(isinstance(tc, dict) for tc in data_dict["test_cases"])
        assert {tc['id'] for tc in data_dict["test_cases"]} == {'TC-1'}

        # extract_case_categories_and_tags 拿到 dict 值列表：分组/标签不再静默丢失，
        # 且 INT-2100 透传标签分类（category_id/category_name）
        assert data_dict["case_categories_list"] == [
            {'id': 'g1', 'name': '分组1'}]
        assert data_dict["case_tags_list"] == [
            {'id': 't1', 'name': '标签1', 'category_id': 5, 'category_name': '标签分类X'}]

        # 用例数据正确构建（results_by_case 命中、资源列/维度值落位）
        assert len(data_dict["source_cases"]) == 1
        case = data_dict["source_cases"][0]
        assert case['id'] == 'TC-1' and case['name'] == '对比用例'
        assert case['category'] == '分组1'
        assert case['tags'] == [{'name': '标签1'}]

        # 对比矩阵：容器列 task_1 / task_2 均有值
        matrix = data_dict["comparison_data"]["matrix"]
        assert 'TC-1' in matrix
        assert matrix['TC-1']['case_name'] == '对比用例'
        assert matrix['TC-1']['task_1']['values']['ASR得分'] == 80.0
        assert matrix['TC-1']['task_2']['values']['ASR得分'] == 60.0

    def test_build_case_data_compare_accepts_mapping_input(self, stub_grpc):
        """防御分支：_build_case_data_compare 直接收 {id: dict} 映射也不崩溃。"""
        tasks_map = {t['id']: t for t in TASKS}
        cases = ReportCompareHelpers._build_case_data_compare(
            TESTCASE_MAP, RESULTS, DIMENSIONS, tasks_map)

        assert len(cases) == 1
        assert cases[0]['id'] == 'TC-1'
        assert set(cases[0]['results'][0].keys()) == {
            'resource', 'status', 'start_time', 'end_time'}

    def test_get_source_cases_accepts_dict_tasks(self, stub_grpc):
        """同链路第二个 str/dict 误用：_get_source_cases 对 dict tasks 取 id 不再崩溃。"""
        # 无已存报告 → source_cases 为空列表（_prepare_compare_data 内回落 cases）
        assert ReportCompareHelpers._get_source_cases(TASKS) == []
