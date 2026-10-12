# -*- coding: utf-8 -*-
"""INT-143 验收：GET /algorithm/reference-params/{param_id} 单条查询全链路契约钉。

原缺陷（INT-138 前端巡检发现）：前端 algorithmApi.getReferenceParam 调用
GET /api/v1/algorithm/reference-params/{paramId}，而后端参考参数仅有
列表 GET / POST / PUT / DELETE 四条路由，单条 GET 缺失 → 前端一旦调用即
405 Method Not Allowed（潜伏缺陷，无视图调用故无用户可见故障）。

修复（commit 87d25c09）：补齐后端全链路
  路由 → AlgorithmQueryService → ACL(端口+实现) → gRPC 代理
  → proto GetReferenceParam RPC → task_service servicer
  → AlgorithmParamQueryService.get_reference_param → repo（端口早已存在）。

本文件为静态/单测层契约钉（实机 CRUD 回归见 issue 验收评论）：
1. 路由表：api_gateway.app 存在 GET /api/v1/algorithm/reference-params/{param_id}
   （原缺陷形态：该路径仅 PUT/DELETE → GET 405），列表路由回归锚点同钉。
2. 权限：路由依赖 require_permission('algorithm:read')（与列表一致）；
   从路由 dependant 取真实 _checker 验证无权限 → 403、有权限/admin 通配 →
   放行（AUTH_MODE=off 下中间件注入 '*'，实机无法复现 403，由本用例覆盖）。
3. 网关链路：ACL 替身下 AlgorithmQueryService.get_reference_param 成功 →
   (payload, 200)；失败 → wrap_grpc_response 回退 400（proto 响应无 code
   字段，404 语义在网关侧表现为 400，与 GetCaseParam 一致）。
4. servicer 链路：GetReferenceParam 命中 → success=True + data JSON 串；
   未命中 → success=False + message + data=""。
5. 契约两端：pb2 已生成 GetReferenceParamRequest/Stub/Servicer；前端
   algorithmApi.getReferenceParam 的方法与路径模板与后端路由一致。
"""
import inspect
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parents[2]


# ══════════════════ 1. 路由表（原 405 缺陷的回归钉） ══════════════════
# 注：新版 FastAPI include_router 以懒加载 _IncludedRouter 挂载，app.routes 不
# 平铺真实路径，故 router 层断言 APIRoute（path/methods），挂载前缀用
# url_path_for（公开 API，路由不存在时抛 KeyError）钉死。


def _find_bp_route(path):
    from api_gateway.routes.algorithm_bp import router
    for r in router.routes:
        if getattr(r, 'path', None) == path:
            return r
    return None


def test_single_query_route_registered_with_get():
    route = _find_bp_route('/reference-params/{param_id}')
    assert route is not None, 'GET /reference-params/{param_id} 未注册（原缺陷形态）'
    assert 'GET' in route.methods


def test_sibling_reference_param_routes_unaffected():
    from api_gateway.routes.algorithm_bp import router
    methods = {m for r in router.routes
               if getattr(r, 'path', None) == '/reference-params'
               for m in getattr(r, 'methods', set())}
    assert {'GET', 'POST'} <= methods


def test_app_mounts_algorithm_router_at_expected_prefix():
    # app 模块可能被其他 issue 的并发 WIP 短暂破坏（import 期失败），此处不导入
    # app；挂载前缀以源码钉 + 实机 HTTP 200（见验收评论）双证
    src = (REPO_ROOT / 'api_gateway' / 'app.py').read_text(encoding='utf-8')
    assert "include_router(algorithm_router, prefix='/api/v1/algorithm'" in src


# ══════════════════ 2. 权限依赖（algorithm:read） ══════════════════

def _get_route_checker():
    route = _find_bp_route('/reference-params/{param_id}')
    assert route is not None
    checker = route.dependant.dependencies[0].call
    required = next(
        c.cell_contents for c in (checker.__closure__ or ())
        if isinstance(c.cell_contents, (set, frozenset))
    )
    return checker, set(required)


def test_route_requires_algorithm_read_permission():
    _, required = _get_route_checker()
    assert required == {'algorithm:read'}
    src = inspect.getsource(_find_bp_route(
        '/reference-params/{param_id}').endpoint)
    assert "require_permission('algorithm:read')" in src


