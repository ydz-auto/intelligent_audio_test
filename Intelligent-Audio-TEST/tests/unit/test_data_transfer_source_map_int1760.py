# -*- coding: utf-8 -*-
"""INT-1760：离线搬运 source_map 登记计划 + 建表迁移静态守卫

覆盖（不连库）：
- 四类实体映射计划的登记口径：只登记真重映射、source_task_id 取源任务、
  维度行经源结果反查、缺失 task_id 不静默丢弃；
- 唯一键去重；
- 失败重放快照（批次登记 source_map 字段）语义；
- DATA_TRANSFER_SERVER_ID 解析与回落；
- 建表迁移 DDL / 索引 / 唯一约束与 ORM 元数据逐项对齐、幂等、接引导链。
"""
import importlib.util
import os
import re

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')

from shared.constants.data_transfer import (  # noqa: E402
    SOURCE_MAP_BATCH_FIELD,
    SourceMapEntity,
)
from task_service.domain.services.data_transfer.source_map import (  # noqa: E402
    dedupe_entries,
    plan_source_map_entries,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = ('scripts/migrations/202610/'
                  'add_data_transfer_source_maps_int1760.py')
_MIGRATION_PATH = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')
_TABLE = 'data_transfer_source_maps'


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows():
    """包内原始行（A 侧 id）：2 任务 / 2 结果 / 1 维度 / 1 报告"""
    return {
        'test_tasks': [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}],
        'test_results': [
            {'id': 100, 'task_id': 1},
            {'id': 101, 'task_id': 2},
        ],
        'test_result_dimensions': [
            {'id': 200, 'test_result_id': 100, 'dimension_id': 1},
            {'id': 201, 'test_result_id': 101, 'dimension_id': 1},
        ],
        'test_reports': [{'id': 300, 'task_id': 1}],
    }


def _mappings(all_conflict=True):
    if all_conflict:
        return {
            'tasks': {1: 11, 2: 12},
            'test_results': {100: 110, 101: 111},
            'test_result_dimensions': {200: 210, 201: 211},
            'test_reports': {300: 310},
        }
    return {
        'tasks': {1: 1, 2: 2},
        'test_results': {100: 100, 101: 101},
        'test_result_dimensions': {200: 200, 201: 201},
        'test_reports': {300: 300},
    }


class TestPlanSourceMapEntries:
    def test_registers_four_entity_types_on_remap(self):
        entries, warnings = plan_source_map_entries('server-A', _rows(), _mappings())
        assert warnings == []
        by_type = {}
        for entry in entries:
            by_type.setdefault(entry['entity_type'], []).append(entry)
        assert set(by_type) == SourceMapEntity.values()
        assert [(e['source_id'], e['local_id']) for e in by_type['tasks']] == [(1, 11), (2, 12)]
        assert [(e['source_id'], e['local_id']) for e in by_type['test_results']] == \
            [(100, 110), (101, 111)]
        assert [(e['source_id'], e['local_id']) for e in by_type['test_result_dimensions']] == \
            [(200, 210), (201, 211)]
        assert [(e['source_id'], e['local_id']) for e in by_type['test_reports']] == [(300, 310)]

    def test_source_task_id_is_source_task_not_local(self):
        entries, _ = plan_source_map_entries('server-A', _rows(), _mappings())
        index = {(e['entity_type'], e['source_id']): e for e in entries}
        # 任务：source_task_id == source_id == A 原始 task_id（不是本地 11）
        assert index[('tasks', 1)]['source_task_id'] == 1
        # 结果：取包内结果行的 task_id（A 原始），不是本地任务 id
        assert index[('test_results', 100)]['source_task_id'] == 1
        assert index[('test_results', 101)]['source_task_id'] == 2
        # 维度：经源结果 id 反查源任务，而不是本地结果
        assert index[('test_result_dimensions', 200)]['source_task_id'] == 1
        assert index[('test_result_dimensions', 201)]['source_task_id'] == 2
        # 报告：取包内报告行 task_id
        assert index[('test_reports', 300)]['source_task_id'] == 1

    def test_identity_mappings_are_not_registered(self):
        """未冲突（source_id == local_id）不登记（卡片范围）"""
        entries, warnings = plan_source_map_entries('server-A', _rows(), _mappings(False))
        assert entries == []
        assert warnings == []

    def test_partial_conflict_only_registers_remapped(self):
        mappings = _mappings(False)
        mappings['test_results'][100] = 110
        entries, _ = plan_source_map_entries('server-A', _rows(), mappings)
        assert [(e['entity_type'], e['source_id'], e['local_id']) for e in entries] == \
            [('test_results', 100, 110)]

    def test_dimension_without_packaged_result_is_warned_not_silent(self):
        rows = _rows()
        rows['test_result_dimensions'].append({'id': 202, 'test_result_id': 999})
        mappings = _mappings()
        mappings['test_result_dimensions'][202] = 212
        entries, warnings = plan_source_map_entries('server-A', rows, mappings)
        assert all(e['source_id'] != 202 for e in entries)
        assert any('202' in w and '999' in w for w in warnings)

    def test_result_without_task_id_is_warned(self):
        rows = _rows()
        rows['test_results'].append({'id': 102})
        mappings = _mappings()
        mappings['test_results'][102] = 112
        entries, warnings = plan_source_map_entries('server-A', rows, mappings)
        assert all(e['source_id'] != 102 for e in entries)
        assert any('102' in w for w in warnings)

    def test_empty_source_server_registers_nothing_and_warns(self):
        entries, warnings = plan_source_map_entries('', _rows(), _mappings())
        assert entries == []
        assert warnings and 'source_server' in warnings[0]

    def test_dedupe_by_unique_key(self):
        entries = [
            {'source_server': 's', 'source_task_id': 1, 'entity_type': 'tasks',
             'source_id': 1, 'local_id': 9},
            {'source_server': 's', 'source_task_id': 1, 'entity_type': 'tasks',
             'source_id': 1, 'local_id': 9},
        ]
        assert len(dedupe_entries(entries)) == 1


