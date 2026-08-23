# -*- coding: utf-8 -*-
"""
为 report_summary_meta 表新增 field_mappings 列

背景：
  报告生成时需要快照 field_mapping（算法输出字段配置），
  避免后续配置变更影响已生成报告的展示。
  field_mappings 按 algorithm_type 分组存储，JSON 格式。

DDL 变更：
  ALTER TABLE report_summary_meta
      ADD COLUMN field_mappings JSON;

回滚：
  ALTER TABLE report_summary_meta
      DROP COLUMN IF EXISTS field_mappings;

使用方法：
    python backend/scripts/migrations/202608/add_field_mappings_to_report_summary_meta.py
    python backend/scripts/migrations/202608/add_field_mappings_to_report_summary_meta.py --dry-run
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
        print("\n[Step 1] 新增 field_mappings 列")
        _exec_ddl(
            conn,
            "ALTER TABLE report_summary_meta ADD COLUMN field_mappings JSON",
            "field_mappings 列已添加",
            "field_mappings 列已存在"
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
