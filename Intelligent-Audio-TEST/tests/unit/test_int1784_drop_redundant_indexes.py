# -*- coding: utf-8 -*-
"""INT-1784：冗余索引下线迁移（引导链 ㊸）——幂等 / 双匹配 / 覆盖索引保留守卫。

背景：`logs` 单表 15 个索引、全库 387 个索引里有一批**定义层面可证明冗余**的
btree（同名同定义的历史重复、被同表复合索引前缀覆盖的短索引）。本卡只删这类，
`idx_scan=0` 的「可能有用」索引一个不动。

索引有三个重建源，必须同时断掉，否则下次部署又会被建回来：
① ORM 的 `Index(...)` / `Column(index=True)`；② 引导链里 202608/202610 的采索引
脚本；③ 本卡的 drop 迁移（兜底收敛）。

本文件（全部不连库）把下列契约钉死：
1. 迁移脚本在引导链里且带 `--apply`，位置在 INT-1741 的 ANALYZE 之前
   （ANALYZE 必须保持引导链末步）；
2. 默认 dry-run 不发任何 DROP；`--apply` 只 DROP 清单内的 22 个索引；
3. **双匹配**：实际定义与期望不符（加列 / 改 WHERE / 变 UNIQUE）时跳过并 WARN；
4. **覆盖索引在位**才删：覆盖索引缺失或列序不构成前缀时跳过；
5. 幂等：第二次执行全部 SKIP、无 DROP 语句；
6. `report_detail_data` 只有 0 行时才 DROP TABLE；
7. 重建源已断：ORM 元数据与历史迁移脚本都不再声明/创建这些索引。
"""
import importlib.util
import os
import re
import sys

from psycopg2 import sql as _pg_sql

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = ('scripts/migrations/202610/'
                  'drop_redundant_indexes_int1784.py')
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')
_ANALYZE_REL = ('scripts/migrations/202610/'
                'analyze_stale_statistics_int1741.py')

# 模块 import 期只校验配置非空，不连库
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_script = _load(_MIGRATION, 'int1784_drop_redundant_indexes')
_bootstrap = _load(_BOOTSTRAP_PATH, 'int1784_db_bootstrap')


def _sql_text(query):
    """把 psycopg2.sql.Composed 渲染成可断言的文本（假连接没有真连接上下文）。"""
    if isinstance(query, str):
        return query
    seq = getattr(query, 'seq', None)
    if seq is None:
        return repr(query)
    parts = []
    for item in seq:
        if isinstance(item, _pg_sql.Identifier):
            parts.append('"%s"' % item.string.replace('"', '""'))
        elif isinstance(item, _pg_sql.SQL):
            parts.append(item.string)
        else:
            parts.append(str(item))
    return ''.join(parts)


# ---------------------------------------------------------------- 假连接

class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        text = _sql_text(query)
        self._conn.executed.append(text)
        if 'FROM pg_index i' in text:
            wanted = set(params[0]) if params else set()
            self._rows = [(table, name, definition)
                          for (table, name), definition
                          in sorted(self._conn.indexes.items())
                          if table in wanted]
        elif 'to_regclass' in text:
            self._rows = [(self._conn.legacy_table or None,)]
        elif text.strip().upper().startswith('SELECT COUNT(*)'):
            self._rows = [(self._conn.legacy_rows,)]
        elif 'pg_relation_size' in text:
            self._rows = [('2 MB',)]
        else:
            self._rows = []
            if text.strip().upper().startswith('DROP INDEX'):
                self._conn.dropped_indexes.append(text)
            if text.strip().upper().startswith('DROP TABLE'):
                self._conn.dropped_tables.append(text)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, indexes, legacy_table='report_detail_data',
                 legacy_rows=0):
        self.indexes = dict(indexes)
        self.legacy_table = legacy_table
        self.legacy_rows = legacy_rows
        self.executed = []
        self.dropped_indexes = []
        self.dropped_tables = []
        self.autocommit = True

    def cursor(self):
        return _FakeCursor(self)

    def rollback(self):
        pass

    def close(self):
        pass


def _definition(table, name, columns, where=None):
    """按 pg_get_indexdef 的形态造一条定义（会带引号 + 限定 schema）。"""
    quoted = ', '.join('"%s"' % col for col in columns.split(', '))
    sql = f'CREATE INDEX {name} ON public.{table} USING btree ({quoted})'
    if where:
        sql += f' WHERE {where}'
    return sql