class TestSourceMapSnapshot:
    """批次登记里的 source_map 快照（失败重放依据，D0 A3 第 3 条）"""

    class _Store:
        def __init__(self):
            self._data = {}

        def save_task(self, key, fields, ttl_seconds=86400):
            self._data.setdefault(key, {}).update(fields)

        def load_task(self, key):
            return dict(self._data.get(key, {}))

    def test_source_map_snapshot_roundtrip_and_keeps_tables(self):
        from shared.utils.data_transfer_batch import TransferBatchRegistry

        registry = TransferBatchRegistry(store=self._Store())
        registry.record('b1', 'task_service', {'test_tasks': [11, 12]})
        entries = [{'source_server': 's', 'source_task_id': 1, 'entity_type': 'tasks',
                    'source_id': 1, 'local_id': 11}]
        registry.record_source_map('b1', 'task_service', entries)

        assert registry.load_source_map('b1', 'task_service') == entries
        # 主键登记不被快照覆盖（同一 HASH 字段内的两个子键）
        assert registry.load_service('b1', 'task_service') == {'test_tasks': [11, 12]}
        # 字段名契约与常量一致（重放脚本按它取快照）
        raw = registry._store.load_task(registry._key('b1'))
        assert SOURCE_MAP_BATCH_FIELD in raw['task_service']

    def test_record_keeps_existing_source_map(self):
        from shared.utils.data_transfer_batch import TransferBatchRegistry

        registry = TransferBatchRegistry(store=self._Store())
        registry.record_source_map('b2', 'task_service', [{'source_id': 1}])
        registry.record('b2', 'task_service', {'test_tasks': [1]})
        assert registry.load_source_map('b2', 'task_service') == [{'source_id': 1}]


class TestServerIdResolution:
    def test_configured_value_wins(self, monkeypatch):
        from shared.infrastructure.config import BaseConfig
        from shared.utils import data_transfer_server

        monkeypatch.setattr(BaseConfig, 'DATA_TRANSFER_SERVER_ID', 'stable-A')
        assert data_transfer_server.resolve_transfer_server_id() == 'stable-A'

    def test_fallback_is_service_name_plus_hostname(self, monkeypatch):
        from shared.infrastructure.config import BaseConfig
        from shared.utils import data_transfer_server

        monkeypatch.setattr(BaseConfig, 'DATA_TRANSFER_SERVER_ID', '')
        monkeypatch.setattr(BaseConfig, 'SERVICE_NAME', 'task_service')
        monkeypatch.setattr(data_transfer_server.socket, 'gethostname',
                            lambda: 'host-1')
        assert data_transfer_server.resolve_transfer_server_id() == 'task_service-host-1'
        assert data_transfer_server.compose_fallback_server_id('', '') == 'unknown-unknown'


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION_PATH), f'建表迁移缺失：{_MIGRATION_REL}'
    return _load_module(_MIGRATION_PATH, 'int1760_source_map_migration')


