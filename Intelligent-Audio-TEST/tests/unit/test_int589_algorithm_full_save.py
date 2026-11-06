# -*- coding: utf-8 -*-
"""INT-589 验收测试：算法定义全量保存事务 RPC + 草稿 + 乐观锁。

验收标准覆盖：
1. 事务 RPC：一次提交定义+嵌套子实体全部落库；人为制造中途失败 → 整体回滚，
   DB 无半成品残留；
2. 幂等：同版本重放不产生重复子实体；
3. 乐观锁：两个并发保存（同版本先后提交），后提交者得 CONFLICT 码；
4. 草稿：自动保存草稿可恢复；发布走全量校验，校验失败不落库；
5. 旧分步保存路径回归：由现有算法测试套件覆盖，本卡不重复。

测试走文件型 SQLite 隔离库（init_db + create_all 指定表），不动共享库。
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


_ALL_TABLES = (
    'AlgorithmGroup', 'AlgorithmDefinition', 'AlgorithmDeviceParam',
    'AlgorithmApiParam', 'CaseAlgorithmParam', 'AlgorithmReferenceParam',
    'ParamMapping', 'AlgorithmDimensionRelation', 'AlgorithmDefinitionDraft',
)


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建算法相关全部表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-589 事务测试需要文件型 sqlite，实际绑定 {engine.url}'
    )
    remove_db_session()
    from shared.models.database import Base
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmGroup as AlgorithmGroupPO,
        AlgorithmDefinition as AlgorithmDefinitionPO,
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
        AlgorithmApiParam as AlgorithmApiParamPO,
        CaseAlgorithmParam as CaseAlgorithmParamPO,
        AlgorithmReferenceParam as AlgorithmReferenceParamPO,
        ParamMapping as ParamMappingPO,
        AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
        AlgorithmDefinitionDraft as AlgorithmDefinitionDraftPO,
    )
    tables = [
        AlgorithmGroupPO.__table__, AlgorithmDefinitionPO.__table__,
        AlgorithmDeviceParamPO.__table__, AlgorithmApiParamPO.__table__,
        CaseAlgorithmParamPO.__table__, AlgorithmReferenceParamPO.__table__,
        ParamMappingPO.__table__, AlgorithmDimensionRelationPO.__table__,
        AlgorithmDefinitionDraftPO.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    yield
    remove_db_session()


@pytest.fixture()
def clean_tables(db):
    """每用例清空算法相关表（teardown 保证隔离库不留残留 + 身份映射复位）。"""
    from algorithm_service.infrastructure.persistence import models as _models
    yield
    session = get_db_session()
    for name in _ALL_TABLES:
        session.query(getattr(_models, name)).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()


@pytest.fixture(autouse=True)
def _mock_dimension_validation(monkeypatch):
    """默认 mock 关联维度存在性校验为「全部存在」。

    单测环境无 evaluation_service gRPC 对端，跨服务校验不可用；
    需验证校验失败语义的用例自行 monkeypatch 覆盖返回值。
    """
    import algorithm_service.application.handlers.algorithm_handlers as _handlers
    monkeypatch.setattr(_handlers, 'validate_dimension_ids_exist', lambda ids: [])


def _count(session, name):
    """按表名统计行数。"""
    from algorithm_service.infrastructure.persistence import models as _models
    return session.query(getattr(_models, name)).count()


def _full_payload(**overrides):
    """构造完整定义 payload（基础字段 + 六类子实体）。"""
    payload = {
        'algorithm_type': 'voice_llm',
        'name': '语音大模型',
        'group_id': None,
        'description': '全量保存测试算法',
        'status': 'online',
        'icon': 'icon.png',
        'display_order': 1,
        'device_params': [
            {'param_code': 'ch', 'param_name': '声道', 'direction': 'input',
             'param_type': 'text', 'required': True},
        ],
        'api_params': [
            {'param_code': 'api_key', 'param_name': 'API密钥', 'direction': 'input',
             'param_type': 'text'},
        ],
        'case_params': [
            {'param_code': 'lang', 'param_name': '语言', 'param_type': 'text',
             'scope': 'common'},
        ],
        'reference_params': [
            {'code': 'ref_text', 'name': '参考文本', 'param_type': 'text'},
        ],
        'mappings': [
            {'source': 'device', 'source_param': 'ch', 'dimension_id': 1,
             'target_param': 'channels', 'transform_type': 'none'},
        ],
        'associated_dimensions': [
            {'dimension_id': 1, 'is_default': True, 'weight': 1.0},
        ],
    }
    payload.update(overrides)
    return payload


def _make_command(payload, **cmd_overrides):
    """payload → SaveAlgorithmDefinitionCommand。"""
    from algorithm_service.application.commands.algorithm_commands import (
        SaveAlgorithmDefinitionCommand,
    )
    return SaveAlgorithmDefinitionCommand(
        id=payload.get('id'),
        algorithm_type=payload['algorithm_type'],
        name=payload['name'],
        group_id=payload.get('group_id'),
        description=payload.get('description'),
        status=payload.get('status'),
        icon=payload.get('icon'),
        display_order=payload.get('display_order'),
        device_params=payload.get('device_params') or [],
        api_params=payload.get('api_params') or [],
        case_params=payload.get('case_params') or [],
        reference_params=payload.get('reference_params') or [],
        mappings=payload.get('mappings'),
        associated_dimensions=payload.get('associated_dimensions') or [],
        expected_updated_at=payload.get('expected_updated_at'),
        **cmd_overrides,
    )


def _handle_save(payload, monkeypatch):
    """经真实 handler 执行全量保存（维度校验默认 mock 见 autouse 夹具）。"""
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )
    return AlgorithmCommandHandler().handle_save_definition(_make_command(payload))


def _load_definition(session, algorithm_type='voice_llm'):
    """按 type 加载未删除定义 PO。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    return session.query(AlgorithmDefinitionPO).filter_by(
        type=algorithm_type, deleted=False
    ).first()


