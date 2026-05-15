# -*- coding: utf-8 -*-
"""
数据库迁移：检查并修复所有算法相关表的字段差距

用法: python scripts/check_and_fix_algorithm_tables.py
"""
import os
import sys

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')

from sqlalchemy import create_engine, text, inspect
engine = create_engine(f'sqlite:///{db_path}')


def table_has_column(conn, table_name, column_name):
    """检查表是否有指定列"""
    inspector = inspect(conn)
    columns = inspector.get_columns(table_name)
    return any(col['name'] == column_name for col in columns)


def check_table(conn, table_name, expected_columns):
    """检查表结构"""
    print(f"\n{'='*60}")
    print(f"检查表: {table_name}")
    print(f"{'='*60}")

    inspector = inspect(conn)
    actual_columns = [col['name'] for col in inspector.get_columns(table_name)]

    missing = []
    for col in expected_columns:
        if col not in actual_columns:
            missing.append(col)
            print(f"  ✗ 缺失字段: {col}")
        else:
            print(f"  ✓ 字段存在: {col}")

    return missing


def migrate():
    """执行数据库迁移检查"""
    print("="*60)
    print("开始检查数据库表结构")
    print("="*60)

    with engine.connect() as conn:
        # 1. 检查 algorithm_definitions 表
        missing_algo_def = check_table(conn, 'algorithm_definitions', [
            'id', 'type', 'name', 'group_id', 'description', 'status',
            'icon', 'display_order', 'created_at', 'updated_at', 'deleted'
        ])

        # 2. 检查 param_mappings 表
        missing_param_map = check_table(conn, 'param_mappings', [
            'id', 'algorithm_type', 'component_type', 'direction', 'field_type',
            'source_param', 'target_key', 'mapped_from', 'transform_type',
            'created_at', 'updated_at', 'deleted'
        ])

        # 3. 检查 dimensions 表
        missing_dim = check_table(conn, 'dimensions', [
            'id', 'name', 'keywords', 'description', 'category_id', 'type',
            'result_type', 'result_min', 'result_max', 'decimal_places',
            'weight', 'estimated_exec_time', 'rule', 'api_settings', 'status',
            'deleted', 'created_at', 'updated_at', 'api_status', 'required_inputs',
            'api_endpoints', 'api_url', 'score_unit', 'associated_algorithms'
        ])

        # 添加缺失的字段
        print(f"\n{'='*60}")
        print("开始修复缺失字段")
        print(f"{'='*60}")

        # algorithm_definitions 修复
        if 'group_id' not in missing_algo_def:
            if not table_has_column(conn, 'algorithm_definitions', 'group_id'):
                conn.execute(text("ALTER TABLE algorithm_definitions ADD COLUMN group_id INTEGER"))
                print("  ✓ 添加: algorithm_definitions.group_id")

        # param_mappings 修复
        for col in missing_param_map:
            if col == 'direction':
                conn.execute(text("ALTER TABLE param_mappings ADD COLUMN direction VARCHAR(10) DEFAULT 'input'"))
                print(f"  ✓ 添加: param_mappings.{col}")
            elif col == 'field_type':
                conn.execute(text("ALTER TABLE param_mappings ADD COLUMN field_type VARCHAR(20) DEFAULT 'text'"))
                print(f"  ✓ 添加: param_mappings.{col}")
            elif col == 'mapped_from':
                conn.execute(text("ALTER TABLE param_mappings ADD COLUMN mapped_from VARCHAR(100)"))
                print(f"  ✓ 添加: param_mappings.{col}")

        # dimensions 修复
        if not table_has_column(conn, 'dimensions', 'required_inputs'):
            conn.execute(text("ALTER TABLE dimensions ADD COLUMN required_inputs JSON DEFAULT '[]'"))
            print("  ✓ 添加: dimensions.required_inputs")

        if not table_has_column(conn, 'dimensions', 'api_endpoints'):
            conn.execute(text("ALTER TABLE dimensions ADD COLUMN api_endpoints JSON DEFAULT '[]'"))
            print("  ✓ 添加: dimensions.api_endpoints")

        if not table_has_column(conn, 'dimensions', 'associated_algorithms'):
            conn.execute(text("ALTER TABLE dimensions ADD COLUMN associated_algorithms TEXT DEFAULT '[]'"))
            print("  ✓ 添加: dimensions.associated_algorithms")

        conn.commit()

    print(f"\n{'='*60}")
    print("检查完成!")
    print(f"{'='*60}")


if __name__ == '__main__':
    migrate()