@pytest.fixture(scope='module')
def orm_table():
    import task_service.infrastructure.persistence.models  # noqa: F401
    from shared.models.database import Base
    return Base.metadata.tables[_TABLE]


class TestMigrationDdlMatchesOrm:
    @staticmethod
    def _ddl_columns(sql):
        body = sql[sql.index('(') + 1:sql.rindex(')')]
        columns = {}
        for raw in body.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.upper().startswith(
                    ('CONSTRAINT', 'PRIMARY KEY', 'UNIQUE')):
                continue
            match = re.match(r'^([a-z_][a-z0-9_]*)\s+(.+?),?$', stripped)
            assert match, f'无法解析的 DDL 行：{raw!r}'
            columns[match.group(1)] = match.group(2).rstrip(',')
        return columns

    def test_ddl_table_name(self, migration):
        assert [table for table, _sql in migration.CREATE_TABLES] == [_TABLE]

    def test_ddl_columns_match_orm(self, migration, orm_table):
        table, sql = migration.CREATE_TABLES[0]
        columns = self._ddl_columns(sql)
        assert set(columns) == {c.name for c in orm_table.columns}
        for column in orm_table.columns:
            ddl = columns[column.name]
            orm_type = str(column.type).upper().replace('DATETIME', 'TIMESTAMP')
            ddl_type = re.match(r'^([A-Za-z]+(?:\(\d+\))?)', ddl).group(1).upper()
            if orm_type == 'BIGINT' and column.primary_key:
                ddl_type = {'BIGSERIAL': 'BIGINT'}.get(ddl_type, ddl_type)
            assert ddl_type == orm_type, f'{column.name} 类型不一致 DDL={ddl!r}'
            ddl_not_null = 'NOT NULL' in ddl or 'PRIMARY KEY' in ddl
            assert ddl_not_null == (not column.nullable), f'{column.name} 可空性不一致'
            assert ('DEFAULT' in ddl) == (column.server_default is not None), \
                f'{column.name} server_default 不一致'

    def test_ddl_indexes_match_orm(self, migration, orm_table):
        orm_indexes = {(i.name, i.unique) for i in orm_table.indexes}
        ddl_indexes = {(name, unique) for name, table, _cols, unique
                       in migration.INDEXES if table == _TABLE}
        assert ddl_indexes == orm_indexes

    def test_ddl_unique_constraint_matches_orm(self, migration, orm_table):
        from sqlalchemy import UniqueConstraint

        orm_uq = {(c.name, tuple(col.name for col in c.columns))
                  for c in orm_table.constraints if isinstance(c, UniqueConstraint)}
        ddl_uq = {(name, tuple(col.strip() for col in cols.split(',')))
                  for name, table, cols in migration.UNIQUE_CONSTRAINTS
                  if table == _TABLE}
        assert ddl_uq == orm_uq
        # D0 A4 第 2 条：唯一键落在 local 侧，source_id 不进唯一键
        assert orm_uq == {('uq_transfer_source_map_local',
                           ('source_server', 'entity_type', 'local_id'))}

    def test_ddl_is_idempotent(self, migration):
        table, sql = migration.CREATE_TABLES[0]
        assert f'CREATE TABLE IF NOT EXISTS {table}' in sql
        for index_name, ddl_table, cols, unique in migration.INDEXES:
            stmt = migration._index_sql(index_name, ddl_table, cols, unique)
            assert 'IF NOT EXISTS' in stmt
            assert ('UNIQUE INDEX' in stmt) == unique
        with open(_MIGRATION_PATH, encoding='utf-8') as f:
            text = f.read()
        assert '_constraint_exists' in text, '唯一约束兜底必须先查存在性，重复部署不报错'
        assert "add_argument('--dry-run'" in text

    def test_bootstrap_chain_includes_migration(self):
        steps = [list(step) for step in
                 _load_module(_BOOTSTRAP_PATH, 'int1760_bootstrap').BOOTSTRAP_STEPS]
        assert any(_MIGRATION_REL in step for step in steps), (
            f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：建库早于本卡的存量库不会建表，'
            '整包导入段 6 登记即 UndefinedTable')

    def test_create_all_registers_table(self):
        module = _load_module(os.path.join(
            PROJECT_ROOT, 'scripts', 'create_all_tables.py'), 'int1760_create_all')
        module._import_all_models()
        from shared.models.database import Base
        assert _TABLE in Base.metadata.tables
