# -*- coding: utf-8 -*-
"""
为 evaluation_dimension_params 表新增 pass_threshold 字段

背景：
  新增 pass_rate 聚合策略（达标率：达标用例数 / 总用例数）。
  达标条件通过 agg_role 区分：
    - pass_le: dimension_value <= pass_threshold（及格线型，越低越好）
    - pass_ge: dimension_value >= pass_threshold（及格线型，越高越好）
    - pass_eq: dimension_value == pass_threshold（精确匹配型）
  pass_threshold 存储阈值/目标值，与 agg_role=pass_le/pass_ge/pass_eq 配合使用。

DDL 变更：
  ALTER TABLE evaluation_dimension_params
      ADD COLUMN pass_threshold DOUBLE PRECISION;

回滚：
  ALTER TABLE evaluation_dimension_params
      DROP COLUMN IF EXISTS pass_threshold;

使用方法：
    python backend/scripts/migrations/202608/add_pass_threshold_to_eval_params.py
    python backend/scripts/migrations/202608/add_pass_threshold_to_eval_params.py --dry-run
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
        print("\n[Step 1] 新增 pass_threshold 列")
        _exec_ddl(
            conn,
            "ALTER TABLE evaluation_dimension_params ADD COLUMN pass_threshold DOUBLE PRECISION",
            "pass_threshold 列已添加",
            "pass_threshold 列已存在"
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
