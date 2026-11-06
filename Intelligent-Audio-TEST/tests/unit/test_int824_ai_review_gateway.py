# -*- coding: utf-8 -*-
"""INT-824 专项：api_gateway AI 复核契约层 + 权限注册。

覆盖（对齐 INT-800 契约定稿 #4 + 验收标准）：
- 路由表：review_bp 注册 POST /ai-review / GET /{task_id}/ai-review-history /
  POST /ai-review/{id}/adopt / POST /ai-review/{id}/reject，且权限码正确
  （发起/驳回 task.result.ai_review、历史 task:read、采纳 task.result.review）
- 权限门槛生效：无权限 403、有权限/admin 通配放行（AUTH_MODE=off 下实机注入 '*',
  由本用例直测 checker 覆盖 403）
- HTTP 契约（FastAPI TestClient + 替身 ACL）：四端点入参出参与契约一致、统一信封
  {success,message,data}；发起入参校验（result_ids≥1）；历史 Query 过滤透传；
  采纳入参校验（备注必填/状态至少一项/非法状态）
- AiReviewRecordDto 形状：契约定稿表 ai_reviews 全字段
- seed_rbac 注册：PERMISSIONS 含 task.result.ai_review、TESTER_PERMS 含该码
  （admin '*' 通配；algo_engineer 是否授予为负责人拍板项，本卡不授）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import inspect
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import api_gateway.application.services.task.ai_review_service as ars_module
from api_gateway.application.services.task.ai_review_service import AiReviewService
from api_gateway.infrastructure.acl import AiReviewAclRepositoryImpl
from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
from api_gateway.routes.review_bp import router as review_router
from api_gateway.schemas.ai_review import (
    AiReviewInitiateRequest, AiReviewAdoptRequest, AiReviewRecordDto,
)

# ==================== 路由表 + 权限 ====================

AI_PATHS = {
    '/ai-review': 'POST',
    '/{task_id}/ai-review-history': 'GET',
    '/ai-review/{id}/adopt': 'POST',
    '/ai-review/{id}/reject': 'POST',
}


def _find_route(path, method):
    for r in review_router.routes:
        if getattr(r, 'path', None) == path and method in (getattr(r, 'methods', set()) or set()):
            return r
    return None


def test_ai_review_routes_registered():
    for path, method in AI_PATHS.items():
        assert _find_route(path, method) is not None, f'{method} {path} 未注册'


def _route_checker(path, method):
    route = _find_route(path, method)
    assert route is not None
    checker = route.dependant.dependencies[0].call
    required = next(
        c.cell_contents for c in (checker.__closure__ or ())
        if isinstance(c.cell_contents, (set, frozenset))
    )
    return checker, set(required)


def test_ai_review_route_permissions():
    expected = {
        ('/ai-review', 'POST'): {'task.result.ai_review'},
        ('/{task_id}/ai-review-history', 'GET'): {'task:read'},
        ('/ai-review/{id}/adopt', 'POST'): {'task.result.review'},
        ('/ai-review/{id}/reject', 'POST'): {'task.result.ai_review'},
    }
    for (path, method), perms in expected.items():
        _, required = _route_checker(path, method)
        assert required == perms, f'{method} {path}: {required} != {perms}'
    src = inspect.getsource(_find_route('/ai-review', 'POST').endpoint)
    assert "require_permission('task.result.ai_review')" in src
    src = inspect.getsource(_find_route('/ai-review/{id}/reject', 'POST').endpoint)
    assert "require_permission('task.result.ai_review')" in src


def test_ai_review_permission_checker_403():
    """无权限 403（AUTH_MODE=off 下实机注入 '*'，由本用例覆盖门槛）。"""
    for (path, method), perms in [
        (('/ai-review', 'POST'), {'task.result.ai_review'}),
        (('/{task_id}/ai-review-history', 'GET'), {'task:read'}),
        (('/ai-review/{id}/adopt', 'POST'), {'task.result.review'}),
        (('/ai-review/{id}/reject', 'POST'), {'task.result.ai_review'}),
    ]:
        checker, _ = _route_checker(path, method)
        req = SimpleNamespace(state=SimpleNamespace(permissions=[]))
        with pytest.raises(HTTPException) as ei:
            checker(req)
        assert ei.value.status_code == 403
        assert next(iter(perms)) in ei.value.detail


def test_ai_review_permission_checker_pass():
    """有权限 / admin 通配放行。"""
    for (path, method), perms in [
        (('/ai-review', 'POST'), {'task.result.ai_review'}),
        (('/{task_id}/ai-review-history', 'GET'), {'task:read'}),
        (('/ai-review/{id}/adopt', 'POST'), {'task.result.review'}),
        (('/ai-review/{id}/reject', 'POST'), {'task.result.ai_review'}),
    ]:
        checker, _ = _route_checker(path, method)
        assert checker(SimpleNamespace(state=SimpleNamespace(
            permissions=set(perms)))) is None
        assert checker(SimpleNamespace(state=SimpleNamespace(
            permissions={'*'}))) is None


def test_app_mounts_review_router_prefix():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / 'api_gateway' / 'app.py').read_text(encoding='utf-8')
    assert "review_router, prefix='/api/v1/tasks/results'" in src


# ==================== HTTP 契约（替身 ACL） ====================

AI_RECORD = {
    'id': 1,
    'result_id': 10,
    'task_id': 5,
    'test_case_id': 'C1',
    'dimension_id': 7,
    'status': 'completed',
    'verdict': 'passed',
    'confidence': 0.92,
    'reasoning': '置信度达标',
    'adopted': 0,
    'adopted_by_user_id': None,
    'adopted_at': None,
    'rejected': 0,
    'rejected_by_user_id': None,
    'rejected_at': None,
    'created_at': '2026-10-19T10:00:00',
    'updated_at': '2026-10-19T10:00:00',
}


class FakeAiReviewAcl:
    """网关 ACL 替身：模拟 task_service gRPC 信封返回。"""

    def __init__(self):
        self.calls = []

    def initiate_review(self, data):
        self.calls.append(('initiate', data))
        return {'success': True, 'message': '已发起 1 条 AI 复核',
                'data': {'items': [dict(AI_RECORD)], 'reused': False, 'skipped': []}}

    def list_ai_review_history(self, task_id, filters):
        self.calls.append(('history', task_id, filters))
        rows = [dict(AI_RECORD)]
        if filters.get('dimension_id') and int(filters['dimension_id']) != AI_RECORD['dimension_id']:
            rows = []
        return {'success': True, 'message': 'ok', 'data': {'items': rows}}

    def adopt_review(self, review_id, data):
        self.calls.append(('adopt', review_id, data))
        rec = dict(AI_RECORD)
        rec.update({
            'adopted': 1, 'adopted_by_user_id': 7, 'adopted_at': '2026-10-19T11:00:00',
        })
        return {'success': True, 'message': '已采纳 AI 复核结论',
                'data': {'item': rec, 'applied': [{'field_name': 'execution_status'}]}}

    def reject_review(self, review_id):
        self.calls.append(('reject', review_id))
        rec = dict(AI_RECORD)
        rec.update({
            'rejected': 1, 'rejected_by_user_id': 9, 'rejected_at': '2026-10-19T11:30:00',
        })
        return {'success': True, 'message': 'AI 复核已驳回，原判定不变', 'data': rec}


@pytest.fixture
def client(monkeypatch):
    fake = FakeAiReviewAcl()
    monkeypatch.setattr(ars_module, '_ai_review_acl', fake)

    app = FastAPI()
    app.add_middleware(AuthMiddleware, auth_mode='off')
    app.add_middleware(RequestAdapterMiddleware)
    app.include_router(review_router, prefix='/api/v1/tasks/results', tags=['task-review'])
    test_client = TestClient(app)
    test_client.fake_acl = fake
    return test_client


def test_post_ai_review_initiate(client):
    resp = client.post('/api/v1/tasks/results/ai-review', json={
        'result_ids': [10], 'dimension_ids': [7],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    data = body['data']
    assert len(data['items']) == 1
    assert data['items'][0]['result_id'] == 10
    assert data['items'][0]['verdict'] == 'passed'
    assert data['reused'] is False
    # ACL 收到原始入参（force 缺省补 False，语义等同省略）
    assert client.fake_acl.calls[-1][0] == 'initiate'
    assert client.fake_acl.calls[-1][1] == {
        'result_ids': [10], 'dimension_ids': [7], 'force': False}


def test_post_ai_review_initiate_force(client):
    resp = client.post('/api/v1/tasks/results/ai-review', json={
        'result_ids': [10], 'force': True,
    })
    assert resp.status_code == 200
    payload = client.fake_acl.calls[-1][1]
    assert payload['force'] is True


def test_post_ai_review_initiate_empty_result_ids_400(client):
    """result_ids 空 → 网关校验拒绝（400，对齐人工复核校验口径）。"""
    resp = client.post('/api/v1/tasks/results/ai-review', json={'result_ids': []})
    assert resp.status_code == 400
    assert resp.json()['success'] is False


def test_get_ai_review_history(client):
    resp = client.get('/api/v1/tasks/results/5/ai-review-history')
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    assert body['data']['items'][0]['task_id'] == 5
    assert client.fake_acl.calls[-1][0] == 'history'
    assert client.fake_acl.calls[-1][1] == 5
    assert client.fake_acl.calls[-1][2] == {}


def test_get_ai_review_history_filters_passed(client):
    resp = client.get('/api/v1/tasks/results/5/ai-review-history',
                      params={'result_id': 10, 'dimension_id': 7, 'status': 'completed'})
    assert resp.status_code == 200
    assert client.fake_acl.calls[-1][2] == {
        'result_id': '10', 'dimension_id': '7', 'status': 'completed'}


def test_get_ai_review_history_empty_filter_ignored(client):
    """空 query 值不透传（task_service 侧 int 校验前过滤）。"""
    client.get('/api/v1/tasks/results/5/ai-review-history',
               params={'status': ''})
    assert client.fake_acl.calls[-1][2] == {}


def test_post_ai_review_adopt(client):
    resp = client.post('/api/v1/tasks/results/ai-review/1/adopt', json={
        'execution_status': 'completed', 'comment': '人工确认采纳 AI 结论',
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    item = body['data']['item']
    assert item['adopted'] == 1
    assert item['adopted_by_user_id'] == 7
    assert client.fake_acl.calls[-1][0] == 'adopt'
    assert client.fake_acl.calls[-1][1] == 1
    assert client.fake_acl.calls[-1][2] == {
        'execution_status': 'completed', 'evaluation_status': None, 'comment': '人工确认采纳 AI 结论'}


def test_post_ai_review_adopt_validation_400(client):
    # 未设置任何状态
    resp = client.post('/api/v1/tasks/results/ai-review/1/adopt', json={'comment': 'x'})
    assert resp.status_code == 400
    # 非法执行状态
    resp = client.post('/api/v1/tasks/results/ai-review/1/adopt',
                       json={'execution_status': 'pending', 'comment': 'x'})
    assert resp.status_code == 400
    # 非法评估状态
    resp = client.post('/api/v1/tasks/results/ai-review/1/adopt',
                       json={'evaluation_status': 'running', 'comment': 'x'})
    assert resp.status_code == 400
    # 缺备注（必填）→ 网关校验拒绝
    resp = client.post('/api/v1/tasks/results/ai-review/1/adopt',
                       json={'execution_status': 'completed'})
    assert resp.status_code == 400
    assert resp.json()['success'] is False


def test_post_ai_review_reject(client):
    resp = client.post('/api/v1/tasks/results/ai-review/1/reject')
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    assert body['data']['rejected'] == 1
    assert body['data']['verdict'] == 'passed'  # 原判定不变
    assert client.fake_acl.calls[-1][0] == 'reject'
    assert client.fake_acl.calls[-1][1] == 1


def test_ai_review_acl_error_propagates(monkeypatch):
    """ACL 失败 → error_response（统一信封 success=false + HTTP 码映射）。

    信封形状对齐 gRPC 代理：业务码透传在顶层 code（INT-141 F2 口径）。
    """
    class FailingAcl:
        def initiate_review(self, data):
            return {'success': False, 'message': 'LLM 端点不可达', 'data': None, 'code': 500}
        def list_ai_review_history(self, task_id, filters):
            return {'success': False, 'message': '查询失败', 'data': None, 'code': 500}
        def adopt_review(self, review_id, data):
            return {'success': False, 'message': '采纳失败', 'data': None, 'code': 400}
        def reject_review(self, review_id):
            return {'success': False, 'message': '驳回失败', 'data': None, 'code': 400}

    monkeypatch.setattr(ars_module, '_ai_review_acl', FailingAcl())
    app = FastAPI()
    app.add_middleware(AuthMiddleware, auth_mode='off')
    app.add_middleware(RequestAdapterMiddleware)
    app.include_router(review_router, prefix='/api/v1/tasks/results', tags=['task-review'])
    c = TestClient(app)

    r = c.post('/api/v1/tasks/results/ai-review', json={'result_ids': [1]})
    assert r.status_code == 500
    assert r.json()['success'] is False
    r = c.get('/api/v1/tasks/results/5/ai-review-history')
    assert r.status_code == 500
    assert r.json()['success'] is False
    r = c.post('/api/v1/tasks/results/ai-review/1/adopt',
               json={'execution_status': 'completed', 'comment': 'x'})
    assert r.status_code == 400
    assert r.json()['success'] is False


# ==================== Schema 契约 ====================

def test_ai_review_initiate_schema():
    req = AiReviewInitiateRequest.model_validate(
        {'result_ids': [1, 2], 'dimension_ids': [7], 'force': True})
    assert req.result_ids == [1, 2]
    assert req.dimension_ids == [7]
    assert req.force is True
    # 缺省
    req = AiReviewInitiateRequest.model_validate({'result_ids': [1]})
    assert req.dimension_ids is None
    assert req.force is False
    # result_ids 空 → 校验错误
    with pytest.raises(Exception):
        AiReviewInitiateRequest.model_validate({'result_ids': []})


def test_ai_review_adopt_schema_statuses():
    assert AiReviewAdoptRequest(
        execution_status='completed', comment='x').validate_statuses() is None
    assert AiReviewAdoptRequest(
        evaluation_status='failed', comment='x').validate_statuses() is None
    assert AiReviewAdoptRequest(comment='x').validate_statuses() is not None
    assert AiReviewAdoptRequest(
        execution_status='pending', comment='x').validate_statuses() is not None
    assert AiReviewAdoptRequest(
        evaluation_status='running', comment='x').validate_statuses() is not None
    # comment 必填
    with pytest.raises(Exception):
        AiReviewAdoptRequest(execution_status='completed')


def test_ai_review_record_dto_shape():
    dto = AiReviewRecordDto.model_validate(AI_RECORD)
    assert dto.id == 1
    assert dto.status == 'completed'
    assert dto.verdict == 'passed'
    assert dto.confidence == 0.92
    assert dto.adopted == 0
    assert dto.rejected == 0
    # 缺省 Optional 字段
    rec = dict(AI_RECORD)
    rec['test_case_id'] = None
    rec['dimension_id'] = None
    rec['verdict'] = None
    rec['confidence'] = None
    rec['reasoning'] = None
    dto2 = AiReviewRecordDto.model_validate(rec)
    assert dto2.test_case_id is None
    assert dto2.dimension_id is None
    assert dto2.confidence is None


# ==================== seed_rbac 权限注册 ====================

def test_seed_rbac_registers_ai_review_permission():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / 'scripts' / 'migrations' / '202608' / 'seed_rbac.py').read_text(
        encoding='utf-8')
    assert "('task.result.ai_review'," in src  # PERMISSIONS 注册
    assert "'task.result.ai_review'," in src   # TESTER_PERMS 授予
    # admin 通配（'*'）覆盖新码；algo_engineer 未授（负责人拍板项，本卡不授）
    assert "('*', '超级权限" in src


def test_ai_review_service_methods_exist():
    """BFF service 四个契约方法存在（路由层经静态方法调用）。"""
    assert callable(AiReviewService.initiate_review)
    assert callable(AiReviewService.review_history)
    assert callable(AiReviewService.adopt_review)
    assert callable(AiReviewService.reject_review)
