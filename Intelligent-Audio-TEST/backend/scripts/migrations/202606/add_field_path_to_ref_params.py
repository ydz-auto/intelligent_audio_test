# -*- coding: utf-8 -*-
"""
为 algorithm_reference_params 表添加 field_path 和 merge_mode 字段

功能：
1. 添加 field_path 字段 - 标注数据字段路径（如 model / segments[].emotion）
2. 添加 merge_mode 字段 - 多音频合并方式（join/collect/first）

使用方法：
    python add_field_path_to_ref_params.py

依赖：
    pip install sqlalchemy psycopg2-binary

注意：此脚本可重复执行
"""

import os
import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def migrate():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        print("=== 添加 field_path 和 merge_mode 字段 ===\n")

        # 1. 添加 field_path 列
        try:
            conn.execute(text(
                "ALTER TABLE algorithm_reference_params "
                "ADD COLUMN field_path VARCHAR(255)"
            ))
            print("  + algorithm_reference_params.field_path VARCHAR(255)")
        except Exception as e:
            msg = str(e).lower()
            if 'already exists' in msg or 'duplicate column' in msg:
                print("  - field_path 列已存在")
            else:
                raise

        # 2. 添加 merge_mode 列
        try:
            conn.execute(text(
                "ALTER TABLE algorithm_reference_params "
                "ADD COLUMN merge_mode VARCHAR(20) DEFAULT 'join'"
            ))
            print("  + algorithm_reference_params.merge_mode VARCHAR(20) DEFAULT 'join'")
        except Exception as e:
            msg = str(e).lower()
            if 'already exists' in msg or 'duplicate column' in msg:
                print("  - merge_mode 列已存在")
            else:
                raise

        # 3. 为现有记录设置默认值
        result = conn.execute(text(
            "UPDATE algorithm_reference_params SET merge_mode = 'join' WHERE merge_mode IS NULL"
        ))
        if result.rowcount > 0:
            print(f"  ~ 已为 {result.rowcount} 条记录设置 merge_mode = 'join'")

        print("\n=== 迁移完成 ===")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}为 algorithm_reference_params 添加 field_path 和 merge_mode")
    print("=" * 60)
    print()
    print(f"数据库: {POSTGRES_URI[:POSTGRES_URI.rindex('@')]}@localhost/...")
    print()

    if not dry_run:
        confirm = input("是否继续？(y/N): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            sys.exit(0)

    try:
        migrate()
    except Exception as e:
        print(f"\n迁移失败: {e}")
        sys.exit(1)