# ==================== 1. 事务 RPC：全量落库 + 中途失败整体回滚 ====================

def test_save_full_persists_all_entities(db, clean_tables, monkeypatch):
    """一次提交定义 + 六类子实体全部落库（无子实体遗漏）。"""
    session = get_db_session()
    result = _handle_save(_full_payload(), monkeypatch)

    assert result['code'] == 'SAVED'
    assert result['id'] > 0

    definition = _load_definition(session)
    assert definition is not None
    assert definition.name == '语音大模型'
    assert _count(session, 'AlgorithmDeviceParam') == 1
    assert _count(session, 'AlgorithmApiParam') == 1
    assert _count(session, 'CaseAlgorithmParam') == 1
    assert _count(session, 'AlgorithmReferenceParam') == 1
    assert _count(session, 'ParamMapping') == 1
    assert _count(session, 'AlgorithmDimensionRelation') == 1


def test_save_full_midchain_failure_rolls_back(db, clean_tables, monkeypatch):
    """人为制造子实体中途失败 → 整体回滚，DB 无半成品残留。

    构造 case_params 缺 param_code（在 device/api 之后触发 ValueError），
    rollback 后定义根与已 upsert 的子实体全部不落库。
    """
    session = get_db_session()
    payload = _full_payload(case_params=[{'param_name': '缺 code'}])

    with pytest.raises(ValueError, match='用例参数缺少 param_code'):
        _handle_save(payload, monkeypatch)

    # 全表零残留：根定义与任何子实体都不存在
    assert _count(session, 'AlgorithmDefinition') == 0
    assert _count(session, 'AlgorithmDeviceParam') == 0
    assert _count(session, 'AlgorithmApiParam') == 0
    assert _count(session, 'CaseAlgorithmParam') == 0
    assert _count(session, 'AlgorithmReferenceParam') == 0
    assert _count(session, 'ParamMapping') == 0
    assert _count(session, 'AlgorithmDimensionRelation') == 0


