# -*- coding: utf-8 -*-
"""
为 test_results 表新增 result_data_path 字段

背景：
  result_data 中的大字段（adjusted_reference_params, raw_results, alignment_info）
  迁移到文件存储（static/case_result/{task_id}/{test_case_id}/{device_sn}/result_data.json），
  DB 仅存轻量元数据，result_data_path 存文件路径。

DDL 变更：
  ALTER TABLE test_results ADD COLUMN result_data_path VARCHAR(500);
  ALTER TABLE test_results ALTER COLUMN result_data DROP NOT NULL;

回滚：
  ALTER TABLE test_results DROP COLUMN IF EXISTS result_data_path;
  ALTER TABLE test_results ALTER COLUMN result_data SET NOT NULL;

使用方法：
    python backend/scripts/migrations/202506/add_result_data_path_to_test_results.py
    python backend/scripts/migrations/202506/add_result_data_path_to_test_results.py --dry-run
"""

import os
import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def _exec_ddl(conn, sql, success_msg, skip_msg):
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
        print("\n[Step 1] 新增 result_data_path 列")
        _exec_ddl(
            conn,
            "ALTER TABLE test_results ADD COLUMN result_data_path VARCHAR(500)",
            "result_data_path 列已添加",
            "result_data_path 列已存在"
        )

        print("\n[Step 2] result_data 列改为可空")
        _exec_ddl(
            conn,
            "ALTER TABLE test_results ALTER COLUMN result_data DROP NOT NULL",
            "result_data 列已改为可空",
            "result_data 列已是可空"
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
