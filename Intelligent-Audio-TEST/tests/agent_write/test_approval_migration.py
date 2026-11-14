# -*- coding: utf-8 -*-
"""INT-2466 agent_approval 迁移 / ORM / 引导链接线守卫。"""
import importlib.util
import os
import re

import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = 'scripts/migrations/202611/add_agent_approval_table.py'
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
_CREATE_ALL = os.path.join(PROJECT_ROOT, 'scripts', 'create_all_tables.py')
_TABLE = 'agent_approval'
_TYPE_ALIASES = {'DATETIME': 'TIMESTAMP'}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION), _MIGRATION
    return _load(_MIGRATION, 'int2466_agent_approval_migration')


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


def test_table_registered_in_metadata(metadata):
    assert _TABLE in metadata.tables


def test_ddl_columns_match_orm(migration, metadata):
    assert [table for table, _sql in migration.CREATE_TABLES] == [_TABLE]
    orm_table = metadata.tables[_TABLE]
    columns = _ddl_columns(dict(migration.CREATE_TABLES)[_TABLE])
    assert set(columns) == {c.name for c in orm_table.columns}
    for column in orm_table.columns:
        ddl = columns[column.name]
        ddl_type = _norm_type(
            re.match(r'^([A-Za-z]+(?:\(\d+\))?)', ddl).group(1))
        assert ddl_type == _norm_type(str(column.type)), column.name
        ddl_not_null = 'NOT NULL' in ddl or 'PRIMARY KEY' in ddl
        assert ddl_not_null == (not column.nullable), column.name


def test_unique_constraint_on_tool_call(metadata):
    """一次 tool call 1..N 张单（INT-2571 拆单）：按 batch_index 唯一。"""
    table = metadata.tables[_TABLE]
    names = {constraint.name for constraint in table.constraints}
    assert 'uq_agent_approval_run_call_batch' in names
    assert 'uq_agent_approval_run_call' not in names
    unique = next(constraint for constraint in table.constraints
                  if constraint.name == 'uq_agent_approval_run_call_batch')
    assert {column.name for column in unique.columns} == {
        'run_id', 'tool_call_id', 'batch_index'}


def test_indexes_for_status_expiry_and_run(metadata):
    """待办 / 过期扫描走 (status, expires_at)；回放历史走 (run_id, created_at)。"""
    table = metadata.tables[_TABLE]
    indexes = {index.name for index in table.indexes}
    assert 'ix_agent_approval_status_expires' in indexes
    assert 'ix_agent_approval_run' in indexes
    status_index = next(index for index in table.indexes
                        if index.name == 'ix_agent_approval_status_expires')
    assert [column.name for column in status_index.columns] == [
        'status', 'expires_at']


def test_migration_declares_same_constraints(migration):
    assert migration.UNIQUE_CONSTRAINTS == [
        ('uq_agent_approval_run_call_batch', _TABLE,
         'run_id, tool_call_id, batch_index')]
    # 旧唯一键必须先删再建新：存量库否则会保留「一次调用一张单」的约束
    assert migration.DROPPED_CONSTRAINTS == [
        ('uq_agent_approval_run_call', _TABLE)]
    index_names = {name for name, *_rest in migration.INDEXES}
    assert index_names == {
        'ix_agent_approval_status_expires', 'ix_agent_approval_run'}


def test_migration_adds_batch_columns_for_existing_tables(migration):
    """存量库补列：拆单字段全部有 ADD COLUMN 口径（历史行落单张默认值）。"""
    columns = dict(migration.ADDED_COLUMNS)
    assert set(columns) == {
        'batch_id', 'batch_index', 'batch_total', 'object_ref'}
    assert 'NOT NULL DEFAULT 1' in columns['batch_index']
    assert 'NOT NULL DEFAULT 1' in columns['batch_total']
    assert 'NULL' in columns['batch_id'] and 'NULL' in columns['object_ref']


def test_bootstrap_chain_and_prod_whitelist():
    with open(_BOOTSTRAP, encoding='utf-8') as handle:
        text = handle.read()
    assert '202611/add_agent_approval_table.py' in text
    # 结构 DDL：prod 档只跑白名单内的纯 DDL 步骤
    assert "'scripts/migrations/202611/add_agent_approval_table.py'" in text
    # 引导链必须排在 ANALYZE 之前（ANALYZE 恒为最后一步）
    migration_pos = text.index('add_agent_approval_table.py')
    analyze_pos = text.index('analyze_stale_statistics_int1741.py')
    assert migration_pos < analyze_pos


def test_status_values_are_enumerated():
    from agent_service.domain.enums import ApprovalStatus
    assert {item.value for item in ApprovalStatus} == {
        'PENDING', 'APPROVED', 'REJECTED', 'EXPIRED'}


def test_create_all_registers_approval_table(metadata):
    """新表必须登记进模型全集（否则 create_all 不建表、表数守卫失衡）。"""
    module = _load(_CREATE_ALL, 'int2466_create_all')
    # INT-2549 新增 Agent Skill 三表后全集 110 → 113
    assert module.EXPECTED_TABLE_COUNT == 113
    assert _TABLE in metadata.tables
