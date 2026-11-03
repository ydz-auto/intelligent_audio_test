# -*- coding: utf-8 -*-
"""INT-2149 P1：报告链 include_body 维度结果按 result_id 分批拉取。

背景：存在加权维度（weighted_sum_ratio / weighted_wer）时，报告生成链与报告统计链会带
`include_body=True` 拉取维度评估结果，从 `api_raw_response` 快照取分子/分母。旧实现一次
把全部 result_id 发出去，真实任务（402 过滤后 330 条 ≈ 362MB、407 过滤后 177 条）超过
gRPC 单条消息上限（默认 64MB）→ `RESOURCE_EXHAUSTED`；ACL catch 后整批返回 `{}`，加权
维度静默降级为简单平均。

本文件钉死 ACL 层的分批/二分行为（不连库、不起服务）：
1. include_body=True 时按块发送，结果合并成完整 map；
2. 单块撞 RESOURCE_EXHAUSTED 时二分重试；
3. 单条仍超限只丢那一条，其余分块结果保留；
4. include_body=False 保持单次调用（不引入额外往返）。
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


class _Exhausted(grpc.RpcError):
    """模拟客户端收包超限（RESOURCE_EXHAUSTED）。"""

    def code(self):
        return grpc.StatusCode.RESOURCE_EXHAUSTED

    def __str__(self):
        return ('RESOURCE_EXHAUSTED: Received message larger than max '
                '(simulated vs. 67108864)')


class _FakeStub:
    """按请求里的 result_ids 返回维度结果；可配置「超过 N 条就超限」与「毒 id」。"""

    def __init__(self, max_ids_ok=None, poison_ids=()):
        self.max_ids_ok = max_ids_ok
        self.poison_ids = set(poison_ids)
        self.calls = []

    def GetDimensionResultsByResultIds(self, request):
        ids = json.loads(request.result_ids)
        self.calls.append((len(ids), bool(request.include_body)))
        if self.max_ids_ok is not None and len(ids) > self.max_ids_ok:
            raise _Exhausted()
        if any(rid in self.poison_ids for rid in ids):
            raise _Exhausted()
        items = [
            {'test_result_id': rid, 'dimension_id': 84, 'dimension_name': '接管率占比',
             'dimension_value': 1.0, 'api_raw_response': {'ok': True}}
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


def test_include_body_chunks_by_chunk_size(patch_stub):
    """include_body=True：按 _DIM_RESULT_BODY_CHUNK_SIZE 分块，结果完整合并。"""
    stub = patch_stub(_FakeStub())
    ids = list(range(1, 41))  # 40 条 → 16/16/8

    result = EvaluationDataAclRepositoryImpl().get_dimension_results_by_result_ids(
        ids, include_body=True)

    chunk = acl_mod._DIM_RESULT_BODY_CHUNK_SIZE
    expected = [chunk, chunk, 40 - 2 * chunk]
    assert [n for n, _ in stub.calls] == expected
    assert all(body for _, body in stub.calls)
    assert sorted(result.keys()) == ids
    assert all(len(rows) == 1 for rows in result.values())


def test_include_body_shrinks_on_resource_exhausted(patch_stub):
    """单块撞 RESOURCE_EXHAUSTED：二分重试，最终仍拿到完整结果。"""
    stub = patch_stub(_FakeStub(max_ids_ok=8))
    ids = list(range(1, 17))  # 一个 16 条的块

    result = EvaluationDataAclRepositoryImpl().get_dimension_results_by_result_ids(
        ids, include_body=True)

    assert stub.calls[0] == (16, True)
    assert all(n <= 8 for n, _ in stub.calls[1:])
    assert sorted(result.keys()) == ids


def test_include_body_drops_only_poison_item(patch_stub):
    """单条仍超限：只丢那一条，其余分块结果保留，不整批返回空。"""
    stub = patch_stub(_FakeStub(poison_ids={99}))
    ids = list(range(1, 33))
    ids[5] = 99  # 32 条 → 两个 16 条块，其中一块含毒 id

    result = EvaluationDataAclRepositoryImpl().get_dimension_results_by_result_ids(
        ids, include_body=True)

    assert 99 not in result
    assert sorted(result.keys()) == sorted(set(ids) - {99})
    # 含毒块被一直二分到单条；单条仍失败后该块只丢这一条
    assert any(n == 1 for n, _ in stub.calls)


def test_include_body_false_single_call(patch_stub):
    """轻量查询不分批（保持既有单次往返）。"""
    stub = patch_stub(_FakeStub())
    ids = list(range(1, 41))

    result = EvaluationDataAclRepositoryImpl().get_dimension_results_by_result_ids(
        ids, include_body=False)

    assert stub.calls == [(40, False)]
    assert sorted(result.keys()) == ids


def test_empty_ids_no_call(patch_stub):
    stub = patch_stub(_FakeStub())
    assert EvaluationDataAclRepositoryImpl().get_dimension_results_by_result_ids(
        [], include_body=True) == {}
    assert stub.calls == []
