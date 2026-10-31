# -*- coding: utf-8 -*-
"""INT-2266 回归测试：算法定义「整份保存」不得软删/改写设备级参数与映射行。

缺陷（INT-2224 走查 P0-1）：`_algorithm_full_save` 的子实体 upsert 只按
`api_id IS NULL` 圈定「算法级」作用域，未排除 `device_id IS NOT NULL` 的
设备级行：

- `_upsert_device_api_params`：`AlgorithmDeviceParam` 没有 `api_id` 列，
  `hasattr(po_cls, 'api_id')` 为假 → 查询把设备级行一并纳入 `all_rows`，
  尾部「提交集外软删」把未提交的设备级行软删；
- `_upsert_mappings`：只过滤 `api_id=None`，`device_id` 非空的设备级映射
  同样被纳入提交集比较与软删；
- 自然键 `(param_code, direction)` / `(source, source_param, dimension_id)`
  不含作用域，算法级与设备级同键时后写覆盖前写。

契约：设备级行的读写在独立路径（`_mapping_relation_repositories` 的
create/update、`AlgorithmParamRepository`），算法定义整份保存只管理
`api_id IS NULL AND device_id IS NULL` 的算法级行。

本文件两条 fixture 分别覆盖「同键」与「不同键」：
1. 不同键：设备级行不在提交集内 → 修复前被软删；
2. 同键：设备级行与算法级同自然键 → 修复前被改写（算法级行反而不更新）。
"""
import os

import pytest
from sqlalchemy import BigInteger, text
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (  # noqa: E402
    init_db, get_db_session, get_engine, remove_db_session,
)


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


_ALL_TABLES = (
    'AlgorithmGroup', 'AlgorithmDefinition', 'AlgorithmDeviceParam',
    'AlgorithmApiParam', 'CaseAlgorithmParam', 'AlgorithmReferenceParam',
    'ParamMapping', 'AlgorithmDimensionRelation', 'AlgorithmDefinitionDraft',
)

# 清表顺序：子表先于父表（PG 上 FK 生效，按 _ALL_TABLES 顺序删会撞
# algorithm_*_params / param_mappings 指向 algorithm_definitions 的外键）。
_DELETE_ORDER = (
    'AlgorithmDeviceParam', 'AlgorithmApiParam', 'CaseAlgorithmParam',
    'AlgorithmReferenceParam', 'ParamMapping', 'AlgorithmDimensionRelation',
    'AlgorithmDefinitionDraft', 'AlgorithmDefinition', 'AlgorithmGroup',
)

_ALGO = 'voice_llm'
_DEVICE_ID = 7


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建算法相关全部表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-2266 需要文件型 sqlite，实际绑定 {engine.url}'
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
    # SQLite 会丢掉 `postgresql_where` 谓词，把「作用域内唯一」的两条 PG 部分索引
    # 渲染成整列唯一：算法级行与设备级行同自然键时连播种都插不进去，与生产语义
    # 不符。这里去掉这两条 SQLite 特有的整列唯一索引，还原 PG「按作用域唯一」。
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX IF EXISTS uq_algorithm_device_param_algo_level'))
        conn.execute(text('DROP INDEX IF EXISTS uq_param_mapping_algo_level'))
    yield
    remove_db_session()


@pytest.fixture()
def clean_tables(db):
    """每用例清空算法相关表（teardown 保证隔离库不留残留 + 身份映射复位）。"""
    from algorithm_service.infrastructure.persistence import models as _models
    yield
    session = get_db_session()
    for name in _DELETE_ORDER:
        session.query(getattr(_models, name)).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()


@pytest.fixture(autouse=True)
def _mock_dimension_validation(monkeypatch):
    """单测环境无 evaluation_service gRPC 对端，维度存在性校验视为全部存在。"""
    import algorithm_service.application.handlers.algorithm_handlers as _handlers
    monkeypatch.setattr(_handlers, 'validate_dimension_ids_exist', lambda ids: [])


# ========== 载荷与调用辅助 ==========

def _payload(**overrides):
    """完整定义 payload：1 条设备参数 + 1 条映射（均可被用例覆盖）。"""
    payload = {
        'algorithm_type': _ALGO,
        'name': '语音大模型',
        'description': 'INT-2266 设备级作用域回归',
        'status': 'online',
        'display_order': 1,
        'device_params': [
            {'param_code': 'ch', 'param_name': '声道', 'direction': 'input',
             'param_type': 'text', 'default_value': '1'},
        ],
        'api_params': [
            {'param_code': 'api_key', 'param_name': 'API密钥', 'direction': 'input',
             'param_type': 'text'},
        ],
        'case_params': [],
        'reference_params': [],
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


def _save(payload):
    """经真实 command handler 执行整份保存。"""
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


def _current_version(session):
    """取定义当前 updated_at（乐观锁版本）。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    po = session.query(AlgorithmDefinitionPO).filter_by(
        type=_ALGO, deleted=False
    ).first()
    session.expunge_all()
    return po.id, po.updated_at.isoformat()


def _seed_device_level_rows(session):
    """播种设备级作用域行（模拟设备参数抽屉 / 设备映射表的独立写路径）。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
        ParamMapping as ParamMappingPO,
    )
    session.add(AlgorithmDeviceParamPO(
        algorithm_type=_ALGO, device_id=_DEVICE_ID, param_code='ch',
        param_name='设备声道', direction='input', param_type='text',
        default_value='6', deleted=False,
    ))
    session.add(ParamMappingPO(
        algorithm_type=_ALGO, device_id=_DEVICE_ID, source='device',
        source_param='ch', dimension_id=1, target_param='device_channels',
        transform_type='none', deleted=False,
    ))
    session.commit()
    session.expunge_all()


