# -*- coding: utf-8 -*-
"""迁移脚本：新增分组时长统计读模型表 test_case_group_stats

背景：
    用例分组列表组头「总时长」原先每次遍历组内用例 config + 音频时长现算，
    且只有展开过（组内用例分页加载）的分组才有值。改为 CQRS 读侧物化：
    ``task_service/infrastructure/persistence/models/testcase_models.py``
    的 ``TestCaseGroupStats`` 由 ``create_all`` 在新建库时创建；存量库需要本脚本补表。

DDL（与 ORM 声明对齐）：
    CREATE TABLE IF NOT EXISTS test_case_group_stats (
        group_id VARCHAR(50) PRIMARY KEY,
        total_duration DOUBLE PRECISION NOT NULL DEFAULT 0,
        stats_updated_at TIMESTAMP NOT NULL DEFAULT now()
    )

数据来源：
    不预置数据；分组列表首次读取时惰性重算并回写（Redis 为读缓存），
    用例/分组写路径失效后同样按需重算。

幂等性：
    表已存在即 [SKIP]，可重复执行。

用法:
    python scripts/migrations/202611/add_test_case_group_stats_table.py [--dry-run]
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

TABLE = 'test_case_group_stats'
CREATE_SQL = '''
CREATE TABLE IF NOT EXISTS test_case_group_stats (
    group_id VARCHAR(50) PRIMARY KEY,
    total_duration DOUBLE PRECISION NOT NULL DEFAULT 0,
    stats_updated_at TIMESTAMP NOT NULL DEFAULT now()
)
'''


def _table_exists(cur):
    cur.execute('SELECT to_regclass(%s)', (TABLE,))
    return cur.fetchone()[0] is not None


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
        with conn:
            with conn.cursor() as cur:
                if _table_exists(cur):
                    print(f'[{TABLE}] [SKIP] 表已存在')
                    return 0
                print(f'[{TABLE}] [CREATE] 建表（分组总时长读模型）')
                if dry_run:
                    print(CREATE_SQL)
                    return 0
                cur.execute(CREATE_SQL)
        print(f'[{TABLE}] [DONE] 迁移完成')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'新增 {TABLE} 读模型表')
    parser.add_argument('--dry-run', action='store_true', help='只打印 DDL，不执行')
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
