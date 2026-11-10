# -*- coding: utf-8 -*-
"""INT-2381：include_body 迭代分块 + 块内提取标量。

覆盖卡的验收项（B7/B8 相关单元层）：

- ACL 新增迭代形态 `iter_dimension_results_with_body`：逐块 yield
  (chunk_map, chunk_coverage)，块覆盖口径与 INT-2379 C2 一致；
- 领域纯函数 `extract_raw_fields`：从 api_raw_response 按 output_params
  提取标量，原始响应缺失/不可解析返回 None；
- 报告聚合入参契约：item 只有 `raw_fields`，不再有 `api_raw_response`；
- 压缩合并：行级合并后块内提取并丢弃原始响应，行集合与基础 map 一致，
  覆盖信息沿用 C2 结构且全缺 body 时 reason 为 missing_api_raw_response（O2）。

全部为不连库、不起服务的单元测试。
"""
import json
import os
import sys

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
from report_service.domain.services.aggregation_strategies import (  # noqa: E402
    WeightedSumRatioStrategy,
    explain_aggregation_degradation,
    extract_raw_fields,
)
from report_service.domain.services.round_caliber import collect_dim_items  # noqa: E402
import report_service.application.services.report_data_builder_task_mixin as builder_mod  # noqa: E402


def _raw(errors=2, length=100):
    return {'code': 0, 'data': {'result': {'errors': errors, 'length': length}}}


_PARAMS = [
    {'param_code': 'errors', 'field_path': 'errors', 'agg_role': 'numerator'},
    {'param_code': 'length', 'field_path': 'length', 'agg_role': 'denominator'},
]


# ---------------- 领域纯函数：extract_raw_fields ----------------

class TestExtractRawFields:
    def test_extracts_configured_paths(self):
        fields = extract_raw_fields(_raw(3, 120), _PARAMS)
        assert fields == {'present': True, 'values': {'errors': 3, 'length': 120}}

    def test_parses_json_string(self):
        fields = extract_raw_fields(json.dumps(_raw(1, 50)), _PARAMS)
        assert fields['values'] == {'errors': 1, 'length': 50}

    def test_returns_none_without_response(self):
        assert extract_raw_fields(None, _PARAMS) is None
        assert extract_raw_fields({}, _PARAMS) is None
        assert extract_raw_fields('not-json', _PARAMS) is None

    def test_default_paths_when_no_agg_role_config(self):
        """未配置分子/分母 agg_role 时按历史默认 errors / length 提取。"""
        fields = extract_raw_fields(_raw(4, 88), [])
        assert fields['values'] == {'errors': 4, 'length': 88}

    def test_missing_field_stored_as_none(self):
        fields = extract_raw_fields({'code': 0, 'data': {'result': {'errors': 1}}}, _PARAMS)
        assert fields['values'] == {'errors': 1, 'length': None}


# ---------------- ACL 迭代形态 ----------------

class _ChunkStub:
    """按 result_ids 返回带 body 的维度结果；可配置毒 id。"""

    def __init__(self, poison_ids=()):
        self.poison_ids = set(poison_ids)
        self.calls = []

    def GetDimensionResultsByResultIds(self, request):
        ids = json.loads(request.result_ids)
        self.calls.append(tuple(ids))
        if any(rid in self.poison_ids for rid in ids):
            raise _Exhausted()
        items = [
            {'test_result_id': rid, 'dimension_id': 84, 'dimension_value': 1.0,
             'round_number': None, 'api_raw_response': _raw()}
            for rid in ids
        ]
        return eval_pb.EvaluationDataResponse(
            success=True, message='', data=json.dumps({'items': items}))


