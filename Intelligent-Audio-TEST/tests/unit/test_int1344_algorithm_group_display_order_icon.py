# -*- coding: utf-8 -*-
"""INT-1344 验收测试：算法分组 display_order/icon 不落库修复回归。

历史缺陷（INT-1253 CRUD 走查、INT-1318 前端源码核对确认非前端问题）：
- 算法分组新建/编辑提交 display_order（排序）与 icon（图标）后不落库，
  落库恒为 display_order=0、icon=null；description 正常。
- 根因：algorithm_service 分组写路径自 schema 到聚合根均未携带
  icon/display_order——Pydantic 忽略多余字段（接口层静默丢弃）、
  命令/聚合根/转换器/仓储 add 均未读写该两列。

修复口径（对齐 definition 侧，_apply_definition_to_po 先例）：
- 契约：CreateGroupRequest/Command 补 icon + display_order（缺省 0）；
  UpdateGroupRequest/Command 补同字段（PATCH 语义：None=不改现值）。
- 贯通 handler → 聚合根 → PO（create 落提交值，update PATCH 覆盖）。

本文件按验收职责补齐回归锁定：
1. 新建分组填 icon/display_order → PO 与读回均等于提交值；
2. 新建不填 → 落库 icon=None、display_order=0（向后兼容默认）；
3. 编辑全字段（icon/display_order）→ 全部落库（假成功回归）；
4. 编辑仅带 name/description → icon/display_order 保持原值（PATCH）；
5. 命令缺省：Create 默认 display_order=0，Update 默认 icon/display_order=None；
6. 生产路径 gRPC servicer（网关 → CreateAlgorithmGroup）透传 icon/display_order。
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.user_context import set_current_user_id
from shared.models.database import init_db, get_db_session, get_engine, remove_db_session


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建算法分组表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-1344 需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from shared.models.database import Base
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmGroup as AlgorithmGroupPO,
    )
    Base.metadata.create_all(bind=engine, tables=[AlgorithmGroupPO.__table__])
    yield
    remove_db_session()


@pytest.fixture()
def clean_table(db):
    """每用例清空算法分组表（teardown 保证共享库不留本卡残留）。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmGroup as AlgorithmGroupPO,
    )
    session = get_db_session()
    session.query(AlgorithmGroupPO).delete()
    session.commit()
    yield
    session = get_db_session()
    session.query(AlgorithmGroupPO).delete()
    session.commit()


def _run_create(**fields):
    """经真实 handler 执行 CreateAlgorithmGroupCommand，返回新分组 ID。"""
    from algorithm_service.application.commands.algorithm_commands import (
        CreateAlgorithmGroupCommand,
    )
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )
    cmd = CreateAlgorithmGroupCommand(**fields)
    return AlgorithmCommandHandler().handle_create_group(cmd)


def _run_update(**fields):
    """经真实 handler 执行 UpdateAlgorithmGroupCommand。"""
    from algorithm_service.application.commands.algorithm_commands import (
        UpdateAlgorithmGroupCommand,
    )
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )
    cmd = UpdateAlgorithmGroupCommand(**fields)
    AlgorithmCommandHandler().handle_update_group(cmd)


