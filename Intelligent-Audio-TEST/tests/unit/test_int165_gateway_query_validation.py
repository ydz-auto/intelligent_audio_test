# -*- coding: utf-8 -*-
"""INT-165 网关 ACL 边界 query 参数校验单测

原缺陷：GET /api/v1/digital-spl?per_page=abc → int('abc') ValueError
未捕获 → 500。修复后统一经 parse_int_args 清洗：非法值 → 400 +
INVALID_TYPE(102) 结构化错误，缺省与钳制行为保持。

覆盖：
1. parse_int_args 规则清洗（非法 page/per_page/api_id、缺省、空串、钳制）
2. RmsSplQueryService.get_all 服务层行为（400 结构化错误 + ACL 收到的清洗值）
3. 真实路由 /api/v1/digital-spl 端到端（400 非 500，合法路径 200 回归）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.application.services.api_rms_spl import rms_spl_query_service
from api_gateway.application.services.api_rms_spl.rms_spl_query_service import RmsSplQueryService
from api_gateway.domain.dto import CommandResultDTO
from api_gateway.infrastructure import request_adapter
from api_gateway.infrastructure.query_validator import (
    IntParamRule,
    QueryParamValidationError,
    parse_int_args,
)
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.digital_spl_bp import router as digital_spl_router
from api_gateway.utils.error_codes import ErrorCode


# 服务层 get_all 使用的规则集（与实现保持同一份引用）
RULES = rms_spl_query_service._LIST_INT_RULES


class TestParseIntArgs:

    def test_valid_values_int_coerced(self):
        parsed = parse_int_args({'page': '3', 'per_page': '5', 'api_id': '7'}, RULES)
        assert parsed == {'page': 3, 'per_page': 5, 'api_id': 7}
        # 必须是 int 而非 str，才能安全进入 proto int32 边界
        assert all(isinstance(v, int) for v in parsed.values())

    def test_missing_and_empty_fall_back_to_default(self):
        parsed = parse_int_args({'page': '', 'api_id': ''}, RULES)
        assert parsed == {'page': 1, 'per_page': 10, 'api_id': None}

    def test_per_page_clamped_both_ends(self):
        assert parse_int_args({'per_page': '0'}, RULES)['per_page'] == 1
        assert parse_int_args({'per_page': '150'}, RULES)['per_page'] == 100
        assert parse_int_args({'per_page': '-3'}, RULES)['per_page'] == 1

    def test_page_clamped_to_min_1(self):
        assert parse_int_args({'page': '0'}, RULES)['page'] == 1

    def test_invalid_per_page_raises_structured_error(self):
        with pytest.raises(QueryParamValidationError) as exc_info:
            parse_int_args({'per_page': 'abc'}, RULES)
        err = exc_info.value
        assert isinstance(err, ValueError)
        assert err.param == 'per_page'
        assert err.value == 'abc'
        assert 'per_page' in str(err)

    def test_invalid_page_raises(self):
        with pytest.raises(QueryParamValidationError) as exc_info:
            parse_int_args({'page': '1.5'}, RULES)
        assert exc_info.value.param == 'page'

    def test_invalid_api_id_raises(self):
        with pytest.raises(QueryParamValidationError) as exc_info:
            parse_int_args({'api_id': 'xyz'}, RULES)
        assert exc_info.value.param == 'api_id'

    def test_api_id_negative_int_passes_through(self):
        """api_id 无钳制区间，符号由业务侧语义处理（与原 int() 行为一致）。"""
        assert parse_int_args({'api_id': '-5'}, RULES)['api_id'] == -5

    def test_float_string_rejected(self):
        with pytest.raises(QueryParamValidationError):
            parse_int_args({'per_page': '5.5'}, RULES)


class _AclStub:
    """记录 get_all 入参并返回固定结果的 ACL 桩。"""

    def __init__(self, result=None):
        self.calls = []
        self._result = result or CommandResultDTO(
            success=True, data={'items': [], 'total': 0}, message='ok')

    def get_all(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


@pytest.fixture()
def acl_stub(monkeypatch):
    stub = _AclStub()
    monkeypatch.setattr(rms_spl_query_service, '_rms_spl_acl', stub)
    return stub


def _set_query(query: dict):
    request_adapter.set_current_request(
        type('R', (), {'query_params': dict(query)})())


class TestGetAllService:

    def test_invalid_per_page_returns_400_structured(self, acl_stub):
        _set_query({'per_page': 'abc'})
        payload, http_code = RmsSplQueryService.get_all()
        assert http_code == 400
        assert payload['success'] is False
        assert payload['code'] == int(ErrorCode.INVALID_TYPE)
        assert 'per_page' in payload['message']
        assert payload['detail'] == {'param': 'per_page', 'value': 'abc'}
        assert acl_stub.calls == []  # 校验失败不得触达 ACL/gRPC

    def test_invalid_page_returns_400(self, acl_stub):
        _set_query({'page': 'abc'})
        payload, http_code = RmsSplQueryService.get_all()
        assert http_code == 400
        assert payload['code'] == int(ErrorCode.INVALID_TYPE)

    def test_invalid_api_id_returns_400(self, acl_stub):
        _set_query({'api_id': 'abc'})
        payload, http_code = RmsSplQueryService.get_all()
        assert http_code == 400
        assert payload['code'] == int(ErrorCode.INVALID_TYPE)

    def test_defaults_preserved_without_params(self, acl_stub):
        _set_query({})
        payload, http_code = RmsSplQueryService.get_all()
        assert http_code == 200
        assert acl_stub.calls == [
            {'page': 1, 'per_page': 10, 'api_id': None, 'calibration_status': None}]

    def test_clamping_preserved(self, acl_stub):
        _set_query({'per_page': '150'})
        RmsSplQueryService.get_all()
        assert acl_stub.calls[0]['per_page'] == 100

        _set_query({'per_page': '0'})
        RmsSplQueryService.get_all()
        assert acl_stub.calls[1]['per_page'] == 1

    def test_valid_params_passed_as_int(self, acl_stub):
        _set_query({'page': '2', 'per_page': '5', 'api_id': '9',
                    'calibration_status': 'CALIBRATED'})
        payload, http_code = RmsSplQueryService.get_all()
        assert http_code == 200
        assert acl_stub.calls[0] == {
            'page': 2, 'per_page': 5, 'api_id': 9,
            'calibration_status': 'CALIBRATED'}
        assert isinstance(acl_stub.calls[0]['api_id'], int)

    def test_acl_failure_maps_to_invalid_params(self, acl_stub, monkeypatch):
        monkeypatch.setattr(
            rms_spl_query_service, '_rms_spl_acl',
            _AclStub(CommandResultDTO(success=False, message='下游失败')))
        _set_query({})
        payload, http_code = RmsSplQueryService.get_all()
        assert http_code == 400
        assert payload['success'] is False
        assert payload['message'] == '下游失败'


def _make_app():
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(digital_spl_router, prefix='/api/v1/digital-spl')
    return app


@pytest.fixture()
def client(acl_stub):
    return TestClient(_make_app())


class TestDigitalSplRouteEndToEnd:

    def test_per_page_abc_returns_400_not_500(self, client):
        resp = client.get('/api/v1/digital-spl?per_page=abc')
        assert resp.status_code == 400
        body = resp.json()
        assert body['success'] is False
        assert body['code'] == int(ErrorCode.INVALID_TYPE)
        assert 'per_page' in body['message']

    def test_page_and_api_id_invalid_return_400(self, client):
        assert client.get('/api/v1/digital-spl?page=abc').status_code == 400
        assert client.get('/api/v1/digital-spl?api_id=abc').status_code == 400

    def test_legal_path_regression(self, client):
        resp = client.get('/api/v1/digital-spl?page=1&per_page=5')
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True

    def test_default_params_regression(self, client):
        resp = client.get('/api/v1/digital-spl')
        assert resp.status_code == 200

    def test_clamp_regression(self, client):
        assert client.get('/api/v1/digital-spl?per_page=999').status_code == 200
