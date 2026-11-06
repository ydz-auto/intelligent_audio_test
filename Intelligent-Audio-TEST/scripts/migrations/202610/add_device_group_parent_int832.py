# -*- coding: utf-8 -*-
"""迁移脚本：device_groups 嵌套分组 parent_id + 局部唯一索引（INT-832）

功能：
- device_groups 表加 parent_id VARCHAR(50) NULL（根分组为 NULL，存量数据全部为根）
- drop 全局部分唯一索引 uq_device_group_name_active
- 新增两个部分唯一索引（决策 3）：
  - uq_device_group_root_name_active：根分组 name 唯一（deleted=false AND parent_id IS NULL）
  - uq_device_group_child_name_active：同父子分组 (parent_id, name) 唯一（deleted=false AND parent_id IS NOT NULL）

与 device_service/infrastructure/persistence/models/device_models.py DeviceGroup
ORM 元数据（__table_args__ 两个局部部分唯一索引）逐列对齐，
保证全新库（create_all_tables.py）与既有库（本脚本）结构一致。

幂等，可重复执行（列/索引已存在即 SKIP；drop 目标不存在即 SKIP）。

用法:
    python scripts/migrations/202610/add_device_group_parent_int832.py [--dry-run]

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


def _column_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def _index_exists(cur, index):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index,))
    return cur.fetchone() is not None


def main(dry_run=False):
    import psycopg2
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()
    total_steps = 0

    # 1. device_groups 加 parent_id 列（根分组 NULL；存量数据即全部为根）
    if _column_exists(cur, 'device_groups', 'parent_id'):
        print('SKIP: 列 device_groups.parent_id 已存在')
    else:
        print('APPLY: device_groups 加列 parent_id VARCHAR(50) NULL')
        if not dry_run:
            cur.execute('ALTER TABLE device_groups ADD COLUMN parent_id VARCHAR(50) NULL')
        total_steps += 1

    # 2. drop 全局唯一索引 uq_device_group_name_active
    if _index_exists(cur, 'uq_device_group_name_active'):
        print('DROP: uq_device_group_name_active')
        if not dry_run:
            cur.execute('DROP INDEX IF EXISTS uq_device_group_name_active')
        total_steps += 1
    else:
        print('SKIP: 索引 uq_device_group_name_active 不存在（已替换）')

    # 3. 根分组 name 部分唯一索引
    if _index_exists(cur, 'uq_device_group_root_name_active'):
        print('SKIP: 索引 uq_device_group_root_name_active 已存在')
    else:
        print('APPLY: 创建 uq_device_group_root_name_active（根分组 name 唯一）')
        if not dry_run:
            cur.execute(
                'CREATE UNIQUE INDEX uq_device_group_root_name_active '
                'ON device_groups (name) '
                "WHERE deleted = false AND parent_id IS NULL"
            )
        total_steps += 1

    # 4. 同父子分组 (parent_id, name) 部分唯一索引
    if _index_exists(cur, 'uq_device_group_child_name_active'):
        print('SKIP: 索引 uq_device_group_child_name_active 已存在')
    else:
        print('APPLY: 创建 uq_device_group_child_name_active（同父子分组 (parent_id, name) 唯一）')
        if not dry_run:
            cur.execute(
                'CREATE UNIQUE INDEX uq_device_group_child_name_active '
                'ON device_groups (parent_id, name) '
                "WHERE deleted = false AND parent_id IS NOT NULL"
            )
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
    parser = argparse.ArgumentParser(description='device_groups parent_id + 局部唯一索引迁移（INT-832）')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
