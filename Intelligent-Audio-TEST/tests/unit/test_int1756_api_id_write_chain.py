# -*- coding: utf-8 -*-
"""INT-1756（C6a）返工补测：网关 → gRPC mixin → 仓储的真实写入链路。

审计 P2-2 复现的缺陷：网关 ``create_param`` 用 ``req.model_dump()`` 组 gRPC
载荷，而 ``param_type_source`` 不在 Create schema 的字段里（APIModel 是
``extra="ignore"``）→ 该键被丢弃，algorithm_service 回落 ``"device"`` ——
带 ``api_id`` 的「API 参数」被建进 ``algorithm_device_params``，而该表没有
``api_id`` 列（仓储按 ``hasattr`` 忽略），``api_id`` 一并丢失，于是 **API
级参数没有任何创建路径能落库**。

本文件不再用 fake ACL 只断言「网关把 api_id 交给了 ACL」，而是把网关载荷
按真实代理的方式（``json.dumps`` → ``pb.CreateParamRequest``）送进真实
gRPC mixin → 应用层 handler → 真实 SQLAlchemy 仓储（文件型 sqlite），断言
行实际落在哪张表、``api_id`` 是否落值。
"""
import json
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from shared.models.database import (  # noqa: E402
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from shared.proto import algorithm_service_pb2 as pb  # noqa: E402

ALGO = 'translation'
API_A = 11


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def db():
    """文件型 sqlite + 两张参数表（gRPC 线程与建表库必须是同一个库）。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-1756 写链路测试需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmApiParam as AlgorithmApiParamPO,
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[AlgorithmApiParamPO.__table__, AlgorithmDeviceParamPO.__table__],
    )
    yield engine
    remove_db_session()


@pytest.fixture()
def clean_tables(db):
    """每用例前后清空两张参数表（本 run 不落共享库）。"""
    _purge()
    yield
    _purge()


def _purge():
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmApiParam as AlgorithmApiParamPO,
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    session = get_db_session()
    session.query(AlgorithmApiParamPO).delete()
    session.query(AlgorithmDeviceParamPO).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()


class _FakeAPIConfigProxy:
    """api_config_service 桩：只提供 api_id → algorithm_type 的存在性/归属。"""

    def __init__(self, apis):
        self._apis = apis

    def get_one(self, api_id):
        data = self._apis.get(api_id)
        if data is None:
            return {'success': False, 'message': '未找到API配置',
                    'data': None, 'code': 404}
        return {'success': True, 'message': 'Success', 'data': data, 'code': 200}


class _RealChainACL:
    """网关 ACL 桩：把载荷按真实代理的序列化方式送进真实 gRPC mixin。

    ``api_gateway/infrastructure/grpc_proxies/algorithm_config_proxies.py``
    的 ``create_param`` 就是 ``json.dumps(data)`` → ``pb.CreateParamRequest``，
    这里保持一致，确保「JSON 序列化后还剩什么键」被真实覆盖。
    """

    def __init__(self, servicer):
        self._servicer = servicer
        self.payloads = []

    def create_param(self, data):
        self.payloads.append(dict(data))
        request = pb.CreateParamRequest(
            data=json.dumps(data, ensure_ascii=False, default=str))
        resp = self._servicer.CreateParam(request)
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
            'code': 200 if resp.success else 400,
        }


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self):
        return self._payload


@pytest.fixture()
def chain(monkeypatch, clean_tables):
    """装配：网关 service + fake api 配置代理 + 真实 servicer 链路。"""
    from api_gateway.application.services.algorithm import (
        algorithm_command_service as command_service,
    )
    from algorithm_service.interfaces.grpc.servicers import (
        AlgorithmDefinitionServicer,
    )

    monkeypatch.setattr(command_service, 'api_config_service',
                        _FakeAPIConfigProxy({
                            API_A: {'id': API_A, 'algorithm_type': ALGO,
                                    'name': 'A家'},
                        }))
    acl = _RealChainACL(AlgorithmDefinitionServicer())
    monkeypatch.setattr(command_service, '_algorithm_acl', acl)

    def _post(payload):
        monkeypatch.setattr(command_service, 'request', _FakeRequest(payload))
        result = command_service.AlgorithmCommandService.create_param()
        return result[1], result[0]

    return _post, acl


def _rows():
    """(algorithm_api_params 行, algorithm_device_params 行)。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmApiParam as AlgorithmApiParamPO,
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    session = get_db_session()
    try:
        api_rows = session.query(AlgorithmApiParamPO).all()
        device_rows = session.query(AlgorithmDeviceParamPO).all()
        # 提前取出标量，避免 session 关闭后 DetachedInstanceError
        api_out = [(r.param_code, r.api_id, r.direction, r.param_name)
                   for r in api_rows]
        device_out = [(r.param_code, r.param_name) for r in device_rows]
        return api_out, device_out
    finally:
        remove_db_session()


# ========== P2-2 回归：param_type_source 必须到达服务端 ==========

def test_gateway_payload_keeps_param_type_source(chain):
    post, acl = chain
    http_code, _ = post({
        'param_type_source': 'api', 'algorithm_type': ALGO, 'api_id': API_A,
        'param_code': 'lang', 'param_type': 'text', 'direction': 'input',
    })
    assert http_code == 200
    assert acl.payloads[0]['param_type_source'] == 'api', (
        'schema extra="ignore" 把判别键丢了 —— 服务端会回落 device 分支'
    )


# ========== 真实链路：API 级参数落 algorithm_api_params 且 api_id 有值 ==========

def test_create_api_param_lands_in_api_table_with_api_id(chain):
    post, _ = chain
    http_code, payload = post({
        'param_type_source': 'api', 'algorithm_type': ALGO, 'api_id': API_A,
        'param_code': 'lang', 'param_name': 'A家语言', 'param_type': 'text',
        'direction': 'input', 'ui_order': 1,
    })
    assert http_code == 200, payload

    api_rows, device_rows = _rows()
    assert device_rows == [], 'API 参数不得落 algorithm_device_params'
    assert len(api_rows) == 1
    param_code, api_id, direction, param_name = api_rows[0]
    assert (param_code, api_id, direction, param_name) == (
        'lang', API_A, 'input', 'A家语言')


def test_create_api_param_without_api_id_stays_algorithm_level(chain):
    """不传 api_id 仍是算法类型级 API 参数（api_id 落 NULL）。"""
    post, _ = chain
    http_code, payload = post({
        'param_type_source': 'api', 'algorithm_type': ALGO,
        'param_code': 'duration', 'param_type': 'text', 'direction': 'output',
    })
    assert http_code == 200, payload
    api_rows, device_rows = _rows()
    assert device_rows == []
    assert [(r[0], r[1]) for r in api_rows] == [('duration', None)]


def test_create_device_param_still_lands_in_device_table(chain):
    """设备参数不受影响：仍落 algorithm_device_params。"""
    post, acl = chain
    http_code, payload = post({
        'param_type_source': 'device', 'algorithm_type': ALGO,
        'param_code': 'sample_rate', 'param_type': 'text',
    })
    assert http_code == 200, payload
    assert acl.payloads[0]['param_type_source'] == 'device'
    api_rows, device_rows = _rows()
    assert api_rows == []
    assert [r[0] for r in device_rows] == ['sample_rate']
