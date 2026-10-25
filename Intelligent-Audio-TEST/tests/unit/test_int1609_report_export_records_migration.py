# -*- coding: utf-8 -*-
"""INT-1609：report_export_records 建表迁移（㊴）静态守卫。

背景：INT-1555 新增整张 report_export_records 表（报告导出历史）时只靠
create_all 建表，没补迁移脚本；INT-1565 的迁移守卫
（tests/unit/test_int1565_schema_migration_guard.py）基线快照采集于 INT-1555
之前，不含该表 → 整表列被判「缺迁移」，filename / report_ids 两个列名又恰好
没在其它迁移文本里出现，守卫红。

本文件把修复钉死（纯静态，不连库）：
1. 迁移 DDL 的列集合 / 可空性 / 索引名必须与 ORM 元数据逐项对齐
   （避免建表迁移与模型漂移，形成第二份真相）；
2. DDL 必须幂等（CREATE TABLE/INDEX IF NOT EXISTS），引导链每次部署都会跑；
3. docker/db_bootstrap_entrypoint.py 的 BOOTSTRAP_STEPS 必须包含该步
   （只写脚本不接引导链 = 存量库永远不建表，INT-1565 同类根因）。

DB：无（模型元数据 + 迁移文本 + 引导链常量）。
"""
import importlib.util
import os
import re

import pytest

# 导入 PO 需要 BaseConfig（OSS 凭据仅 import 期校验非空，本守卫不触网）
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202610',
    'add_report_export_records_int1555.py')
_MIGRATION_REL = 'scripts/migrations/202610/add_report_export_records_int1555.py'
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')
_TABLE = 'report_export_records'


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def migration():
    assert os.path.isfile(_MIGRATION), f'建表迁移缺失：{_MIGRATION_REL}'
    return _load_module(_MIGRATION, 'int1609_report_export_migration')


@pytest.fixture(scope='module')
def orm_table():
    from report_service.infrastructure.persistence.models. \
        report_export_record_models import ReportExportRecord
    return ReportExportRecord.__table__


def _ddl_columns(sql):
    """从 CREATE TABLE 文本取 {列名: 列定义尾部}（本脚本 DDL 为四空格缩进单行列）。"""
    body = sql[sql.index('(') + 1:sql.rindex(')')]
    columns = {}
    for raw in body.splitlines():
        match = re.match(r'^\s{4}([a-z_][a-z0-9_]*)\s+(.+?),?\s*$', raw)
        if match:
            columns[match.group(1)] = match.group(2).rstrip(',')
    return columns


def test_ddl_columns_match_orm(migration, orm_table):
    columns = _ddl_columns(migration.CREATE_TABLE_SQL)
    assert migration.TABLE == _TABLE
    assert set(columns) == {c.name for c in orm_table.columns}, (
        '建表迁移列集合与 ReportExportRecord ORM 不一致')
    for column in orm_table.columns:
        ddl = columns[column.name]
        ddl_not_null = 'NOT NULL' in ddl or 'PRIMARY KEY' in ddl
        assert ddl_not_null == (not column.nullable), (
            f'{_TABLE}.{column.name} 可空性与 ORM 不一致：DDL={ddl!r} '
            f'ORM nullable={column.nullable}')


def test_ddl_indexes_match_orm(migration, orm_table):
    ddl_indexes = {index_name for index_name, _table, _col in migration.INDEXES}
    assert ddl_indexes == {index.name for index in orm_table.indexes}, (
        '建表迁移索引名与 ORM __table_args__ 不一致')
    for index_name, table, column in migration.INDEXES:
        assert table == _TABLE
        assert column in orm_table.columns


def test_ddl_is_idempotent(migration):
    assert 'CREATE TABLE IF NOT EXISTS' in migration.CREATE_TABLE_SQL
    with open(_MIGRATION, encoding='utf-8') as f:
        text = f.read()
    assert 'CREATE INDEX IF NOT EXISTS' in text
    # 引导链不带 --apply 执行，脚本必须默认执行且幂等（不是 dry-run 默认）
    assert "add_argument('--dry-run'" in text


def test_bootstrap_steps_include_table_migration():
    steps = [list(step) for step in
             _load_module(_BOOTSTRAP_PATH,
                          'int1609_db_bootstrap').BOOTSTRAP_STEPS]
    assert any(_MIGRATION_REL in step for step in steps), (
        f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：建库早于 INT-1555 的存量库'
        '不会建 report_export_records，导出历史接口即 UndefinedTable（INT-1609）')
