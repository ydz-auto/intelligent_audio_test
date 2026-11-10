# -*- coding: utf-8 -*-
"""INT-2379：报告聚合失败块行级回落 + 覆盖标记。

覆盖卡的验收项（A1/A2/A3/A5/A6/A7/A9）：

- ACL 带 body 拉取失败块时上抛覆盖信息（failed_chunks / dropped_ids），
  非超限失败先重试 1 次；
- 行级合并：基础 map 为完整性基准，body 失败只丢字段不丢行（I1/I2）；
- 加权维度部分覆盖打 `partial_api_raw_response_coverage` 并带 coverage；
- 全部缺 body 沿用 `missing_api_raw_response`，不回退成 partial；
- 查询链响应输出 `aggregation_degraded` / `aggregation_coverage`；
- 大体量 include_body 聚合护栏（C6）串行化并发请求且响应内容不变。

全部为不连库、不起服务的单元测试。
"""
import json
import os
import sys
import threading
import time

import grpc
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('DATABASE_URI', 'postgresql://u:p@localhost:1/unused')

from shared.proto import evaluation_service_pb2 as eval_pb  # noqa: E402
from report_service.infrastructure.acl import evaluation_acl_repository as acl_mod  # noqa: E402
from report_service.infrastructure.acl.evaluation_acl_repository import (  # noqa: E402
    EvaluationDataAclRepositoryImpl,
)
from shared.utils.dto_utils import dto_to_dict  # noqa: E402
from report_service.application.services.dimension_body_merge import (  # noqa: E402
    build_coverage,
    merge_body_into_base,
)
from report_service.domain.services.aggregation_strategies import (  # noqa: E402
    explain_aggregation_degradation,
)
import report_service.application.services.report_data_builder_task_mixin as builder_mod  # noqa: E402


# ---------------- fakes ----------------

class _Exhausted(grpc.RpcError):
    """模拟客户端收包超限（RESOURCE_EXHAUSTED）。"""

    def code(self):
        return grpc.StatusCode.RESOURCE_EXHAUSTED

    def __str__(self):
        return 'RESOURCE_EXHAUSTED: Received message larger than max (simulated)'


def _raw(errors=1, length=100):
    return {'code': 0, 'data': {'result': {'errors': errors, 'length': length}}}


class _BodyStub:
    """按 result_ids 返回带 body 的维度结果；可配置持续失败块 / 毒 id / 首错后成功。"""

    def __init__(self, fail_ids=(), poison_ids=(), fail_first_ids=()):
        self.fail_ids = set(fail_ids)
        self.poison_ids = set(poison_ids)
        self.fail_first_ids = set(fail_first_ids)
        self.calls = []
        self.attempts = {}

    def GetDimensionResultsByResultIds(self, request):
        ids = json.loads(request.result_ids)
        self.calls.append(tuple(ids))
        if any(rid in self.poison_ids for rid in ids):
            raise _Exhausted()
        if any(rid in self.fail_ids for rid in ids):
            return eval_pb.EvaluationDataResponse(
                success=False, message='api_raw_response object missing', data='')
        if any(rid in self.fail_first_ids for rid in ids):
            for rid in ids:
                self.attempts[rid] = self.attempts.get(rid, 0) + 1
            if any(self.attempts[rid] == 1 for rid in ids):
                return eval_pb.EvaluationDataResponse(
                    success=False, message='transient oss error', data='')
        items = [
            {'test_result_id': rid, 'dimension_id': 84,
             'dimension_name': '接管率占比', 'dimension_value': 1.0,
             'round_number': None, 'api_raw_response': _raw()}
            for rid in ids
        ]
        return eval_pb.EvaluationDataResponse(
            success=True, message='', data=json.dumps({'items': items}))


@pytest.fixture
def patch_stub(monkeypatch):
    def _install(stub):
        import shared.clients.grpc_clients as shared_clients
        monkeypatch.setattr(
            shared_clients, 'get_evaluation_data_service_stub', lambda: stub)
        return stub
    return _install


def _as_dict_map(dim_map):
    """ACL 返回的是 DTO；应用层经 _dto_to_dict 还原 dict 后再合并。"""
    return {rid: [dto_to_dict(d) for d in rows] for rid, rows in dim_map.items()}


def _base_map(ids, dim_id=84):
    return {rid: [{'test_result_id': rid, 'dimension_id': dim_id,
                   'dimension_name': '接管率占比', 'dimension_value': 1.0,
                   'score': 1.0, 'round_number': None, 'evaluation_status': 'completed'}]
            for rid in ids}


