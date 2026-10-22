# -*- coding: utf-8 -*-
"""INT-1382 验收测试：删除算法级联软删其设备/API/用例/参考参数、映射、维度关联。

缺陷背景（INT-1264 CRUD 走查发现，真实库 intelligent_audio_test）：
`DELETE /api/v1/algorithm/definitions/{type}` 只软删 `algorithm_definitions`
根行（deleted=True），其 `algorithm_device_params` / `algorithm_api_params`
子行未级联软删，仍可从 `GET /api/v1/algorithm/params` 查到且 hidden=False，
形成孤儿参数污染列表、测试数据需手动清理。

修复（本卡，algorithm_service 仓储侧）：`AlgorithmDefinitionRepository.soft_delete`
与 `AlgorithmDefinitionQueryRepository.bulk_soft_delete` 同事务级联置六类子表
deleted=True —— 设备/API/用例/参考参数、参数映射、维度关联，均按 algorithm_type
关联。

回归测试走文件型 SQLite 隔离库（init_db + create_all 指定表），不动共享库。
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
    'ParamMapping', 'AlgorithmDimensionRelation',
)


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建算法相关全部表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-1382 级联删除测试需要文件型 sqlite，实际绑定 {engine.url}'
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
    )
    tables = [
        AlgorithmGroupPO.__table__, AlgorithmDefinitionPO.__table__,
        AlgorithmDeviceParamPO.__table__, AlgorithmApiParamPO.__table__,
        CaseAlgorithmParamPO.__table__, AlgorithmReferenceParamPO.__table__,
        ParamMappingPO.__table__, AlgorithmDimensionRelationPO.__table__,
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


def _seed_algorithm(session, algo_type, name):
    """播种一个算法定义 + 六类子实体，返回定义 id。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
        AlgorithmDeviceParam as AlgorithmDeviceParamPO,
        AlgorithmApiParam as AlgorithmApiParamPO,
        CaseAlgorithmParam as CaseAlgorithmParamPO,
        AlgorithmReferenceParam as AlgorithmReferenceParamPO,
        ParamMapping as ParamMappingPO,
        AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
    )
    definition = AlgorithmDefinitionPO(
        type=algo_type, name=name, status='online', deleted=False)
    session.add(definition)
    session.flush()
    session.add_all([
        AlgorithmDeviceParamPO(
            algorithm_type=algo_type, param_code='dev_p', param_name='设备参数',
            param_type='text', deleted=False),
        AlgorithmApiParamPO(
            algorithm_type=algo_type, param_code='api_p', param_name='API参数',
            param_type='text', deleted=False),
        CaseAlgorithmParamPO(
            algorithm_type=algo_type, param_code='case_p', param_name='用例参数',
            param_type='text', deleted=False),
        AlgorithmReferenceParamPO(
            algorithm_type=algo_type, code='ref_p', name='参考参数',
            param_type='text', deleted=False),
        ParamMappingPO(
            algorithm_type=algo_type, source='api', source_param='api_p',
            target_param='out_p', deleted=False),
        AlgorithmDimensionRelationPO(
            algorithm_type=algo_type, dimension_id=1, deleted=False),
    ])
    session.commit()
    return definition.id


def _all_child_counts(session, algo_type):
    """统计某算法各子表 deleted=False 行数（dict）。"""
    from algorithm_service.infrastructure.persistence import models as _m
    return {
        'device': session.query(_m.AlgorithmDeviceParam).filter_by(
            algorithm_type=algo_type, deleted=False).count(),
        'api': session.query(_m.AlgorithmApiParam).filter_by(
            algorithm_type=algo_type, deleted=False).count(),
        'case': session.query(_m.CaseAlgorithmParam).filter_by(
            algorithm_type=algo_type, deleted=False).count(),
        'reference': session.query(_m.AlgorithmReferenceParam).filter_by(
            algorithm_type=algo_type, deleted=False).count(),
        'mapping': session.query(_m.ParamMapping).filter_by(
            algorithm_type=algo_type, deleted=False).count(),
        'relation': session.query(_m.AlgorithmDimensionRelation).filter_by(
            algorithm_type=algo_type, deleted=False).count(),
    }