def _realistic_indexes():
    """按主库 2026-10-24 的实际定义造一套索引（清单 + 覆盖索引）。"""
    indexes = {}
    for spec in _script.INDEX_SPECS:
        indexes[(spec.table, spec.name)] = _definition(
            spec.table, spec.name, spec.columns)
    # 覆盖索引的真实列序
    for spec in _script.INDEX_SPECS:
        covering_cols = _COVERING_COLUMNS[spec.covered_by]
        indexes[(spec.table, spec.covered_by)] = _definition(
            spec.table, spec.covered_by, covering_cols)
    # 一个必须保留的无关索引（证明不会误删）
    indexes[('logs', 'idx_time')] = _definition('logs', 'idx_time', 'time')
    return indexes


_COVERING_COLUMNS = {
    'idx_audio_algorithm_type': 'algorithm_type',
    'idx_audio_algorithm_audio': 'audio_id',
    'idx_task_time': 'task_id, time',
    'idx_test_reports_task_id': 'task_id',
    'idx_audio_annotations_audio_deleted': 'audio_id, deleted',
    'idx_audio_tags_audio_tag': 'audio_id, tag_id',
    'idx_audios_created_visibility': 'created_by_user_id, visibility',
    'idx_audios_deleted_created': 'deleted, created_at',
    'idx_cherry_cart_user_source': 'user_id, source_task_id',
    'ix_alarm_status_time': 'status, triggered_at',
    'ix_status_event_device_time': 'device_id, created_at',
    'idx_dimensions_created_visibility': 'created_by_user_id, visibility',
    'idx_favorite_user_type': 'user_id, entity_type',
    'idx_category_time': 'category, time',
    'idx_level_time': 'level, time',
    'idx_report_favorite_user': 'user_id, entity_type',
    'idx_test_cases_created_visibility': 'created_by_user_id, visibility',
    'idx_report_type_status': 'type, status',
    'idx_test_reports_created_visibility': 'created_by_user_id, visibility',
    'idx_trd_round': 'test_result_id, round_number',
    'idx_test_tasks_created_visibility': 'created_by_user_id, visibility',
}


def _collect():
    out = []
    return out, out.append


# ---------------------------------------------------------------- 清单自检

def test_migration_file_exists():
    assert os.path.isfile(_MIGRATION), f'迁移脚本不存在：{_MIGRATION_REL}'


def test_specs_are_unique_and_complete():
    """22 个目标索引，互不重复，覆盖索引不在待删清单内。"""
    assert len(_script.INDEX_SPECS) == 22, (
        f'待删清单应为 22 个（A 5 + B 17），实际 {len(_script.INDEX_SPECS)}')
    keys = [(spec.table, spec.name) for spec in _script.INDEX_SPECS]
    assert len(keys) == len(set(keys)), '待删清单里有重复项'
    names = {name for _table, name in keys}
    for spec in _script.INDEX_SPECS:
        assert spec.columns, f'{spec.name} 缺少期望列定义'
        assert spec.covered_by not in names, (
            f'{spec.covered_by} 既是覆盖索引又在待删清单里')


# ---------------------------------------------------------------- 引导链

def test_bootstrap_chain_includes_step_with_apply():
    steps = [step for step in _bootstrap.BOOTSTRAP_STEPS
             if step[1] == _MIGRATION_REL]
    assert steps, f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：存量库永远不会瘦身'
    assert '--apply' in steps[0], (
        f'{_MIGRATION_REL} 在引导链中缺少 --apply（只预览不执行）')


def test_bootstrap_step_runs_before_analyze():
    """ANALYZE 必须保持引导链末步（INT-1741 静态守卫），本步排在它之前。"""
    order = [step[1] for step in _bootstrap.BOOTSTRAP_STEPS]
    assert order[-1] == _ANALYZE_REL, 'ANALYZE 不再是引导链末步'
    assert order.index(_MIGRATION_REL) < order.index(_ANALYZE_REL)


# ---------------------------------------------------------------- 预览 / 执行

def test_dry_run_drops_nothing():
    conn = _FakeConn(_realistic_indexes())
    out, emit = _collect()
    dropped, table_dropped = _script.run(conn, apply_changes=False, out=emit)
    assert dropped == 0 and table_dropped is False
    assert conn.dropped_indexes == [], 'dry-run 不得发 DROP INDEX'
    assert conn.dropped_tables == [], 'dry-run 不得发 DROP TABLE'
    preview = [text for text in out if text.startswith('[DRY-RUN] DROP INDEX')]
    assert len(preview) == 22, f'dry-run 应列出 22 个待删索引，实际 {len(preview)}'


