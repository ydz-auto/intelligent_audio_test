# -*- coding: utf-8 -*-
"""INT-959 回归：二次对比 prepare_data 6/7 元组解包错位。

report_compare_helpers._collect_all_resources 错误路径（无测试结果 /
无设备或API资源）只返回 6 元组，而
report_compare_generator_secondary_mixin._prepare_secondary_data:22
按 7 元组解包 → prepare_data 阶段抛 not enough values to unpack
(expected 7, got 6)，异常被 _secondary_compare_async 的 except 吞成
泛化文案「对比报告生成失败，请稍后重试」，成功路径不可达。

修复（INT-959）：_collect_all_resources 统一返回 7 元组
(results, resources, devices_list, apis_list, device_ids, api_ids, error)，
错误路径补齐前 6 位为 None、error 恒为末位；明确业务错误经 SSE
secondary_compare_generated 事件的 error 字段如实呈现。

覆盖：
- 错误路径（无测试结果数据 / 有结果但无设备或API资源）：_collect_all_resources
  返回 7 元组，_prepare_secondary_data 返回 (None, 明确错误)，不抛解包异常。
- 正常路径（有结果与设备/API 资源）：_collect_all_resources 返回 7 元组
  （error=None），_prepare_secondary_data 产出数据 dict。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import report_service.application.services.report_compare_helpers as rch  # noqa: E402
from report_service.application.services.report_compare_helpers import ReportCompareHelpers  # noqa: E402
from report_service.application.services.report_compare_generator_secondary_mixin import ReportSecondaryDataMixin  # noqa: E402
from report_service.application.services.report_data_builder import ReportDataBuilder  # noqa: E402
from report_service.application.services.report_helpers import ReportHelpers  # noqa: E402
from report_service.application.services.report_utils import ReportUtils  # noqa: E402


_TASK_WITH_CONFIG = {'id': 1, 'config': {}}
_REPORTS = [{'id': 7}, {'id': 8}]
_NO_RESULTS_ERROR = '未找到测试结果数据'
_NO_RESOURCES_ERROR = '未找到设备或API资源数据'


def _resource_name_stub(res, task=None, use_time_prefix=False):
    return 'res-1'


class TestCollectAllResourcesErrorArity:
    """错误路径统一 7 元组：前 6 位 None、error 末位，解包不再错位。"""

    def test_no_results_returns_7_tuple(self, monkeypatch):
        monkeypatch.setattr(rch, '_grpc_get_test_results_by_task_ids', lambda task_ids: [])

        out = ReportCompareHelpers._collect_all_resources([1], [_TASK_WITH_CONFIG])

        assert len(out) == 7, f'错误路径应返 7 元组，实际 {len(out)}'
        assert out == (None, None, None, None, None, None, _NO_RESULTS_ERROR)

    def test_no_results_prepare_secondary_returns_clear_error(self, monkeypatch):
        monkeypatch.setattr(rch, '_grpc_get_test_results_by_task_ids', lambda task_ids: [])

        data, error = ReportSecondaryDataMixin._prepare_secondary_data(
            [7, 8], _REPORTS, [_TASK_WITH_CONFIG], [1])

        # 修复前此处抛 not enough values to unpack (expected 7, got 6)
        assert data is None
        assert error == _NO_RESULTS_ERROR

    def test_no_resources_returns_7_tuple(self, monkeypatch):
        monkeypatch.setattr(rch, '_grpc_get_test_results_by_task_ids',
                            lambda task_ids: [{'id': 11, 'task_id': 1}])
        monkeypatch.setattr(ReportHelpers, 'get_resource_name',
                            staticmethod(_resource_name_stub))
        monkeypatch.setattr(ReportDataBuilder, '_get_task_resources',
                            staticmethod(lambda task_ids: ([], [], [], [])))

        out = ReportCompareHelpers._collect_all_resources([1], [_TASK_WITH_CONFIG])

        assert len(out) == 7, f'错误路径应返 7 元组，实际 {len(out)}'
        assert out == (None, None, None, None, None, None, _NO_RESOURCES_ERROR)

    def test_no_resources_prepare_secondary_returns_clear_error(self, monkeypatch):
        monkeypatch.setattr(rch, '_grpc_get_test_results_by_task_ids',
                            lambda task_ids: [{'id': 11, 'task_id': 1}])
        monkeypatch.setattr(ReportHelpers, 'get_resource_name',
                            staticmethod(_resource_name_stub))
        monkeypatch.setattr(ReportDataBuilder, '_get_task_resources',
                            staticmethod(lambda task_ids: ([], [], [], [])))

        data, error = ReportSecondaryDataMixin._prepare_secondary_data(
            [7, 8], _REPORTS, [_TASK_WITH_CONFIG], [1])

        assert data is None
        assert error == _NO_RESOURCES_ERROR


class TestCollectAllResourcesNormalPath:
    """正常路径：7 元组 error=None，_prepare_secondary_data 产出完整数据。"""

    @pytest.fixture(autouse=True)
    def _stub_success_chain(self, monkeypatch):
        results = [{'id': 11, 'task_id': 1, 'test_case_id': 201,
                    'execution_status': 'completed'}]
        monkeypatch.setattr(rch, '_grpc_get_test_results_by_task_ids',
                            lambda task_ids: results)
        monkeypatch.setattr(ReportHelpers, 'get_resource_name',
                            staticmethod(_resource_name_stub))
        monkeypatch.setattr(ReportDataBuilder, '_get_task_resources',
                            staticmethod(lambda task_ids: (['dev1'], ['api1'], [1], [2])))
        # 下游计算均打桩：只验证 _collect_all_resources ↔ _prepare_secondary_data 解包链路
        monkeypatch.setattr(ReportCompareHelpers, '_build_all_dimensions',
                            staticmethod(lambda res_ids: (['dim1'], ['m1'], None)))
        monkeypatch.setattr(ReportDataBuilder, '_get_dimension_results_batch',
                            staticmethod(lambda res_ids, include_body=False: ({11: []}, {})))
        monkeypatch.setattr(ReportUtils, 'calculate_core_metrics',
                            staticmethod(lambda **kw: {
                                'metric_data': {'res-1': []},
                                'tag_metric_data': {},
                                'raw_data': {'res-1': {'dim1': []}},
                                'case_type_stats': [],
                                'resources': ['res-1'],
                            }))
        monkeypatch.setattr(ReportUtils, 'build_resource_headers',
                            staticmethod(lambda **kw: ['res-1']))
        monkeypatch.setattr(ReportUtils, 'calculate_device_api_stats',
                            staticmethod(lambda **kw: ({}, {})))
        monkeypatch.setattr(ReportDataBuilder, '_get_task_test_cases',
                            staticmethod(lambda task_ids: ([], [])))
        monkeypatch.setattr(ReportCompareHelpers, '_get_source_cases_from_reports',
                            staticmethod(lambda reports: [{'id': 'c1', 'name': 'case-1'}]))
        monkeypatch.setattr(ReportCompareHelpers, '_build_comparison_matrix_secondary',
                            staticmethod(lambda task_ids, reports, all_dimensions: {}))
        return results

    def test_collect_all_resources_returns_full_7_tuple(self, monkeypatch, _stub_success_chain):
        out = ReportCompareHelpers._collect_all_resources([1], [_TASK_WITH_CONFIG])

        assert len(out) == 7
        assert out == ([{'id': 11, 'task_id': 1, 'test_case_id': 201,
                         'execution_status': 'completed'}],
                       ['res-1'], ['dev1'], ['api1'], [1], [2], None)

    def test_prepare_secondary_data_succeeds(self, monkeypatch, _stub_success_chain):
        data, error = ReportSecondaryDataMixin._prepare_secondary_data(
            [7, 8], _REPORTS, [_TASK_WITH_CONFIG], [1])

        assert error is None
        assert data is not None
        assert data['results'] == _stub_success_chain
        assert data['resources'] == ['res-1']
        assert data['devices_list'] == ['dev1']
        assert data['apis_list'] == ['api1']
        assert data['device_ids'] == [1]
        assert data['api_ids'] == [2]
        assert data['all_dimensions'] == ['dim1']
        assert data['all_metrics'] == ['m1']
        assert data['source_cases'] == [{'id': 'c1', 'name': 'case-1'}]
        assert data['case_categories_list'] == [{'id': 'default_group', 'name': '无分组'}]
        assert data['case_tags_list'] == [{'id': 'default_tag', 'name': '无标签', 'category_id': None, 'category_name': None}]
