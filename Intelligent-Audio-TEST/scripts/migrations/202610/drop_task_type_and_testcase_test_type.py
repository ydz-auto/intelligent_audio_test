# -*- coding: utf-8 -*-
"""迁移脚本：废弃字段收尾 —— 回填用例级路由列并删除 task.type / test_type / published_tasks.type

背景（差异#2 收尾，见 doc/功能设计文档/01_测试执行/01_UseCase总览.md §0.1/§0.7 适配说明
与 UC-0903 验收"废弃字段不再读写"）：
- task_case_relations.device_type：执行路由唯一依据。历史行为 NULL 时按源任务
  test_tasks.type 回填（api → http_api / e2e → physical / 其他 → physical），
  回填后执行链路不再读取 task.type。
- test_tasks.type / test_cases.test_type / published_tasks.type：整体废弃，直接删除列。
  合并容器任务改由 task_merge_relations(merged_task_id) 存在性标识，
  用例不再区分类型（用例纯数据原则，07_用例管理/用例管理功能设计文档.md §1.1）。

用法:
    python scripts/migrations/202610/drop_task_type_and_testcase_test_type.py [--dry-run]

幂等性:
    重复执行安全：回填仅处理 device_type IS NULL 的行；列已不存在即 [SKIP]。
"""
import sys
import os

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password

# 待删除列: (table, column)
DROP_COLUMNS = [
    ('test_tasks', 'type'),
    ('test_cases', 'test_type'),
    ('published_tasks', 'type'),
]

# device_type 回填映射（源任务 test_tasks.type → 用例级 device_type）
BACKFILL_SQL = """
UPDATE task_case_relations tcr
SET device_type = CASE t.type
    WHEN 'api' THEN 'http_api'
    WHEN 'e2e' THEN 'physical'
    ELSE 'physical'
END
FROM test_tasks t
WHERE tcr.task_id = t.id
  AND tcr.device_type IS NULL
"""


def column_exists(cur, table, column):
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

    # ① 回填 device_type（必须在删列之前执行）
    if column_exists(cur, 'test_tasks', 'type'):
        sql = BACKFILL_SQL
        if dry_run:
            cur.execute(
                """
                SELECT count(*) FROM task_case_relations tcr
                JOIN test_tasks t ON tcr.task_id = t.id
                WHERE tcr.device_type IS NULL
                """)
            print(f"[DRY-RUN] 将回填 {cur.fetchone()[0]} 行 task_case_relations.device_type")
        else:
            print("[EXEC] 回填 task_case_relations.device_type（api→http_api / e2e→physical）")
            cur.execute(sql)
            print(f"[DONE] 回填完成，涉及 {cur.rowcount} 行")
    else:
        print("[SKIP] test_tasks.type 已删除，device_type 无历史 NULL 回填需求"
              "（如仍有 NULL 行请先排查来源）")

    # ② 删除废弃列
    for table, column in DROP_COLUMNS:
        if not column_exists(cur, table, column):
            print(f"[SKIP] {table}.{column} 已不存在")
            continue
        sql = f"ALTER TABLE {table} DROP COLUMN {column}"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            print(f"[DONE] {table}.{column} 已删除")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)
