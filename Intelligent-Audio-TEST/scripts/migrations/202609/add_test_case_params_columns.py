# -*- coding: utf-8 -*-
"""迁移脚本：test_cases 增加 algorithm_params / reference_params 独立列

背景（对齐 V9.7.10 fix_migration_errors.py Step 1）：
- test_cases 表的参考参数从 config.rounds[] 拆出为独立列 reference_params，
  algorithm_params 也独立成列（模型 testcase_models.py 已定义这两列）
- 本脚本确保存量库具备这两列（幂等，可重复执行）

用法:
    python scripts/migrations/202609/add_test_case_params_columns.py [--dry-run]

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


def _col_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def main(dry_run=False):
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS)
    cur = conn.cursor()
    try:
        columns = (
            ('algorithm_params', 'JSON'),
            ('reference_params', 'JSON'),
        )
        for col, col_type in columns:
            if _col_exists(cur, 'test_cases', col):
                print(f'  [SKIP] test_cases.{col} 列已存在')
                continue
            if dry_run:
                print(f'  [DRY-RUN] 待新增列: test_cases.{col} ({col_type})')
                continue
            cur.execute(f'ALTER TABLE test_cases ADD COLUMN {col} {col_type}')
            conn.commit()
            print(f'  [OK] 新增列: test_cases.{col} ({col_type})')
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='test_cases 增加 algorithm_params / reference_params 列')
    parser.add_argument('--dry-run', action='store_true', help='仅检查列是否存在，不执行 DDL')
    args = parser.parse_args()
    print('=' * 60)
    print('test_cases 增加 algorithm_params / reference_params 独立列')
    print('=' * 60)
    main(dry_run=args.dry_run)
