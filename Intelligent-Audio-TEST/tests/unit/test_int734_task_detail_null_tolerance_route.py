# -*- coding: utf-8 -*-
"""INT-734 验收回归（路由层）：任务详情接口复核字段 null 容错。

原缺陷：GET /api/v1/tasks/{id} 对复核表无记录的任务全量 422 —— 上游透传
reviewed/review_count 为 null，网关 TaskCaseBrief.reviewed（非空 bool）与
TaskDetailData.review_count（非空 int）校验失败。

修复（schema 放宽 Optional + 服务组装 null 归一 False/0）后，本用例经真实
FastAPI 路由 + to_response 序列化链路验证：
1. 上游 null 复核字段 → 200，reviewed 恒为 bool False、review_count 恒为整数 0
2. 上游正常（已复核）数据 → 200，reviewed bool true、review_count 整数 > 0
（服务层/ACL 级回归已由 test_int340_manual_review.py 的 2 个新增用例覆盖，
本文件只补路由→schema 的 HTTP 契约层。）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.task.task_query_service as tqs
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.task_bp import router as task_router


def _make_app():
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        # AUTH_MODE=off 语义：注入通配权限，require_permission 放行
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(task_router, prefix='/api/v1/tasks')
    return app


def _upstream_detail(reviewed=None, review_count=None, extra_cases=0):
    """构造 task_service 详情 dict；复核字段可显式传 null（INT-734 场景）。"""
    cases = [{
        'case_id': 'C1',
        'name': '用例1',
        'status': 'failed',
        'execution_status': 'failed',
        'evaluation_status': 'completed',
        'reviewed': reviewed,
    }]
    cases += [{
        'case_id': f'C{i}',
        'name': f'用例{i}',
        'status': 'completed',
        'execution_status': 'completed',
        'evaluation_status': 'completed',
        'reviewed': False,
    } for i in range(2, 2 + extra_cases)]
    return {
        'id': 1,
        'name': 'INT734任务',
        'status': 'completed',
        'completed_cases': 0,
        'failed_cases': 1,
        'review_count': review_count,
        'cases': cases,
    }


@pytest.fixture(autouse=True)
def _patch_acl(monkeypatch):
    """把网关 get_one 的上游 ACL 换成可控桩，隔离 gRPC/DB。"""
    class _FakeAcl:
        def __init__(self):
            self.detail = _upstream_detail(reviewed=None, review_count=None)

        def get_task_detail(self, task_id):
            return {'success': True, 'data': self.detail}

    fake = _FakeAcl()
    monkeypatch.setattr(tqs, '_task_acl', fake)
    return fake


@pytest.fixture()
def client(_patch_acl):
    return TestClient(_make_app())


class TestTaskDetailNullReviewRoute:

    def test_null_review_fields_return_200_bool_int(self, client):
        """上游 reviewed/review_count 为 null → 200 且归一 bool False / 整数 0。"""
        resp = client.get('/api/v1/tasks/1')
        assert resp.status_code == 200, f'原缺陷 422，实际 {resp.status_code}: {resp.text[:300]}'
        body = resp.json()
        assert body['success'] is True
        data = body['data']
        assert data['review_count'] == 0
        assert isinstance(data['review_count'], int)
        assert data['cases'][0]['reviewed'] is False
        assert isinstance(data['cases'][0]['reviewed'], bool)

    def test_missing_review_fields_default_false_zero(self, client, _patch_acl):
        """上游完全未提供复核字段（键缺失）→ 缺省 False/0（未复核语义）。"""
        detail = _upstream_detail()
        del detail['review_count']
        for c in detail['cases']:
            del c['reviewed']
        _patch_acl.detail = detail
        resp = client.get('/api/v1/tasks/1')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['review_count'] == 0
        assert data['cases'][0]['reviewed'] is False

    def test_reviewed_present_passes_through(self, client, _patch_acl):
        """上游正常已复核数据 → reviewed bool true、review_count 整数>0 透传。"""
        detail = _upstream_detail(reviewed=True, review_count=3, extra_cases=2)
        _patch_acl.detail = detail
        resp = client.get('/api/v1/tasks/1')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['review_count'] == 3
        assert isinstance(data['review_count'], int)
        assert data['cases'][0]['reviewed'] is True