def _device_param_rows(session):
    """取算法内的设备级参数行（device_id 非空）。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    rows = session.query(AlgorithmDeviceParamPO).filter(
        AlgorithmDeviceParamPO.algorithm_type == _ALGO,
        AlgorithmDeviceParamPO.device_id.isnot(None),
    ).all()
    session.expunge_all()
    return rows


def _algorithm_param_rows(session):
    """取算法级参数行（device_id IS NULL）。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    )
    rows = session.query(AlgorithmDeviceParamPO).filter(
        AlgorithmDeviceParamPO.algorithm_type == _ALGO,
        AlgorithmDeviceParamPO.device_id.is_(None),
    ).all()
    session.expunge_all()
    return rows


def _device_mapping_rows(session):
    """取算法内的设备级映射行（device_id 非空）。"""
    from algorithm_service.infrastructure.persistence.models import (
        ParamMapping as ParamMappingPO,
    )
    rows = session.query(ParamMappingPO).filter(
        ParamMappingPO.algorithm_type == _ALGO,
        ParamMappingPO.device_id.isnot(None),
    ).all()
    session.expunge_all()
    return rows


def _algorithm_mapping_rows(session):
    """取算法级映射行（device_id IS NULL）。"""
    from algorithm_service.infrastructure.persistence.models import (
        ParamMapping as ParamMappingPO,
    )
    rows = session.query(ParamMappingPO).filter(
        ParamMappingPO.algorithm_type == _ALGO,
        ParamMappingPO.device_id.is_(None),
    ).all()
    session.expunge_all()
    return rows


# ========== 1. 不同键：设备级行不在提交集内，不得被「提交集外软删」 ==========

def test_full_save_does_not_soft_delete_device_level_rows(db, clean_tables):
    """算法级改键（ch → ch2）时，设备级同表行必须保持活跃且字段不变。"""
    session = get_db_session()
    assert _save(_payload())['code'] == 'SAVED'
    definition_id, version = _current_version(session)
    _seed_device_level_rows(session)

    result = _save(_payload(
        id=definition_id,
        expected_updated_at=version,
        device_params=[
            {'param_code': 'ch2', 'param_name': '新声道', 'direction': 'input',
             'param_type': 'text'},
        ],
        mappings=[
            {'source': 'device', 'source_param': 'ch2', 'dimension_id': 1,
             'target_param': 'channels2', 'transform_type': 'none'},
        ],
    ))
    assert result['code'] == 'OK'

    # 设备级行：不在提交集内，但属于另一作用域 → 不得被软删，字段不得改写
    dev_params = _device_param_rows(session)
    assert len(dev_params) == 1
    assert dev_params[0].deleted is False
    assert dev_params[0].param_code == 'ch'
    assert dev_params[0].param_name == '设备声道'
    assert dev_params[0].default_value == '6'

    dev_mappings = _device_mapping_rows(session)
    assert len(dev_mappings) == 1
    assert dev_mappings[0].deleted is False
    assert dev_mappings[0].source_param == 'ch'
    assert dev_mappings[0].target_param == 'device_channels'

    # 算法级行照常整份替换：旧键软删、新键活跃
    algo_params = {r.param_code: r for r in _algorithm_param_rows(session)}
    assert algo_params['ch'].deleted is True
    assert algo_params['ch2'].deleted is False
    active_mappings = [r for r in _algorithm_mapping_rows(session) if not r.deleted]
    assert len(active_mappings) == 1
    assert active_mappings[0].source_param == 'ch2'


# ========== 2. 同键：不得覆盖设备级行，算法级行要正常更新 ==========

def test_full_save_same_natural_key_updates_only_algorithm_level_rows(db, clean_tables):
    """设备级与算法级同自然键时，提交值只落到算法级行，设备级行原样保留。"""
    session = get_db_session()
    assert _save(_payload())['code'] == 'SAVED'
    definition_id, version = _current_version(session)
    _seed_device_level_rows(session)

    result = _save(_payload(
        id=definition_id,
        expected_updated_at=version,
        device_params=[
            {'param_code': 'ch', 'param_name': '算法声道', 'direction': 'input',
             'param_type': 'text', 'default_value': '2'},
        ],
        mappings=[
            {'source': 'device', 'source_param': 'ch', 'dimension_id': 1,
             'target_param': 'algo_channels', 'transform_type': 'none'},
        ],
    ))
    assert result['code'] == 'OK'

    # 设备级行：未被提交值改写
    dev_params = _device_param_rows(session)
    assert len(dev_params) == 1
    assert dev_params[0].param_name == '设备声道'
    assert dev_params[0].default_value == '6'
    assert dev_params[0].deleted is False

    dev_mappings = _device_mapping_rows(session)
    assert len(dev_mappings) == 1
    assert dev_mappings[0].target_param == 'device_channels'
    assert dev_mappings[0].deleted is False

    # 算法级行：同键提交正确落库（证明没被设备级行的同键坍缩挤掉）
    algo_params = [r for r in _algorithm_param_rows(session) if not r.deleted]
    assert len(algo_params) == 1
    assert algo_params[0].param_name == '算法声道'
    assert algo_params[0].default_value == '2'

    algo_mappings = [r for r in _algorithm_mapping_rows(session) if not r.deleted]
    assert len(algo_mappings) == 1
    assert algo_mappings[0].target_param == 'algo_channels'