def _seed_group(name='声纹分组', icon='group-icon.png', order=3, description='原始描述'):
    """直写 PO 播种一条算法分组，返回其 id。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmGroup as AlgorithmGroupPO,
    )
    session = get_db_session()
    po = AlgorithmGroupPO(
        name=name, description=description, icon=icon,
        display_order=order, deleted=False,
    )
    session.add(po)
    session.commit()
    return po.id


def _reload_po(group_id):
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmGroup as AlgorithmGroupPO,
    )
    session = get_db_session()
    po = session.query(AlgorithmGroupPO).filter_by(id=group_id).first()
    session.expunge(po)
    return po


# ── 1. 新建填 icon/display_order 必须落库 ──

def test_create_persists_icon_and_display_order(db, clean_table):
    set_current_user_id(134401)
    group_id = _run_create(name='接线测试_排序图标组', icon='test-icon', display_order=3)

    po = _reload_po(group_id)
    assert po.icon == 'test-icon', '新建分组 icon 必须落库（回归：恒为 null）'
    assert po.display_order == 3, '新建分组 display_order 必须落库（回归：恒为 0）'


def test_create_defaults_icon_none_order_zero(db, clean_table):
    """不提交 icon/display_order 时落库默认 icon=None、display_order=0（向后兼容）。"""
    set_current_user_id(134402)
    group_id = _run_create(name='接线测试_默认组')

    po = _reload_po(group_id)
    assert po.icon is None
    assert po.display_order == 0


# ── 2. 编辑全字段提交必须全部落库（假成功回归） ──

def test_update_persists_icon_and_display_order(db, clean_table):
    group_id = _seed_group()
    _run_update(
        id=group_id,
        name='声纹分组V2',
        description='新描述',
        icon='icon-new.png',
        display_order=42,
    )

    po = _reload_po(group_id)
    assert po.name == '声纹分组V2'
    assert po.description == '新描述'
    assert po.icon == 'icon-new.png', '编辑 icon 必须落库（回归：静默丢弃）'
    assert po.display_order == 42, '编辑 display_order 必须落库（回归：静默丢弃）'


# ── 3. 编辑仅带 name/description 时 icon/display_order 保持原值（PATCH） ──

def test_update_without_icon_order_preserves_existing(db, clean_table):
    group_id = _seed_group(icon='group-icon.png', order=3)
    _run_update(id=group_id, name='改名后', description='改描述')

    po = _reload_po(group_id)
    assert po.name == '改名后'
    assert po.description == '改描述'
    assert po.icon == 'group-icon.png', '未携带 icon 必须保持原值（PATCH 语义）'
    assert po.display_order == 3, '未携带 display_order 必须保持原值（PATCH 语义）'


# ── 4. 命令缺省值（PATCH 而非覆写） ──

def test_command_defaults_keep_fields_unset():
    from algorithm_service.application.commands.algorithm_commands import (
        CreateAlgorithmGroupCommand,
        UpdateAlgorithmGroupCommand,
    )
    create_cmd = CreateAlgorithmGroupCommand(name='新建')
    assert create_cmd.icon is None
    assert create_cmd.display_order == 0, 'Create 缺省 display_order 应为 0'

    update_cmd = UpdateAlgorithmGroupCommand(id=1, name='改名')
    assert update_cmd.icon is None, 'Update 未携带 icon 必须默认 None（PATCH 语义）'
    assert update_cmd.display_order is None, 'Update 未携带 display_order 必须默认 None（PATCH 语义）'


# ── 5. 生产路径 gRPC servicer 透传 icon/display_order（网关 → algorithm_service） ──

def test_grpc_create_group_passes_icon_and_display_order(db, clean_table):
    from algorithm_service.interfaces.grpc.servicers import AlgorithmGroupServicer
    set_current_user_id(134403)
    request = SimpleNamespace(
        data=json.dumps({
            'name': '接线测试_grpc组',
            'description': 'grpc描述',
            'icon': 'grpc-icon.png',
            'display_order': 7,
        })
    )
    servicer = AlgorithmGroupServicer()
    resp = servicer.CreateAlgorithmGroup(request, context=None)
    assert resp.success is True

    data = json.loads(resp.data)
    group_id = data['id']
    po = _reload_po(group_id)
    assert po.icon == 'grpc-icon.png', 'gRPC 新建路径 icon 必须落库（回归：静默丢弃）'
    assert po.display_order == 7, 'gRPC 新建路径 display_order 必须落库（回归：恒为 0）'


def test_grpc_update_group_passes_icon_and_display_order(db, clean_table):
    from algorithm_service.interfaces.grpc.servicers import AlgorithmGroupServicer
    group_id = _seed_group(icon='group-icon.png', order=3)
    request = SimpleNamespace(
        group_id=group_id,
        data=json.dumps({
            'name': '改名',
            'description': '改描述',
            'icon': 'grpc-icon2.png',
            'display_order': 9,
        })
    )
    servicer = AlgorithmGroupServicer()
    resp = servicer.UpdateAlgorithmGroup(request, context=None)
    assert resp.success is True

    po = _reload_po(group_id)
    assert po.name == '改名'
    assert po.icon == 'grpc-icon2.png'
    assert po.display_order == 9


def test_grpc_update_group_without_icon_order_preserves(db, clean_table):
    """gRPC 更新未携带 icon/display_order（网关 exclude_none 丢弃）→ 保持原值。"""
    from algorithm_service.interfaces.grpc.servicers import AlgorithmGroupServicer
    group_id = _seed_group(icon='group-icon.png', order=3)
    request = SimpleNamespace(
        group_id=group_id,
        data=json.dumps({'name': '仅改名'}),
    )
    servicer = AlgorithmGroupServicer()
    resp = servicer.UpdateAlgorithmGroup(request, context=None)
    assert resp.success is True

    po = _reload_po(group_id)
    assert po.icon == 'group-icon.png', 'gRPC 未携带 icon 必须保持原值（PATCH 语义）'
    assert po.display_order == 3, 'gRPC 未携带 display_order 必须保持原值（PATCH 语义）'


# ── 6. REST 序列化含 icon/display_order ──

def test_group_to_dict_serializes_icon_and_display_order(db, clean_table):
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmQueryHandler,
    )
    from algorithm_service.application.queries.algorithm_queries import (
        GetAlgorithmGroupQuery,
    )
    from algorithm_service.interfaces.api.routes import _group_to_dict
    set_current_user_id(134404)
    group_id = _run_create(name='接线测试_序列化组', icon='ser-icon.png', display_order=5)

    aggregate = AlgorithmQueryHandler().handle_get_group(
        GetAlgorithmGroupQuery(id=group_id))
    payload = _group_to_dict(aggregate)
    assert payload['icon'] == 'ser-icon.png'
    assert payload['display_order'] == 5
