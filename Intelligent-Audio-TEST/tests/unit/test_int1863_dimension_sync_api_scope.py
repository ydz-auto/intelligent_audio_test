# -*- coding: utf-8 -*-
"""INT-1863：评估维度参数同步只管理算法级（api_id IS NULL）映射。

缺陷背景（INT-1863，C6a/INT-1756 遗留）：``param_mappings`` 自 C6a 起带
``api_id`` 作用域（NULL = 算法类型级默认，非空 = API 实例级），但维度同步的
写路径仍按「一张表只有算法级」的旧口径整表操作：

- ``sync_for_dimension`` 的 ``active_mappings`` 只按 ``dimension_id + source``
  查，命中同 ``source_param`` 的 API 级行就直接改写 ``target_param`` /
  ``source_direction``，并把提交集外的 API 级独有行 ``deleted=True``；
- ``list_for_dimension`` 同样把 API 级行当维度级算法映射一并返回。

期望口径（本文件逐条守住）：
1. 默认（``api_id=None``）同步 / 查询只命中 ``api_id IS NULL`` 的算法级行；
   新建行显式落 ``api_id=None``；
2. 同一 ``(source_param, dimension_id)`` 同时存在算法级与 API 级行时，一轮
   同步后 API 级行的 ``target_param`` / ``source_direction`` / ``deleted``
   均不变，算法级行按提交集正常增删；
3. 作用域由调用方显式给定（``api_id`` 形参），不靠「一次查出所有作用域再按
   ``source_param`` 合并」；传值时只动该 API 的行。

回归测试走文件型 SQLite 隔离库（init_db + create_all 指定表），不动共享库。
SQLite 把模型里 ``postgresql_where`` 的部分唯一索引渲染成无条件的唯一索引，
故建表后先删掉它、再按生产口径（INT-1756 迁移 ㊻）重建「算法级 / API 级」
两条部分唯一索引：算法级与 API 级同键行才能在本用例中共存。
"""
import os

import pytest
from sqlalchemy import BigInteger, event, text
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


ALGO = 'translation'
API_A = 11
DIM_TEXT = 101
SRC = 'evaluation'


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 库并建 param_mappings / algorithm_definitions。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'INT-1863 维度同步作用域测试需要文件型 sqlite，实际绑定 {engine.url}'
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
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX IF EXISTS uq_algorithm_source_to_dimension'))
        conn.execute(text(
            'CREATE UNIQUE INDEX uq_param_mapping_algo_level ON param_mappings '
            '(algorithm_type, source, source_param, dimension_id) '
            'WHERE deleted = 0 AND api_id IS NULL'
        ))
        conn.execute(text(
            'CREATE UNIQUE INDEX uq_param_mapping_api_level ON param_mappings '
            '(algorithm_type, api_id, source, source_param, dimension_id) '
            'WHERE deleted = 0 AND api_id IS NOT NULL'
        ))
    yield engine
    remove_db_session()


@pytest.fixture()
def clean_tables(db):
    """每用例前后清空两张表（隔离库不落共享库）。"""
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


def _seed(rows):
    """播种算法定义 + 给定 param_mappings 行。"""
    from algorithm_service.infrastructure.persistence.models import (
        AlgorithmDefinition as AlgorithmDefinitionPO,
        ParamMapping as ParamMappingPO,
    )
    session = get_db_session()
    session.add(AlgorithmDefinitionPO(type=ALGO, name='翻译算法'))
    session.flush()
    for row in rows:
        session.add(ParamMappingPO(**row))
    session.commit()
    session.expunge_all()
    remove_db_session()


def _row(source_param, api_id, target_param, direction='output', deleted=False,
         dimension_id=DIM_TEXT):
    return dict(
        algorithm_type=ALGO, api_id=api_id, source=SRC,
        source_param=source_param, source_direction=direction,
        dimension_id=dimension_id, target_param=target_param,
        transform_type='none', deleted=deleted,
    )


def _dump():
    """id → (api_id, source_param, target_param, source_direction, deleted)。"""
    from algorithm_service.infrastructure.persistence.models import (
        ParamMapping as ParamMappingPO,
    )
    session = get_db_session()
    rows = session.query(ParamMappingPO).order_by(ParamMappingPO.id).all()
    data = {
        r.id: (r.api_id, r.source_param, r.target_param,
               r.source_direction, bool(r.deleted))
        for r in rows
    }
    session.expunge_all()
    remove_db_session()
    return data


# 算法级：q_text（提交集内）、o_legacy（提交集外）
# API A：q_text（与算法级同 source_param，target/direction 不同）、o_api_only（独有）
_BASE_ROWS = [
    _row('q_text', None, 'q_text', direction='input'),
    _row('o_legacy', None, 'o_legacy'),
    _row('q_text', API_A, 'q_text_api_a'),
    _row('o_api_only', API_A, 'o_api_only'),
]


