# -*- coding: utf-8 -*-
"""INT-2488 agent_llm_provider 迁移 / 模型注册守卫。"""
import importlib.util
import os
import re

import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = 'scripts/migrations/202611/add_agent_llm_provider_table.py'
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
_CREATE_ALL = os.path.join(PROJECT_ROOT, 'scripts', 'create_all_tables.py')
_README = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', 'README.md')
_TABLE = 'agent_llm_provider'
_TYPE_ALIASES = {'DATETIME': 'TIMESTAMP'}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION), _MIGRATION
    return _load(_MIGRATION, 'int2488_agent_provider_migration')


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


def test_table_registered_in_metadata(metadata):
    assert _TABLE in metadata.tables


def test_ddl_columns_match_orm(migration, metadata):
    assert [table for table, _sql in migration.CREATE_TABLES] == [_TABLE]
    orm_table = metadata.tables[_TABLE]
    columns = _ddl_columns(dict(migration.CREATE_TABLES)[_TABLE])
    assert set(columns) == {c.name for c in orm_table.columns}
    for column in orm_table.columns:
        ddl = columns[column.name]
        ddl_type = _norm_type(re.match(r'^([A-Za-z]+(?:\(\d+\))?)', ddl).group(1))
        assert ddl_type == _norm_type(str(column.type)), column.name
        ddl_not_null = 'NOT NULL' in ddl or 'PRIMARY KEY' in ddl
        assert ddl_not_null == (not column.nullable), column.name
        assert ('DEFAULT' in ddl) == (column.server_default is not None), \
            column.name


def test_indexes_match_orm(migration, metadata):
    orm_indexes = {(i.name, i.unique)
                   for i in metadata.tables[_TABLE].indexes}
    ddl_indexes = {(name, unique) for name, table, _cols, unique
                   in migration.INDEXES if table == _TABLE}
    ddl_indexes |= {(name, True) for name, table, _cols, _where
                    in migration.PARTIAL_UNIQUE_INDEXES if table == _TABLE}
    assert ddl_indexes == orm_indexes


def test_required_indexes_present(migration):
    names = {name for name, _t, _c, _u in migration.INDEXES}
    assert 'ix_agent_llm_provider_owner_default' in names
    assert 'ix_agent_llm_provider_owner_status' in names
    assert any(name == 'uq_agent_llm_provider_default'
               for name, _t, _c, _w in migration.PARTIAL_UNIQUE_INDEXES)


def test_migration_is_idempotent(migration):
    for table, sql in migration.CREATE_TABLES:
        assert f'CREATE TABLE IF NOT EXISTS {table}' in sql
    text = open(_MIGRATION, encoding='utf-8').read()
    assert "add_argument('--dry-run'" in text
    assert "add_argument('--apply'" in text


def test_bootstrap_step_before_analyze(migration):
    module = _load(_BOOTSTRAP, 'int2488_bootstrap')
    steps = [list(step) for step in module.BOOTSTRAP_STEPS]
    scripts = [step[1] for step in steps]
    assert _MIGRATION_REL in scripts
    assert scripts.index(_MIGRATION_REL) < scripts.index(
        'scripts/migrations/202610/analyze_stale_statistics_int1741.py')
    assert _MIGRATION_REL in module.PROD_DDL_SCRIPTS
    assert '--apply' in steps[scripts.index(_MIGRATION_REL)]


def test_create_all_registers_provider_table():
    text = open(_CREATE_ALL, encoding='utf-8').read()
    assert 'AgentLlmProvider' in text
    module = _load(_CREATE_ALL, 'int2488_create_all')
    # INT-2466 新增 agent_approval 后全集 109 → 110；INT-2549 新增 Agent Skill
    # 三表后 110 → 113；INT-2551 审核链后 113 → 114
    assert module.EXPECTED_TABLE_COUNT == 114


def test_readme_lists_step():
    text = open(_README, encoding='utf-8').read()
    assert 'add_agent_llm_provider_table.py' in text