def test_save_full_update_midchain_failure_rolls_back(db, clean_tables, monkeypatch):
    """更新路径中途失败 → 根 CAS 与子实体整体回滚，旧数据保持原状。"""
    session = get_db_session()
    result = _handle_save(_full_payload(), monkeypatch)
    definition = _load_definition(session)
    version = definition.updated_at.isoformat()

    # 更新 payload：合法 device + 非法 mapping（缺 source_param）→ 中段失败
    payload = _full_payload(
        id=definition.id,
        expected_updated_at=version,
        device_params=[
            {'param_code': 'ch2', 'param_name': '新声道', 'direction': 'input',
             'param_type': 'text'},
        ],
        mappings=[{'source': 'device', 'target_param': 'x'}],  # 缺 source_param
    )
    with pytest.raises(ValueError, match='参数映射缺少 source_param'):
        _handle_save(payload, monkeypatch)

    # 回滚后：定义基础字段仍是旧值，device 子实体未被替换为 ch2
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    definition = _load_definition(session)
    assert definition.name == '语音大模型'
    assert _count(session, 'AlgorithmDeviceParam') == 1
    dev = session.query(AlgorithmDeviceParamPO).filter_by(
        algorithm_type='voice_llm', deleted=False
    ).first()
    assert dev.param_code == 'ch'


# ==================== 2. 幂等：同版本重放不产生重复子实体 ====================

def test_same_version_replay_no_duplicate_sub_entities(db, clean_tables, monkeypatch):
    """同版本重放（version 未变即再次保存）→ 子实体不重复。"""
    session = get_db_session()
    result = _handle_save(_full_payload(), monkeypatch)
    definition = _load_definition(session)
    version = definition.updated_at.isoformat()

    # 相同 payload + 当前 version 再次保存 → OK 且不产生重复子实体
    result2 = _handle_save(
        _full_payload(id=definition.id, expected_updated_at=version), monkeypatch
    )
    assert result2['code'] == 'OK'
    assert _count(session, 'AlgorithmDeviceParam') == 1
    assert _count(session, 'AlgorithmApiParam') == 1
    assert _count(session, 'CaseAlgorithmParam') == 1
    assert _count(session, 'AlgorithmReferenceParam') == 1
    assert _count(session, 'ParamMapping') == 1
    assert _count(session, 'AlgorithmDimensionRelation') == 1