def _long_items(ids, with_body_ids):
    return [
        {'dimension_value': 1.0, 'test_result_id': rid,
         'raw_fields': ({'present': True, 'values': {'errors': 1, 'length': 100}}
                        if rid in with_body_ids else None)}
        for rid in ids
    ]


# ---------------- ACL 覆盖信息 ----------------

class TestAclCoverage:
    def test_failed_chunk_reported_and_rows_kept_by_merge(self, patch_stub, monkeypatch):
        """A1：第 2 块持续 success=False → 覆盖信息含该块 rid，合并后行不丢。"""
        monkeypatch.setattr(acl_mod, '_DIM_RESULT_BODY_CHUNK_SIZE', 2)
        stub = patch_stub(_BodyStub(fail_ids={3, 4}))
        ids = [1, 2, 3, 4]

        result = EvaluationDataAclRepositoryImpl().get_dimension_results_with_body(ids)

        assert sorted(result.dim_map.keys()) == [1, 2]
        coverage = result.coverage()
        assert coverage['missing'] == [3, 4]
        assert coverage['reason'] == 'partial_api_raw_response_coverage'
        assert len(coverage['failed_chunks']) == 1
        # 失败块首次失败 + 重试 1 次（同一 chunk 两次请求）
        assert stub.calls.count((3, 4)) == 2

        merged, stats = merge_body_into_base(_base_map(ids), _as_dict_map(result.dim_map))
        assert sorted(merged.keys()) == ids                    # I1：行不丢
        for rid in ids:
            assert merged[rid][0]['dimension_value'] == 1.0    # I2：值不变
        assert merged[3][0].get('api_raw_response') is None
        assert merged[1][0]['api_raw_response']['code'] == 0
        assert stats['missing_result_ids'] == [3, 4]

    def test_poison_single_result_dropped_and_flagged(self, patch_stub, monkeypatch):
        """A2：单条超限只丢该 result，dropped_ids 上抛，其余照常。"""
        monkeypatch.setattr(acl_mod, '_DIM_RESULT_BODY_CHUNK_SIZE', 16)
        stub = patch_stub(_BodyStub(poison_ids={2}))

        result = EvaluationDataAclRepositoryImpl().get_dimension_results_with_body([1, 2, 3])

        assert 2 not in result.dim_map
        assert sorted(result.dim_map.keys()) == [1, 3]
        assert result.dropped_ids == [2]
        coverage = result.coverage()
        assert coverage['dropped_ids'] == [2]
        assert 2 in coverage['missing']
        assert any(len(chunk) == 1 for chunk in stub.calls)

    def test_transient_failure_retries_once_and_has_no_partial(self, patch_stub, monkeypatch):
        """A6：第 1 次 success=False、第 2 次成功的块 → 正常路径，不产生 partial。"""
        monkeypatch.setattr(acl_mod, '_DIM_RESULT_BODY_CHUNK_SIZE', 2)
        stub = patch_stub(_BodyStub(fail_first_ids={1, 2}))

        result = EvaluationDataAclRepositoryImpl().get_dimension_results_with_body([1, 2])

        assert sorted(result.dim_map.keys()) == [1, 2]
        coverage = result.coverage()
        assert coverage['missing'] == []
        assert coverage['reason'] is None
        assert coverage['failed_chunks'] == []
        # 块被请求两次：首次失败 + 重试成功
        assert stub.calls.count((1, 2)) == 2
        merged, stats = merge_body_into_base(
            _base_map([1, 2]), _as_dict_map(result.dim_map))
        assert merged[1][0]['api_raw_response']['code'] == 0
        assert stats['missing_result_ids'] == []

    def test_coverage_missing_truncated_with_total(self):
        from report_service.domain.dto import DimensionResultsWithBody
        ids = list(range(1, 71))
        res = DimensionResultsWithBody(
            dim_map={}, requested_ids=ids, covered_ids=[],
            failed_chunks=[(0, 16, 'boom')], dropped_ids=[7])
        cov = res.coverage()
        assert len(cov['missing']) == 50
        assert cov['missing_total'] == 70
        assert cov['requested'] == 70 and cov['covered'] == 0
        assert cov['dropped_ids'] == [7]


# ---------------- 行级合并不变量 ----------------

