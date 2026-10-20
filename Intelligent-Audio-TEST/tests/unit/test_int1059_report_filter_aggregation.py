# -*- coding: utf-8 -*-
"""INT-1059 专项：V9.7.10 报告筛选/聚合五连移植的等价核验与移植点锁定。

覆盖移植的三项后端行为（b47cae340 / 7bb9fd339 / 0c6b2028a）：
1. 筛选聚合资源 key 与报告生成口径一致（无时间前缀、含版本、含 result_type 后缀）
   ——修复「筛选后数据全为 -」（b47cae340）；
2. case-averages 响应补充 tag_metric_data（标签×资源×指标，策略聚合 0~100，
   前端不再手写平均，避免超 100%）（7bb9fd339/e4e5dface）；
3. case-averages 支持 reportId（对比/二次对比报告经对比矩阵/摘要解析源任务集合，
   与 taskId 走同一聚合工具）（0c6b2028a）。

等价核验（a9c4adc56：逐轮失败值 0 不被排除导致 pass_rate 误报 100%）：
- 非 average 维度 item 收集不依赖 score > 0（collect_dim_items 保留 0 值 item），
  PassRateStrategy 将 0 值计入分母 → 失败轮不会从分母消失。见 test_pass_rate_includes_failed_round_zero。

gRPC helper 以 monkeypatch 替换（对齐 test_int614 惯例）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

import pytest
from unittest.mock import patch

from shared.models.common_enums import TaskStatus


_DIMS = [
    {'id': 1, 'name': '达标率', 'statistic_method': 'pass_rate',
     'agg_denominator': 'case', 'exclude_rounds': []},
    {'id': 2, 'name': '准确率', 'statistic_method': 'average',
     'agg_denominator': 'case', 'exclude_rounds': []},
]


def _dim_row(dim_id, value, round_number=None, api_raw_response=None):
    return {
        'dimension_id': dim_id,
        'dimension_value': value,
        'round_number': round_number,
        'api_raw_response': api_raw_response,
    }


def _result(rid, tc_id, device_id=None, api_id=None, result_data=None, result_data_path=None,
            task_id=7):
    return {
        'id': rid,
        'task_id': task_id,
        'test_case_id': tc_id,
        'device_id': device_id,
        'api_id': api_id,
        'execution_status': TaskStatus.COMPLETED.value,
        'result_data': result_data,
        'result_data_path': result_data_path,
    }


def _tc(tid, group_name, tags):
    return {
        'id': tid,
        'name': f'用例{tid}',
        'group': {'id': 1, 'name': group_name},
        'tags': tags,
    }


def _test_cases_map(cases):
    out = {}
    for c in cases:
        out[c['id']] = c
        out[str(c['id'])] = c
    return out


class _FakeRepo:
    """ReportStatsQueryMixin.repository 桩（reportId 解析用）。"""

    def __init__(self, aggregate=None, comparison=None, summaries=None):
        self._aggregate = aggregate
        self._comparison = comparison
        self._summaries = summaries or []

    def get_by_id(self, report_id):
        return self._aggregate

    def load_comparison(self, report_id):
        return self._comparison

    def load_summaries(self, report_id):
        return self._summaries


class _FakeComparison:
    def __init__(self, comparison_data):
        self.comparison_data = comparison_data


class _FakeAggregate:
    def __init__(self, task_id=0):
        self.task_id = task_id


class _FakeSummary:
    def __init__(self, metadata):
        self.metadata = metadata


# ======================================================================
# 1. 资源 key 口径 + tag_metric_data + pass_rate 失败轮 0（b47cae340/7bb9fd339/a9c4adc56）
# ======================================================================

class TestFilterAggregationCaliber:
    """ReportAggregationService.calculate_averages：资源 key 与报告生成一致 + tag_metric_data。"""

    def _run_calculate(self):
        """单设备任务、两用例：用例101无标签且达标(0.8)，用例102带 tagA 且失败(0.0)。"""
        task = {'id': 7, 'name': 't', 'total_cases': 2,
                'completed_cases': 2, 'failed_cases': 0}
        results = [
            _result(1, 101, device_id=1),
            _result(2, 102, device_id=1),
        ]
        dim_map = {
            1: [_dim_row(1, 0.8), _dim_row(2, 80.0)],
            2: [_dim_row(1, 0.0), _dim_row(2, 60.0)],
        }
        tc_map = _test_cases_map([
            _tc(101, 'g1', []),
            _tc(102, 'g1', [{'name': 'tagA'}]),
        ])

        import report_service.application.services.report_aggregation.stats_mixin as stats_mod
        import report_service.application.services.report_aggregation.resource_mixin as agg_resource_mod
        import report_service.application.services.report_utils.resource_mixin as utils_resource_mod

        device = {'id': 1, 'name': 'dev', 'app_version': '1.0'}
        api = {'id': 2, 'name': 'api', 'api_type': 'http', 'base_url': 'http://x', 'headers': None}

        with patch.object(stats_mod, '_grpc_list_dimensions_all', return_value=_DIMS), \
             patch.object(stats_mod, '_grpc_get_dimension_params',
                          return_value=[{'param_direction': 'output', 'agg_role': 'pass_ge',
                                         'pass_threshold': 0.6}]), \
             patch.object(stats_mod, '_grpc_get_dim_results', return_value=dim_map), \
             patch.object(agg_resource_mod, '_grpc_get_task_devices',
                          return_value=[{'device_id': 1}]), \
             patch.object(agg_resource_mod, '_grpc_get_task_apis',
                          return_value=[{'api_id': 2}]), \
             patch.object(agg_resource_mod, '_grpc_get_devices_by_ids',
                          return_value={1: device}), \
             patch.object(agg_resource_mod, '_grpc_get_apis_by_ids',
                          return_value={2: api}), \
             patch.object(agg_resource_mod, '_grpc_list_testcases_by_ids',
                          return_value=tc_map), \
             patch.object(utils_resource_mod, '_grpc_get_device',
                          return_value=device), \
             patch.object(utils_resource_mod, '_grpc_get_api',
                          return_value=api):
            from report_service.application.services.report_aggregation_service import (
                ReportAggregationService,
            )
            return ReportAggregationService.calculate_averages(
                task, [101, 102], results, 7)

    def test_resource_keys_match_report_generation(self):
        """资源 key 无时间前缀、含版本（b47cae340：不再带 t{task}-{time} 前缀）。"""
        stats = self._run_calculate()
        assert '1-dev-1.0' in stats['resources']
        assert '2-api' in stats['resources']
        # 旧口径（带时间前缀）的 key 不应出现
        assert not any(r.startswith('t7-') for r in stats['resources'])
        # metric_data 非空：聚合匹配不再恒失败（筛选后不再是全 "-"）
        assert stats['metric_data']['g1']['1-dev-1.0']['达标率'] == 50.0
        assert stats['metric_data']['g1']['1-dev-1.0']['准确率'] == 70.0

    def test_pass_rate_includes_failed_round_zero(self):
        """a9c4adc56 等价核验：失败轮 0 计入分母，pass_rate 不再误报 100%。"""
        stats = self._run_calculate()
        # 2 用例 1 达标 → 50%，非 100%
        assert stats['averages_map']['达标率'] == 50.0

    def test_tag_metric_data_returned_with_strategy_aggregation(self):
        """7bb9fd339：tag_metric_data 由后端策略聚合产出（0~100，前端不再手写平均）。"""
        stats = self._run_calculate()
        tag_data = stats['tag_metric_data']
        assert '未标记' in tag_data
        assert 'tagA' in tag_data
        # 无标签用例 0.8 达标 → 100%；tagA 用例 0.0 失败 → 0%
        assert tag_data['未标记']['1-dev-1.0']['达标率'] == 100.0
        assert tag_data['tagA']['1-dev-1.0']['达标率'] == 0.0
        # 平均维度简单平均
        assert tag_data['未标记']['1-dev-1.0']['准确率'] == 80.0
        assert tag_data['tagA']['1-dev-1.0']['准确率'] == 60.0


# ======================================================================
# 2. reportId 解析（0c6b2028a）
# ======================================================================

class TestReportIdResolution:
    """_query_cases_for_averages reportId 分支：经对比矩阵/摘要解析源任务集合。"""

    def _make_handler(self, repo, monkeypatch):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        m.repository = repo
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': i, 'name': f't{i}', 'status': 'completed'} for i in ids])
        return m

    def test_report_id_resolves_comparison_matrix_task_ids(self, monkeypatch):
        """对比报告：comparison matrix.task_ids 解析为源任务集合。"""
        repo = _FakeRepo(
            aggregate=_FakeAggregate(task_id=0),
            comparison=_FakeComparison({'task_ids': [7, 8]}),
        )
        m = self._make_handler(repo, monkeypatch)

        captured = {}

        def _fake_query(task_id_filter, result_task_filter, *a, **k):
            captured['tf'] = task_id_filter
            captured['rf'] = result_task_filter
            return ['c-1', 'c-2'], []

        monkeypatch.setattr(m, '_query_test_cases_and_results', _fake_query)

        task, task_id_filter, fcid, tr, tasks_map, use_time_prefix = m._query_cases_for_averages(
            None, None, [], [], True, report_id=101)

        assert task['id'] == 7  # 取第一个源任务作为标签格式化代表
        assert task_id_filter == [7, 8]
        assert captured['tf'] == [7, 8]
        assert captured['rf'] == [7, 8]
        # INT-1059 返工：对比报告按源任务聚合（use_time_prefix=True + 源任务映射）
        assert use_time_prefix is True
        assert set(tasks_map.keys()) == {7, 8}

    def test_report_id_resolves_summary_task_ids_fallback(self, monkeypatch):
        """无对比矩阵时回退 summary metadata.task_ids。"""
        repo = _FakeRepo(
            aggregate=_FakeAggregate(task_id=0),
            comparison=None,
            summaries=[_FakeSummary({'task_ids': [3, 4]})],
        )
        m = self._make_handler(repo, monkeypatch)

        captured = {}

        def _fake_query(task_id_filter, result_task_filter, *a, **k):
            captured['tf'] = task_id_filter
            return ['c-1'], []

        monkeypatch.setattr(m, '_query_test_cases_and_results', _fake_query)

        task, task_id_filter, fcid, tr, tasks_map, use_time_prefix = m._query_cases_for_averages(
            None, None, [], [], True, report_id=102)
        assert task_id_filter == [3, 4]
        assert captured['tf'] == [3, 4]
        assert use_time_prefix is True
        assert set(tasks_map.keys()) == {3, 4}

    def test_report_id_missing_report_returns_error(self, monkeypatch):
        """报告不存在 → 错误 dict（非 tuple）。"""
        repo = _FakeRepo(aggregate=None)
        m = self._make_handler(repo, monkeypatch)
        out = m._query_cases_for_averages(None, None, [], [], True, report_id=999)
        assert isinstance(out, dict)
        assert out['message'] == '未找到指定报告'

    def test_report_id_no_tasks_returns_error(self, monkeypatch):
        """对比报告未关联任何任务 → 错误 dict。"""
        repo = _FakeRepo(aggregate=_FakeAggregate(task_id=0), comparison=_FakeComparison({}))
        m = self._make_handler(repo, monkeypatch)
        out = m._query_cases_for_averages(None, None, [], [], True, report_id=103)
        assert isinstance(out, dict)
        assert out['message'] == '对比报告未关联任何任务'

    def test_report_id_task_report_keeps_no_prefix(self, monkeypatch):
        """普通任务报告经 reportId 查询：报告主表含 task_id → 资源 key 无前缀（use_time_prefix=False）。"""
        repo = _FakeRepo(
            aggregate=_FakeAggregate(task_id=91),
            comparison=None,
            summaries=[],
        )
        m = self._make_handler(repo, monkeypatch)

        def _fake_query(task_id_filter, result_task_filter, *a, **k):
            return ['c-1'], []

        monkeypatch.setattr(m, '_query_test_cases_and_results', _fake_query)

        task, task_id_filter, fcid, tr, tasks_map, use_time_prefix = m._query_cases_for_averages(
            None, None, [], [], True, report_id=91)
        assert task_id_filter == [91]
        assert use_time_prefix is False
        assert tasks_map == {91: {'id': 91, 'name': 't91', 'status': 'completed'}}

    def test_handle_get_case_averages_report_id_passthrough(self, monkeypatch):
        """handle_get_case_averages：report_id 走通，响应含 tag_metric_data 键。"""
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        repo = _FakeRepo(
            aggregate=_FakeAggregate(task_id=0),
            comparison=_FakeComparison({'task_ids': [7]}),
        )
        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        m.repository = repo
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': i, 'name': f't{i}', 'status': 'completed'} for i in ids])
        monkeypatch.setattr(
            m, '_calculate_averages',
            lambda task, fcid, tr, tid, **kw: {
                'filtered_case_ids': fcid, 'test_results': tr,
                'overall_averages': [], 'averages_map': {},
                'metric_data': {}, 'tag_metric_data': {},
                'raw_data': {}, 'normal_distribution_data': {},
                'resources': [], 'resource_headers': [],
                'metric_name_to_id': {},
            })

        out = m.handle_get_case_averages({'report_id': 101, 'tags': ['tagA']})
        assert 'tag_metric_data' in out
        assert out['total_cases'] == 0

    def test_handle_get_case_averages_requires_task_or_report(self):
        """两者都缺 → 错误（INT-1059：reportId 为可选，taskId 不再必填）。"""
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        out = m.handle_get_case_averages({})
        assert out['message'] == '缺少必要参数: task_id 或 report_id'


# ======================================================================
# 2.5 对比报告按源任务聚合（INT-1059 返工：P2 打回修复）
# ======================================================================

class TestComparisonPerTaskAggregation:
    """对比/二次对比报告筛选（use_time_prefix=True）：资源/指标 key 按源任务加前缀，
    与对比摘要列一致，前端对比面板列不再 0.00/空白。"""

    def _run_calculate(self):
        """两源任务共享同一 API 资源：任务7 用例101 达标、任务8 用例102 失败。"""
        tasks_map = {
            7: {'id': 7, 'name': 't7'},   # 无 started_at → notime 前缀
            8: {'id': 8, 'name': 't8'},
        }
        results = [
            _result(1, 101, api_id=2, task_id=7),
            _result(2, 102, api_id=2, task_id=8),
        ]
        dim_map = {
            1: [_dim_row(1, 0.8), _dim_row(2, 80.0)],
            2: [_dim_row(1, 0.0), _dim_row(2, 60.0)],
        }
        tc_map = _test_cases_map([
            _tc(101, 'g1', []),
            _tc(102, 'g1', [{'name': 'tagA'}]),
        ])

        import report_service.application.services.report_aggregation.stats_mixin as stats_mod
        import report_service.application.services.report_aggregation.resource_mixin as agg_resource_mod
        import report_service.application.services.report_utils.resource_mixin as utils_resource_mod

        api = {'id': 2, 'name': 'api', 'api_type': 'http', 'base_url': 'http://x',
               'headers': None, 'meta': {'version': '1.0'}}

        with patch.object(stats_mod, '_grpc_list_dimensions_all', return_value=_DIMS), \
             patch.object(stats_mod, '_grpc_get_dimension_params',
                          return_value=[{'param_direction': 'output', 'agg_role': 'pass_ge',
                                         'pass_threshold': 0.6}]), \
             patch.object(stats_mod, '_grpc_get_dim_results', return_value=dim_map), \
             patch.object(agg_resource_mod, '_grpc_list_testcases_by_ids',
                          return_value=tc_map), \
             patch.object(utils_resource_mod, '_grpc_get_api',
                          return_value=api), \
             patch.object(utils_resource_mod, '_grpc_get_device',
                          return_value=None):
            from report_service.application.services.report_aggregation_service import (
                ReportAggregationService,
            )
            return ReportAggregationService.calculate_averages(
                tasks_map[7], [101, 102], results, [7, 8],
                tasks_map=tasks_map, use_time_prefix=True,
            )

    def test_resources_keep_per_task_prefix(self):
        """资源 key 带 t{task}-notime- 前缀（与对比摘要列一致），不合并去重。"""
        stats = self._run_calculate()
        assert 't7-notime-2-api-1.0' in stats['resources']
        assert 't8-notime-2-api-1.0' in stats['resources']
        # 两个源任务共享同一 API → 两条资源列（不跨任务合并）
        assert stats['resources'] == ['t7-notime-2-api-1.0', 't8-notime-2-api-1.0']

    def test_metric_data_keyed_per_task(self):
        """metric_data 按源任务各自聚合：任务7 达标 100%、任务8 失败 0%。"""
        stats = self._run_calculate()
        md = stats['metric_data']['g1']
        assert md['t7-notime-2-api-1.0']['达标率'] == 100.0
        assert md['t8-notime-2-api-1.0']['达标率'] == 0.0
        assert md['t7-notime-2-api-1.0']['准确率'] == 80.0
        assert md['t8-notime-2-api-1.0']['准确率'] == 60.0

    def test_tag_metric_data_keyed_per_task(self):
        """tag_metric_data 同样按源任务聚合（未标记→任务7，tagA→任务8）。"""
        stats = self._run_calculate()
        tag_data = stats['tag_metric_data']
        assert tag_data['未标记']['t7-notime-2-api-1.0']['达标率'] == 100.0
        assert tag_data['tagA']['t8-notime-2-api-1.0']['达标率'] == 0.0
        assert 't8-notime-2-api-1.0' not in tag_data['未标记']
        assert 't7-notime-2-api-1.0' not in tag_data['tagA']

    def test_resource_headers_match_resources(self):
        """resource_headers key 与 resources 一一对应。"""
        stats = self._run_calculate()
        header_keys = [h['key'] for h in stats['resource_headers']]
        assert header_keys == stats['resources']


# ======================================================================
# 3. 网关契约（0c6b2028a：GetCaseAveragesRequest.report_id）
# ======================================================================

class TestGatewaySchema:
    def test_report_id_accepted(self):
        from api_gateway.schemas.report import GetCaseAveragesRequest
        req = GetCaseAveragesRequest.model_validate(
            {'report_id': 101, 'tags': ['a'], 'categories': ['g1']})
        assert req.report_id == 101
        assert req.task_id is None

    def test_task_id_still_accepted(self):
        from api_gateway.schemas.report import GetCaseAveragesRequest
        req = GetCaseAveragesRequest.model_validate(
            {'task_id': 7, 'tags': ['a']})
        assert req.task_id == 7
        assert req.report_id is None

    def test_neither_rejected(self):
        from api_gateway.schemas.report import GetCaseAveragesRequest
        req = GetCaseAveragesRequest.model_validate({})
        assert req.task_id is None
        assert req.report_id is None
