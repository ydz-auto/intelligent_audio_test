# -*- coding: utf-8 -*-
"""迁移脚本：Report Studio 文档放开来源类型（INT-1763，离线搬运设计文档 §6.2/§6.4）

背景（D0 裁定 INT-1758 A6）：
- 链路 3b 把用户上传的 MD / HTML / PPTX 文件建成 Report Studio 文档
  （``source_type='uploaded_file'``），链路 3c 的 Agent 总结
  （``source_type='agent_summary'``）也可能没有平台报告行、只有父文档；
- 这两类文档没有 ``test_reports.id``，故 ``report_studio_documents.report_id``
  与 ``report_studio_chart_specs.report_id`` 必须放开非空；
- html/pptx 只落文件（``source_file_path`` / ``source_format`` /
  ``source_file_size``），md 直接进 ``markdown_content``，不落文件列。

步骤（全部幂等）：
    ① report_studio_documents ADD source_type VARCHAR(20) NOT NULL
       DEFAULT 'platform_report'（存量行由默认值回填，语义等价）
    ② ADD parent_doc_id VARCHAR(36) NULL
    ③ ADD source_file_path VARCHAR(512) NULL
    ④ ADD source_format VARCHAR(10) NULL
    ⑤ ADD source_file_size BIGINT NULL
    ⑥ report_studio_documents.report_id DROP NOT NULL
    ⑦ report_studio_chart_specs.report_id DROP NOT NULL
    ⑧ 建索引 idx_rs_doc_source_type(source_type) / idx_rs_doc_parent(parent_doc_id)
    ⑨ 结构回读自检

用法：
    python scripts/migrations/202610/alter_report_studio_sources.py            # 预览（默认 dry-run）
    python scripts/migrations/202610/alter_report_studio_sources.py --apply    # 执行
    python scripts/migrations/202610/alter_report_studio_sources.py --rollback # 回滚

幂等性：列/索引存在即 [SKIP]；``DROP NOT NULL`` 先查
``information_schema.columns.is_nullable``，已可空则不再 ALTER。
回滚：反向 DROP COLUMN / DROP INDEX；恢复 ``report_id`` NOT NULL 前先统计
NULL 行（上传文档 / 孤儿 Agent 总结），存在即拒绝并提示先处理这些文档。
"""
import argparse
import os
import sys
from urllib.parse import urlparse

import psycopg2

DOC_TABLE = 'report_studio_documents'
CHART_TABLE = 'report_studio_chart_specs'

# (列名, DDL 定义, 说明)
NEW_COLUMNS = [
    ('source_type', "VARCHAR(20) NOT NULL DEFAULT 'platform_report'",
     '文档来源：platform_report / uploaded_file / agent_summary'),
    ('parent_doc_id', 'VARCHAR(36) NULL', '父文档（Agent 总结 → 源上传文档）'),
    ('source_file_path', 'VARCHAR(512) NULL', 'html/pptx 源文件存储路径'),
    ('source_format', 'VARCHAR(10) NULL', '源文件格式 md / html / pptx'),
    ('source_file_size', 'BIGINT NULL', '源文件字节数'),
]

INDEXES = [
    ('idx_rs_doc_source_type', DOC_TABLE, 'source_type'),
    ('idx_rs_doc_parent', DOC_TABLE, 'parent_doc_id'),
]

# 回滚顺序：先删索引再删列（反序）
ROLLBACK_COLUMNS = [c[0] for c in reversed(NEW_COLUMNS)]


def _connect():
    database_url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URI')
    if not database_url:
        print('未配置 DATABASE_URL / DATABASE_URI 环境变量', file=sys.stderr)
        sys.exit(1)
    parsed = urlparse(database_url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = %s", (table,))
    return cur.fetchone() is not None


def _column_info(cur, table, column):
    """返回 (exists, is_nullable) ；不存在时 is_nullable=None。"""
    cur.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s",
        (table, column))
    row = cur.fetchone()
    if row is None:
        return False, None
    return True, row[0]


def _index_exists(cur, index_name):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,))
    return cur.fetchone() is not None


def _null_report_count(cur, table):
    cur.execute(f"SELECT count(*) FROM {table} WHERE report_id IS NULL")
    return int(cur.fetchone()[0])


