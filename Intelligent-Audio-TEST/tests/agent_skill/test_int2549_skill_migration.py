# -*- coding: utf-8 -*-
"""INT-2549 迁移 / 模型注册静态守卫（验收 11）。

- 三张表的建表 DDL 与 ORM 元数据逐列对齐（列名 / 类型 / 可空性 / DEFAULT）；
- 索引名与唯一性与 ORM 一致（含局部唯一索引的作用域谓词）；
- ``(skill_id, version)`` 唯一约束一致；
- 引导链包含本步且排在 ANALYZE 之前，prod 白名单同样登记；
- 正文只存版本表（``agent_skill`` 无 body 列，避免双写）。
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
_MIGRATION_REL = 'scripts/migrations/202611/add_agent_skill_tables.py'
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
_TABLES = ('agent_skill', 'agent_skill_version', 'agent_run_skill')
_TYPE_ALIASES = {'DATETIME': 'TIMESTAMP'}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION)
    return _load(_MIGRATION, 'int2549_agent_skill_migration')


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
        match = re.match(
            r'^(?:"([a-z_][a-z0-9_]*)"|([a-z_][a-z0-9_]*))\s+(.+?),?$',
            stripped)
        assert match, f'无法解析的 DDL 行: {raw!r}'
        columns[match.group(1) or match.group(2)] = match.group(3).rstrip(',')
    return columns


def _norm_type(name):
    base = name.upper()
    return _TYPE_ALIASES.get(base, base)


def test_migration_declares_three_tables(migration, metadata):
    assert [table for table, _sql in migration.CREATE_TABLES] == list(_TABLES)
    for table in _TABLES:
        assert table in metadata.tables


def test_ddl_columns_match_orm(migration, metadata):
    for table, sql in migration.CREATE_TABLES:
        orm_table = metadata.tables[table]
        columns = _ddl_columns(sql)
        assert set(columns) == {c.name for c in orm_table.columns}, table
        for column in orm_table.columns:
            ddl = columns[column.name]
            ddl_type = _norm_type(
                re.match(r'^([A-Za-z]+(?:\(\d+\))?)', ddl).group(1))
            orm_type = _norm_type(str(column.type))
            assert ddl_type == orm_type, f'{table}.{column.name} 类型不一致'
            ddl_not_null = 'NOT NULL' in ddl or 'PRIMARY KEY' in ddl
            assert ddl_not_null == (not column.nullable), (
                f'{table}.{column.name} 可空性与 ORM 不一致')
            assert ('DEFAULT' in ddl) == (column.server_default is not None), (
                f'{table}.{column.name} DEFAULT 与 ORM 不一致')


def test_body_only_in_version_table(migration, metadata):
    columns = _ddl_columns(dict(migration.CREATE_TABLES)['agent_skill'])
    assert 'body' not in columns, '正文只存版本表，agent_skill 不得双写'
    assert 'body' in _ddl_columns(
        dict(migration.CREATE_TABLES)['agent_skill_version'])


def test_indexes_match_orm(migration, metadata):
    for table, _sql in migration.CREATE_TABLES:
        orm_indexes = {(i.name, i.unique)
                       for i in metadata.tables[table].indexes}
        ddl_indexes = {(name, unique) for name, ddl_table, _cols, unique, _where
                       in migration.INDEXES if ddl_table == table}
        assert ddl_indexes == orm_indexes, f'{table} 索引不一致'


def test_partial_unique_index_predicates(migration):
    predicates = {name: where for name, _table, _cols, unique, where
                  in migration.INDEXES if unique}
    assert predicates == {
        'uq_agent_skill_owner_name': "scope = 'USER'",
        'uq_agent_skill_tenant_name': "scope = 'TENANT'",
    }


def test_unique_constraint_matches_orm(migration, metadata):
    from sqlalchemy import UniqueConstraint
    orm_uq = {(c.name, tuple(col.name for col in c.columns))
              for c in metadata.tables['agent_skill_version'].constraints
              if isinstance(c, UniqueConstraint)}
    ddl_uq = {(name, tuple(col.strip() for col in cols.split(',')))
              for name, table, cols in migration.UNIQUE_CONSTRAINTS
              if table == 'agent_skill_version'}
    assert ddl_uq == orm_uq


def test_migration_is_idempotent(migration):
    for table, sql in migration.CREATE_TABLES:
        assert f'CREATE TABLE IF NOT EXISTS {table}' in sql
    text = open(_MIGRATION, encoding='utf-8').read()
    assert 'IF NOT EXISTS' in text
    assert '_constraint_exists' in text
    assert "add_argument('--dry-run'" in text
    assert "add_argument('--apply'" in text


def test_bootstrap_contains_step_before_analyze():
    module = _load(_BOOTSTRAP, 'int2549_bootstrap')
    scripts = [step[1] for step in module.BOOTSTRAP_STEPS]
    assert _MIGRATION_REL in scripts
    assert scripts.index(_MIGRATION_REL) < scripts.index(
        'scripts/migrations/202610/analyze_stale_statistics_int1741.py')
    assert _MIGRATION_REL in module.PROD_DDL_SCRIPTS


def test_rbac_registers_skill_permissions():
    path = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', '202608',
                        'seed_rbac.py')
    text = open(path, encoding='utf-8').read()
    assert "('agent:skill:read'" in text
    assert "('agent:skill:manage'" in text


def test_no_scope_status_magic_strings():
    """验收 10：枚举化 —— 代码与接口里不出现作用域 / 状态魔法字符串。"""
    relative = [
        'agent_service/application/skill_service.py',
        'agent_service/application/skill_guard.py',
        'agent_service/application/skill_registry.py',
        'agent_service/domain/services/skill_visibility.py',
        'agent_service/infrastructure/skill/composite_skill_repository.py',
        'agent_service/infrastructure/persistence/skill_repositories.py',
        'agent_service/infrastructure/persistence/models/agent_models.py',
        'agent_service/interfaces/api/routes.py',
    ]
    forbidden = ("'PLATFORM'", "'TENANT'", "'USER'", "'DRAFT'", "'ACTIVE'",
                 "'DISABLED'", '"PLATFORM"', '"TENANT"', '"USER"',
                 '"DRAFT"', '"ACTIVE"', '"DISABLED"')
    for rel in relative:
        text = open(os.path.join(PROJECT_ROOT, *rel.split('/')),
                    encoding='utf-8').read()
        hits = [token for token in forbidden if token in text]
        assert not hits, f'{rel} 出现魔法字符串：{hits}'

