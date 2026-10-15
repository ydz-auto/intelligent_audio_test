# -*- coding: utf-8 -*-
"""迁移脚本：挑选合并四表（INT-339 任务结果 Cherry-Pick 挑选合并）

功能：
- 建 cherry_pick_cart_items 表（per-user 购物车，引用源结果 + 溯源快照）
- 建 task_cherry_pick_relations 表（cherry-pick 容器任务 ↔ result_id 引用关系，
  引用方案 A——容器分类存在性判定，test_results.task_id 禁止改挂）
- 建 cherry_pick_sets / cherry_pick_set_items 表（挑选集另存/恢复两向）

幂等，可重复执行（全部 CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS）。

用法:
    python scripts/migrations/202610/add_cherry_pick_tables_int339.py [--dry-run]

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


def _index_exists(cur, index_name):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,))
    return cur.fetchone() is not None


def _exec(cur, conn, sql, dry_run):
    if dry_run:
        print(f"[DRY-RUN] {sql.strip()[:120]}")
        return
    print(f"[EXEC] {sql.strip()[:120]}")
    cur.execute(sql)
    conn.commit()


CART_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS cherry_pick_cart_items (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        result_id INTEGER NOT NULL,
        source_task_id INTEGER NOT NULL,
        source_task_name VARCHAR(255),
        source_case_id VARCHAR(50),
        source_device_id INTEGER,
        source_api_id INTEGER,
        execution_status VARCHAR(20),
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_cherry_cart_user_result UNIQUE (user_id, result_id)
    )
"""

RELATION_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS task_cherry_pick_relations (
        id BIGSERIAL PRIMARY KEY,
        cherry_pick_task_id INTEGER NOT NULL REFERENCES test_tasks(id),
        result_id INTEGER NOT NULL,
        source_task_id INTEGER NOT NULL,
        source_task_name VARCHAR(255),
        source_case_id VARCHAR(50),
        source_device_id INTEGER,
        source_api_id INTEGER,
        created_by_user_id BIGINT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_cherry_rel_task_result UNIQUE (cherry_pick_task_id, result_id)
    )
"""

SETS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS cherry_pick_sets (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        created_by_user_id BIGINT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
    )
"""

SET_ITEMS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS cherry_pick_set_items (
        id BIGSERIAL PRIMARY KEY,
        set_id BIGINT NOT NULL REFERENCES cherry_pick_sets(id),
        result_id INTEGER NOT NULL,
        source_task_id INTEGER NOT NULL,
        source_task_name VARCHAR(255),
        source_case_id VARCHAR(50),
        source_device_id INTEGER,
        source_api_id INTEGER,
        execution_status VARCHAR(20),
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_cherry_set_item_result UNIQUE (set_id, result_id)
    )
"""

INDEXES = (
    ('idx_cherry_cart_user', 'CREATE INDEX IF NOT EXISTS idx_cherry_cart_user ON cherry_pick_cart_items (user_id)'),
    ('idx_cherry_cart_user_source', 'CREATE INDEX IF NOT EXISTS idx_cherry_cart_user_source ON cherry_pick_cart_items (user_id, source_task_id)'),
    ('idx_cherry_rel_container', 'CREATE INDEX IF NOT EXISTS idx_cherry_rel_container ON task_cherry_pick_relations (cherry_pick_task_id)'),
    ('idx_cherry_rel_source_task', 'CREATE INDEX IF NOT EXISTS idx_cherry_rel_source_task ON task_cherry_pick_relations (source_task_id)'),
    ('idx_cherry_set_user', 'CREATE INDEX IF NOT EXISTS idx_cherry_set_user ON cherry_pick_sets (user_id)'),
    ('idx_cherry_set_item_set', 'CREATE INDEX IF NOT EXISTS idx_cherry_set_item_set ON cherry_pick_set_items (set_id)'),
)


def main():
    parser = argparse.ArgumentParser(description='INT-339 挑选合并四表迁移')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print(f"数据库: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()

    for name, sql in (
        ('cherry_pick_cart_items', CART_TABLE_SQL),
        ('task_cherry_pick_relations', RELATION_TABLE_SQL),
        ('cherry_pick_sets', SETS_TABLE_SQL),
        ('cherry_pick_set_items', SET_ITEMS_TABLE_SQL),
    ):
        if _table_exists(cur, name):
            print(f"  [SKIP] 表 {name} 已存在")
            continue
        _exec(cur, conn, sql, args.dry_run)

    for index_name, sql in INDEXES:
        if _index_exists(cur, index_name):
            continue
        _exec(cur, conn, sql, args.dry_run)

    cur.close()
    conn.close()
    print('\n迁移完成!' if not args.dry_run else '\n[DRY-RUN] 未实际写入数据。')


if __name__ == '__main__':
    main()
