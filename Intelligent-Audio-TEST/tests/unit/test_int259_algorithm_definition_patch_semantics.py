# -*- coding: utf-8 -*-
"""INT-259 验收测试：算法编辑 PATCH 语义（模态窗假成功修复回归）。

历史缺陷（INT-145 同型）：
- UpdateAlgorithmDefinitionCommand.name 曾为非空必填，且聚合根仅落
  name/description——算法列表「启用/禁用」toggle 只携带 status，导致
  name 被覆写为 ""、description 被覆写为 None（算法名被清空）；
  编辑模态窗改分组/上下线/图标/排序「确定」提示成功但静默丢弃不落库。

修复口径：命令改 PATCH 语义（字段为 None = 不改动现值），贯通
group_id / status / icon / display_order 至 handler → 聚合根 → PO。

三态覆盖（开发 commit 自述「PATCH 语义三态单测通过」但仓库内无对应
测试文件，本卡按验收职责补齐回归锁定）：
1. toggle 态：仅携带 status 的部分更新——name/description/分组/图标/排序
   全部保持原值（回归：算法名被清空）；
2. 全字段态：编辑模态窗完整提交——六个可写字段全部落库（回归：假成功）；
3. 显式改名态：仅携带 name——名称更新、其余字段保持原值；
4. 未知状态字符串容错按 draft 处理（与持久层 _status_from_po 口径一致）；
5. 落库验证走真实 SQLite 库 + AlgorithmDefinitionRepository，防「聚合根
   已改、PO 未写」的半程假成功。
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

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session


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
        f'INT-259 PATCH 回归需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from shared.models.database import Base
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmGroup as AlgorithmGroupPO,
        AlgorithmDefinition as AlgorithmDefinitionPO,
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
        AlgorithmApiParam as AlgorithmApiParamPO,
        AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[AlgorithmGroupPO.__table__, AlgorithmDefinitionPO.__table__,
                AlgorithmDeviceParamPO.__table__, AlgorithmApiParamPO.__table__,
                AlgorithmDimensionRelationPO.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture()
def clean_table(db):
    """每用例清空算法定义表（teardown 保证共享库不留本卡残留）。"""
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


def _seed_definition(name='声纹识别', group_id=7, icon='icon-src.png', order=3,
                     description='原始描述', status='online'):
    """直写 PO 播种一条算法定义，返回其 id。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    session = get_db_session()
    po = AlgorithmDefinitionPO(
        type='voiceprint_test', name=name, group_id=group_id,
        description=description, status=status, icon=icon,
        display_order=order, deleted=False,
    )
    session.add(po)
    session.commit()
    return po.id


def _reload_po(definition_id):
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    session = get_db_session()
    po = session.query(AlgorithmDefinitionPO).filter_by(id=definition_id).first()
    session.expunge(po)
    return po


def _run_update(**fields):
    """经真实 handler 执行 UpdateAlgorithmDefinitionCommand。"""
    from algorithm_service.application.commands.algorithm_commands import (
        UpdateAlgorithmDefinitionCommand,
    )
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )
    cmd = UpdateAlgorithmDefinitionCommand(**fields)
    AlgorithmCommandHandler().handle_update_definition(cmd)


# ── 三态 1：toggle（仅 status）不得清空其他字段 ──

def test_toggle_status_only_preserves_all_other_fields(db, clean_table):
    definition_id = _seed_definition()
    _run_update(id=definition_id, status='offline')

    po = _reload_po(definition_id)
    assert po.name == '声纹识别', 'toggle 后算法名必须保持原值（回归：被清空为 ""）'
    assert po.description == '原始描述', 'toggle 后描述必须保持原值（回归：被覆写为 None）'
    assert po.group_id == 7
    assert po.icon == 'icon-src.png'
    assert po.display_order == 3
    assert po.status == 'offline', '仅 status 应更新'


# ── 三态 2：编辑模态窗全字段提交必须全部落库（假成功回归） ──

def test_full_field_update_persists_every_field(db, clean_table):
    definition_id = _seed_definition(group_id=7, icon='icon-src.png', order=3)
    _run_update(
        id=definition_id,
        name='声纹识别V2',
        description='新描述',
        group_id=8,
        status='offline',
        icon='icon-new.png',
        display_order=42,
    )

    po = _reload_po(definition_id)
    assert po.name == '声纹识别V2'
    assert po.description == '新描述'
    assert po.group_id == 8, '分组必须落库（回归：静默丢弃）'
    assert po.status == 'offline', '上下线状态必须落库（回归：静默丢弃）'
    assert po.icon == 'icon-new.png', '图标必须落库（回归：静默丢弃）'
    assert po.display_order == 42, '显示顺序必须落库（回归：静默丢弃）'


# ── 三态 3：仅携带 name 的显式改名 ──

def test_name_only_update_changes_name_keeps_rest(db, clean_table):
    definition_id = _seed_definition()
    _run_update(id=definition_id, name='改名后')

    po = _reload_po(definition_id)
    assert po.name == '改名后'
    assert po.description == '原始描述'
    assert po.group_id == 7
    assert po.status == 'online'
    assert po.icon == 'icon-src.png'
    assert po.display_order == 3


# ── 未携带 name 时 command 默认 None（PATCH 而非覆写空串） ──

def test_command_defaults_keep_fields_unset():
    from algorithm_service.application.commands.algorithm_commands import (
        UpdateAlgorithmDefinitionCommand,
    )
    cmd = UpdateAlgorithmDefinitionCommand(id=1)
    assert cmd.name is None, '未携带 name 必须默认 None（PATCH 语义），而非空串'
    assert cmd.status is None
    assert cmd.group_id is None
    assert cmd.icon is None
    assert cmd.display_order is None


# ── 未知状态字符串容错按 draft（与持久层 _status_from_po 口径一致） ──

def test_unknown_status_string_maps_to_draft(db, clean_table):
    definition_id = _seed_definition(status='online')
    _run_update(id=definition_id, status='not_a_status')

    po = _reload_po(definition_id)
    assert po.status == 'draft', '未知状态字符串应容错为 draft'


# ── 更新不存在的定义必须报错（不静默假成功） ──

def test_update_missing_definition_raises(db, clean_table):
    with pytest.raises(ValueError, match='不存在'):
        _run_update(id=999999, name='幽灵算法')
