# -*- coding: utf-8 -*-
"""
废弃 test_cases 表的 algorithm_params 和 reference_params 列

背景：
  数据已迁移到 config JSON 的 rounds[] 结构中：
  - algorithm_params → config.rounds[].algorithmParams
  - reference_params → config.rounds[].referenceParamsPath（文件存储）

DDL 变更：
  ALTER TABLE test_cases DROP COLUMN IF EXISTS algorithm_params;
  ALTER TABLE test_cases DROP COLUMN IF EXISTS reference_params;

回滚：
  ALTER TABLE test_cases ADD COLUMN algorithm_params JSON;
  ALTER TABLE test_cases ADD COLUMN reference_params JSON;

使用方法：
    python backend/scripts/migrations/202506/drop_testcase_deprecated_columns.py
    python backend/scripts/migrations/202506/drop_testcase_deprecated_columns.py --dry-run
"""

import os
import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def _exec_ddl(conn, sql, success_msg, skip_msg):
    """在独立 SAVEPOINT 中执行 DDL，避免失败污染外层事务"""
    savepoint = conn.begin_nested()
    try:
        conn.execute(text(sql))
        savepoint.commit()
        print(f"  [OK] {success_msg}")
    except Exception as e:
        savepoint.rollback()
        if 'does not exist' in str(e).lower() or 'already' in str(e).lower():
            print(f"  [SKIP] {skip_msg}")
        else:
            raise


def main():
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("=== DRY-RUN MODE ===")

    eng = create_engine(POSTGRES_URI)
    conn = eng.connect()
    trans = conn.begin()

    try:
        # Step 1: 检查列是否存在
        print("\n[Step 1] 检查 test_cases 表列状态")
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'test_cases' AND column_name IN ('algorithm_params', 'reference_params') "
            "ORDER BY column_name"
        ))
        existing_cols = [row[0] for row in result]
        print(f"  当前存在的待删除列: {existing_cols if existing_cols else '(无)'}")

        if not existing_cols:
            print("\n[INFO] 列已不存在，无需迁移")
            trans.rollback()
            return

        # Step 2: 检查是否有非空数据（仅警告，不阻止迁移）
        print("\n[Step 2] 检查列中是否有非空数据")
        for col in existing_cols:
            result = conn.execute(text(
                f"SELECT COUNT(*) FROM test_cases WHERE {col} IS NOT NULL"
            ))
            count = result.scalar()
            if count > 0:
                print(f"  [WARN] {col} 列有 {count} 条非空数据，删除后不可恢复")
            else:
                print(f"  [OK] {col} 列无非空数据")

        # Step 3: 删除 algorithm_params 列
        print("\n[Step 3] 删除 algorithm_params 列")
        _exec_ddl(
            conn,
            "ALTER TABLE test_cases DROP COLUMN IF EXISTS algorithm_params",
            "algorithm_params 列已删除",
            "algorithm_params 列不存在"
        )

        # Step 4: 删除 reference_params 列
        print("\n[Step 4] 删除 reference_params 列")
        _exec_ddl(
            conn,
            "ALTER TABLE test_cases DROP COLUMN IF EXISTS reference_params",
            "reference_params 列已删除",
            "reference_params 列不存在"
        )

        if dry_run:
            trans.rollback()
            print("\n[DRY-RUN] 已回滚所有变更")
        else:
            trans.commit()
            print("\n[SUCCESS] 所有变更已提交")

    except Exception as e:
        trans.rollback()
        print(f"\n[ERROR] 迁移失败，已回滚: {e}")
        raise
    finally:
        conn.close()
        eng.dispose()


if __name__ == '__main__':
    main()
