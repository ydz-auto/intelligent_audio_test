# -*- coding: utf-8 -*-
"""
为 test_result_dimensions 表新增 round_number 字段

DDL 变更：
  ALTER TABLE test_result_dimensions ADD COLUMN round_number INTEGER DEFAULT NULL;
  CREATE INDEX idx_trd_round ON test_result_dimensions(test_result_id, round_number);

数据修复：
  将已有的 voice_llm 单轮结果的 round_number 设为 0

回滚：
  DROP INDEX IF EXISTS idx_trd_round;
  ALTER TABLE test_result_dimensions DROP COLUMN IF EXISTS round_number;

使用方法：
    python backend/scripts/migrations/202606/add_round_number_to_result_dimensions.py
    python backend/scripts/migrations/202606/add_round_number_to_result_dimensions.py --dry-run
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
        if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
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
        # Step 1: 新增 round_number 列
        print("\n[Step 1] 新增 round_number 列")
        _exec_ddl(
            conn,
            "ALTER TABLE test_result_dimensions ADD COLUMN round_number INTEGER DEFAULT NULL",
            "新增 round_number 列成功",
            "round_number 列已存在"
        )

        # Step 2: 创建复合索引
        print("\n[Step 2] 创建复合索引 idx_trd_round")
        _exec_ddl(
            conn,
            "CREATE INDEX idx_trd_round ON test_result_dimensions(test_result_id, round_number)",
            "索引 idx_trd_round 创建成功",
            "索引 idx_trd_round 已存在"
        )

        # Step 3: 数据修复 - 已有的 voice_llm 结果设置 round_number=0
        print("\n[Step 3] 数据修复: 已有 voice_llm 结果设置 round_number=0")
        result = conn.execute(text(
            "UPDATE test_result_dimensions SET round_number = 0 "
            "WHERE round_number IS NULL AND algorithm_type = 'voice_llm'"
        ))
        print(f"  更新了 {result.rowcount} 条 voice_llm 结果记录")

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
