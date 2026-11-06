# -*- coding: utf-8 -*-
"""Benchmark 网关审计操作人注入单测（审计 P4-8：网关把登录用户注入命令）

覆盖：
- 排行计算：payload.operator 由网关认证身份（AuthMiddleware username）注入
- 基线导入：published_by 以认证身份为准，前端自报值仅作未认证回退
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.infrastructure import request_adapter
import api_gateway.application.services.benchmark.benchmark_service as gw_benchmark


class _State:
    def __init__(self, json_body, username):
        self._json_body = json_body
        self.username = username


class _FakeRequest:
    def __init__(self, json_body, username):
        self.state = _State(json_body, username)


@pytest.fixture()
def capture_acl(monkeypatch):
    captured = {}

    def _compute(payload):
        captured['compute'] = dict(payload)
        return {'success': True, 'data': {}, 'message': 'ok', 'code': 0}

    def _import(payload):
        captured['import'] = dict(payload)
        return {'success': True, 'data': {}, 'message': 'ok', 'code': 0}

    monkeypatch.setattr(gw_benchmark, '_benchmark_acl', SimpleNamespace(
        compute_ranking=_compute, import_baselines=_import))
    return captured


@pytest.fixture()
def fake_request():
    def _set(json_body, username):
        request_adapter.set_current_request(_FakeRequest(json_body, username))
    yield _set
    request_adapter.set_current_request(None)


def test_compute_injects_authenticated_operator(capture_acl, fake_request):
    fake_request({'category': 'asr'}, 'audit_operator')
    gw_benchmark.BenchmarkService.compute_ranking()
    assert capture_acl['compute']['operator'] == 'audit_operator'


def test_import_published_by_auth_identity_overrides_self_report(capture_acl, fake_request):
    fake_request({'sourceId': 1, 'category': 'asr', 'entries': [],
                  'publishedBy': 'front-end-self'}, 'audit_operator')
    gw_benchmark.BenchmarkService._import_baselines()
    assert capture_acl['import']['published_by'] == 'audit_operator'


def test_import_published_by_falls_back_without_auth(capture_acl, fake_request):
    # AUTH_MODE=off 等未认证场景：回退前端自报值
    fake_request({'sourceId': 1, 'category': 'asr', 'entries': [],
                  'publishedBy': 'front-end-self'}, '')
    gw_benchmark.BenchmarkService._import_baselines()
    assert capture_acl['import']['published_by'] == 'front-end-self'
