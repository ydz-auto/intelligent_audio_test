# -*- coding: utf-8 -*-
"""INT-1004 验收测试：网关 create_param 不再丢失 param_type_source → API 参数不落错表。

缺陷背景（INT-910 真实数据走查发现，Vue页面工程师A）：
`api_gateway/.../algorithm_command_service.py:create_param` 用
`param_type_source` 选择校验 schema 后执行 `req.model_dump(by_alias=False,
exclude_none=True)`；两个 schema（AlgorithmApiParamCreate /
AlgorithmDeviceParamCreate）均不包含该字段且 APIModel `extra="ignore"`，
导致 `param_type_source='api'` 在跨 gRPC 边界前被丢弃 → algorithm_service
`CreateParam` 回落默认 device → API 参数错落 device_params 表（刷新后出现在
「设备参数」页签）。

修复（本卡）：网关侧 `model_dump` 后重新注入 `param_type_source`。

回归测试分两层：
1. 网关链路：mock gRPC stub，断言跨边界 JSON 重带 `param_type_source` 且
   `direction` 保留（直接防复用 model_dump 再丢字段）；
2. 落库契约：文件型 SQLite 下走真实 servicer RPC + 仓储，断言
   `param_type_source='api'` 落 api_params 表、默认 device 落 device_params 表。
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


# ══════════════════ 1. 网关链路：字段重注入契约 ══════════════════


def _fake_request(json_body=None):
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params={}, method='GET',
                           is_json=False, headers={})


def _run_gateway_create_param(monkeypatch, json_body):
    """patch gRPC stub，捕获跨边界 CreateParamRequest，返回 captured 与 (payload, http_code)。"""
    from api_gateway.infrastructure.request_adapter import set_current_request
    from api_gateway.application.services.algorithm import (
        algorithm_command_service as _svc,
    )
    from api_gateway.infrastructure.grpc_proxies import (
        algorithm_config_proxies as _proxies,
    )
    captured = {}

    def _fake_stub_factory():
        def _create_param(req):
            captured['data'] = req.data
            return SimpleNamespace(
                success=True,
                message='ok',
                data=json.dumps({'id': 1, 'algorithm_type': 'int1004_probe'}),
            )
        return SimpleNamespace(CreateParam=_create_param)

    monkeypatch.setattr(_proxies, 'get_algorithm_config_service_stub',
                        _fake_stub_factory)
    set_current_request(_fake_request(json_body=json_body))
    try:
        payload, http_code = _svc.AlgorithmCommandService.create_param()
    finally:
        set_current_request(None)
    return captured, payload, http_code


_API_BODY = {
    'algorithm_type': 'int1004_probe_api',
    'param_code': 'int1004_probe_api_param',
    'param_name': '探针 API 参数',
    'param_type': 'text',
    'direction': 'output',
    'required': True,
    'param_type_source': 'api',
}


def test_gateway_reinjects_param_type_source_api(monkeypatch):
    """param_type_source='api' 必须随 data 跨 gRPC 边界透传，且 direction 保留。"""
    captured, payload, http_code = _run_gateway_create_param(monkeypatch, dict(_API_BODY))
    assert http_code == 200
    assert payload.get('success') is True
    assert captured, 'gRPC 代理未被调用（契约钉失效）'
    wire = json.loads(captured['data'])
    assert wire['param_type_source'] == 'api', (
        f'param_type_source 在 model_dump 后被丢弃（原缺陷形态），实际: {wire}'
    )
    assert wire['direction'] == 'output', 'direction 不得被改写'
    assert wire['algorithm_type'] == 'int1004_probe_api'


def test_gateway_default_device_still_injected(monkeypatch):
    """未携带 param_type_source 时按默认 device 注入（回归：device 路径不受影响）。"""
    body = {k: v for k, v in _API_BODY.items() if k != 'param_type_source'}
    captured, payload, http_code = _run_gateway_create_param(monkeypatch, body)
    assert http_code == 200
    assert payload.get('success') is True
    wire = json.loads(captured['data'])
    assert wire['param_type_source'] == 'device'


def test_gateway_api_schema_validation_still_applies(monkeypatch):
    """param_type_source='api' 走 AlgorithmApiParamCreate 校验（缺必填仍 400）。"""
    from api_gateway.infrastructure.request_adapter import set_current_request
    from api_gateway.application.services.algorithm import (
        algorithm_command_service as _svc,
    )
    bad_body = {**_API_BODY, 'param_code': ''}  # param_code min_length=1
    set_current_request(_fake_request(json_body=bad_body))
    try:
        payload, http_code = _svc.AlgorithmCommandService.create_param()
    finally:
        set_current_request(None)
    assert payload.get('success') is False
    assert http_code == 400


# ══════════════════ 2. task_service 路由契约（网关→微服务的中间跳） ══════════════════

def _run_task_create_param(data):
    """调用 task_service AlgorithmParamCrudService.create_param，repo 用替身记录路由。"""
    from unittest.mock import MagicMock
    from task_service.application.algorithm.algorithm_param_crud_service import (
        AlgorithmParamCrudService,
    )
    svc = AlgorithmParamCrudService()
    repo = MagicMock()
    repo.find_api_param_by_code.return_value = None
    repo.find_device_param_by_code.return_value = None
    repo.create_api_param.return_value = {'id': 1}
    repo.create_device_param.return_value = {'id': 1}
    svc.repo = repo
    result = svc.create_param(data)
    return result, repo


def test_task_routes_api_source_to_create_api_param():
    """param_type_source='api'（网关修复后重注入）→ task_service 必须走 create_api_param。"""
    result, repo = _run_task_create_param(dict(_API_BODY))
    assert result.get('success') is True
    assert repo.create_api_param.called, 'param_type_source=api 必须路由到 create_api_param'
    assert not repo.create_device_param.called, '不得误路由到 create_device_param（原缺陷形态）'
    # 透传的 data 保留 direction，不因路由改写
    sent = repo.create_api_param.call_args[0][0]
    assert sent['param_type_source'] == 'api' and sent['direction'] == 'output'


def test_task_defaults_missing_source_to_device():
    """网关漏注入（原缺陷）时 task_service 按默认 device 路由 → 复现错表路径。"""
    body = {k: v for k, v in _API_BODY.items() if k != 'param_type_source'}
    result, repo = _run_task_create_param(body)
    assert result.get('success') is True
    assert repo.create_device_param.called
    assert not repo.create_api_param.called


# ══════════════════ 3. 落库契约：param_type_source 路由到正确表 ══════════════════

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session  # noqa: E402


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建设备/API 参数两张表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-1004 落库契约需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from shared.models.database import Base
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
        AlgorithmApiParam as AlgorithmApiParamPO,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[AlgorithmDeviceParamPO.__table__, AlgorithmApiParamPO.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture()
def clean_param_tables(db):
    """每用例清空参数表（teardown 保证隔离库不留本卡残留）。"""
    from algorithm_service.infrastructure.persistence import models as _models
    yield
    session = get_db_session()
    session.query(_models.AlgorithmDeviceParam).delete()
    session.query(_models.AlgorithmApiParam).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()


def _call_create_param_rpc(data_dict):
    """经真实 servicer RPC（proto CreateParamRequest 线格式）创建参数。"""
    from algorithm_service.interfaces.grpc.servicers import AlgorithmDefinitionServicer
    from shared.proto import task_service_pb2 as task_pb
    servicer = AlgorithmDefinitionServicer()
    resp = servicer.CreateParam(task_pb.CreateParamRequest(
        data=json.dumps(data_dict, ensure_ascii=False),
    ))
    return resp


def _counts():
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as DevicePO,
        AlgorithmApiParam as ApiPO,
    )
    session = get_db_session()
    return (
        session.query(DevicePO).filter_by(deleted=False).count(),
        session.query(ApiPO).filter_by(deleted=False).count(),
    )


def test_api_param_lands_in_api_params_table(clean_param_tables):
    """param_type_source='api' 创建 → 落 api_params 表，device_params 表为空。"""
    resp = _call_create_param_rpc(_API_BODY)
    assert resp.success, f'RPC 失败: {resp.message}'
    created = json.loads(resp.data)
    assert created['direction'] == 'output', 'direction 必须落库保留'

    device_n, api_n = _counts()
    assert api_n == 1, 'param_type_source=api 必须落 api_params 表'
    assert device_n == 0, 'API 参数不得落 device_params 表（原缺陷形态）'

    from algorithm_service.infrastructure.persistence.models import AlgorithmApiParam
    po = get_db_session().query(AlgorithmApiParam).filter_by(
        algorithm_type='int1004_probe_api',
        param_code='int1004_probe_api_param',
        deleted=False,
    ).first()
    assert po is not None and po.direction == 'output'


def test_default_device_lands_in_device_params_table(clean_param_tables):
    """未携带 param_type_source（默认 device）创建 → 落 device_params 表。"""
    body = {k: v for k, v in _API_BODY.items() if k != 'param_type_source'}
    resp = _call_create_param_rpc(body)
    assert resp.success, f'RPC 失败: {resp.message}'

    device_n, api_n = _counts()
    assert device_n == 1, '默认 device 参数必须落 device_params 表'
    assert api_n == 0

    from algorithm_service.infrastructure.persistence.models import AlgorithmDeviceParam
    po = get_db_session().query(AlgorithmDeviceParam).filter_by(
        algorithm_type='int1004_probe_api',
        param_code='int1004_probe_api_param',
        deleted=False,
    ).first()
    assert po is not None and po.direction == 'output'