def test_apply_drops_exactly_the_specs():
    conn = _FakeConn(_realistic_indexes())
    out, emit = _collect()
    dropped, table_dropped = _script.run(conn, apply_changes=True, out=emit)
    assert dropped == 22, f'应删除 22 个索引，实际 {dropped}'
    assert table_dropped is True

    dropped_names = {
        re.search(r'DROP INDEX IF EXISTS "([^"]+)"', text).group(1)
        for text in conn.dropped_indexes
    }
    assert dropped_names == {spec.name for spec in _script.INDEX_SPECS}
    # 覆盖索引与无关索引一个都不能少
    assert 'idx_task_time' not in dropped_names
    assert 'idx_time' not in dropped_names
    assert 'idx_audio_annotations_audio_deleted' not in dropped_names
    assert 'idx_test_tasks_created_visibility' not in dropped_names


def test_second_run_is_idempotent():
    conn = _FakeConn(_realistic_indexes())
    _script.run(conn, apply_changes=True, out=lambda _line: None)

    # 第一次删掉的从库里消失，模拟「再跑一遍」
    for text in conn.dropped_indexes:
        name = re.search(r'"([^"]+)"', text).group(1)
        for key in [key for key in conn.indexes if key[1] == name]:
            del conn.indexes[key]
    conn.dropped_indexes.clear()
    conn.dropped_tables.clear()
    conn.indexes.pop(('logs', 'report_detail_data'), None)
    conn.legacy_table = None

    out, emit = _collect()
    dropped, table_dropped = _script.run(conn, apply_changes=True, out=emit)
    assert dropped == 0 and table_dropped is False
    assert conn.dropped_indexes == [], '第二次执行不得再发 DROP INDEX'
    assert conn.dropped_tables == [], '第二次执行不得再发 DROP TABLE'
    assert any('已不存在（幂等）' in line for line in out)
    assert any(f'表 {_script.LEGACY_TABLE} 已不存在' in line for line in out)


# ---------------------------------------------------------------- 双匹配守卫

def test_definition_mismatch_is_skipped():
    """定义被人改过（例如加了 WHERE 变部分索引）→ 跳过并 WARN，不误删。"""
    indexes = _realistic_indexes()
    indexes[('logs', 'idx_level')] = _definition(
        'logs', 'idx_level', 'level', where='(level = \'ERROR\'::text)')
    conn = _FakeConn(indexes)
    out, emit = _collect()
    dropped, _ = _script.run(conn, apply_changes=True, out=emit)
    assert dropped == 21
    names = {re.search(r'DROP INDEX IF EXISTS "([^"]+)"', text).group(1)
             for text in conn.dropped_indexes}
    assert 'idx_level' not in names
    assert any('[WARN] logs.idx_level 跳过' in line and '定义与期望不符' in line
               for line in out)


def test_unique_index_is_skipped():
    indexes = _realistic_indexes()
    indexes[('logs', 'idx_category')] = _definition(
        'logs', 'idx_category', 'category').replace(
            'CREATE INDEX', 'CREATE UNIQUE INDEX')
    conn = _FakeConn(indexes)
    out, emit = _collect()
    dropped, _ = _script.run(conn, apply_changes=True, out=emit)
    assert dropped == 21
    assert any('UNIQUE' in line for line in out)


def test_covering_index_missing_is_skipped():
    """覆盖索引不在 → 删了这条查询就没索引可用，宁可不减负。"""
    indexes = _realistic_indexes()
    indexes.pop(('test_tasks', 'idx_test_tasks_created_visibility'))
    conn = _FakeConn(indexes)
    out, emit = _collect()
    dropped, _ = _script.run(conn, apply_changes=True, out=emit)
    assert dropped == 21
    names = {re.search(r'DROP INDEX IF EXISTS "([^"]+)"', text).group(1)
             for text in conn.dropped_indexes}
    assert 'ix_test_tasks_created_by_user_id' not in names
    assert any('覆盖索引 idx_test_tasks_created_visibility 不存在' in line
               for line in out)


def test_covering_index_not_a_prefix_is_skipped():
    """覆盖索引列序不以前缀覆盖（顺序反了）→ 跳过。"""
    indexes = _realistic_indexes()
    indexes[('audios', 'idx_audios_created_visibility')] = _definition(
        'audios', 'idx_audios_created_visibility', 'visibility, created_by_user_id')
    conn = _FakeConn(indexes)
    out, emit = _collect()
    dropped, _ = _script.run(conn, apply_changes=True, out=emit)
    assert dropped == 21
    names = {re.search(r'DROP INDEX IF EXISTS "([^"]+)"', text).group(1)
             for text in conn.dropped_indexes}
    assert 'ix_audios_created_by_user_id' not in names
    assert any('列序不以前缀覆盖' in line for line in out)


