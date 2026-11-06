# -*- coding: utf-8 -*-
"""INT-2300 回归：PUT /algorithm/mappings 带 source_type 必须落库到 source。

缺陷（INT-2272 验收时实测发现）：网关 ``MappingUpdateRequest`` 收下
``source_type`` 并原样下发 gRPC，但 ``MappingRepository.update_attrs()`` 只读
``fields['source']``，``source_type`` 被静默丢弃 —— ``PUT`` 返回 200，
``GET`` 仍是旧来源。INT-2272 修复前表现为 400（缺字段），修复后变成更隐蔽的
「200 但静默不生效」。

契约（本文件逐条守住）：
1. ``update_attrs`` 的 source 取值与 ``create`` 同口径：``source_type`` 优先，
   ``source`` 作为兼容键仍可用；
2. 两者都没带时不动 source；
3. 网关 PUT 请求体里的 ``source_type`` 原样进 ACL 载荷；
4. 落库后按 ID 重新读出（GET 口径）回显新来源。

回归走文件型 SQLite 隔离库（init_db + create_all 指定表），不动共享库。
"""
import json
import os

import pytest
from sqlalchemy import BigInteger, text
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (  # noqa: E402
    Base, get_db_session, get_engine, init_db, remove_db_session,
)


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


ALGO = 'ceshi_int2300'


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建 algorithm_definitions / param_mappings。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-2300 映射更新回归需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
        ParamMapping as ParamMappingPO,
    )
    Base.metadata.create_all(bind=engine, tables=[
        AlgorithmDefinitionPO.__table__,
        ParamMappingPO.__table__,
    ])
    yield engine
    remove_db_session()


@pytest.fixture()
def clean_tables(db):
    """每用例前后清空两张表（隔离库不留残留）。"""
    _purge()
    yield
    _purge()


def _purge():
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
        ParamMapping as ParamMappingPO,
    )
    session = get_db_session()
    session.query(ParamMappingPO).delete()
    session.query(AlgorithmDefinitionPO).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()


def _seed_mapping(source='case'):
    """播种算法定义 + 一条映射（经真实仓储 create，create 口径传 source_type）。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    from algorithm_service.infrastructure.persistence.param_repository import (
        mapping_repository,
    )

    session = get_db_session()
    session.add(AlgorithmDefinitionPO(type=ALGO, name='INT-2300 回归算法'))
    session.commit()
    session.expunge_all()
    remove_db_session()

    created = mapping_repository.create({
        'algorithm_type': ALGO,
        'source_type': source,
        'source_param': 'src_out',
        'source_direction': 'output',
        'target_param': 'dst_in',
        'transform_type': 'none',
    })
    assert created['source'] == source
    remove_db_session()
    return created['id']


def _call_update_mapping(mapping_id, payload):
    """直调真实 gRPC UpdateMapping（真实 handler + 真实仓储），返回解析后的响应。"""
    from shared.proto import algorithm_service_pb2 as algo_pb
    from algorithm_service.application.handlers.algorithm_param_handlers import (
        AlgorithmParamCommandHandler,
    )
    from algorithm_service.interfaces.grpc.mixins.param_command_mixin import (
        _ParamCommandMixin,
    )

    servicer = _ParamCommandMixin.__new__(_ParamCommandMixin)
    servicer.param_command_handler = AlgorithmParamCommandHandler()
    # 单测无配置缓存依赖：只替身缓存失效钩子，写链路全部走真实实现
    servicer._invalidate_cache = lambda **kwargs: None
    resp = _ParamCommandMixin.UpdateMapping(
        servicer,
        algo_pb.UpdateMappingRequest(
            mapping_id=mapping_id,
            data=json.dumps(payload, ensure_ascii=False),
        ),
    )
    assert resp.success is True, resp.message
    return json.loads(resp.data)


def _read_back(mapping_id):
    """按 ID 用仓储重新读出（等价于 GET 的读口径）。"""
    from algorithm_service.infrastructure.persistence.param_repository import (
        mapping_repository,
    )

    remove_db_session()
    row = mapping_repository.get_by_id(mapping_id)
    remove_db_session()
    return row


# ==================== 写路径取值口径 ====================

def test_put_with_source_type_persists_and_reads_back(clean_tables):
    """复现卡面场景：PUT body 只带 {"source_type": "api"} → 重新读出为 api。"""
    mapping_id = _seed_mapping(source='case')
    assert _read_back(mapping_id)['source'] == 'case'

    result = _call_update_mapping(mapping_id, {'source_type': 'api'})
    assert result['source'] == 'api', 'PUT 响应未回显新来源'
    assert _read_back(mapping_id)['source'] == 'api', 'source_type 未落库'

    # 其它字段不受影响
    row = _read_back(mapping_id)
    assert row['source_param'] == 'src_out'
    assert row['target_param'] == 'dst_in'


def test_update_still_accepts_legacy_source_key(clean_tables):
    """直接传 source 的调用方口径不变。"""
    mapping_id = _seed_mapping(source='case')

    result = _call_update_mapping(mapping_id, {'source': 'reference'})
    assert result['source'] == 'reference'
    assert _read_back(mapping_id)['source'] == 'reference'


def test_source_type_wins_over_source(clean_tables):
    """两个键同时出现时按 create 口径取 source_type。"""
    mapping_id = _seed_mapping(source='case')

    result = _call_update_mapping(
        mapping_id, {'source': 'device', 'source_type': 'api'})
    assert result['source'] == 'api'
    assert _read_back(mapping_id)['source'] == 'api'


def test_update_without_source_keys_keeps_source(clean_tables):
    """不带来源键的更新（如只改目标参数）不得清空 / 改写来源。"""
    mapping_id = _seed_mapping(source='case')

    result = _call_update_mapping(mapping_id, {'target_param': 'dst_other'})
    assert result['source'] == 'case'
    row = _read_back(mapping_id)
    assert row['source'] == 'case'
    assert row['target_param'] == 'dst_other'


# ==================== 网关 PUT 载荷 ====================

class _FakeRequest:
    """最小请求替身：request_adapter 从 state._json_body 读 JSON body。"""

    def __init__(self, body):
        self.state = type('_State', (), {'_json_body': dict(body)})()

    def get_json(self, silent=False):
        return dict(self.state._json_body)


def test_gateway_put_forwards_source_type_to_acl(monkeypatch):
    """网关 PUT body 的 source_type 原样进 ACL（gRPC）载荷，不被 schema 丢弃。"""
    from api_gateway.infrastructure import request_adapter
    import api_gateway.application.services.algorithm.algorithm_command_service as svc

    captured = {}

    def _update(mapping_id, data):
        captured['mapping_id'] = mapping_id
        captured['data'] = dict(data)
        return {'success': True, 'data': {'id': mapping_id, 'source': 'api'},
                'message': 'Mapping updated'}

    monkeypatch.setattr(svc, '_algorithm_acl',
                        type('_Acl', (), {'update_mapping': staticmethod(_update)}))
    request_adapter.set_current_request(_FakeRequest({'source_type': 'api'}))
    try:
        payload, http_code = svc.AlgorithmCommandService.update_mapping(10885)
    finally:
        request_adapter.set_current_request(None)

    assert http_code == 200, payload
    assert captured['mapping_id'] == 10885
    assert captured['data'].get('source_type') == 'api'