def test_permission_checker_403_without_perm():
    checker, _ = _get_route_checker()
    req = SimpleNamespace(state=SimpleNamespace(permissions=[]))
    with pytest.raises(HTTPException) as ei:
        checker(req)
    assert ei.value.status_code == 403
    assert 'algorithm:read' in ei.value.detail


def test_permission_checker_pass_with_perm_or_admin():
    checker, _ = _get_route_checker()
    assert checker(SimpleNamespace(state=SimpleNamespace(
        permissions={'algorithm:read'}))) is None
    assert checker(SimpleNamespace(state=SimpleNamespace(
        permissions={'*'}))) is None


# ══════════════════ 3. 网关链路（QueryService + ACL 替身） ══════════════════

def test_gateway_query_service_success_and_failure(monkeypatch):
    from api_gateway.application.services.algorithm import \
        algorithm_query_service as aqs

    acl = MagicMock(name='algorithm_acl')
    acl.get_reference_param.return_value = {
        'success': True, 'message': '', 'data': {'id': 31, 'code': 'p1'}}
    monkeypatch.setattr(aqs, '_algorithm_acl', acl)
    payload, http = aqs.AlgorithmQueryService.get_reference_param(31)
    assert http == 200
    assert payload['success'] is True
    assert payload['data'] == {'id': 31, 'code': 'p1'}
    acl.get_reference_param.assert_called_once_with(31)

    acl.get_reference_param.return_value = {
        'success': False, 'message': 'Reference parameter not found', 'code': 400}
    payload, http = aqs.AlgorithmQueryService.get_reference_param(99999999)
    assert http == 400
    assert payload['success'] is False
    assert payload['message'] == 'Reference parameter not found'


# ══════════════════ 4. servicer 链路（task_service 侧） ══════════════════

def _make_servicer(result):
    from task_service.interfaces.grpc.algorithm_config import \
        AlgorithmConfigServiceServicer
    servicer = AlgorithmConfigServiceServicer()
    svc = MagicMock(name='algorithm_param_service')
    svc.get_reference_param.return_value = result
    servicer._svc = svc
    return servicer, svc


def test_servicer_get_reference_param_found():
    from shared.proto import task_service_pb2 as task_pb
    servicer, svc = _make_servicer({
        'success': True, 'message': '', 'data': {'id': 31, 'code': 'p1'}})
    resp = servicer.GetReferenceParam(
        task_pb.GetReferenceParamRequest(param_id=31))
    svc.get_reference_param.assert_called_once_with(31)
    assert resp.success is True
    assert json.loads(resp.data) == {'id': 31, 'code': 'p1'}


def test_servicer_get_reference_param_not_found():
    from shared.proto import task_service_pb2 as task_pb
    servicer, _ = _make_servicer({
        'success': False, 'message': 'Reference parameter not found', 'code': 404})
    resp = servicer.GetReferenceParam(
        task_pb.GetReferenceParamRequest(param_id=99999999))
    assert resp.success is False
    assert resp.message == 'Reference parameter not found'
    assert resp.data == ''


# ══════════════════ 5. 契约两端（proto 生成物 + 前端 URL 模板） ══════════════════

def test_proto_generated_has_get_reference_param():
    import grpc
    from shared.proto import task_service_pb2 as task_pb
    from shared.proto import task_service_pb2_grpc as task_grpc
    req = task_pb.GetReferenceParamRequest(param_id=31)
    assert req.param_id == 31
    # grpcio 生成代码的 Stub 方法是 __init__ 里的实例属性（非类属性），
    # 用哑 channel 实例化验证；Servicer 方法为类级 def
    stub = task_grpc.AlgorithmConfigServiceStub(
        grpc.insecure_channel('localhost:1'))
    assert hasattr(stub, 'GetReferenceParam')
    assert hasattr(task_grpc.AlgorithmConfigServiceServicer,
                   'GetReferenceParam')


def test_frontend_get_reference_param_matches_backend_route():
    ts = (REPO_ROOT / 'frontend' / 'src' / 'infrastructure' / 'api'
          / 'algorithmApi.ts').read_text(encoding='utf-8')
    m = re.search(
        r'async getReferenceParam\(paramId[^}]*?\)\s*\{.*?\n  \},', ts, re.S)
    assert m, '前端 algorithmApi.getReferenceParam 未找到'
    block = m.group(0)
    assert "'GET'" in block
    assert '`/algorithm/reference-params/${paramId}`' in block
