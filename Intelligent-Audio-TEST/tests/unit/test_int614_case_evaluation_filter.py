# -*- coding: utf-8 -*-
"""INT-614 守卫：统计前置过滤（按用例评估状态过滤）对齐 V9.7.10。

原缺陷：V9.7.10 报告生成链在统计取值前调用
`ReportUtils.filter_results_by_case_evaluation(results)` —— 用例任一维度评估状态
非 completed 则整个用例不参与统计。V9.7.31 report_service 缺失该函数（仅
`filter_results_by_case_ids` 按 case_id 过滤、不看评估状态），`evaluation_status`
只停留在 DTO 字段，聚合链取值未过滤。

修复：
- 新增 `filter_results_by_case_evaluation(test_results, dim_results_map)` 纯函数
  （_report_case_filters.py），对齐 V9.7.10 语义：
    任一维度评估结果 evaluation_status 非 completed → 该用例所有结果排除；
    evaluation_status 为 None（无评估行/旧数据）不排除（对齐 SQL NULL 语义）。
- 报告主生成链 `report_task_generator._prepare_report_data`：维度结果拉取后立即过滤，
  过滤后重取 res_ids / dim_results_map / dim_stats（下游 all_dimensions/汇总/指标
  口径与 V9.7.10 过滤后一致）。
- 查询链 `stats_mixin.calculate_averages`：维度结果拉取后立即过滤（统计/聚合链
  取值前过滤；filtered_case_ids 保持 category/tags 口径不变）。

本文件覆盖：纯函数语义矩阵 + 查询链集成 + 报告主生成链集成。
"""
import os
from types import SimpleNamespace
from unittest.mock import patch

# BaseConfig 在 import 时校验环境变量（与仓库既有单测同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import TaskStatus
from report_service.application.handlers._report_case_filters import (
    filter_results_by_case_evaluation,
)
import report_service.application.services.report_aggregation.stats_mixin as stats_mod
from report_service.application.services.report_aggregation.stats_mixin import (
    _AggregationStatsMixin,
)
from report_service.application.services.report_aggregation.service import (
    ReportAggregationService,
)
import report_service.application.services.report_aggregation.resource_mixin as agg_resource_mod
import report_service.application.services.report_task_generator as gen_mod


# ======================================================================
# 纯函数：filter_results_by_case_evaluation
# ======================================================================

def _tr(rid, tc_id, **extra):
    return {'id': rid, 'test_case_id': tc_id, 'execution_status': TaskStatus.COMPLETED.value, **extra}


def _dim_row(dim_id, value, ev_status, round_number=None):
    return {'dimension_id': dim_id, 'dimension_value': value,
            'round_number': round_number, 'evaluation_status': ev_status}


class TestFilterResultsByCaseEvaluation:
    def test_excludes_case_with_non_completed_dimension(self):
        results = [_tr(1, 101), _tr(2, 102)]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 60.0, 'pending')],   # 用例 102 任一维度非 completed
        }
        out = filter_results_by_case_evaluation(results, dim_map)
        assert [r['id'] for r in out] == [1]
        assert [r['test_case_id'] for r in out] == [101]

    def test_keeps_all_completed(self):
        results = [_tr(1, 101), _tr(2, 102)]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 60.0, 'completed')],
        }
        out = filter_results_by_case_evaluation(results, dim_map)
        assert len(out) == 2

    def test_same_case_multiple_results_all_excluded(self):
        """同一用例的多条结果（如多资源）全被排除。"""
        results = [_tr(1, 101, device_id=1), _tr(2, 101, device_id=2), _tr(3, 102)]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 70.0, 'running')],   # 用例 101 非 completed
            3: [_dim_row(1, 60.0, 'completed')],
        }
        out = filter_results_by_case_evaluation(results, dim_map)
        assert [r['id'] for r in out] == [3]

    def test_none_status_not_excluded(self):
        """evaluation_status 为 None（无评估行/旧数据）不排除——对齐 V9.7.10 SQL NULL 语义。"""
        results = [_tr(1, 101), _tr(2, 102)]
        dim_map = {
            1: [{'dimension_id': 1, 'dimension_value': 80.0, 'evaluation_status': None}],
            2: [{'dimension_id': 1, 'dimension_value': 60.0, 'evaluation_status': None}],
        }
        out = filter_results_by_case_evaluation(results, dim_map)
        assert len(out) == 2

    def test_failed_status_excluded(self):
        results = [_tr(1, 101)]
        dim_map = {1: [_dim_row(1, 80.0, 'failed')]}
        out = filter_results_by_case_evaluation(results, dim_map)
        assert out == []

    def test_result_without_dim_rows_kept(self):
        """结果在 dim_results_map 中无条目 → 不排除。"""
        results = [_tr(1, 101), _tr(2, 102)]
        dim_map = {1: [_dim_row(1, 80.0, 'completed')]}  # 2 无维度行
        out = filter_results_by_case_evaluation(results, dim_map)
        assert len(out) == 2

    def test_empty_inputs(self):
        assert filter_results_by_case_evaluation([], {}) == []
        assert filter_results_by_case_evaluation(None, {}) is None
        assert filter_results_by_case_evaluation([_tr(1, 101)], {}) == [_tr(1, 101)]

    def test_object_payloads(self):
        """兼容对象载荷（SimpleNamespace）。"""
        results = [
            SimpleNamespace(id=1, test_case_id=101),
            SimpleNamespace(id=2, test_case_id=102),
        ]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 60.0, 'pending')],
        }
        out = filter_results_by_case_evaluation(results, dim_map)
        assert [r.id for r in out] == [1]

    def test_mixed_dict_object_payloads(self):
        results = [_tr(1, 101), SimpleNamespace(id=2, test_case_id=102)]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 60.0, 'pending')],
        }
        out = filter_results_by_case_evaluation(results, dim_map)
        assert [r['id'] if isinstance(r, dict) else r.id for r in out] == [1]

    def test_case_without_tc_id_not_excluded_via_none(self):
        """test_case_id 缺失的结果不应被 None 排除键误伤。"""
        results = [_tr(1, 101), {'id': 2, 'test_case_id': None, 'execution_status': 'completed'}]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 60.0, 'failed')],   # test_case_id=None → 不写入排除集合
        }
        out = filter_results_by_case_evaluation(results, dim_map)
        assert [r.get('id') if isinstance(r, dict) else r.id for r in out] == [1, 2]

    def test_evaluation_status_case_insensitive_not_applied(self):
        """'COMPLETED' 大写仍视为非 completed（状态值全小写，不做大小写归一）。"""
        results = [_tr(1, 101)]
        dim_map = {1: [_dim_row(1, 80.0, 'COMPLETED')]}
        out = filter_results_by_case_evaluation(results, dim_map)
        assert out == []


