# -*- coding: utf-8 -*-
"""迁移脚本：test_tasks 补齐列表查询索引（生产副本结构对齐）

背景（2026-11-02 生产热备副本演练）：
    ``task_service/infrastructure/persistence/models/task_models.py`` 的
    ``TestTask.__table_args__`` 声明了 4 个索引，但只由 ``create_all`` 在
    **新建表**时带出；建库早于这些索引声明的存量库（生产热备实测）一个都没有。
    任务列表 / 状态筛选 / 算法类型筛选都靠它们，缺了就是全表顺序扫描。

DDL（与 ORM 声明逐字对齐，索引名一致，便于后续 diff 收敛）：
    CREATE INDEX IF NOT EXISTS idx_task_status ON test_tasks (status)
    CREATE INDEX IF NOT EXISTS idx_task_algorithm_type ON test_tasks (algorithm_type)
    CREATE INDEX IF NOT EXISTS idx_task_created_at ON test_tasks (created_at)
    CREATE INDEX IF NOT EXISTS idx_task_status_deleted ON test_tasks (status, deleted)

幂等性：
    索引已存在即 [SKIP]，可重复执行；表不存在（空库）直接跳过。

用法:
    python scripts/migrations/202611/add_task_list_indexes.py [--dry-run]
"""
import argparse
import os
import sys
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URI')
parsed = urlparse(DATABASE_URL) if DATABASE_URL else None

TABLE = 'test_tasks'

# (索引名, 建索引 DDL)——与 task_models.TestTask.__table_args__ 保持一致
INDEXES = (
    ('idx_task_status',
     'CREATE INDEX IF NOT EXISTS idx_task_status ON test_tasks (status)'),
    ('idx_task_algorithm_type',
     'CREATE INDEX IF NOT EXISTS idx_task_algorithm_type '
     'ON test_tasks (algorithm_type)'),
    ('idx_task_created_at',
     'CREATE INDEX IF NOT EXISTS idx_task_created_at ON test_tasks (created_at)'),
    ('idx_task_status_deleted',
     'CREATE INDEX IF NOT EXISTS idx_task_status_deleted '
     'ON test_tasks (status, deleted)'),
)


def _table_exists(cur):
    cur.execute('SELECT to_regclass(%s)', (TABLE,))
    return cur.fetchone()[0] is not None


def _index_exists(cur, index_name):
    cur.execute('SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s',
                (TABLE, index_name))
    return cur.fetchone() is not None


def main(dry_run=False):
    if parsed is None:
        print('未配置 DATABASE_URL / DATABASE_URI 环境变量', file=sys.stderr)
        return 1
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )
    try:
        cur = conn.cursor()
        if not _table_exists(cur):
            print(f'[SKIP] 表 {TABLE} 不存在（空库由 create_all 建表时带出索引）')
            return 0
        for name, sql in INDEXES:
            if _index_exists(cur, name):
                print(f'[SKIP] 索引 {name} 已存在')
                continue
            if dry_run:
                print(f'[DRY-RUN] {sql}')
                continue
            print(f'[EXEC] {sql}')
            cur.execute(sql)
            conn.commit()
            print(f'[DONE] 索引 {name} 已创建')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='test_tasks 列表查询索引补齐')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