def _definition_deleted(session, algo_type):
    """读取算法定义根行 deleted 标记。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    po = session.query(AlgorithmDefinitionPO).filter_by(type=algo_type).first()
    return po.deleted


# ==================== 1. 单删：级联软删六类子实体 ====================

def test_single_delete_cascades_all_children(db, clean_tables):
    """删除算法定义 → 设备/API/用例/参考参数、映射、维度关联全部级联软删。"""
    session = get_db_session()
    algo_type = 'int1382_single'
    definition_id = _seed_algorithm(session, algo_type, '单删级联测试')

    from algorithm_service.infrastructure.persistence._algorithm_aggregate_repositories import (
        AlgorithmDefinitionRepository,
    )
    ok = AlgorithmDefinitionRepository().soft_delete(definition_id)

    assert ok is True
    assert _definition_deleted(session, algo_type) is True
    assert _all_child_counts(session, algo_type) == {
        'device': 0, 'api': 0, 'case': 0, 'reference': 0,
        'mapping': 0, 'relation': 0,
    }, '算法删除后其全部子实体必须级联软删（原缺陷形态：仍可从列表查到）'


def test_single_delete_keeps_other_algorithms_children(db, clean_tables):
    """删除算法 A 不影响算法 B 的子实体（级联仅限被删算法的 algorithm_type）。"""
    session = get_db_session()
    _seed_algorithm(session, 'int1382_del_a', '被删算法')
    _seed_algorithm(session, 'int1382_keep_b', '保留算法')

    from algorithm_service.infrastructure.persistence._algorithm_aggregate_repositories import (
        AlgorithmDefinitionRepository,
    )
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    a = session.query(AlgorithmDefinitionPO).filter_by(
        type='int1382_del_a').first()
    AlgorithmDefinitionRepository().soft_delete(a.id)

    assert _all_child_counts(session, 'int1382_del_a')['device'] == 0
    assert _all_child_counts(session, 'int1382_keep_b') == {
        'device': 1, 'api': 1, 'case': 1, 'reference': 1,
        'mapping': 1, 'relation': 1,
    }, '未删除算法的子实体不得被连带软删'


def test_params_list_no_orphan_after_delete(db, clean_tables):
    """症状级回归：删除算法后 /algorithm/params 的查询路径不再返回孤儿参数。"""
    session = get_db_session()
    algo_type = 'int1382_symptom'
    _seed_algorithm(session, algo_type, '症状回归')

    from algorithm_service.infrastructure.persistence._algorithm_aggregate_repositories import (
        AlgorithmDefinitionRepository,
    )
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
    )
    definition = session.query(AlgorithmDefinitionPO).filter_by(
        type=algo_type).first()
    AlgorithmDefinitionRepository().soft_delete(definition.id)

    from algorithm_service.infrastructure.persistence._algorithm_param_repository import (
        AlgorithmParamRepository,
    )
    repo = AlgorithmParamRepository()
    assert repo.list_by_algorithm(algo_type, 'device') == [], (
        '删除后设备参数不得残留于列表（原缺陷：GET /algorithm/params 仍返回）'
    )
    assert repo.list_by_algorithm(algo_type, 'api') == []
    # 全量列表（不按 algorithm_type 过滤）同样不得返回已删算法的孤儿参数
    assert all(p['algorithm_type'] != algo_type
               for p in repo.list_by_algorithm('', 'device'))
    assert all(p['algorithm_type'] != algo_type
               for p in repo.list_by_algorithm('', 'api'))


# ==================== 2. 批量删除：同样级联软删 ====================

def test_bulk_delete_cascades_children(db, clean_tables):
    """批量软删多个算法 → 各自子实体全部级联软删。"""
    session = get_db_session()
    for t in ('int1382_bulk_a', 'int1382_bulk_b'):
        _seed_algorithm(session, t, f'批量删除{t}')

    from algorithm_service.infrastructure.persistence._algorithm_query_repositories import (
        AlgorithmDefinitionQueryRepository,
    )
    deleted = AlgorithmDefinitionQueryRepository().bulk_soft_delete(
        ['int1382_bulk_a', 'int1382_bulk_b'])
    assert sorted(deleted) == ['int1382_bulk_a', 'int1382_bulk_b']

    for t in ('int1382_bulk_a', 'int1382_bulk_b'):
        assert _definition_deleted(session, t) is True
        assert _all_child_counts(session, t) == {
            'device': 0, 'api': 0, 'case': 0, 'reference': 0,
            'mapping': 0, 'relation': 0,
        }, f'批量删除后算法 {t} 的子实体必须级联软删'


def test_bulk_delete_keeps_others_children(db, clean_tables):
    """批量删除只波及目标算法，未在清单中的算法子实体保持不变。"""
    session = get_db_session()
    _seed_algorithm(session, 'int1382_bulk_del', '批量被删')
    _seed_algorithm(session, 'int1382_bulk_keep', '批量保留')

    from algorithm_service.infrastructure.persistence._algorithm_query_repositories import (
        AlgorithmDefinitionQueryRepository,
    )
    AlgorithmDefinitionQueryRepository().bulk_soft_delete(['int1382_bulk_del'])

    assert _all_child_counts(session, 'int1382_bulk_del')['device'] == 0
    assert _all_child_counts(session, 'int1382_bulk_keep')['device'] == 1


# ==================== 3. RPC 全链路：SoftDeleteAlgorithm 级联生效 ====================

def test_soft_delete_algorithm_rpc_cascades(db, clean_tables):
    """经真实 servicer RPC（SoftDeleteAlgorithmRequest）删除 → 级联软删生效。"""
    session = get_db_session()
    algo_type = 'int1382_rpc'
    definition_id = _seed_algorithm(session, algo_type, 'RPC 级联测试')

    from algorithm_service.interfaces.grpc.servicers import AlgorithmDefinitionServicer
    from shared.proto import algorithm_service_pb2 as pb
    resp = AlgorithmDefinitionServicer().SoftDeleteAlgorithm(
        pb.SoftDeleteAlgorithmRequest(algorithm_id=definition_id))
    assert resp.success, f'RPC 删除失败: {resp.message}'

    assert _definition_deleted(session, algo_type) is True
    assert _all_child_counts(session, algo_type) == {
        'device': 0, 'api': 0, 'case': 0, 'reference': 0,
        'mapping': 0, 'relation': 0,
    }, 'SoftDeleteAlgorithm RPC 路径必须级联软删子实体'
