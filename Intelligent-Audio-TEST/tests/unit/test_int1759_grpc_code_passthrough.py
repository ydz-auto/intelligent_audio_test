# -*- coding: utf-8 -*-
"""INT-1759：TaskConfigResponse.code 透传（servicer → 网关代理 → HTTP 映射）

D0 裁定 §A7 的前置：业务码必须能从 task_service 走到网关 HTTP 状态，
否则用例一致性拒绝（422）只会变成 500/400。本文件不起 DB / gRPC / Redis。
"""
import json
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.proto import task_service_pb2 as task_pb


def _resp(success=False, message='失败', data=None, code=0):
    return SimpleNamespace(success=success, message=message,
                           data=json.dumps(data) if data is not None else '', code=code)


def _result(success=False, message='失败', data=None, code=0):
    """模拟应用服务返回 dict（含顶层业务码）"""
    return {'success': success, 'message': message, 'data': data, 'code': code}


# ==================== task_service servicer 侧 ====================

def test_data_transfer_servicer_passes_code():
    from task_service.interfaces.grpc.data_transfer import DataTransferServiceServicer
    resp = DataTransferServiceServicer._resp(_result(data={'missingCaseIds': ['c9']}, code=422))
    assert isinstance(resp, task_pb.TaskConfigResponse)
    assert resp.code == 422
    assert json.loads(resp.data)['missingCaseIds'] == ['c9']


def test_task_config_servicer_passes_code():
    from task_service.interfaces.grpc.task_config import TaskConfigServiceServicer
    assert TaskConfigServiceServicer._resp(_result(code=404)).code == 404


def test_cherry_pick_servicer_passes_code_and_strips_data_code():
    from task_service.interfaces.grpc.cherry_pick import CherryPickServiceServicer
    resp = CherryPickServiceServicer._resp(_result(data={'code': 404}, code=404))
    assert resp.code == 404
    assert 'code' not in json.loads(resp.data or '{}')


def test_review_servicer_passes_code():
    from task_service.interfaces.grpc.review import ReviewServiceServicer
    assert ReviewServiceServicer._resp(_result(data={'code': 403}, code=403)).code == 403


def test_published_task_servicer_passes_code():
    from task_service.interfaces.grpc.published_task_config import (
        PublishedTaskConfigServiceServicer,
    )
    assert PublishedTaskConfigServiceServicer._resp(_result(code=409)).code == 409


def test_evaluation_strategy_servicer_passes_code():
    from task_service.interfaces.grpc.evaluation_strategy_config import (
        EvaluationStrategyServiceServicer,
    )
    assert EvaluationStrategyServiceServicer._resp(_result(code=409)).code == 409


def test_servicer_success_leaves_code_zero():
    from task_service.interfaces.grpc.task_config import TaskConfigServiceServicer
    resp = TaskConfigServiceServicer._resp(_result(success=True, message='ok', data={'a': 1}))
    assert resp.code == 0
    assert resp.success is True


# ==================== 网关代理侧 ====================

@pytest.mark.parametrize('module_attr', [
    'ai_review_proxies._AiReviewProxy',
    'cherry_pick_proxies._CherryPickProxy',
    'review_proxies._ReviewProxy',
    'evaluation_strategy_proxies._EvaluationStrategyProxy',
    'published_task_config_proxies._PublishedTaskConfigProxy',
    'task_testcase_config_proxies._TaskConfigProxy',
])
def test_proxy_reads_proto_code(module_attr):
    import importlib
    module_name, cls_name = module_attr.split('.')
    cls = getattr(importlib.import_module(
        f'api_gateway.infrastructure.grpc_proxies.{module_name}'), cls_name)
    result = cls()._resp(_resp(code=404))
    assert result['code'] == 404


@pytest.mark.parametrize('module_attr', [
    'cherry_pick_proxies._CherryPickProxy',
    'task_testcase_config_proxies._TaskConfigProxy',
])
def test_proxy_falls_back_to_data_code_for_old_servicer(module_attr):
    """旧 servicer 未填 proto code（=0）时按 data.code 兜底（INT-566 口径不回归）"""
    import importlib
    module_name, cls_name = module_attr.split('.')
    cls = getattr(importlib.import_module(
        f'api_gateway.infrastructure.grpc_proxies.{module_name}'), cls_name)
    result = cls()._resp(_resp(data={'code': 403}))
    assert result['code'] == 403


def test_data_transfer_proxy_reads_proto_code():
    from api_gateway.infrastructure.grpc_proxies.data_transfer_proxies import _DataTransferProxy
    result = _DataTransferProxy()._resp(_resp(data={'missingCaseIds': ['c1']}, code=422))
    assert result['code'] == 422
    assert result['data']['missingCaseIds'] == ['c1']


def test_success_without_code_keeps_old_shape():
    from api_gateway.infrastructure.grpc_proxies.data_transfer_proxies import _DataTransferProxy
    result = _DataTransferProxy()._resp(_resp(success=True, message='', data={'ok': 1}))
    assert 'code' not in result


# ==================== 网关 HTTP 映射 ====================

def test_gateway_maps_422_to_http_422_with_data():
    from api_gateway.application.services.transfer.data_transfer_service import _failure
    payload, http_code = _failure(_result(data={'missingCaseIds': ['c1'], 'missingCount': 1},
                                          code=422), '导入失败', default_http=500)
    assert http_code == 422
    assert payload['success'] is False
    assert payload['code'] == 422
    assert payload['data']['missingCaseIds'] == ['c1']


def test_gateway_keeps_legacy_default_http_for_uncoded_failure():
    from api_gateway.application.services.transfer.data_transfer_service import _failure
    # 业务码缺失（manifest 解析异常等）→ 预检仍回 400、执行仍回 500（不改变既有语义）
    assert _failure(_result(), '预检失败')[1] == 400
    assert _failure(_result(), '导入失败', default_http=500)[1] == 500


def test_gateway_maps_400_business_code():
    from api_gateway.application.services.transfer.data_transfer_service import _failure
    payload, http_code = _failure(_result(message='不支持的导入意图', code=400),
                                  '预检失败')
    assert http_code == 400
    assert payload['code'] == 400

