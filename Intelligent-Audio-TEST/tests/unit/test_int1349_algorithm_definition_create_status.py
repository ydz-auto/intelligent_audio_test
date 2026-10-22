# -*- coding: utf-8 -*-
"""INT-1349 验收测试：算法定义 create 应用提交的 status。

缺陷（INT-1253 CRUD 走查发现）：
- POST /algorithm/definitions 无论提交 status=online 还是 status=offline，
  落库都是 status="draft"（create 硬编码草稿态，未应用提交的 status）。

修复口径：create 应应用提交的 status（online/offline/draft）落库，
draft 仅作草稿态；缺省（status 未提交）仍按 draft。

覆盖：
1. create(status='offline') → PO.status == 'offline'
2. create(status='online')  → PO.status == 'online'
3. create(status='draft')   → PO.status == 'draft'
4. create(status 缺省)      → PO.status == 'draft'（草稿态兜底）
5. 经 gRPC 请求 data 透传（mixins.algorithm_definition_mixin 的
   CreateAlgorithmDefinition 读 status 并传给命令）

测试走文件型 SQLite 隔离库 + AlgorithmCommandHandler / 真实仓储，
不动共享库（口径同 INT-259 / INT-589）。
"""
import os
import sys

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session  # noqa: E402


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建算法定义相关表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-1349 需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from shared.models.database import Base
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[AlgorithmDefinitionPO.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture()
def clean_table(db):
    """每用例清空算法定义表（teardown 保证隔离库不留残留）。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    session = get_db_session()
    session.query(AlgorithmDefinitionPO).delete()
    session.commit()
    yield
    session = get_db_session()
    session.query(AlgorithmDefinitionPO).delete()
    session.commit()


def _create_definition(**cmd_fields):
    """经真实 handler 执行 CreateAlgorithmDefinitionCommand，返回新定义 id。"""
    from algorithm_service.application.commands.algorithm_commands import (
        CreateAlgorithmDefinitionCommand,
    )
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )
    cmd = CreateAlgorithmDefinitionCommand(
        group_id=None,
        name='接线测试_下线验证',
        algorithm_type='jxcs_offline_test',
        **cmd_fields,
    )
    return AlgorithmCommandHandler().handle_create_definition(cmd)


def _reload_po(definition_id):
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    session = get_db_session()
    po = session.query(AlgorithmDefinitionPO).filter_by(id=definition_id).first()
    session.expunge(po)
    return po


# ── 应用提交的 status 落库 ──

def test_create_status_offline(db, clean_table):
    definition_id = _create_definition(status='offline')
    po = _reload_po(definition_id)
    assert po.status == 'offline', 'create 提交 status=offline 必须落库为 offline'


def test_create_status_online(db, clean_table):
    definition_id = _create_definition(status='online')
    po = _reload_po(definition_id)
    assert po.status == 'online', 'create 提交 status=online 必须落库为 online'


def test_create_status_draft(db, clean_table):
    definition_id = _create_definition(status='draft')
    po = _reload_po(definition_id)
    assert po.status == 'draft', 'create 显式提交 status=draft 应落库为 draft（草稿态）'


def test_create_status_default_draft(db, clean_table):
    definition_id = _create_definition()
    po = _reload_po(definition_id)
    assert po.status == 'draft', 'create 未提交 status 应兜底为 draft（草稿态）'


# ── gRPC mixin 透传 status ──

def test_create_grpc_mixin_passes_status(db, clean_table):
    """CreateAlgorithmDefinition RPC 从 data 读 status 并传给命令。"""
    import json
    from shared.proto import algorithm_service_pb2 as _pb

    from algorithm_service.interfaces.grpc.mixins.algorithm_definition_mixin import (
        _AlgorithmDefinitionMixin,
    )
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )

    mixin = _AlgorithmDefinitionMixin()
    mixin.command_handler = AlgorithmCommandHandler()

    request = _pb.CreateAlgorithmDefinitionRequest(
        data=json.dumps({
            'type': 'jxcs_offline_test',
            'name': '接线测试_下线验证',
            'status': 'offline',
        }, ensure_ascii=False),
    )
    resp = mixin.CreateAlgorithmDefinition(request, context=None)
    assert resp.success, f'CreateAlgorithmDefinition RPC 失败: {resp.message}'

    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    session = get_db_session()
    po = session.query(AlgorithmDefinitionPO).filter_by(
        type='jxcs_offline_test', deleted=False
    ).first()
    assert po is not None
    assert po.status == 'offline', 'gRPC create 必须把 data.status 传给 handler 落库'