# ---------------------------------------------------------------- 废弃表

def test_legacy_table_with_rows_is_not_dropped():
    conn = _FakeConn(_realistic_indexes(), legacy_rows=7)
    out, emit = _collect()
    _dropped, table_dropped = _script.run(conn, apply_changes=True, out=emit)
    assert table_dropped is False
    assert conn.dropped_tables == []
    assert any('有 7 行数据' in line for line in out)


def test_legacy_table_absent_is_skipped():
    conn = _FakeConn(_realistic_indexes(), legacy_table=None)
    out, emit = _collect()
    _dropped, table_dropped = _script.run(conn, apply_changes=True, out=emit)
    assert table_dropped is False
    assert conn.dropped_tables == []


# ---------------------------------------------------------------- 重建源已断

def test_orm_metadata_no_longer_declares_target_indexes():
    """create_all 是索引重建源之一：ORM 元数据里不得再有这些 Index。"""
    from task_service.infrastructure.persistence.models.system_models import Log
    from task_service.infrastructure.persistence.models.task_models import Task
    from task_service.infrastructure.persistence.models.testcase_models import (
        TestCase)
    from task_service.infrastructure.persistence.models.cherry_pick_models import (
        CherryPickCartItem)
    from audio_service.infrastructure.persistence.models.audio_models import (
        Audio, AudioAnnotation, AudioTag)
    from report_service.infrastructure.persistence.models.report_models import (
        Report)
    from evaluation_service.infrastructure.persistence.models.evaluation_models \
        import Dimension
    from device_service.infrastructure.persistence.models.device_models import (
        DeviceAlarm, DeviceStatusEvent)

    tables = [Log.__table__, Task.__table__, TestCase.__table__,
              CherryPickCartItem.__table__, Audio.__table__,
              AudioAnnotation.__table__, AudioTag.__table__,
              Report.__table__, Dimension.__table__,
              DeviceAlarm.__table__, DeviceStatusEvent.__table__]
    by_table = {table.name: table for table in tables}

    expected_absent = {
        'logs': {'idx_task_id', 'idx_level', 'idx_category'},
        'test_tasks': {'ix_test_tasks_created_by_user_id'},
        'test_cases': {'ix_test_cases_created_by_user_id'},
        'cherry_pick_cart_items': {'idx_cherry_cart_user'},
        'audios': {'ix_audios_created_by_user_id', 'idx_audios_deleted'},
        'audio_annotations': {'idx_audio_annotations_audio_id'},
        'audio_tags': {'idx_audio_tags_audio_id'},
        'test_reports': {'idx_report_task_id', 'idx_report_type',
                         'ix_test_reports_created_by_user_id'},
        'dimensions': {'ix_dimensions_created_by_user_id'},
        'device_alarms': {'ix_device_alarms_status'},
        'device_status_events': {'ix_device_status_events_device_id'},
    }
    for table_name, absent in expected_absent.items():
        existing = {index.name for index in by_table[table_name].indexes}
        assert not (existing & absent), (
            f'{table_name} 仍在元数据里声明 {existing & absent}，'
            'create_all 会把它们建回来')

    # 覆盖索引必须还在元数据里（否则新建库没有索引支撑）。
    # 注意：(created_by_user_id, visibility) 与 idx_test_reports_task_id 由引导链里的
    # 迁移脚本创建（不在 ORM 声明里），见 test_covering_index_available_on_fresh_db。
    expected_present = {
        'logs': {'idx_task_time', 'idx_level_time', 'idx_category_time'},
        'cherry_pick_cart_items': {'idx_cherry_cart_user_source'},
        'audios': {'idx_audios_created_visibility', 'idx_audios_deleted_created'},
        'audio_annotations': {'idx_audio_annotations_audio_deleted'},
        'audio_tags': {'idx_audio_tags_audio_tag'},
        'test_reports': {'idx_report_type_status'},
        'device_alarms': {'ix_alarm_status_time'},
        'device_status_events': {'ix_status_event_device_time'},
    }
    for table_name, present in expected_present.items():
        existing = {index.name for index in by_table[table_name].indexes}
        assert present <= existing, (
            f'{table_name} 元数据缺覆盖索引 {present - existing}')