class TestRowLevelMerge:
    def test_invariants_i1_i2_and_body_fields(self):
        base = {
            1: [
                {'test_result_id': 1, 'dimension_id': 84, 'round_number': None,
                 'dimension_value': 10.0, 'score': 9.0, 'evaluation_status': 'completed'},
                {'test_result_id': 1, 'dimension_id': 84, 'round_number': 0,
                 'dimension_value': 7.0, 'score': 7.0, 'evaluation_status': 'completed'},
            ],
            2: [
                {'test_result_id': 2, 'dimension_id': 84, 'round_number': None,
                 'dimension_value': 20.0, 'score': 20.0, 'evaluation_status': 'completed'},
            ],
        }
        body = {
            1: [
                # body 行即使带着不同取值，也不能覆盖基础 map 的取值列（I2）
                {'test_result_id': 1, 'dimension_id': 84, 'round_number': None,
                 'dimension_value': 99.0, 'score': 99.0,
                 'api_raw_response': _raw()},
                # 基础 map 没有的 key：忽略（I1）
                {'test_result_id': 1, 'dimension_id': 999, 'round_number': None,
                 'api_raw_response': _raw()},
            ],
        }

        merged, stats = merge_body_into_base(base, body)

        assert sorted(merged.keys()) == sorted(base.keys())
        for rid, rows in base.items():
            assert len(merged[rid]) == len(rows)
            for base_row, merged_row in zip(rows, merged[rid]):
                assert merged_row['dimension_value'] == base_row['dimension_value']
                assert merged_row['score'] == base_row['score']
                assert merged_row['evaluation_status'] == base_row['evaluation_status']
        # body 只补字段：整体行拿到 api_raw_response，轮次行保留但缺 body
        assert merged[1][0]['api_raw_response']['code'] == 0
        assert merged[1][1].get('api_raw_response') is None
        # rid 2 没有 body → 行保留
        assert merged[2][0]['dimension_value'] == 20.0
        assert stats['missing_result_ids'] == [1, 2]
        assert stats['ignored_body_rows'] == 1

    def test_build_coverage_counts_only_rows_with_base(self):
        merged, stats = merge_body_into_base(
            _base_map([1, 2, 3]), {1: [{'test_result_id': 1, 'dimension_id': 84,
                                        'round_number': None,
                                        'api_raw_response': _raw()}]})
        cov = build_coverage({'failed_chunks': [(16, 32, 'x')], 'dropped_ids': [9]}, stats)
        assert cov['requested'] == 3 and cov['covered'] == 1
        assert cov['missing'] == [2, 3]
        assert cov['failed_chunks'] == [(16, 32, 'x')]
        assert cov['dropped_ids'] == [9]
        assert cov['reason'] == 'partial_api_raw_response_coverage'


# ---------------- 加权维度覆盖标记 ----------------

_PARAMS = [
    {'dim_id': 9, 'param_code': 'errors', 'field_path': 'errors', 'agg_role': 'numerator'},
    {'dim_id': 9, 'param_code': 'length', 'field_path': 'length', 'agg_role': 'denominator'},
]


class TestPartialDegradationMarker:
    def test_partial_coverage_marked_even_when_value_computed(self):
        """A1：部分 item 缺 body 且策略算出值 → partial 标记 + coverage 明细。"""
        items = _long_items([1, 2, 3], with_body_ids={1, 2})
        deg = explain_aggregation_degradation(
            'weighted_sum_ratio', items, output_params=_PARAMS,
            denominator_mode='case', aggregate_value=55.0)
        assert deg is not None
        assert deg['reason'] == 'partial_api_raw_response_coverage'
        assert deg['applied_method'] == 'weighted_sum_ratio'
        assert deg['coverage']['requested'] == 3
        assert deg['coverage']['covered'] == 2
        assert deg['coverage']['missing'] == [3]
        assert deg['coverage']['missing_total'] == 1

    def test_full_coverage_not_marked(self):
        items = _long_items([1, 2], with_body_ids={1, 2})
        assert explain_aggregation_degradation(
            'weighted_sum_ratio', items, output_params=_PARAMS,
            aggregate_value=55.0) is None

    def test_all_missing_keeps_missing_api_raw_response(self):
        """A3：全部块失败 → 全缺 body，沿用 missing_api_raw_response，不出现 partial。"""
        items = _long_items([1, 2], with_body_ids=set())
        deg = explain_aggregation_degradation(
            'weighted_sum_ratio', items, output_params=_PARAMS,
            denominator_mode='case', aggregate_value=None)
        assert deg is not None
        assert deg['reason'] == 'missing_api_raw_response'
        assert deg.get('coverage') is None

    def test_non_weighted_dimension_never_marked(self):
        items = _long_items([1, 2], with_body_ids=set())
        assert explain_aggregation_degradation(
            'average', items, output_params=[], aggregate_value=None) is None

    def test_mark_degraded_metrics_writes_coverage(self):
        from report_service.application.services.report_task_generator import ReportTaskGenerator
        all_metrics = [{'id': 9, 'name': '接管率占比'}]
        degraded = {'接管率占比': {
            'configured_method': 'weighted_sum_ratio',
            'applied_method': 'weighted_sum_ratio',
            'reason': 'partial_api_raw_response_coverage',
            'detail': 'x',
            'coverage': {'requested': 3, 'covered': 2, 'missing': [3],
                         'missing_total': 1},
        }}
        ReportTaskGenerator._mark_degraded_metrics(all_metrics, degraded)
        assert all_metrics[0]['aggregation_degraded'] is True
        assert all_metrics[0]['degradation_reason'] == 'partial_api_raw_response_coverage'
        assert all_metrics[0]['coverage']['missing'] == [3]


