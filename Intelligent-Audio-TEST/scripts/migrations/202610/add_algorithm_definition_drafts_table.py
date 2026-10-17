# -*- coding: utf-8 -*-
"""迁移脚本：algorithm_definition_drafts 表（INT-589 草稿存储模型）

功能：
- 建 algorithm_definition_drafts 表（算法定义草稿 JSON 快照）
- 建 algorithm_type 唯一索引

DDL 与 algorithm_service/infrastructure/persistence/models/algorithm_models.py
的 AlgorithmDefinitionDraft ORM 元数据逐列对齐（client-side default 不入
DDL，server_default 仅 func.now() 时间戳列），保证全新库（create_all_tables.py）
与既有库（本脚本）结构一致。

幂等，可重复执行（表/索引已存在即 SKIP）。

用法:
    python scripts/migrations/202610/add_algorithm_definition_drafts_table.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse

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


def _index_exists(cur, index):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
    return cur.fetchone() is not None


TABLE_DDL = {
    'algorithm_definition_drafts': """
        CREATE TABLE algorithm_definition_drafts (
            id SERIAL PRIMARY KEY,
            algorithm_type VARCHAR(50) NOT NULL,
            snapshot TEXT,
            created_by_user_id BIGINT,
            updated_by_user_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """,
}

INDEX_DDL = [
    ('uq_algorithm_definition_draft_type',
     'CREATE UNIQUE INDEX uq_algorithm_definition_draft_type '
     'ON algorithm_definition_drafts (algorithm_type)'),
]


def main(dry_run=False):
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()
    total_steps = 0

    for table, ddl in TABLE_DDL.items():
        if _table_exists(cur, table):
            print(f'SKIP: 表 {table} 已存在')
            continue
        print(f'APPLY: 创建表 {table}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    for index, ddl in INDEX_DDL:
        if _index_exists(cur, index):
            print(f'SKIP: 索引 {index} 已存在')
            continue
        print(f'APPLY: 创建索引 {index}')
        if not dry_run:
            cur.execute(ddl)
        total_steps += 1

    if dry_run:
        conn.rollback()
        print(f'[DRY-RUN] 共 {total_steps} 步待执行')
    else:
        conn.commit()
        print(f'完成：共执行 {total_steps} 步')
    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='algorithm_definition_drafts 表迁移（INT-589）'
    )
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
