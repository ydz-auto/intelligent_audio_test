# -*- coding: utf-8 -*-
"""
为 case_algorithm_params 表添加 annotation_code 和 field_path 字段

功能：
1. 添加 annotation_code 字段 - 关联的音频标注代码（默认同 param_code）
2. 添加 field_path 字段 - 标注数据字段路径（默认同 param_code）

使用方法：
    python -m backend.scripts.migrations.202607.add_annotation_fields_to_case_params

注意：此脚本可重复执行（幂等）
"""

import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)


def migrate():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        print("=== 为 case_algorithm_params 添加 annotation_code 和 field_path 字段 ===\n")

        # 1. 添加 annotation_code 列
        try:
            conn.execute(text(
                "ALTER TABLE case_algorithm_params "
                "ADD COLUMN annotation_code VARCHAR(100)"
            ))
            print("  + case_algorithm_params.annotation_code VARCHAR(100)")
        except Exception as e:
            msg = str(e).lower()
            if 'already exists' in msg or 'duplicate column' in msg:
                print("  - annotation_code 列已存在")
            else:
                raise

        # 2. 添加 field_path 列
        try:
            conn.execute(text(
                "ALTER TABLE case_algorithm_params "
                "ADD COLUMN field_path VARCHAR(255)"
            ))
            print("  + case_algorithm_params.field_path VARCHAR(255)")
        except Exception as e:
            msg = str(e).lower()
            if 'already exists' in msg or 'duplicate column' in msg:
                print("  - field_path 列已存在")
            else:
                raise

        # 3. 为现有参数设置默认值：annotation_code = algorithm_type, field_path = param_code
        result = conn.execute(text(
            "UPDATE case_algorithm_params "
            "SET annotation_code = algorithm_type "
            "WHERE annotation_code IS NULL"
        ))
        print(f"  ~ 更新 {result.rowcount} 条记录的 annotation_code = algorithm_type")

        result = conn.execute(text(
            "UPDATE case_algorithm_params "
            "SET field_path = param_code "
            "WHERE field_path IS NULL"
        ))
        print(f"  ~ 更新 {result.rowcount} 条记录的 field_path = param_code")

        print("\n=== 迁移完成 ===")


if __name__ == '__main__':
    migrate()
