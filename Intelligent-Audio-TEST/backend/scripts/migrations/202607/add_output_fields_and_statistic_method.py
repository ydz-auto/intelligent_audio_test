# -*- coding: utf-8 -*-
"""
为 evaluation_dimension_params 表添加输出字段相关列，
为 dimensions 表添加统计方式列。

功能：
1. evaluation_dimension_params 表：
   - 添加 param_direction 列（input/output，默认 input）
   - 添加 field_path 列（结果提取路径）
   - 添加 agg_role 列（聚合角色：numerator/denominator/value）
   - 添加 output_role 列（输出字段角色：main/aux）
   - 添加 visible_in_report 列（是否在报告中显示）
   - 删除旧唯一约束 uq_dimension_param_code
   - 添加新唯一约束 uq_dimension_param_code_direction (dimension_id, param_code, param_direction)
2. dimensions 表：
   - 添加 statistic_method 列（统计方式：average/weighted_wer，默认 average）

使用方法：
    python add_output_fields_and_statistic_method.py
    python add_output_fields_and_statistic_method.py --dry-run

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


def _col_exists(conn, table, column):
    """检查列是否已存在（兼容中英文 PostgreSQL）"""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def _constraint_exists(conn, name):
    """检查约束是否已存在"""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = :name"
    ), {"name": name})
    return result.fetchone() is not None


def migrate():
    engine = create_engine(POSTGRES_URI)

    with engine.begin() as conn:
        print("=== 1. 迁移 evaluation_dimension_params 表 ===\n")

        # 1.1 添加 param_direction 列
        if _col_exists(conn, 'evaluation_dimension_params', 'param_direction'):
            print("  - param_direction 列已存在")
        else:
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "ADD COLUMN param_direction VARCHAR(10) NOT NULL DEFAULT 'input'"
            ))
            print("  + evaluation_dimension_params.param_direction VARCHAR(10) NOT NULL DEFAULT 'input'")

        # 1.2 添加 field_path 列
        if _col_exists(conn, 'evaluation_dimension_params', 'field_path'):
            print("  - field_path 列已存在")
        else:
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "ADD COLUMN field_path VARCHAR(200)"
            ))
            print("  + evaluation_dimension_params.field_path VARCHAR(200)")

        # 1.3 添加 agg_role 列
        if _col_exists(conn, 'evaluation_dimension_params', 'agg_role'):
            print("  - agg_role 列已存在")
        else:
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "ADD COLUMN agg_role VARCHAR(20)"
            ))
            print("  + evaluation_dimension_params.agg_role VARCHAR(20)")

        # 1.4 添加 output_role 列
        if _col_exists(conn, 'evaluation_dimension_params', 'output_role'):
            print("  - output_role 列已存在")
        else:
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "ADD COLUMN output_role VARCHAR(10)"
            ))
            print("  + evaluation_dimension_params.output_role VARCHAR(10)")

        # 1.5 添加 visible_in_report 列
        if _col_exists(conn, 'evaluation_dimension_params', 'visible_in_report'):
            print("  - visible_in_report 列已存在")
        else:
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "ADD COLUMN visible_in_report BOOLEAN DEFAULT TRUE"
            ))
            print("  + evaluation_dimension_params.visible_in_report BOOLEAN DEFAULT TRUE")

        # 1.6 为现有 output 记录设置 output_role 默认值
        result = conn.execute(text(
            "UPDATE evaluation_dimension_params SET output_role = 'main' "
            "WHERE param_direction = 'output' AND (output_role IS NULL OR output_role = '')"
        ))
        if result.rowcount > 0:
            print(f"  ~ 已为 {result.rowcount} 条 output 记录设置 output_role = 'main'")

        # 1.7 为现有记录设置 param_direction 默认值（已是 input，补兜底）
        result = conn.execute(text(
            "UPDATE evaluation_dimension_params SET param_direction = 'input' "
            "WHERE param_direction IS NULL OR param_direction = ''"
        ))
        if result.rowcount > 0:
            print(f"  ~ 已为 {result.rowcount} 条记录设置 param_direction = 'input'")

        # 1.8 删除旧唯一约束
        try:
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "DROP CONSTRAINT IF EXISTS uq_dimension_param_code"
            ))
            print("  - 已删除旧约束 uq_dimension_param_code（如存在）")
        except Exception as e:
            print(f"  ! 删除旧约束时跳过: {e}")

        # 1.9 添加新唯一约束
        if _constraint_exists(conn, 'uq_dimension_param_code_direction'):
            print("  - 约束 uq_dimension_param_code_direction 已存在")
        else:
            conn.execute(text(
                "ALTER TABLE evaluation_dimension_params "
                "ADD CONSTRAINT uq_dimension_param_code_direction "
                "UNIQUE (dimension_id, param_code, param_direction)"
            ))
            print("  + 新约束 uq_dimension_param_code_direction (dimension_id, param_code, param_direction)")

        print("\n=== 2. 迁移 dimensions 表 ===\n")

        # 2.1 添加 statistic_method 列
        if _col_exists(conn, 'dimensions', 'statistic_method'):
            print("  - statistic_method 列已存在")
        else:
            conn.execute(text(
                "ALTER TABLE dimensions "
                "ADD COLUMN statistic_method VARCHAR(30) NOT NULL DEFAULT 'average'"
            ))
            print("  + dimensions.statistic_method VARCHAR(30) NOT NULL DEFAULT 'average'")

        # 2.2 为现有记录设置默认值
        result = conn.execute(text(
            "UPDATE dimensions SET statistic_method = 'average' "
            "WHERE statistic_method IS NULL OR statistic_method = ''"
        ))
        if result.rowcount > 0:
            print(f"  ~ 已为 {result.rowcount} 条记录设置 statistic_method = 'average'")

        print("\n=== 迁移完成 ===")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}添加输出字段配置和统计方式")
    print("=" * 60)
    print()
    print("变更内容:")
    print("  1. evaluation_dimension_params: +param_direction, +field_path, +agg_role")
    print("     唯一约束: uq_dimension_param_code → uq_dimension_param_code_direction")
    print("  2. dimensions: +statistic_method")
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
