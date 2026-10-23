# -*- coding: utf-8 -*-
"""迁移脚本：新建 report_export_records 表（报告导出历史，INT-1555）

背景（INT-1609 缺陷）：
- ReportExportRecord PO（report_service）随 INT-1555 落库，但当时只靠
  scripts/create_all_tables.py 的 create_all 建表；INT-1565 的迁移守卫
  （tests/unit/test_int1565_schema_migration_guard.py）要求「ORM 元数据里
  有、基线快照 tests/data/schema_baseline.json 里没有」的列必须在
  scripts/migrations/ 有对应迁移文本，而基线快照采集于 INT-1555 之前，
  整张新表被当作缺迁移 → 守卫红，阻断 INT-1568 集成推送。
- 本脚本按守卫约定补一条建表迁移：create_all 只建「缺失的表」，本步对
  建库早于 INT-1555 的存量库是结构自愈兜底；全新库 create_all 已含本表，
  执行本脚本为全 [SKIP]。

DDL 与 report_service ORM 元数据
（report_service/infrastructure/persistence/models/report_export_record_models.py）
逐列对齐：
    id BIGSERIAL PK / report_ids JSON NOT NULL / scope VARCHAR(255) NOT NULL /
    format VARCHAR(10) NOT NULL / status VARCHAR(20) NOT NULL / error TEXT NULL /
    filename VARCHAR(255) NULL / created_by BIGINT NULL /
    created_at TIMESTAMP NOT NULL DEFAULT now()
索引 idx_report_export_created_at(created_at) /
     idx_report_export_created_by(created_by)。
无外键：202608 基线后引用完整性由应用层管理。

步骤（幂等）：
    ① CREATE TABLE IF NOT EXISTS report_export_records (...)
    ② CREATE INDEX IF NOT EXISTS 两个索引
    ③ 结构自检（information_schema 回读列数 + 索引）

用法:
    python scripts/migrations/202610/add_report_export_records_int1555.py [--dry-run]

幂等性:
    表/索引已存在即 [SKIP]，重复执行不报错、不产生重复数据。
"""
import argparse
import os
import sys

import psycopg2

TABLE = 'report_export_records'

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id BIGSERIAL PRIMARY KEY,
    report_ids JSON NOT NULL,
    scope VARCHAR(255) NOT NULL,
    format VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    error TEXT NULL,
    filename VARCHAR(255) NULL,
    created_by BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""

INDEXES = [
    ('idx_report_export_created_at', TABLE, 'created_at'),
    ('idx_report_export_created_by', TABLE, 'created_by'),
]


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _index_exists(cur, table, index):
    cur.execute(
        "SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s",
        (table, index))
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()

    # ① 建表
    if _table_exists(cur, TABLE):
        print(f'[SKIP] 表 {TABLE} 已存在')
    elif dry_run:
        print(f'[DRY-RUN] CREATE TABLE IF NOT EXISTS {TABLE}')
    else:
        print(f'[EXEC] CREATE TABLE IF NOT EXISTS {TABLE}')
        cur.execute(CREATE_TABLE_SQL.strip())
        print(f'[DONE] 表 {TABLE} 已就绪')

    # ② 索引
    for index_name, table, col_name in INDEXES:
        if _index_exists(cur, table, index_name):
            print(f'[SKIP] 索引 {index_name} 已存在')
            continue
        idx_sql = (f'CREATE INDEX IF NOT EXISTS {index_name} '
                   f'ON {table} ({col_name})')
        if dry_run:
            print(f'[DRY-RUN] {idx_sql}')
        else:
            print(f'[EXEC] {idx_sql}')
            cur.execute(idx_sql)
            print(f'[DONE] 索引 {index_name} 已就绪')

    # ③ 结构自检（information_schema 回读）
    if not dry_run:
        cur.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_name = %s "
            "ORDER BY ordinal_position", (TABLE,))
        cols = cur.fetchall()
        print(f'[VERIFY] {TABLE}: {len(cols)} 列')
        for name, dtype, nullable in cols:
            print(f'  - {name} {dtype}{" NULL" if nullable == "YES" else " NOT NULL"}')

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='report_export_records 报告导出历史表（INT-1555）迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
