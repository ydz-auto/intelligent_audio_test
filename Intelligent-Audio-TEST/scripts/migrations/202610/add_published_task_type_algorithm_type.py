# -*- coding: utf-8 -*-
"""迁移脚本：published_tasks 补 algorithm_type 列并回填历史数据（INT-148）

背景（V9.7.10 对齐缺陷包，已发布任务列表筛选端到端缺失）：
- published_tasks.algorithm_type：发布时从快照 algorithmType 冻结的冗余列，
  列表按算法筛选直查本列（对齐 V9.7.10 add_published_task_algorithm_type 迁移）。
- published_tasks.type（任务类型 api/e2e）随任务类型概念废除一并删除
  （见 drop_published_task_type_and_case_derived_test_type.py），本脚本不再补该列。

用法:
    python scripts/migrations/202610/add_published_task_type_algorithm_type.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]；回填仅更新 NULL 行。
"""
import sys
import os
import json

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
parsed = urlparse(DATABASE_URL) if DATABASE_URL else None
DB_HOST = parsed.hostname if parsed else None
DB_PORT = (parsed.port or 5432) if parsed else 5432
DB_NAME = parsed.path.lstrip('/') if parsed else None
DB_USER = parsed.username if parsed else None
DB_PASS = parsed.password if parsed else None

TABLE = 'published_tasks'

COLUMNS = [
    ('algorithm_type', 'VARCHAR(50)'),
]


def _column_exists(cur, table, column):
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    for col_name, col_type in COLUMNS:
        if _column_exists(cur, TABLE, col_name):
            print(f"[SKIP] {TABLE}.{col_name} 已存在")
            continue
        alter = f"ALTER TABLE {TABLE} ADD COLUMN {col_name} {col_type}"
        if dry_run:
            print(f"[DRY-RUN] {alter}")
        else:
            print(f"[EXEC] {alter}")
            cur.execute(alter)
            print(f"[DONE] {TABLE}.{col_name} 已添加")

    if not dry_run:
        # 索引（列创建后建；对齐 V9.7.10 idx_published_task_algorithm_type）
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_published_task_algorithm_type
            ON published_tasks(algorithm_type)
        """)
        # 回填：仅处理 algorithm_type 为 NULL 的历史行
        cur.execute(f"""
            SELECT id, snapshot_config FROM {TABLE}
            WHERE algorithm_type IS NULL
        """)
        rows = cur.fetchall()
        updated = 0
        for row_id, snapshot_raw in rows:
            try:
                snapshot = snapshot_raw if isinstance(snapshot_raw, dict) else (
                    json.loads(snapshot_raw) if snapshot_raw else {})
            except (TypeError, ValueError):
                snapshot = {}
            algorithm_type = snapshot.get('algorithmType') if isinstance(snapshot, dict) else None
            cur.execute(f"""
                UPDATE {TABLE}
                SET algorithm_type = %s
                WHERE id = %s
            """, (algorithm_type, row_id))
            updated += 1
        print(f"[DONE] 历史数据回填 {updated} 行")

    cur.close()
    conn.close()


if __name__ == '__main__':
    if not DATABASE_URL:
        print('错误: 未配置 DATABASE_URL 环境变量')
        sys.exit(1)
    migrate(dry_run='--dry-run' in sys.argv)
    print('迁移完成')