def migrate(dry_run=True):
    conn = _connect()
    conn.autocommit = True
    tag = 'DRY' if dry_run else 'APPLY'
    try:
        cur = conn.cursor()
        missing = [t for t in (DOC_TABLE, CHART_TABLE) if not _table_exists(cur, t)]
        if missing:
            print(f"[SKIP] 表不存在，跳过（应由 create_all 建表）: {', '.join(missing)}")
            return

        # ①~⑤ 加列
        for column, ddl, note in NEW_COLUMNS:
            exists, _ = _column_info(cur, DOC_TABLE, column)
            if exists:
                print(f'[SKIP] 列 {DOC_TABLE}.{column} 已存在')
                continue
            sql = f'ALTER TABLE {DOC_TABLE} ADD COLUMN IF NOT EXISTS {column} {ddl}'
            print(f'[{tag}] {sql}  -- {note}')
            if not dry_run:
                cur.execute(sql)

        # ⑥⑦ 放开 report_id 非空
        for table in (DOC_TABLE, CHART_TABLE):
            exists, nullable = _column_info(cur, table, 'report_id')
            if not exists:
                print(f'[SKIP] 表 {table} 无 report_id 列')
                continue
            if nullable == 'YES':
                print(f'[SKIP] {table}.report_id 已可空')
                continue
            sql = f'ALTER TABLE {table} ALTER COLUMN report_id DROP NOT NULL'
            print(f'[{tag}] {sql}')
            if not dry_run:
                cur.execute(sql)

        # ⑧ 索引
        for index_name, table, column in INDEXES:
            if _index_exists(cur, index_name):
                print(f'[SKIP] 索引 {index_name} 已存在')
                continue
            sql = f'CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})'
            print(f'[{tag}] {sql}')
            if not dry_run:
                cur.execute(sql)

        # ⑨ 结构回读自检
        if dry_run:
            print('[DRY] 未执行，跳过结构回读')
            return
        cur.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "ORDER BY ordinal_position", (DOC_TABLE,))
        print(f'[VERIFY] {DOC_TABLE}:')
        for name, dtype, nullable in cur.fetchall():
            print(f'  - {name} {dtype}{" NULL" if nullable == "YES" else " NOT NULL"}')
        cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE source_type = 'platform_report') "
            f"FROM {DOC_TABLE}")
        total, platform = cur.fetchone()
        print(f'[VERIFY] 存量文档 {total} 行，source_type=platform_report {platform} 行')
        for index_name, table, column in INDEXES:
            print(f'[VERIFY] 索引 {index_name} {"✓" if _index_exists(cur, index_name) else "✗"}')
    finally:
        conn.close()


def rollback():
    conn = _connect()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        if not _table_exists(cur, DOC_TABLE):
            print(f'[SKIP] 表 {DOC_TABLE} 不存在')
            return

        # 恢复 NOT NULL 前必须先确认没有 NULL 行（上传文档 / 孤儿 Agent 总结）
        for table in (DOC_TABLE, CHART_TABLE):
            exists, nullable = _column_info(cur, table, 'report_id')
            if not exists or nullable == 'NO':
                continue
            nulls = _null_report_count(cur, table)
            if nulls:
                print(f'[REFUSE] {table} 有 {nulls} 行 report_id IS NULL'
                      f'（上传文档 / Agent 总结），恢复 NOT NULL 前请先处理这些行',
                      file=sys.stderr)
                sys.exit(2)

        for index_name, _table, _column in INDEXES:
            if _index_exists(cur, index_name):
                cur.execute(f'DROP INDEX IF EXISTS {index_name}')
                print(f'[EXEC] DROP INDEX {index_name}')
            else:
                print(f'[SKIP] 索引 {index_name} 不存在')

        for column in ROLLBACK_COLUMNS:
            exists, _ = _column_info(cur, DOC_TABLE, column)
            if not exists:
                print(f'[SKIP] 列 {DOC_TABLE}.{column} 不存在')
                continue
            cur.execute(f'ALTER TABLE {DOC_TABLE} DROP COLUMN IF EXISTS {column}')
            print(f'[EXEC] ALTER TABLE {DOC_TABLE} DROP COLUMN {column}')

        for table in (DOC_TABLE, CHART_TABLE):
            exists, nullable = _column_info(cur, table, 'report_id')
            if exists and nullable == 'YES':
                cur.execute(f'ALTER TABLE {table} ALTER COLUMN report_id SET NOT NULL')
                print(f'[EXEC] {table}.report_id SET NOT NULL')
        print('[DONE] 已回滚到迁移前结构')
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='执行迁移（默认 dry-run 预览）')
    ap.add_argument('--rollback', action='store_true', help='回滚本次迁移')
    args = ap.parse_args()
    if args.rollback:
        rollback()
    else:
        migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
