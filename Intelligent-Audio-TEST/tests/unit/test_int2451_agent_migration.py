# -*- coding: utf-8 -*-
"""INT-2451 迁移 / 模型注册静态守卫。

- 七张表的建表 DDL 与 ORM 元数据逐列对齐（列名 / 类型 / 可空性 / DEFAULT）；
- 索引与唯一约束名和唯一性与 ORM 一致；
- 引导链包含本步且排在 INT-1741 ANALYZE 之前；
- create_all 模型全集登记（新增服务漏导即红）。
"""
import importlib.util
import os
import re

import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = 'scripts/migrations/202611/add_agent_runtime_tables.py'
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
_CREATE_ALL = os.path.join(PROJECT_ROOT, 'scripts', 'create_all_tables.py')
_TABLES = (
    'agent_session', 'agent_run', 'agent_run_event', 'agent_step',
    'agent_tool_call', 'agent_artifact', 'agent_context_snapshot',
)
_TYPE_ALIASES = {'DATETIME': 'TIMESTAMP'}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION)
    return _load(_MIGRATION, 'int2451_agent_migration')


@pytest.fixture(scope='module')
def metadata():
    from agent_service.infrastructure.persistence import models  # noqa: F401
    from shared.models.database import Base
    return Base.metadata


def _ddl_columns(sql):
    body = sql[sql.index('(') + 1:sql.rindex(')')]
    columns = {}
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.upper().startswith(
                ('CONSTRAINT', 'PRIMARY KEY', 'UNIQUE')):
            continue
        match = re.match(r'^(?:"([a-z_][a-z0-9_]*)"|([a-z_][a-z0-9_]*))\s+(.+?),?$',
                         stripped)
        assert match, f'无法解析的 DDL 行: {raw!r}'
        columns[match.group(1) or match.group(2)] = match.group(3).rstrip(',')
    return columns


def _norm_type(name):
    base = name.upper()
    return _TYPE_ALIASES.get(base, base)


def test_migration_covers_exactly_the_seven_tables(migration, metadata):
    declared = [table for table, _sql in migration.CREATE_TABLES]
    assert declared == list(_TABLES)
    for table in _TABLES:
        assert table in metadata.tables


def test_ddl_columns_match_orm(migration, metadata):
    for table, sql in migration.CREATE_TABLES:
        orm_table = metadata.tables[table]
        columns = _ddl_columns(sql)
        assert set(columns) == {c.name for c in orm_table.columns}, table
        for column in orm_table.columns:
            ddl = columns[column.name]
            ddl_type = _norm_type(re.match(r'^([A-Za-z]+(?:\(\d+\))?)', ddl).group(1))
            orm_type = _norm_type(str(column.type))
            assert ddl_type == orm_type, f'{table}.{column.name} 类型不一致'
            ddl_not_null = 'NOT NULL' in ddl or 'PRIMARY KEY' in ddl
            assert ddl_not_null == (not column.nullable), (
                f'{table}.{column.name} 可空性与 ORM 不一致')
            assert ('DEFAULT' in ddl) == (column.server_default is not None), (
                f'{table}.{column.name} DEFAULT 与 ORM 不一致')


def test_indexes_match_orm(migration, metadata):
    for table, _sql in migration.CREATE_TABLES:
        orm_indexes = {(i.name, i.unique) for i in metadata.tables[table].indexes}
        ddl_indexes = {(name, unique) for name, ddl_table, _cols, unique
                       in migration.INDEXES if ddl_table == table}
        assert ddl_indexes == orm_indexes, f'{table} 索引不一致'


def test_unique_constraints_match_orm(migration, metadata):
    from sqlalchemy import UniqueConstraint
    for table, _sql in migration.CREATE_TABLES:
        orm_uq = {(c.name, tuple(col.name for col in c.columns))
                  for c in metadata.tables[table].constraints
                  if isinstance(c, UniqueConstraint)}
        ddl_uq = {(name, tuple(col.strip().strip('"') for col in cols.split(',')))
                  for name, ddl_table, cols in migration.UNIQUE_CONSTRAINTS
                  if ddl_table == table}
        assert ddl_uq == orm_uq, f'{table} 唯一约束不一致'


def test_migration_is_idempotent(migration):
    for table, sql in migration.CREATE_TABLES:
        assert f'CREATE TABLE IF NOT EXISTS {table}' in sql
    for name, table, cols, unique in migration.INDEXES:
        sql = migration._index_sql(name, table, cols, unique)
        assert 'IF NOT EXISTS' in sql
        assert ('UNIQUE INDEX' in sql) == unique
    text = open(_MIGRATION, encoding='utf-8').read()
    assert '_constraint_exists' in text

    parser = __import__('argparse')
    assert "add_argument('--dry-run'" in text
    assert "add_argument('--apply'" in text


def test_bootstrap_contains_step_before_analyze(migration):
    module = _load(_BOOTSTRAP, 'int2451_bootstrap')
    steps = [list(step) for step in module.BOOTSTRAP_STEPS]
    scripts = [step[1] for step in steps]
    assert _MIGRATION_REL in scripts
    assert scripts.index(_MIGRATION_REL) < scripts.index(
        'scripts/migrations/202610/analyze_stale_statistics_int1741.py')
    assert _MIGRATION_REL in module.PROD_DDL_SCRIPTS


def test_create_all_registers_agent_models(metadata):
    text = open(_CREATE_ALL, encoding='utf-8').read()
    assert 'agent_service.infrastructure.persistence.models' in text
    for table in _TABLES:
        assert table in metadata.tables