def test_sync_leaves_api_level_rows_untouched(clean_tables):
    """同一 (source_param, dimension_id) 双作用域并存：同步只动算法级行。"""
    from algorithm_service.infrastructure.persistence.algorithm_repository import (
        param_mapping_query_repository,
    )

    _seed(_BASE_ROWS)
    before = _dump()
    assert len(before) == 4

    ok = param_mapping_query_repository.sync_for_dimension(
        DIM_TEXT,
        [{'param_code': 'q_text'}, {'param_code': 'o_new'}],
        direction='input',
    )
    assert ok is True

    after = _dump()
    by_key = {(api_id, src_param): row for row in after.values()
              for api_id, src_param in [(row[0], row[1])]}

    # 1) API 级同键行完全不变：target / direction / deleted 均保持原值
    api_q = by_key[(API_A, 'q_text')]
    assert api_q[2] == 'q_text_api_a', 'API 级同键行被算法级同步改写 target_param'
    assert api_q[3] == 'output', 'API 级同键行被算法级同步改写 source_direction'
    assert api_q[4] is False

    # 2) API 级独有行不被当「提交集外」软删
    api_only = by_key[(API_A, 'o_api_only')]
    assert api_only[4] is False, 'API 级独有行被算法级同步软删'

    # 3) 算法级行按提交集正常增删
    algo_q = by_key[(None, 'q_text')]
    assert algo_q[2] == 'q_text'
    assert algo_q[3] == 'input'
    assert algo_q[4] is False
    assert by_key[(None, 'o_legacy')][4] is True, '算法级提交集外行未软删'
    algo_new = by_key[(None, 'o_new')]
    assert algo_new[3] == 'input'
    assert algo_new[4] is False

    # 4) 没有新增 API 级行（新建行显式 api_id=None）
    api_rows = [r for r in after.values() if r[0] == API_A]
    assert len(api_rows) == 2
    assert len(after) == 5


def test_list_for_dimension_default_is_algorithm_level_only(clean_tables):
    """默认查询只返回算法级行（含软删项），API 级行不混入。"""
    from algorithm_service.infrastructure.persistence.algorithm_repository import (
        param_mapping_query_repository,
    )

    _seed(_BASE_ROWS + [_row('o_gone', None, 'o_gone', deleted=True)])

    default_rows = param_mapping_query_repository.list_for_dimension(DIM_TEXT)
    assert all(r['api_id'] is None for r in default_rows)
    default_params = {r['source_param'] for r in default_rows}
    assert default_params == {'q_text', 'o_legacy', 'o_gone'}
    # 含软删项（本方法口径：不按 deleted 过滤，由调用方判断）
    assert 'o_gone' in default_params

    scoped_rows = param_mapping_query_repository.list_for_dimension(
        DIM_TEXT, api_id=API_A)
    assert {r['api_id'] for r in scoped_rows} == {API_A}
    assert {r['source_param'] for r in scoped_rows} == {'q_text', 'o_api_only'}

    # list_by_dimension 是 ABC 上的同一查询，作用域口径必须一致
    assert [r['id'] for r in param_mapping_query_repository.list_by_dimension(
        DIM_TEXT)] == [r['id'] for r in default_rows]


def test_sync_explicit_api_scope_only_touches_that_api(clean_tables):
    """作用域形参化：传 api_id 只动该 API 的行，算法级行原样保留。"""
    from algorithm_service.infrastructure.persistence.algorithm_repository import (
        param_mapping_query_repository,
    )

    _seed(_BASE_ROWS)

    assert param_mapping_query_repository.sync_for_dimension(
        DIM_TEXT, [{'param_code': 'q_text'}], direction='output',
        api_id=API_A,
    ) is True

    by_key = {(r[0], r[1]): r for r in _dump().values()}

    # API 作用域：提交集内的 q_text 被更新，独有行被软删
    assert by_key[(API_A, 'q_text')][2] == 'q_text'
    assert by_key[(API_A, 'q_text')][4] is False
    assert by_key[(API_A, 'o_api_only')][4] is True

    # 算法级两行原样：q_text 未被改写，o_legacy 未被软删
    assert by_key[(None, 'q_text')][2] == 'q_text'
    assert by_key[(None, 'q_text')][3] == 'input'
    assert by_key[(None, 'o_legacy')][4] is False


def test_sync_select_carries_api_id_is_null_predicate(clean_tables):
    """实际 SQL 证据：同步的 SELECT 带 ``param_mappings.api_id IS NULL``。"""
    from algorithm_service.infrastructure.persistence.algorithm_repository import (
        param_mapping_query_repository,
    )

    _seed([_row('q_text', None, 'q_text', direction='input')])

    captured = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        captured.append(' '.join(statement.split()))

    event.listen(get_engine(), 'before_cursor_execute', _capture)
    try:
        param_mapping_query_repository.sync_for_dimension(
            DIM_TEXT, [{'param_code': 'q_text'}], direction='input')
    finally:
        event.remove(get_engine(), 'before_cursor_execute', _capture)

    selects = [s for s in captured if s.upper().startswith('SELECT')]
    assert selects, f'未捕获到同步查询 SQL：{captured}'
    sync_select = next(s for s in selects if 'param_mappings' in s)
    assert 'api_id IS NULL' in sync_select, sync_select