_MIGRATION_REGISTRY = (
    'scripts/migrations/202608/remove_foreign_keys_and_soft_delete.py',
    'scripts/migrations/202610/fix_leftover_foreign_keys_and_indexes.py',
    'scripts/migrations/202610/add_device_management_tables.py',
    'scripts/migrations/202610/add_cherry_pick_tables_int339.py',
    'scripts/migrations/202610/add_trash_operator_and_favorites.py',
    'scripts/migrations/202610/add_operator_columns_int299.py',
)


def test_migration_registry_does_not_recreate_targets():
    """历史采索引脚本是第二重建源：里面不得再有这些索引的创建语句。"""
    texts = {}
    for rel in _MIGRATION_REGISTRY:
        with open(os.path.join(PROJECT_ROOT, *rel.split('/')),
                  encoding='utf-8') as fh:
            texts[rel] = fh.read()

    # ① 202608 / 202610 的 INDEX_DEFINITIONS 元组
    tuple_targets = (
        "'idx_audio_annotations_audio_id', 'audio_annotations'",
        "'idx_audio_tags_audio_id', 'audio_tags'",
        "'idx_audio_algo_rel_audio_id', 'audio_algorithm_relations'",
        "'idx_audio_algo_rel_algorithm_type', 'audio_algorithm_relations'",
        "'idx_test_result_dimensions_test_result_id', 'test_result_dimensions'",
        "'idx_logs_task_id', 'logs'",
    )
    for rel in _MIGRATION_REGISTRY[:2]:
        for needle in tuple_targets:
            assert needle not in texts[rel], f'{rel} 仍会创建 {needle}'

    # ② 裸 CREATE INDEX 语句
    create_targets = (
        'CREATE INDEX ix_device_status_events_device_id',
        'CREATE INDEX ix_device_alarms_status',
        'CREATE INDEX IF NOT EXISTS idx_cherry_cart_user ',
        'CREATE INDEX idx_favorite_user_id',
        'CREATE INDEX idx_report_favorite_user_id',
        'CREATE INDEX IF NOT EXISTS ix_{table}_created_by_user_id ON {table}',
    )
    for rel in _MIGRATION_REGISTRY:
        for needle in create_targets:
            assert needle not in texts[rel], f'{rel} 仍会创建 {needle}'

    # ③ int299 的 created_by 索引兜底段里不得再有 audios（列补齐段不受影响）
    int299 = texts['scripts/migrations/202610/add_operator_columns_int299.py']
    section_start = int299.index('# 3. 既有三表')
    assert "'audios'" not in int299[section_start:section_start + 800], (
        'int299 仍会为 audios 兜底创建 ix_audios_created_by_user_id')


def test_covering_index_available_on_fresh_db():
    """覆盖索引必须在「全新库」也有来源：ORM 元数据或引导链迁移脚本。

    否则新建库删掉单列索引后就无索引可用（created_by 过滤退化为全表扫描）。
    """
    from task_service.infrastructure.persistence.models.system_models import Log
    from task_service.infrastructure.persistence.models.task_models import Task
    from task_service.infrastructure.persistence.models.testcase_models import (
        TestCase)
    from task_service.infrastructure.persistence.models.cherry_pick_models import (
        CherryPickCartItem)
    from audio_service.infrastructure.persistence.models.audio_models import (
        Audio, AudioAnnotation, AudioAlgorithmRelation, AudioTag)
    from report_service.infrastructure.persistence.models.report_models import (
        Report)
    from evaluation_service.infrastructure.persistence.models.evaluation_models \
        import Dimension
    from evaluation_service.infrastructure.persistence.models.result_models \
        import TestResultDimension
    from device_service.infrastructure.persistence.models.device_models import (
        DeviceAlarm, DeviceStatusEvent)

    orm_names = set()
    for model in (Log, Task, TestCase, CherryPickCartItem, Audio,
                  AudioAnnotation, AudioAlgorithmRelation, AudioTag, Report,
                  Dimension, TestResultDimension, DeviceAlarm,
                  DeviceStatusEvent):
        orm_names |= {index.name for index in model.__table__.indexes}

    registry_text = ''
    for rel in _MIGRATION_REGISTRY:
        with open(os.path.join(PROJECT_ROOT, *rel.split('/')),
                  encoding='utf-8') as fh:
            registry_text += fh.read()

    for spec in _script.INDEX_SPECS:
        assert spec.covered_by in orm_names or spec.covered_by in registry_text, (
            f'覆盖索引 {spec.covered_by}（{spec.table}）在全新库里没有创建来源：'
            '删掉单列索引后该表将失去索引支撑')
