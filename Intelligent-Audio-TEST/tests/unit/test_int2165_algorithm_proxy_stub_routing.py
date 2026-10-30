# -*- coding: utf-8 -*-
"""INT-2165：网关 algorithm 参数映射/参数列表误用 task_service stub 的回归单测。

现象：``/algorithm/mappings`` 与 ``/algorithm/params`` 恒 500，错误为
``'AlgorithmConfigServiceStub' object has no attribute 'GetParamMappingForComponent'``。

根因：这两个 RPC 属于 algorithm_service 的 ``AlgorithmQueryService``
（``shared/proto/algorithm_service.proto``），task_service 的
``AlgorithmConfigService`` 从来没有这两个 RPC；网关却用
``get_algorithm_config_service_stub()``（task 通道）+ ``task_service_pb2`` 请求体。

本测试锁住三点：走 query stub、请求体是 algorithm_service proto 类型、
api_id 用 proto3 optional presence 表达「未传 vs 显式值」。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

from shared.proto import algorithm_service_pb2 as algo_pb  # noqa: E402
from shared.proto import task_service_pb2 as task_pb  # noqa: E402
from api_gateway.infrastructure.grpc_proxies.algorithm_config_proxies import (  # noqa: E402
    _AlgorithmConfigProxy,
)


class _Resp:
    """AlgorithmResponse 的最小替身。"""

    def __init__(self, success=True, message='ok', data=''):
        self.success = success
        self.message = message
        self.data = data


class _FakeQueryStub:
    def __init__(self, payload=None, fail=False):
        self.calls = []
        self._payload = payload if payload is not None else []
        self._fail = fail

    def GetApiParamsList(self, request):
        self.calls.append(('GetApiParamsList', request))
        if self._fail:
            raise RuntimeError('algorithm_service unavailable')
        return _Resp(data=json.dumps(self._payload))

    def GetParamMappingForComponent(self, request):
        self.calls.append(('GetParamMappingForComponent', request))
        if self._fail:
            raise RuntimeError('algorithm_service unavailable')
        return _Resp(data=json.dumps(self._payload))


class _ForbiddenConfigStub:
    """task 通道 stub：本卡修复后不应再被这两个方法触达。"""

    def __getattr__(self, name):
        raise AssertionError(f'task_service AlgorithmConfigService 被误用: {name}')


@pytest.fixture()
def wire(monkeypatch):
    """把 grpc_clients 的两个 stub getter 换成替身。"""
    from shared.clients import grpc_clients

    query = _FakeQueryStub([
        {'id': 424, 'algorithm_type': 'voice_llm', 'api_id': 424,
         'code': 'text', 'name': '文本', 'param_type': 'text', 'direction': 'input'},
    ])
    forbidden = _ForbiddenConfigStub()
    monkeypatch.setattr(grpc_clients, 'get_algorithm_query_service_stub', lambda: query)
    monkeypatch.setattr(grpc_clients, 'get_algorithm_config_service_stub', lambda: forbidden)
    return query


def test_task_service_contract_has_no_such_rpcs():
    """契约事实：这两个 RPC 只在 algorithm_service.proto，task_service 没有。"""
    assert not hasattr(task_pb, 'GetApiParamsListRequest')
    assert not hasattr(task_pb, 'GetParamMappingForComponentRequest')

    task_rpcs = task_pb.DESCRIPTOR.services_by_name['AlgorithmConfigService'].methods_by_name
    assert 'GetApiParamsList' not in task_rpcs
    assert 'GetParamMappingForComponent' not in task_rpcs

    algo_rpcs = algo_pb.DESCRIPTOR.services_by_name['AlgorithmQueryService'].methods_by_name
    assert 'GetApiParamsList' in algo_rpcs
    assert 'GetParamMappingForComponent' in algo_rpcs


def test_get_api_params_uses_algorithm_query_service(wire):
    proxy = _AlgorithmConfigProxy()
    result = proxy.get_api_params(algorithm_type='voice_llm', api_id=424)

    assert result['success'] is True
    assert result['data'][0]['id'] == 424

    assert len(wire.calls) == 1
    method, req = wire.calls[0]
    assert method == 'GetApiParamsList'
    assert isinstance(req, algo_pb.GetApiParamsListRequest)
    assert req.algorithm_type == 'voice_llm'
    assert req.HasField('api_id') and req.api_id == 424


def test_get_api_params_omits_absent_api_id(wire):
    """api_id 未传时不写该键，presence 保留（不回落成 0/默认层）。"""
    proxy = _AlgorithmConfigProxy()
    proxy.get_api_params(algorithm_type='voice_llm')

    _, req = wire.calls[0]
    assert isinstance(req, algo_pb.GetApiParamsListRequest)
    assert not req.HasField('api_id')


def test_get_param_mapping_uses_algorithm_query_service(wire):
    wire._payload = [
        {'id': 7, 'algorithm_type': 'voice_llm', 'api_id': 424,
         'source': 'api', 'source_param': 'text', 'target_param': 'transcript',
         'dimension_id': 101, 'dimension_name': '文本'},
    ]
    proxy = _AlgorithmConfigProxy()
    result = proxy.get_param_mapping_for_component(
        algorithm_type='voice_llm', component_type='evaluation', api_id=424)

    assert result['success'] is True
    assert result['data'][0]['source_param'] == 'text'

    method, req = wire.calls[0]
    assert method == 'GetParamMappingForComponent'
    assert isinstance(req, algo_pb.GetParamMappingForComponentRequest)
    assert req.algorithm_type == 'voice_llm'
    assert req.component_type == 'evaluation'
    assert req.HasField('api_id') and req.api_id == 424


def test_failure_returns_error_envelope(monkeypatch):
    """algorithm_service 异常时回落错误信封（不再抛 AttributeError 假成功）。"""
    from shared.clients import grpc_clients

    failing = _FakeQueryStub(fail=True)
    monkeypatch.setattr(grpc_clients, 'get_algorithm_query_service_stub', lambda: failing)
    monkeypatch.setattr(
        grpc_clients, 'get_algorithm_config_service_stub', lambda: _ForbiddenConfigStub())

    proxy = _AlgorithmConfigProxy()

    api_params = proxy.get_api_params(algorithm_type='voice_llm', api_id=424)
    assert api_params['success'] is False
    assert api_params['code'] == 500
    assert '获取API参数列表失败' in api_params['message']

    mappings = proxy.get_param_mapping_for_component(
        algorithm_type='voice_llm', component_type='evaluation', api_id=424)
    assert mappings['success'] is False
    assert mappings['code'] == 500
    assert '获取参数映射失败' in mappings['message']