# ======================================================================
# 查询链集成：stats_mixin.calculate_averages 统计前置过滤
# ======================================================================

_DIMS = [
    {'id': 1, 'name': '准确率', 'statistic_method': 'average',
     'agg_denominator': 'case', 'exclude_rounds': []},
]
_NO_PARAMS: list = []


def _query_chain_results():
    return [
        {'id': 1, 'task_id': 7, 'test_case_id': 101,
         'execution_status': TaskStatus.COMPLETED.value, 'device_id': 1},
        {'id': 2, 'task_id': 7, 'test_case_id': 102,
         'execution_status': TaskStatus.COMPLETED.value, 'device_id': 1},
    ]


def _query_chain_dim_map():
    return {
        1: [_dim_row(1, 80.0, 'completed')],
        2: [_dim_row(1, 60.0, 'pending')],   # 用例 102 非 completed → 应被过滤
    }


def _query_chain_test_cases():
    return {
        101: {'id': 101, 'group': {'id': 1, 'name': 'g1'}, 'tags': []},
        '101': {'id': 101, 'group': {'id': 1, 'name': 'g1'}, 'tags': []},
        102: {'id': 102, 'group': {'id': 1, 'name': 'g1'}, 'tags': []},
        '102': {'id': 102, 'group': {'id': 1, 'name': 'g1'}, 'tags': []},
    }


class TestQueryChainStatsPrefilter:
    def _run_calculate_averages(self):
        task = {'id': 7, 'name': 't', 'total_cases': 2,
                'completed_cases': 2, 'failed_cases': 0}
        tc_map = _query_chain_test_cases()
        with patch.object(stats_mod, '_grpc_list_dimensions_all',
                          return_value=_DIMS), \
             patch.object(stats_mod, '_grpc_get_dimension_params',
                          return_value=_NO_PARAMS), \
             patch.object(stats_mod, '_grpc_get_dim_results',
                          return_value=_query_chain_dim_map()), \
             patch.object(agg_resource_mod, '_grpc_get_task_devices',
                          return_value=[]), \
             patch.object(agg_resource_mod, '_grpc_get_task_apis',
                          return_value=[]), \
             patch.object(agg_resource_mod, '_grpc_get_devices_by_ids',
                          return_value={}), \
             patch.object(agg_resource_mod, '_grpc_get_apis_by_ids',
                          return_value={}), \
             patch.object(agg_resource_mod, '_grpc_list_testcases_by_ids',
                          return_value=tc_map), \
             patch.object(stats_mod.ReportHelpers, 'get_resource_name',
                          return_value='dev-1'):
            return ReportAggregationService.calculate_averages(
                task, [101, 102], _query_chain_results(), 7)

    def test_non_completed_case_excluded_from_stats(self):
        stats = self._run_calculate_averages()
        # 用例 102（pending）的结果被过滤：返回的 test_results 只剩用例 101
        result_ids = [r['id'] for r in stats['test_results']]
        assert result_ids == [1]
        # 平均分只来自用例 101（80.0）
        assert stats['averages_map']['准确率'] == 80.0

    def test_case_ids_keep_category_tag_filter_caliber(self):
        """filtered_case_ids 保持 category/tags 过滤口径（不过滤评估状态）。"""
        stats = self._run_calculate_averages()
        assert stats['filtered_case_ids'] == [101, 102]


# ======================================================================
# 报告主生成链集成：_prepare_report_data 统计前置过滤 + 重取维度结果
# ======================================================================

