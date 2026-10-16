# -*- coding: utf-8 -*-
"""
补齐软删审计列：test_cases / test_case_groups / audios / test_tasks
新增 deleted_at / created_by_user_id / updated_by_user_id 三列（若缺失）。

背景：
    这四张表在生产库中已有 deleted_at / created_by_user_id / updated_by_user_id 列，
    但 ORM 模型从未声明、业务代码从未写入（全表 0 写入，软删动作无审计痕迹）。
    VEGA-32 将三列纳入 ORM（backend/models/soft_delete.py: SoftDeleteMixin），
    本脚本负责把**测试库**等由 create_all 建出的库补齐（create_all 只建表不改表）。
    生产库执行时为幂等空操作。

幂等，可重复执行。

用法（在 Intelligent-Audio-TEST 目录下执行）：
    python backend/scripts/migrations/202610/add_soft_delete_audit_columns.py
    # 测试库：
    DATABASE_URI=postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test_test \
        python backend/scripts/migrations/202610/add_soft_delete_audit_columns.py
"""
import os
import sys

from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

TABLES = ('test_cases', 'test_case_groups', 'audios', 'test_tasks')

# 列名 -> DDL 类型（与 backend/models/soft_delete.py 的 SoftDeleteMixin 一致）
COLUMNS = {
    'deleted_at': 'TIMESTAMP WITHOUT TIME ZONE',
    'created_by_user_id': 'BIGINT',
    'updated_by_user_id': 'BIGINT',
}


def _table_exists(conn, table):
    return conn.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :t"
    ), {'t': table}).fetchone() is not None


def _column_exists(conn, table, column):
    return conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
    ), {'t': table, 'c': column}).fetchone() is not None


def main():
    engine = create_engine(POSTGRES_URI)
    added, skipped, missing_tables = [], [], []
    try:
        with engine.begin() as conn:
            for table in TABLES:
                if not _table_exists(conn, table):
                    missing_tables.append(table)
                    continue
                for column, ddl_type in COLUMNS.items():
                    if _column_exists(conn, table, column):
                        skipped.append(f'{table}.{column}')
                        continue
                    conn.execute(text(
                        f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}'
                    ))
                    added.append(f'{table}.{column}')
    finally:
        engine.dispose()

    print(f'目标库: {POSTGRES_URI}')
    print(f'新增列 {len(added)} 个: {added or "（无，已全部存在）"}')
    print(f'已存在列 {len(skipped)} 个')
    if missing_tables:
        print(f'表不存在（跳过）: {missing_tables}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