def test_replay_excludes_soft_deleted_natural_key_collisions(db, clean_tables, monkeypatch):
    """自然键排除软删项：既有软删行不阻塞、不产生重复活跃行。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    session = get_db_session()
    # 播种一个软删的同自然键 device 行（模拟历史删除，自然键 (ch, input) 被占用）
    session.add(AlgorithmDeviceParamPO(
        algorithm_type='voice_llm', param_code='ch', param_name='旧声道',
        direction='input', param_type='text', deleted=True,
    ))
    session.commit()
    session.expunge_all()

    _handle_save(_full_payload(), monkeypatch)

    # 只产生 1 条活跃行（软删行被自然键 find 排除，不阻塞新建）
    assert _count(session, 'AlgorithmDeviceParam') == 1
    active = session.query(AlgorithmDeviceParamPO).filter_by(
        algorithm_type='voice_llm', deleted=False
    ).first()
    assert active.param_code == 'ch'
    assert active.deleted is False


# ==================== 3. 乐观锁：并发双写后提交者 CONFLICT ====================

def test_optimistic_lock_conflict_on_stale_version(db, clean_tables, monkeypatch):
    """两个并发保存同版本：先提交者 OK，后提交者（同 version）CONFLICT。"""
    session = get_db_session()
    result = _handle_save(_full_payload(), monkeypatch)
    assert result['code'] == 'SAVED'
    definition = _load_definition(session)
    version = definition.updated_at.isoformat()

    # 第一个并发保存：version 匹配 → OK
    result_ok = _handle_save(
        _full_payload(id=definition.id, expected_updated_at=version), monkeypatch
    )
    assert result_ok['code'] == 'OK'

    # 第二个并发保存：复用同一 version（已被上一保存推进）→ CONFLICT
    result_conflict = _handle_save(
        _full_payload(id=definition.id, expected_updated_at=version), monkeypatch
    )
    assert result_conflict['code'] == 'CONFLICT'
    # 冲突时不做任何写
    assert _count(session, 'AlgorithmDeviceParam') == 1


def test_update_without_expected_raises(db, clean_tables, monkeypatch):
    """更新路径缺少 expected_updated_at → VALIDATION_FAILED（缺乐观锁版本）。"""
    session = get_db_session()
    result = _handle_save(_full_payload(), monkeypatch)
    definition = _load_definition(session)

    with pytest.raises(ValueError, match='expected_updated_at'):
        _handle_save(_full_payload(id=definition.id), monkeypatch)


# ==================== 4. 草稿：保存/恢复 + 发布校验失败不落库 ====================

def test_draft_save_and_restore(db, clean_tables, monkeypatch):
    """草稿自动保存可恢复（30s 快照，不落正式六表）。"""
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
        AlgorithmQueryHandler,
    )
    payload = _full_payload()
    saved_at = AlgorithmCommandHandler().handle_save_draft('voice_llm', payload)

    # INT-683：草稿保存返回服务端最后保存时间（供响应补 saved_at）
    assert saved_at is not None
    assert hasattr(saved_at, 'isoformat')

    snapshot = AlgorithmQueryHandler().handle_get_definition_draft('voice_llm')
    assert snapshot is not None
    assert snapshot['algorithm_type'] == 'voice_llm'
    assert snapshot['name'] == '语音大模型'
    # 草稿保存不落正式六表
    session = get_db_session()
    assert _count(session, 'AlgorithmDefinition') == 0
    assert _count(session, 'AlgorithmDeviceParam') == 0


def test_draft_save_updates_saved_at(db, clean_tables, monkeypatch):
    """重复保存草稿：saved_at 随时间推进（upsert 更新路径）。"""
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )
    payload = _full_payload()
    first = AlgorithmCommandHandler().handle_save_draft('voice_llm', payload)
    second = AlgorithmCommandHandler().handle_save_draft('voice_llm', payload)

    assert first is not None and second is not None
    assert second >= first
    # 仍只有一份快照（按 algorithm_type upsert）
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinitionDraft as AlgorithmDefinitionDraftPO,
    )
    session = get_db_session()
    assert session.query(AlgorithmDefinitionDraftPO).filter_by(
        algorithm_type='voice_llm'
    ).count() == 1


def test_publish_clears_draft_snapshot(db, clean_tables, monkeypatch):
    """发布成功 → 草稿快照被清除（下一次自动保存重新累积）。"""
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
        AlgorithmQueryHandler,
    )
    AlgorithmCommandHandler().handle_save_draft('voice_llm', _full_payload())

    result = _handle_save(_full_payload(), monkeypatch)
    assert result['code'] == 'SAVED'
    assert AlgorithmQueryHandler().handle_get_definition_draft('voice_llm') is None


def test_publish_validation_failure_not_persisted(db, clean_tables, monkeypatch):
    """发布走全量校验：维度不存在 → VALIDATION_FAILED，不落库、不清草稿。"""
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
        AlgorithmQueryHandler,
    )
    import algorithm_service.application.handlers.algorithm_handlers as _handlers
    AlgorithmCommandHandler().handle_save_draft('voice_llm', _full_payload())

    monkeypatch.setattr(_handlers, 'validate_dimension_ids_exist', lambda ids: [999])

    with pytest.raises(ValueError, match='关联评估维度不存在'):
        _handle_save(_full_payload(), monkeypatch)

    session = get_db_session()
    assert _count(session, 'AlgorithmDefinition') == 0
    # 校验失败不清草稿（用户仍可继续编辑）
    assert AlgorithmQueryHandler().handle_get_definition_draft('voice_llm') is not None


# ==================== gRPC RPC 入口（code 字段 + 分支映射） ====================

def test_rpc_save_definition_returns_code_saved(db, clean_tables, monkeypatch):
    """SaveAlgorithmDefinition RPC：成功返回 SAVED，code 字段承载机器可读结果。"""
    from algorithm_service.interfaces.grpc.servicers import AlgorithmDefinitionServicer
    import algorithm_service.application.handlers.algorithm_handlers as _handlers
    monkeypatch.setattr(_handlers, 'validate_dimension_ids_exist', lambda ids: [])

    servicer = AlgorithmDefinitionServicer()
    resp = servicer.SaveAlgorithmDefinition(_full_payload())

    assert resp.success is True
    assert resp.code == 'SAVED'
    data = __import__('json').loads(resp.data)
    assert data['id'] > 0
    assert data['algorithm_type'] == 'voice_llm'


def test_rpc_save_definition_conflict_code(db, clean_tables, monkeypatch):
    """SaveAlgorithmDefinition RPC：乐观锁冲突返回 code=CONFLICT。"""
    from algorithm_service.interfaces.grpc.servicers import AlgorithmDefinitionServicer
    import algorithm_service.application.handlers.algorithm_handlers as _handlers
    monkeypatch.setattr(_handlers, 'validate_dimension_ids_exist', lambda ids: [])

    servicer = AlgorithmDefinitionServicer()
    servicer.SaveAlgorithmDefinition(_full_payload())
    definition = _load_definition(get_db_session())
    version = definition.updated_at.isoformat()

    resp = servicer.SaveAlgorithmDefinition(
        _full_payload(id=definition.id, expected_updated_at=version)
    )
    assert resp.success is True
    assert resp.code == 'OK'

    resp = servicer.SaveAlgorithmDefinition(
        _full_payload(id=definition.id, expected_updated_at=version)
    )
    assert resp.success is False
    assert resp.code == 'CONFLICT'
    assert '刷新' in resp.message


def test_rpc_save_definition_validation_failed_code(db, clean_tables, monkeypatch):
    """SaveAlgorithmDefinition RPC：校验失败返回 code=VALIDATION_FAILED。"""
    from algorithm_service.interfaces.grpc.servicers import AlgorithmDefinitionServicer
    import algorithm_service.application.handlers.algorithm_handlers as _handlers
    monkeypatch.setattr(_handlers, 'validate_dimension_ids_exist', lambda ids: [999])

    servicer = AlgorithmDefinitionServicer()
    resp = servicer.SaveAlgorithmDefinition(_full_payload())

    assert resp.success is False
    assert resp.code == 'VALIDATION_FAILED'


def test_rpc_draft_save_and_get(db, clean_tables):
    """SaveAlgorithmDefinitionDraft / GetAlgorithmDefinitionDraft RPC 往返。"""
    from algorithm_service.interfaces.grpc.servicers import AlgorithmDefinitionServicer

    servicer = AlgorithmDefinitionServicer()
    payload = _full_payload()
    resp = servicer.SaveAlgorithmDefinitionDraft(payload)
    assert resp.success is True
    # INT-683：草稿保存响应 data 含 saved_at（ISO 时间戳）
    data = __import__('json').loads(resp.data)
    assert data['saved'] is True
    assert data['algorithm_type'] == 'voice_llm'
    assert 'saved_at' in data
    assert 'T' in data['saved_at'], 'saved_at 应为 ISO 时间戳'

    get_resp = servicer.GetAlgorithmDefinitionDraft({'algorithm_type': 'voice_llm'})
    assert get_resp.success is True
    data = __import__('json').loads(get_resp.data)
    assert data['algorithm_type'] == 'voice_llm'
    assert data['name'] == '语音大模型'
