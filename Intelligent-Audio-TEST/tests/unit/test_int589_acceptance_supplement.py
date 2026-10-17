# -*- coding: utf-8 -*-
"""INT-589 验收补充测试：更新路径根持久化 / 全量替换软删 / 并发 CAS 冲突。

开发提测自带 tests/unit/test_int589_algorithm_full_save.py（14 例）已覆盖
创建落库、中途失败回滚、幂等重放、软删自然键复活、草稿、RPC code 分支。
本文件补三处验收盲区：

1. 更新路径成功时根定义字段实际变更 + updated_at 版本推进（OK 码）；
2. 全量替换语义：提交集外的既有活跃子实体行被软删（不残留重复活跃行）；
3. 真实并发双写（两线程同版本 CAS）：恰一个 OK、一个 CONFLICT。

测试走文件型 SQLite 隔离库（init_db + create_all 指定表），不动共享库。
"""
import os
import sys
import threading

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
        f'INT-589 补充事务测试需要文件型 sqlite，实际绑定 {engine.url}'
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
    """默认 mock 关联维度存在性校验为「全部存在」。"""
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


def _handle_save(payload):
    """经真实 handler 执行全量保存（维度校验 mock 见 autouse 夹具）。"""
    from algorithm_service.application.commands.algorithm_commands import (
        SaveAlgorithmDefinitionCommand,
    )
    from algorithm_service.application.handlers.algorithm_handlers import (
        AlgorithmCommandHandler,
    )
    cmd = SaveAlgorithmDefinitionCommand(
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
    )
    return AlgorithmCommandHandler().handle_save_definition(cmd)


def _load_definition(session, algorithm_type='voice_llm'):
    """按 type 加载未删除定义 PO。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    return session.query(AlgorithmDefinitionPO).filter_by(
        type=algorithm_type, deleted=False
    ).first()


# ==================== 盲区 1：更新路径成功时根持久化 + 版本推进 ====================

def test_update_success_persists_root_and_advances_version(db, clean_tables, monkeypatch):
    """更新路径：根定义字段实际变更 + updated_at 版本推进，返回 OK。"""
    session = get_db_session()
    result = _handle_save(_full_payload())
    assert result['code'] == 'SAVED'
    definition = _load_definition(session)
    version_v1 = definition.updated_at.isoformat()

    # 更新：改 name/description/display_order + 换 device 参数
    result2 = _handle_save(_full_payload(
        id=definition.id,
        expected_updated_at=version_v1,
        name='语音大模型V2',
        description='更新后的描述',
        display_order=5,
        device_params=[
            {'param_code': 'ch2', 'param_name': '新声道', 'direction': 'input',
             'param_type': 'text', 'required': False},
        ],
    ))
    assert result2['code'] == 'OK'
    assert result2['id'] == definition.id

    # 根定义字段已更新，版本已推进
    definition = _load_definition(session)
    assert definition.name == '语音大模型V2'
    assert definition.description == '更新后的描述'
    assert definition.display_order == 5
    assert definition.updated_at.isoformat() != version_v1
    # 新 device 子实体落库（旧 ch 行被全量替换软删，见下一用例）
    assert _count(session, 'AlgorithmDeviceParam') == 2  # ch 软删 + ch2 活跃


# ==================== 盲区 2：全量替换语义（提交集外软删） ====================

def test_full_replace_soft_deletes_omitted_sub_entities(db, clean_tables, monkeypatch):
    """全量替换：提交集外的既有活跃子实体行被软删，不残留重复活跃行。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    session = get_db_session()
    result = _handle_save(_full_payload())
    definition = _load_definition(session)
    version = definition.updated_at.isoformat()

    # 提交集只含新 device ch2，旧 ch 不在提交集 → 软删
    _handle_save(_full_payload(
        id=definition.id,
        expected_updated_at=version,
        device_params=[
            {'param_code': 'ch2', 'param_name': '新声道', 'direction': 'input',
             'param_type': 'text'},
        ],
    ))

    # 旧 ch 行软删、新 ch2 活跃，且各自只有一条（无重复活跃行）
    assert _count(session, 'AlgorithmDeviceParam') == 2
    old = session.query(AlgorithmDeviceParamPO).filter_by(
        algorithm_type='voice_llm', param_code='ch'
    ).first()
    new = session.query(AlgorithmDeviceParamPO).filter_by(
        algorithm_type='voice_llm', param_code='ch2'
    ).first()
    assert old is not None and old.deleted is True
    assert new is not None and new.deleted is False


def test_natural_key_update_in_place_no_duplicate(db, clean_tables, monkeypatch):
    """自然键 find-or-upsert：同键再提交只更新字段，不产生重复行。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    session = get_db_session()
    _handle_save(_full_payload())
    definition = _load_definition(session)
    version = definition.updated_at.isoformat()

    # 同自然键 (ch, input) 再次提交，param_name/required 变更
    _handle_save(_full_payload(
        id=definition.id,
        expected_updated_at=version,
        device_params=[
            {'param_code': 'ch', 'param_name': '声道改名', 'direction': 'input',
             'param_type': 'text', 'required': False},
        ],
    ))

    rows = session.query(AlgorithmDeviceParamPO).filter_by(
        algorithm_type='voice_llm', deleted=False
    ).all()
    assert len(rows) == 1
    assert rows[0].param_code == 'ch'
    assert rows[0].param_name == '声道改名'
    assert rows[0].required is False


# ==================== 盲区 3：真实并发双写（两线程同版本 CAS） ====================

def test_concurrent_double_write_one_ok_one_conflict(db, clean_tables, monkeypatch):
    """两个线程持同一 version 并发提交：恰一个 OK、一个 CONFLICT。"""
    session = get_db_session()
    result = _handle_save(_full_payload())
    assert result['code'] == 'SAVED'
    definition = _load_definition(session)
    version = definition.updated_at.isoformat()
    remove_db_session()

    results = []
    errors = []

    def _thread_save(name_new: str):
        try:
            r = _handle_save(_full_payload(
                id=definition.id,
                expected_updated_at=version,
                name=name_new,
                device_params=[{'param_code': 't', 'param_name': name_new,
                                'direction': 'input', 'param_type': 'text'}],
            ))
            results.append(r['code'])
        except Exception as e:  # noqa: BLE001
            errors.append(f'{name_new}: {e}')
        finally:
            remove_db_session()

    t1 = threading.Thread(target=_thread_save, args=('并发A',))
    t2 = threading.Thread(target=_thread_save, args=('并发B',))
    t1.start(); t2.start()
    t1.join(timeout=30); t2.join(timeout=30)

    assert not errors, f'并发提交出现异常: {errors}'
    # 恰一个 OK、一个 CONFLICT（线程时序不定，只断言结果集合）
    assert sorted(results) == ['CONFLICT', 'OK'], f'并发结果异常: {results}'

    # 冲突方不做任何写：活跃 device 行只保留胜利者一条（t-param；
    # 原创建时的 ch 行被全量替换软删，故总行数 2、活跃行 1）
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    session = get_db_session()
    assert _count(session, 'AlgorithmDefinition') == 1
    assert _count(session, 'AlgorithmDeviceParam') == 2
    active = session.query(AlgorithmDeviceParamPO).filter_by(
        algorithm_type='voice_llm', deleted=False
    ).all()
    assert len(active) == 1
    assert active[0].param_code == 't'
    remove_db_session()
