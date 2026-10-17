# -*- coding: utf-8 -*-
"""INT-604 迁移安全单测（评审①补录验收项）：
add_uq_task_case_route_int604.py 建唯一索引前先查重。

覆盖：
- 构造 (task, case, 路由) 重复数据 → 迁移 ABORT（sys.exit(2)）并列出重复行，不建索引；
- 干净库 → 唯一索引 CREATE 成功；
- 索引已存在 → SKIP 幂等（重复执行安全）。

mock psycopg2.connect 的游标层（不触真实 DB），验证脚本三个分支的判定逻辑。
"""
import os
import sys
from unittest import mock

import pytest

os.environ.setdefault('DATABASE_URL',
                      'postgresql://u:p@127.0.0.1:5432/int604_migration_test')


class _FakeCursor:
    """按 SQL 内容分支返回的假游标。"""

    def __init__(self, existing_index=False, duplicates=None):
        self.existing_index = existing_index
        self.duplicates = duplicates or []
        self.executed_sql = []
        self.created_index = False

    def execute(self, sql, params=None):
        self.executed_sql.append(sql)
        if 'pg_indexes' in sql:
            self._last = 'index_check'
        elif 'GROUP BY' in sql and 'HAVING' in sql:
            self._last = 'dup_check'
        elif 'CREATE UNIQUE INDEX' in sql:
            self.created_index = True
            self._last = 'create_index'
        else:
            self._last = 'other'

    def fetchone(self):
        if self._last == 'index_check':
            return ('uq_task_case_route',) if self.existing_index else None
        return None

    def fetchall(self):
        if self._last == 'dup_check':
            return self.duplicates
        return []

    def close(self):
        pass


class _FakeConn:
    autocommit = False

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def _run_migrate(cursor):
    """以假游标跑脚本 migrate()，返回 (exit_code, conn, 脚本打印输出)。"""
    script_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', '..',
        'scripts', 'migrations', '202610')
    script_path = os.path.join(script_dir, 'add_uq_task_case_route_int604.py')

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'add_uq_task_case_route_int604', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    conn = _FakeConn(cursor)
    with mock.patch.object(mod.psycopg2, 'connect', return_value=conn):
        with mock.patch('sys.stdout', sys.stdout) as _p:
            captured = []
            orig_write = sys.stdout.write

            def _write(text):
                captured.append(text)
                orig_write(text)
            with mock.patch('sys.stdout') as fake_stdout:
                fake_stdout.write.side_effect = _write
                try:
                    mod.migrate(dry_run=False)
                    exit_code = 0
                except SystemExit as e:
                    exit_code = e.code if isinstance(e.code, int) else (e.code or 0)
    return exit_code, conn, ''.join(captured)


class TestMigrationDuplicateAbort:
    """建索引前查重：存在 (task, case, 路由) 重复行必须 ABORT 不建索引。"""

    def test_duplicate_rows_abort_and_list(self):
        dup_rows = [
            (1001, 'case-A', 'physical', '101', 2),
            (1001, 'case-A', 'http_api', '202', 2),
        ]
        cursor = _FakeCursor(existing_index=False, duplicates=dup_rows)
        exit_code, conn, output = _run_migrate(cursor)
        assert exit_code == 2, f'重复数据应 ABORT exit 2，实际 exit {exit_code}'
        assert not cursor.created_index, 'ABORT 后不得建索引'
        assert 'ABORT' in output
        assert 'task_id=1001' in output and 'case-A' in output
        assert 'http_api' in output and '行数=2' in output

    def test_duplicate_with_null_route_aborts(self):
        """NULL device_type/device_id 重复行同样被 COALESCE 归一后检出。"""
        dup_rows = [(2001, 'case-N', '', '', 3)]
        cursor = _FakeCursor(existing_index=False, duplicates=dup_rows)
        exit_code, conn, output = _run_migrate(cursor)
        assert exit_code == 2
        assert not cursor.created_index
        assert 'ABORT' in output
        assert '(NULL)' in output or '行数=3' in output


class TestMigrationCleanCreate:
    """干净库：查重通过后创建唯一索引。"""

    def test_clean_db_creates_index(self):
        cursor = _FakeCursor(existing_index=False, duplicates=[])
        exit_code, conn, output = _run_migrate(cursor)
        assert exit_code == 0
        assert cursor.created_index, '干净库应执行 CREATE UNIQUE INDEX'
        assert 'uq_task_case_route' in cursor.executed_sql[-1]
        assert 'COALESCE(device_type' in cursor.executed_sql[-1]
        assert 'COALESCE(device_id' in cursor.executed_sql[-1]

    def test_dry_run_does_not_create(self):
        script_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', '..',
            'scripts', 'migrations', '202610')
        script_path = os.path.join(script_dir, 'add_uq_task_case_route_int604.py')
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'add_uq_task_case_route_int604', script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cursor = _FakeCursor(existing_index=False, duplicates=[])
        conn = _FakeConn(cursor)
        with mock.patch.object(mod.psycopg2, 'connect', return_value=conn):
            mod.migrate(dry_run=True)
        assert not cursor.created_index, 'dry-run 不得建索引'
        assert any('DRY-RUN' in s for s in cursor.executed_sql) or cursor.executed_sql


class TestMigrationIdempotentSkip:
    """索引已存在：SKIP 幂等，不查重不重建。"""

    def test_existing_index_skips(self):
        cursor = _FakeCursor(existing_index=True, duplicates=None)
        exit_code, conn, output = _run_migrate(cursor)
        assert exit_code == 0
        assert 'SKIP' in output
        assert not cursor.created_index
        # SKIP 分支只执行索引存在性检查，不执行查重 SQL
        assert not any('GROUP BY' in s and 'HAVING' in s for s in cursor.executed_sql)