class _Exhausted(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.RESOURCE_EXHAUSTED

    def __str__(self):
        return 'RESOURCE_EXHAUSTED (simulated)'


@pytest.fixture
def patch_stub(monkeypatch):
    def _install(stub):
        import shared.clients.grpc_clients as shared_clients
        monkeypatch.setattr(
            shared_clients, 'get_evaluation_data_service_stub', lambda: stub)
        return stub
    return _install


class TestAclIteration:
    def test_default_chunk_size_is_four(self):
        """默认分块 = 4（设计文档 §3.9.1 实测表：4 是 B1′ 达标前提下最大的块）。"""
        if 'REPORT_DIM_RESULT_BODY_CHUNK_SIZE' in os.environ:
            pytest.skip('运行环境显式设置了 REPORT_DIM_RESULT_BODY_CHUNK_SIZE')
        assert acl_mod._DIM_RESULT_BODY_CHUNK_SIZE == 4

    def test_yields_chunks_with_coverage(self, patch_stub, monkeypatch):
        monkeypatch.setattr(acl_mod, '_DIM_RESULT_BODY_CHUNK_SIZE', 2)
        stub = patch_stub(_ChunkStub())
        chunks = list(EvaluationDataAclRepositoryImpl()
                      .iter_dimension_results_with_body([1, 2, 3, 4, 5]))

        assert [sorted(c[0].keys()) for c in chunks] == [[1, 2], [3, 4], [5]]
        assert [c[1]['requested_ids'] for c in chunks] == [[1, 2], [3, 4], [5]]
        assert [c[1]['covered_ids'] for c in chunks] == [[1, 2], [3, 4], [5]]
        assert all(not c[1]['failed_chunks'] for c in chunks)
        # 每块一次请求，没有整批请求（峰值只与块大小相关）
        assert [len(c) for c in stub.calls] == [2, 2, 1]

    def test_empty_ids_yields_nothing(self, patch_stub):
        stub = patch_stub(_ChunkStub())
        assert list(EvaluationDataAclRepositoryImpl()
                    .iter_dimension_results_with_body([])) == []
        assert stub.calls == []

    def test_dropped_id_reported_in_chunk_coverage(self, patch_stub, monkeypatch):
        monkeypatch.setattr(acl_mod, '_DIM_RESULT_BODY_CHUNK_SIZE', 8)
        stub = patch_stub(_ChunkStub(poison_ids={2}))
        chunks = list(EvaluationDataAclRepositoryImpl()
                      .iter_dimension_results_with_body([1, 2, 3]))
        merged = {}
        dropped = []
        for part, cov in chunks:
            merged.update(part)
            dropped.extend(cov['dropped_ids'])
        assert sorted(merged.keys()) == [1, 3]
        assert dropped == [2]


# ---------------- 压缩合并：行不丢、原始响应不驻留 ----------------

def _base_map(ids, dim_id=84):
    return {rid: [{'test_result_id': rid, 'dimension_id': dim_id,
                   'dimension_value': 1.0, 'score': 1.0,
                   'round_number': None, 'evaluation_status': 'completed'}]
            for rid in ids}


def _patch_iter(monkeypatch, chunks):
    """用给定 [(chunk_map, coverage)] 替换 ACL 迭代（模拟逐块到达）。"""
    def _fake(result_ids):
        remaining = list(result_ids)
        for chunk_map, coverage in chunks:
            for rid in list(remaining):
                if rid in coverage.get('requested_ids', []):
                    remaining.remove(rid)
            yield chunk_map, coverage

    monkeypatch.setattr(builder_mod, '_grpc_iter_dimension_results_with_body', _fake)


def _chunk(ids, with_body=None):
    with_body = set(ids) if with_body is None else set(with_body)
    return (
        {rid: [{'test_result_id': rid, 'dimension_id': 84, 'round_number': None,
                'dimension_value': 1.0,
                'api_raw_response': _raw() if rid in with_body else None}]
         for rid in ids},
        {'requested_ids': list(ids),
         'covered_ids': [rid for rid in ids if rid in with_body],
         'failed_chunks': [], 'dropped_ids': []},
    )


class TestCompressedMerge:
    def test_rows_kept_and_raw_response_replaced_by_raw_fields(self, monkeypatch):
        _patch_iter(monkeypatch, [_chunk([1, 2]), _chunk([3])])
        merged, coverage = builder_mod.ReportDataTaskMixin._get_dimension_results_compressed(
            _base_map([1, 2, 3]), [1, 2, 3], {84: _PARAMS})

        assert sorted(merged.keys()) == [1, 2, 3]
        for rows in merged.values():
            for row in rows:
                assert 'api_raw_response' not in row
                assert row['raw_fields'] == {
                    'present': True, 'values': {'errors': 2, 'length': 100}}
                assert row['dimension_value'] == 1.0      # 取值列以基础 map 为准
        assert coverage['requested'] == 3
        assert coverage['covered'] == 3
        assert coverage['reason'] is None

    def test_failed_chunk_keeps_rows_and_marks_partial(self, monkeypatch):
        _patch_iter(monkeypatch,
                    [_chunk([1, 2]), ({}, {'requested_ids': [3], 'covered_ids': [],
                                           'failed_chunks': [(0, 1, 'boom')],
                                           'dropped_ids': []})])
        merged, coverage = builder_mod.ReportDataTaskMixin._get_dimension_results_compressed(
            _base_map([1, 2, 3]), [1, 2, 3], {84: _PARAMS})

        assert sorted(merged.keys()) == [1, 2, 3]
        assert merged[3][0]['raw_fields'] is None          # 行保留，只缺 body 字段
        assert coverage['covered'] == 2
        assert coverage['missing'] == [3]
        assert coverage['reason'] == 'partial_api_raw_response_coverage'
        assert coverage['failed_chunks'] == [(0, 1, 'boom')]

    def test_all_missing_reason_is_missing_not_partial(self, monkeypatch):
        """O2：全缺 body 时 coverage.reason 不能再是 partial。"""
        _patch_iter(monkeypatch,
                    [({}, {'requested_ids': [1, 2], 'covered_ids': [],
                           'failed_chunks': [(0, 2, 'boom')], 'dropped_ids': []})])
        merged, coverage = builder_mod.ReportDataTaskMixin._get_dimension_results_compressed(
            _base_map([1, 2]), [1, 2], {84: _PARAMS})

        assert sorted(merged.keys()) == [1, 2]
        assert coverage['covered'] == 0
        assert coverage['missing_total'] == 2
        assert coverage['reason'] == 'missing_api_raw_response'

    def test_coverage_counts_only_base_rows(self, monkeypatch):
        """基础 map 没有的结果（无维度行）不计入覆盖分母。"""
        _patch_iter(monkeypatch, [_chunk([1, 2, 99])])
        merged, coverage = builder_mod.ReportDataTaskMixin._get_dimension_results_compressed(
            _base_map([1, 2]), [1, 2, 99], {84: _PARAMS})

        assert sorted(merged.keys()) == [1, 2]
        assert coverage['requested'] == 2


# ---------------- 聚合 item 契约 ----------------

class TestAggregationItemContract:
    def _rows(self, with_body=True):
        return {1: [{'dimension_id': 84, 'dimension_value': 1.0,
                     'round_number': None,
                     'raw_fields': ({'present': True,
                                     'values': {'errors': 2, 'length': 100}}
                                    if with_body else None)}]}

    def test_collect_dim_items_carries_raw_fields_only(self):
        items = collect_dim_items(1, 84, self._rows(), set())
        assert items and 'api_raw_response' not in items[0]
        assert items[0]['raw_fields']['values'] == {'errors': 2, 'length': 100}

    def test_weighted_strategy_reads_raw_fields(self):
        items = [
            {'dimension_value': 1.0, 'test_result_id': 1,
             'raw_fields': {'present': True, 'values': {'errors': 1, 'length': 100}}},
            {'dimension_value': 1.0, 'test_result_id': 2,
             'raw_fields': {'present': True, 'values': {'errors': 9, 'length': 100}}},
        ]
        assert WeightedSumRatioStrategy().aggregate(
            items, output_params=_PARAMS) == 5.0

    def test_explain_degradation_uses_raw_fields_present(self):
        items = [{'dimension_value': 1.0, 'test_result_id': 1, 'raw_fields': None}]
        deg = explain_aggregation_degradation(
            'weighted_sum_ratio', items, output_params=_PARAMS,
            denominator_mode='case', aggregate_value=None)
        assert deg['reason'] == 'missing_api_raw_response'
