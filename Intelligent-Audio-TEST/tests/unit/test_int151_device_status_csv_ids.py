# -*- coding: utf-8 -*-
"""INT-151 专项：设备状态批量轮询接口 ids CSV 解析。

缺陷：GET /api/v1/test-devices/status?ids=14 → 500
（DeviceStatusQuery.ids 声明为 Optional[List[int]]，get_statuses 把
原始 CSV 字符串直接塞进 model_validate，未按逗号拆分）。

覆盖：
- schema：CSV 单值 / 多值带空格 / 空串 / 尾逗号 / 缺省 / 列表直传 / 非法值
- 服务层（真实请求上下文）：?ids=14（原 500 场景）→ 200 且 ACL 收到 [14]；
  ?ids=1,2 → [1,2]；不带 ids → None（查全部）；?ids=abc → 400 而非 500
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api_gateway.application.services.device.device_query_service as dqs_module
from api_gateway.application.services.device.device_query_service import DeviceQueryService
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes._response import to_response
from api_gateway.schemas.device import DeviceStatusQuery


class TestDeviceStatusQuerySchema:

    def test_csv_single(self):
        assert DeviceStatusQuery.model_validate({'ids': '14'}).ids == [14]

    def test_csv_multi_with_spaces(self):
        assert DeviceStatusQuery.model_validate({'ids': '1, 2 ,3'}).ids == [1, 2, 3]

    def test_empty_string_means_all(self):
        assert DeviceStatusQuery.model_validate({'ids': ''}).ids is None

    def test_trailing_comma(self):
        assert DeviceStatusQuery.model_validate({'ids': '5,'}).ids == [5]

    def test_missing_means_all(self):
        assert DeviceStatusQuery.model_validate({}).ids is None

    def test_list_passthrough(self):
        assert DeviceStatusQuery.model_validate({'ids': [7, 8]}).ids == [7, 8]

    def test_non_numeric_rejected(self):
        with pytest.raises(ValidationError):
            DeviceStatusQuery.model_validate({'ids': 'abc'})


class FakeDeviceAcl:
    """记录 get_statuses 入参的内存 ACL"""

    def __init__(self):
        self.calls = []

    def get_statuses(self, device_ids=None):
        self.calls.append(device_ids)
        return {'success': True, 'message': 'ok', 'data': {'items': [], 'total': 0}, 'code': 200}


def _make_client(monkeypatch, fake_acl):
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    monkeypatch.setattr(dqs_module, '_device_acl', fake_acl)

    @app.get('/status')
    def status():
        return to_response(DeviceQueryService.get_statuses())

    return TestClient(app)


class TestGetStatusesService:

    def test_ids_csv_single_no_500(self, monkeypatch):
        """原缺陷场景：?ids=14 必须 200，且 ACL 收到 [14] 而非 '14'。"""
        fake = FakeDeviceAcl()
        client = _make_client(monkeypatch, fake)
        resp = client.get('/status', params={'ids': '14'})
        assert resp.status_code == 200
        assert fake.calls == [[14]]
        body = resp.json()
        assert body['success'] is True and body['code'] == 0

    def test_ids_csv_multi(self, monkeypatch):
        fake = FakeDeviceAcl()
        client = _make_client(monkeypatch, fake)
        resp = client.get('/status', params={'ids': '1,2'})
        assert resp.status_code == 200
        assert fake.calls == [[1, 2]]

    def test_no_ids_queries_all(self, monkeypatch):
        fake = FakeDeviceAcl()
        client = _make_client(monkeypatch, fake)
        resp = client.get('/status')
        assert resp.status_code == 200
        assert fake.calls == [None]

    def test_invalid_ids_returns_400(self, monkeypatch):
        """非法 ids 走 400 参数错误，不得以未处理异常形式 500。"""
        fake = FakeDeviceAcl()
        client = _make_client(monkeypatch, fake)
        resp = client.get('/status', params={'ids': 'abc'})
        assert resp.status_code == 400
        assert fake.calls == []