# ---------------- 查询链响应 ----------------

class TestQueryChainResponse:
    def _stats(self, degraded, coverage):
        return {
            'filtered_case_ids': [], 'test_results': [],
            'overall_averages': [], 'averages_map': {},
            'metric_data': {}, 'tag_metric_data': {}, 'raw_data': {},
            'normal_distribution_data': {}, 'resources': [],
            'resource_headers': [], 'metric_name_to_id': {},
            'aggregation_degraded': degraded,
            'aggregation_coverage': coverage,
        }

    def _call(self, stats):
        from unittest.mock import patch
        from report_service.application.handlers.report_handlers import ReportQueryHandler
        handler = ReportQueryHandler(repository=None)
        with patch.object(ReportQueryHandler, '_query_cases_for_averages',
                          return_value=(None, None, [], [], {}, False)), \
             patch.object(ReportQueryHandler, '_calculate_averages', return_value=stats):
            return handler.handle_get_case_averages({'task_id': 1})

    def test_degraded_response_exposes_missing_rids(self):
        """A7：注入失败块时 aggregation_degraded=true 且带缺失 rid。"""
        resp = self._call(self._stats(
            {'接管率占比': {'reason': 'partial_api_raw_response_coverage'}},
            {'requested': 4, 'covered': 2, 'missing': [3, 4],
             'missing_total': 2, 'reason': 'partial_api_raw_response_coverage'}))
        assert resp['aggregation_degraded'] is True
        assert resp['aggregation_coverage']['missing'] == [3, 4]

    def test_normal_response_is_not_degraded(self):
        resp = self._call(self._stats({}, {}))
        assert resp['aggregation_degraded'] is False
        assert resp['aggregation_coverage'] == {}


# ---------------- C6 并发护栏 ----------------

class TestAggregationGate:
    def test_concurrent_compression_serialized_and_identical(self, patch_stub, monkeypatch):
        """A9：并发两个大体量聚合不并发执行；INT-2381 后块内压缩结果等价且无原始响应常驻。"""
        state = {'active': 0, 'peak': 0}
        lock = threading.Lock()

        class _SlowStub(_BodyStub):
            def GetDimensionResultsByResultIds(self, request):
                with lock:
                    state['active'] += 1
                    state['peak'] = max(state['peak'], state['active'])
                try:
                    time.sleep(0.2)
                    return super().GetDimensionResultsByResultIds(request)
                finally:
                    with lock:
                        state['active'] -= 1

        patch_stub(_SlowStub())
        base = _base_map([1, 2, 3])
        results = []

        def _run():
            results.append(builder_mod.ReportDataTaskMixin._get_dimension_results_compressed(
                base, [1, 2, 3], {84: _PARAMS}))

        threads = [threading.Thread(target=_run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 2
        assert state['peak'] == 1                      # 串行执行
        merged_a, cov_a = results[0]
        merged_b, cov_b = results[1]
        assert merged_a == merged_b                    # 压缩结果内容不变
        assert cov_a == cov_b
        for rows in merged_a.values():
            for row in rows:
                assert row.get('api_raw_response') is None
                assert row['raw_fields']['present'] is True
                assert row['raw_fields']['values']['errors'] == 1
