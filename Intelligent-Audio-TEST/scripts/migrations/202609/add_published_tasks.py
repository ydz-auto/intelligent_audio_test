# -*- coding: utf-8 -*-
"""迁移脚本：新增 published_tasks 表 + test_tasks 追溯字段（已发布任务功能）

功能：
- 建 published_tasks 表（已发布任务：不可变版本快照 / 版本链 / 归档）
- test_tasks 加追溯字段：execution_source / published_task_id / published_task_version
- published_tasks 加 report_snapshot 列（冻结报告/执行数据/评估数据/用例日志）

幂等，可重复执行。

用法:
    python scripts/migrations/202609/add_published_tasks.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('未配置 DATABASE_URL 环境变量（.env 或环境）', file=sys.stderr)
    sys.exit(1)
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _col_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (table, column)
    )
    return cur.fetchone() is not None


def main(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()

    # 1. 已发布任务表
    if not _table_exists(cur, 'published_tasks'):
        sql = """
            CREATE TABLE published_tasks (
                id SERIAL PRIMARY KEY,
                task_group_id INTEGER,
                source_task_id INTEGER,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'published',
                version INTEGER NOT NULL DEFAULT 1,
                is_current BOOLEAN NOT NULL DEFAULT true,
                snapshot_config JSON,
                publish_reason TEXT,
                published_by VARCHAR(50),
                published_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
                archived_by VARCHAR(50),
                archived_at TIMESTAMP WITHOUT TIME ZONE,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
            )
        """
        if dry_run:
            print(f"[DRY-RUN] CREATE TABLE published_tasks")
        else:
            print("[EXEC] CREATE TABLE published_tasks")
            cur.execute(sql)
            for idx_sql in (
                "CREATE INDEX idx_published_task_status ON published_tasks (status)",
                "CREATE INDEX idx_published_task_source ON published_tasks (source_task_id)",
                "CREATE INDEX idx_published_task_is_current ON published_tasks (is_current)",
            ):
                cur.execute(idx_sql)
            conn.commit()
            print("[DONE] 新增表: published_tasks")
    else:
        print("[SKIP] published_tasks 表已存在")

    # 2. 日常任务追溯字段
    for col, col_type in (
        ('execution_source', "VARCHAR(20) DEFAULT 'manual'"),
        ('published_task_id', 'INTEGER'),
        ('published_task_version', 'INTEGER'),
    ):
        if _col_exists(cur, 'test_tasks', col):
            print(f"[SKIP] test_tasks.{col} 列已存在")
            continue
        sql = f"ALTER TABLE test_tasks ADD COLUMN {col} {col_type}"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            conn.commit()
            print(f"[DONE] test_tasks.{col} 已添加")

    # 3. 已发布任务报告快照列（冻结执行产物：报告/用例结果/评估数据/日志）
    if not _col_exists(cur, 'published_tasks', 'report_snapshot'):
        sql = "ALTER TABLE published_tasks ADD COLUMN report_snapshot JSON"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            conn.commit()
            print("[DONE] published_tasks.report_snapshot 已添加")
    else:
        print("[SKIP] published_tasks.report_snapshot 列已存在")

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='新增 published_tasks 表 + test_tasks 追溯字段迁移')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print("=" * 60)
    print("新增 published_tasks 表 + test_tasks 追溯字段迁移")
    print("=" * 60)
    print(f"数据库: {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")
    main(dry_run=args.dry_run)
