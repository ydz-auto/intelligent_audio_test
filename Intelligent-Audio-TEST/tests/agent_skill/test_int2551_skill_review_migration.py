# -*- coding: utf-8 -*-
"""INT-2551 迁移 / 模型注册静态守卫（验收 10、11）。

- ``agent_skill_review`` 的建表 DDL 与 ORM 元数据逐列对齐；
- 索引 ``(skill_id, version)`` / ``(tenant_id, status_to)`` 与 ORM 一致；
- 引导链包含本步且排在 ANALYZE 之前，prod 白名单同样登记；
- 模型全集表数 113 → 114；
- 审核流代码不出现状态 / 动作魔法字符串（枚举化）。
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
_MIGRATION_REL = 'scripts/migrations/202611/add_agent_skill_review_table.py'
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
_TABLE = 'agent_skill_review'
_TYPE_ALIASES = {'DATETIME': 'TIMESTAMP'}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION)
    return _load(_MIGRATION, 'int2551_skill_review_migration')


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


def test_migration_declares_review_table(migration, metadata):
    assert [table for table, _sql in migration.CREATE_TABLES] == [_TABLE]
    assert _TABLE in metadata.tables


def test_ddl_columns_match_orm(migration, metadata):
    table, sql = migration.CREATE_TABLES[0]
    orm_table = metadata.tables[table]
    columns = _ddl_columns(sql)
    assert set(columns) == {c.name for c in orm_table.columns}
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


def test_indexes_match_orm(migration, metadata):
    orm_indexes = {(i.name, i.unique)
                   for i in metadata.tables[_TABLE].indexes}
    ddl_indexes = {(name, unique) for name, ddl_table, _cols, unique, _where
                   in migration.INDEXES if ddl_table == _TABLE}
    assert ddl_indexes == orm_indexes


def test_required_index_columns(migration):
    """卡面要求：``(skill_id, version)`` 与 ``(tenant_id, status_to)`` 索引。"""
    by_name = {name: (cols, unique) for name, _table, cols, unique, _where
               in migration.INDEXES}
    assert by_name['ix_agent_skill_review_skill_version'] == (
        'skill_id, version', False)
    assert by_name['ix_agent_skill_review_tenant_status'] == (
        'tenant_id, status_to', False)


def test_migration_is_idempotent(migration):
    for table, sql in migration.CREATE_TABLES:
        assert f'CREATE TABLE IF NOT EXISTS {table}' in sql
    text = open(_MIGRATION, encoding='utf-8').read()
    assert 'IF NOT EXISTS' in text
    assert "add_argument('--dry-run'" in text
    assert "add_argument('--apply'" in text
    assert "add_argument('--rollback'" in text


def test_bootstrap_contains_step_before_analyze():
    module = _load(_BOOTSTRAP, 'int2551_bootstrap')
    scripts = [step[1] for step in module.BOOTSTRAP_STEPS]
    assert _MIGRATION_REL in scripts
    assert scripts.index(_MIGRATION_REL) < scripts.index(
        'scripts/migrations/202610/analyze_stale_statistics_int1741.py')
    assert _MIGRATION_REL in module.PROD_DDL_SCRIPTS


def test_model_registered_in_create_all_tables():
    module = _load(os.path.join(PROJECT_ROOT, 'scripts',
                                'create_all_tables.py'),
                   'int2551_create_all')
    assert module.EXPECTED_TABLE_COUNT == 114
    text = open(os.path.join(PROJECT_ROOT, 'scripts',
                             'create_all_tables.py'), encoding='utf-8').read()
    assert 'AgentSkillReview' in text


def test_rbac_registers_admin_permission():
    path = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', '202608',
                        'seed_rbac.py')
    text = open(path, encoding='utf-8').read()
    assert "('agent:skill:admin'" in text


def test_no_status_action_magic_strings():
    """验收 10：状态与动作只经枚举使用，不在逻辑里写字面量。"""
    relative = [
        'agent_service/application/skill_review_service.py',
        'agent_service/domain/services/skill_review_state.py',
        'agent_service/domain/services/skill_tenancy.py',
        'agent_service/infrastructure/persistence/skill_repositories.py',
        'agent_service/infrastructure/persistence/models/agent_models.py',
    ]
    forbidden = ("'PLATFORM'", "'TENANT'", "'USER'", "'DRAFT'", "'ACTIVE'",
                 "'DISABLED'", "'PENDING_REVIEW'", "'SUBMIT'", "'APPROVE'",
                 "'REJECT'", "'WITHDRAW'", "'DISABLE'")
    for rel in relative:
        text = open(os.path.join(PROJECT_ROOT, *rel.split('/')),
                    encoding='utf-8').read()
        hits = [token for token in forbidden if token in text]
        assert not hits, f'{rel} 出现魔法字符串：{hits}'
