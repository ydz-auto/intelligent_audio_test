# -*- coding: utf-8 -*-
"""INT-1514 修复测试：算法「发布」/删除后必须清除草稿快照。

缺陷（INT-1483 走查）：React 编辑弹窗「发布」走 PUT /algorithm/definitions/{type}
（旧聚合更新 RPC），task_service 旧 CRUD 只改 algorithm_definitions，不碰
algorithm_definition_drafts；删除同样不级联 → 重开编辑回显旧草稿并显示
「存在未发布的草稿」横幅，覆盖已发布内容。

修复：
1. algorithm_service.AlgorithmDefinitionService 新增 ClearAlgorithmDefinitionDraft
   RPC（复用 command_handler.handle_clear_draft → repo.clear_snapshot）；
2. 网关 AlgorithmCommandService 在 create/update/delete/bulk-delete 成功后调用，
   清除失败只记日志、不改变主结果（与 handle_save_definition 同口径）。

测试走文件型 SQLite 隔离库（root conftest 进程级临时库），不动共享库。
"""
import json
import os
import sys

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


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建草稿表 + 定义表。"""
    from shared.models.database import init_db, get_engine, remove_db_session

    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-1514 需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from shared.models.database import Base
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
        AlgorithmDefinitionDraft as AlgorithmDefinitionDraftPO,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[AlgorithmDefinitionPO.__table__, AlgorithmDefinitionDraftPO.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture()
def clean_drafts(db):
    """每用例清空草稿表。"""
    from shared.models.database import get_db_session
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinitionDraft as AlgorithmDefinitionDraftPO,
    )
    session = get_db_session()
    session.query(AlgorithmDefinitionDraftPO).delete()
    session.commit()
    yield


# ==================== algorithm_service RPC 入口 ====================

def _servicer():
    from algorithm_service.interfaces.grpc.servicers import AlgorithmDefinitionServicer
    return AlgorithmDefinitionServicer()


def _draft_name(servicer, algo_type):
    from shared.proto import algorithm_service_pb2 as pb
    resp = servicer.GetAlgorithmDefinitionDraft(
        pb.GetAlgorithmDefinitionDraftRequest(algorithm_type=algo_type)
    )
    assert resp.success
    data = json.loads(resp.data) if resp.data else {}
    return data.get('name')


def test_clear_draft_rpc_removes_snapshot(db, clean_drafts):
    """Clear RPC：有草稿 → 清除并回报 cleared=true；再清 → 幂等成功 cleared=false。"""
    from shared.proto import algorithm_service_pb2 as pb

    servicer = _servicer()
    saved = servicer.SaveAlgorithmDefinitionDraft(
        pb.SaveAlgorithmDefinitionDraftRequest(
            data=json.dumps({'algorithm_type': 'itest1514_type', 'name': '草稿态'})
        )
    )
    assert saved.success
    assert _draft_name(servicer, 'itest1514_type') == '草稿态'

    resp = servicer.ClearAlgorithmDefinitionDraft(
        pb.ClearAlgorithmDefinitionDraftRequest(algorithm_type='itest1514_type')
    )
    assert resp.success
    payload = json.loads(resp.data)
    assert payload == {'algorithm_type': 'itest1514_type', 'cleared': True}
    # 快照已删：读草稿返回空对象
    assert _draft_name(servicer, 'itest1514_type') is None

    again = servicer.ClearAlgorithmDefinitionDraft(
        pb.ClearAlgorithmDefinitionDraftRequest(algorithm_type='itest1514_type')
    )
    assert again.success
    assert json.loads(again.data)['cleared'] is False


def test_clear_draft_rpc_requires_algorithm_type(db, clean_drafts):
    """algorithm_type 缺失 → success=false，不抛异常。"""
    from shared.proto import algorithm_service_pb2 as pb

    resp = _servicer().ClearAlgorithmDefinitionDraft(
        pb.ClearAlgorithmDefinitionDraftRequest(algorithm_type='')
    )
    assert resp.success is False
    assert 'algorithm_type' in resp.message


# ==================== 网关编排（发布/删除后清草稿）====================

class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self):
        return self._payload


class _FakeAcl:
    def __init__(self, success=True, bulk_deleted=None):
        self.success = success
        self.bulk_deleted = bulk_deleted
        self.calls = []

    def _result(self):
        return {'success': self.success, 'data': None, 'message': 'ok', 'code': 400}

    def create_algorithm(self, data):
        self.calls.append(('create', data))
        return self._result()

    def update_algorithm(self, algo_type, data):
        self.calls.append(('update', algo_type, data))
        return self._result()

    def delete_algorithm(self, algo_type):
        self.calls.append(('delete', algo_type))
        return self._result()

    def bulk_delete(self, data):
        self.calls.append(('bulk_delete', data))
        if not self.success:
            return self._result()
        return {
            'success': True,
            'message': 'ok',
            'data': {'deleted_types': list(self.bulk_deleted or [])},
        }


class _FakeDraftProxy:
    def __init__(self, success=True, raises=False):
        self.success = success
        self.raises = raises
        self.cleared = []

    def clear_algorithm_definition_draft(self, algorithm_type):
        if self.raises:
            raise RuntimeError('grpc down')
        self.cleared.append(algorithm_type)
        return {'success': self.success, 'message': 'ok', 'data': None}


@pytest.fixture()
def gateway(monkeypatch):
    """把网关命令服务的外部依赖换成桩：ACL（task_service）+ 草稿代理。"""
    import api_gateway.application.services.algorithm.algorithm_command_service as mod

    acl = _FakeAcl()
    proxy = _FakeDraftProxy()
    monkeypatch.setattr(mod, '_algorithm_acl', acl)
    monkeypatch.setattr(mod, '_algorithm_service_proxy', proxy)
    return mod, acl, proxy


def _set_json(monkeypatch, mod, payload):
    monkeypatch.setattr(mod, 'request', _FakeRequest(payload))


def test_update_publish_clears_draft(gateway, monkeypatch):
    """发布（更新）成功 → 清除该 algorithm_type 的草稿。"""
    mod, acl, proxy = gateway
    _set_json(monkeypatch, mod, {'name': '发布态'})

    payload, code = mod.AlgorithmCommandService.update_algorithm('itest1514_type')

    assert code == 200 and payload['success'] is True
    assert acl.calls[0][0] == 'update'
    assert proxy.cleared == ['itest1514_type']


def test_update_failure_keeps_draft(gateway, monkeypatch):
    """发布失败 → 不清除草稿（用户编辑内容不丢）。"""
    mod, acl, proxy = gateway
    acl.success = False
    _set_json(monkeypatch, mod, {'name': '发布态'})

    payload, code = mod.AlgorithmCommandService.update_algorithm('itest1514_type')

    assert payload['success'] is False
    assert proxy.cleared == []


def test_delete_clears_draft(gateway):
    """删除算法 → 级联清草稿（不再残留指向已软删算法的快照）。"""
    mod, acl, proxy = gateway

    payload, code = mod.AlgorithmCommandService.delete_algorithm('itest1514_type')

    assert code == 200 and payload['success'] is True
    assert proxy.cleared == ['itest1514_type']


def test_create_clears_stale_draft(gateway, monkeypatch):
    """新建同类型算法 → 丢弃历史草稿，避免重开编辑回显旧快照。"""
    mod, acl, proxy = gateway
    _set_json(monkeypatch, mod, {'type': 'itest1514_type', 'name': '新建'})

    payload, code = mod.AlgorithmCommandService.create_algorithm()

    assert code == 200 and payload['success'] is True
    assert proxy.cleared == ['itest1514_type']


def test_bulk_delete_clears_only_deleted_types(gateway, monkeypatch):
    """批量删除 → 只清实际删除的类型，未删成功的保留草稿。"""
    mod, acl, proxy = gateway
    acl.bulk_deleted = ['itest1514_a', 'itest1514_b']
    _set_json(monkeypatch, mod, {
        'algorithm_types': ['itest1514_a', 'itest1514_b', 'itest1514_kept'],
    })

    payload, code = mod.AlgorithmCommandService.bulk_delete()

    assert code == 200 and payload['success'] is True
    assert proxy.cleared == ['itest1514_a', 'itest1514_b']


def test_clear_draft_failure_does_not_break_publish(gateway, monkeypatch):
    """清除失败（返回失败 / 抛异常）只记日志，发布结果照常成功。"""
    mod, acl, proxy = gateway
    _set_json(monkeypatch, mod, {'name': '发布态'})

    proxy.success = False
    payload, code = mod.AlgorithmCommandService.update_algorithm('itest1514_type')
    assert code == 200 and payload['success'] is True

    proxy.raises = True
    payload, code = mod.AlgorithmCommandService.update_algorithm('itest1514_type')
    assert code == 200 and payload['success'] is True