class TestPrepareReportDataPrefilter:
    def _run_prepare(self, dim_map_builder, results):
        """精简 stub 驱动 _prepare_report_data，捕获传给 calculate_core_metrics 的 results。"""
        captured = {}
        batch_calls = []

        def _batch(ids):
            batch_calls.append(ids)
            return dim_map_builder(ids), [{'id': 1, 'name': '准确率'}]

        task = {'id': 1, 'name': 't', 'status': 'completed', 'total_cases': 2,
                'completed_cases': 2, 'failed_cases': 0}

        import report_service.application.services.report_utils as utils_mod
        import report_service.application.services.report_query_builder as qb_mod

        builder_stubs = {
            '_get_source_task_ids': lambda t: [],
            '_get_dimension_results_batch': staticmethod(_batch),
            '_calculate_summary_dimensions': lambda stats: [],
            '_get_task_test_cases': lambda ids: ([], []),
            '_get_task_resources': lambda ids: (['dev'], [], [1], []),
            '_get_resource_result_types_batch': lambda *a, **k: ({}, {}),
            '_build_resources_list': lambda *a, **k: ['dev-1'],
            '_build_all_metrics': lambda dims: [{'id': 1, 'name': '准确率'}],
            '_build_case_data': lambda *a, **k: [],
        }
        gen_stubs = {
            '_collect_field_mappings_snapshot': lambda *a, **k: {},
        }
        utils_stubs = {
            'calculate_core_metrics': lambda **k: (
                captured.__setitem__('core_results', k['results']),
                {'metric_data': [], 'tag_metric_data': [], 'raw_data': [],
                 'case_type_stats': [], 'resources': []})[1],
            'build_resource_headers': lambda **k: [],
            'calculate_device_api_stats': lambda **k: ([], []),
        }

        originals_builder = {k: getattr(gen_mod.ReportDataBuilder, k)
                             for k in builder_stubs}
        originals_gen = {k: getattr(gen_mod.ReportTaskGenerator, k)
                         for k in gen_stubs}
        originals_utils = {k: getattr(utils_mod.ReportUtils, k)
                           for k in utils_stubs}
        originals_mod = {
            '_grpc_list_dimensions_all': getattr(gen_mod, '_grpc_list_dimensions_all'),
            '_grpc_get_devices_by_ids': getattr(gen_mod, '_grpc_get_devices_by_ids'),
            '_grpc_get_apis_by_ids': getattr(gen_mod, '_grpc_get_apis_by_ids'),
        }
        saved_extract = qb_mod.ReportQueryBuilder.extract_case_categories_and_tags

        try:
            for name, fn in builder_stubs.items():
                setattr(gen_mod.ReportDataBuilder, name, fn)
            for name, fn in gen_stubs.items():
                setattr(gen_mod.ReportTaskGenerator, name, staticmethod(fn))
            for name, fn in {
                '_grpc_list_dimensions_all': lambda: _DIMS,
                '_grpc_get_devices_by_ids': lambda ids: {},
                '_grpc_get_apis_by_ids': lambda ids: {},
            }.items():
                setattr(gen_mod, name, fn)
            for name, fn in utils_stubs.items():
                setattr(utils_mod.ReportUtils, name, staticmethod(fn))
            qb_mod.ReportQueryBuilder.extract_case_categories_and_tags = staticmethod(
                lambda tc: ([], []))

            data = gen_mod.ReportTaskGenerator._prepare_report_data(task, 1, results)
        finally:
            for name, fn in originals_builder.items():
                setattr(gen_mod.ReportDataBuilder, name, fn)
            for name, fn in originals_gen.items():
                setattr(gen_mod.ReportTaskGenerator, name, fn)
            for name, fn in originals_utils.items():
                setattr(utils_mod.ReportUtils, name, fn)
            for name, fn in originals_mod.items():
                setattr(gen_mod, name, fn)
            qb_mod.ReportQueryBuilder.extract_case_categories_and_tags = saved_extract

        captured['batch_calls'] = batch_calls
        captured['data'] = data
        return captured

    def test_filters_results_before_metrics(self):
        results = [_tr(1, 101), _tr(2, 102)]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 60.0, 'pending')],
        }
        captured = self._run_prepare(lambda ids: dim_map, results)
        # calculate_core_metrics 收到过滤后的结果（只剩用例 101）
        assert captured['core_results'] is not None
        assert [r['id'] for r in captured['core_results']] == [1]
        # 发生过滤 → _get_dimension_results_batch 重取（两次调用）
        assert len(captured['batch_calls']) == 2
        # 报告数据仍生成（非空 dict）
        assert captured['data'] is not None
        assert captured['data']['total_cases'] == 2

    def test_no_filter_no_refetch(self):
        results = [_tr(1, 101), _tr(2, 102)]
        dim_map = {
            1: [_dim_row(1, 80.0, 'completed')],
            2: [_dim_row(1, 60.0, 'completed')],
        }
        captured = self._run_prepare(lambda ids: dim_map, results)
        assert len(captured['batch_calls']) == 1
        assert [r['id'] for r in captured['core_results']] == [1, 2]
