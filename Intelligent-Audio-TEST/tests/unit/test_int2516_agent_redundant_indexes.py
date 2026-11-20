# -*- coding: utf-8 -*-
"""INT-2516 agent_step / agent_context_snapshot 冗余索引下线静态守卫。

- ORM 与 ㊾-8 建表迁移都不再声明跟唯一约束同列同序的普通索引；
- 兜底删索引迁移进引导链、排在 ㊾-8 之后与 ANALYZE 之前，并进 prod 白名单；
- 删索引的筛选逻辑：只有「非唯一 + 定义匹配 + 覆盖的唯一约束索引在位」才删。
"""
import importlib.util
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_DROP_REL = 'scripts/migrations/202611/drop_agent_redundant_indexes_int2516.py'
_RUNTIME_REL = 'scripts/migrations/202611/add_agent_runtime_tables.py'
_BOOTSTRAP = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
_ANALYZE_REL = 'scripts/migrations/202610/analyze_stale_statistics_int1741.py'
_REDUNDANT = (
    ('ix_agent_step_run', 'agent_step', 'run_id, "index"',
     'uq_agent_step_run_index'),
    ('ix_agent_context_snapshot_run', 'agent_context_snapshot',
     'run_id, version', 'uq_agent_context_snapshot_version'),
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _abs(rel):
    return os.path.join(PROJECT_ROOT, *rel.split('/'))


@pytest.fixture(scope='module')
def drop_migration():
    path = _abs(_DROP_REL)
    assert os.path.isfile(path)
    return _load(path, 'int2516_drop_redundant_indexes')


@pytest.fixture(scope='module')
def runtime_migration():
    return _load(_abs(_RUNTIME_REL), 'int2516_runtime_tables')


@pytest.fixture(scope='module')
def metadata():
    from agent_service.infrastructure.persistence import models  # noqa: F401
    from shared.models.database import Base
    return Base.metadata


def test_orm_no_longer_declares_redundant_indexes(metadata):
    for name, table, _cols, _covering in _REDUNDANT:
        declared = {index.name for index in metadata.tables[table].indexes}
        assert name not in declared, f'{table}.{name} 仍是 ORM 声明的普通索引'


def test_runtime_migration_no_longer_creates_redundant_indexes(runtime_migration):
    declared = {names[0] for names in runtime_migration.INDEXES}
    for name, _table, _cols, _covering in _REDUNDANT:
        assert name not in declared


def test_drop_migration_specs_cover_the_two_indexes(drop_migration):
    specs = {(spec.name, spec.table, spec.columns, spec.covered_by)
             for spec in drop_migration.INDEX_SPECS}
    assert specs == set(_REDUNDANT)


def test_bootstrap_runs_drop_step_between_runtime_and_analyze(drop_migration):
    module = _load(_BOOTSTRAP, 'int2516_bootstrap')
    scripts = [step[1] for step in module.BOOTSTRAP_STEPS]
    assert _DROP_REL in scripts
    assert scripts.index(_RUNTIME_REL) < scripts.index(_DROP_REL) < scripts.index(
        _ANALYZE_REL)
    assert _DROP_REL in module.PROD_DDL_SCRIPTS
    step = module.BOOTSTRAP_STEPS[scripts.index(_DROP_REL)]
    assert '--apply' in step, '引导链必须带 --apply，脚本默认 dry-run'


def _index_row(name, table, definition, unique=False):
    return (table, name), (unique, definition)


def _indexes(*rows):
    return dict(rows)


def test_plan_drops_matching_redundant_index(drop_migration):
    indexes = _indexes(
        _index_row(
            'ix_agent_step_run', 'agent_step',
            'CREATE INDEX ix_agent_step_run ON public.agent_step '
            'USING btree (run_id, "index")'),
        _index_row(
            'uq_agent_step_run_index', 'agent_step',
            'CREATE UNIQUE INDEX uq_agent_step_run_index ON public.agent_step '
            'USING btree (run_id, "index")', unique=True),
    )
    to_drop, skipped = drop_migration.plan(indexes)
    assert [spec.name for spec, _ in to_drop] == ['ix_agent_step_run']
    # context_snapshot 的索引不存在 → missing（幂等），不报 WARN
    assert [reason for _spec, reason in skipped] == ['missing']


def test_plan_skips_when_covering_unique_index_missing(drop_migration):
    indexes = _indexes(
        _index_row(
            'ix_agent_step_run', 'agent_step',
            'CREATE INDEX ix_agent_step_run ON public.agent_step '
            'USING btree (run_id, "index")'),
    )
    to_drop, skipped = drop_migration.plan(indexes)
    assert to_drop == []
    assert {reason for _spec, reason in skipped if reason != 'missing'} == {
        'covering-missing'}


def test_plan_skips_definition_mismatch(drop_migration):
    """被人加过列 / 改过定义就不删（宁可不减负，不误删）。"""
    indexes = _indexes(
        _index_row(
            'ix_agent_step_run', 'agent_step',
            'CREATE INDEX ix_agent_step_run ON public.agent_step '
            'USING btree (run_id, "index", created_at)'),
        _index_row(
            'uq_agent_step_run_index', 'agent_step',
            'CREATE UNIQUE INDEX uq_agent_step_run_index ON public.agent_step '
            'USING btree (run_id, "index")', unique=True),
    )
    to_drop, skipped = drop_migration.plan(indexes)
    assert to_drop == []
    assert [reason for _spec, reason in skipped if reason != 'missing'] == [
        'definition-mismatch']


def test_plan_never_drops_a_unique_index(drop_migration):
    indexes = _indexes(
        _index_row(
            'ix_agent_context_snapshot_run', 'agent_context_snapshot',
            'CREATE UNIQUE INDEX ix_agent_context_snapshot_run ON '
            'public.agent_context_snapshot USING btree (run_id, version)',
            unique=True),
        _index_row(
            'uq_agent_context_snapshot_version', 'agent_context_snapshot',
            'CREATE UNIQUE INDEX uq_agent_context_snapshot_version ON '
            'public.agent_context_snapshot USING btree (run_id, version)',
            unique=True),
    )
    to_drop, skipped = drop_migration.plan(indexes)
    assert to_drop == []
    assert 'unique' in {reason for _spec, reason in skipped}


def test_drop_migration_is_idempotent_and_dry_run_by_default(drop_migration):
    text = open(_abs(_DROP_REL), encoding='utf-8').read()
    assert 'DROP INDEX IF EXISTS' in text
    assert "add_argument('--apply'" in text
