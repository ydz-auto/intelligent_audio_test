# -*- coding: utf-8 -*-
"""
数据库迁移：为 param_mappings 表添加新字段
迁移: 添加 direction, field_type, mapped_from 字段

用法: python scripts/migrate_param_mappings_fields.py
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


def migrate():
    """为 param_mappings 表添加新字段"""
    print("=" * 60)
    print("开始迁移: 为 param_mappings 表添加新字段...")
    print("=" * 60)

    with engine.connect() as conn:
        # 检查并添加 direction 字段
        if not table_has_column(conn, 'param_mappings', 'direction'):
            try:
                conn.execute(text("ALTER TABLE param_mappings ADD COLUMN direction VARCHAR(10) DEFAULT 'input'"))
                print("  ✓ 添加字段: param_mappings.direction")
            except Exception as e:
                print(f"  ✗ 添加字段失败 param_mappings.direction: {e}")
        else:
            print("  - 字段已存在: param_mappings.direction")

        # 检查并添加 field_type 字段
        if not table_has_column(conn, 'param_mappings', 'field_type'):
            try:
                conn.execute(text("ALTER TABLE param_mappings ADD COLUMN field_type VARCHAR(20) DEFAULT 'text'"))
                print("  ✓ 添加字段: param_mappings.field_type")
            except Exception as e:
                print(f"  ✗ 添加字段失败 param_mappings.field_type: {e}")
        else:
            print("  - 字段已存在: param_mappings.field_type")

        # 检查并添加 mapped_from 字段
        if not table_has_column(conn, 'param_mappings', 'mapped_from'):
            try:
                conn.execute(text("ALTER TABLE param_mappings ADD COLUMN mapped_from VARCHAR(100)"))
                print("  ✓ 添加字段: param_mappings.mapped_from")
            except Exception as e:
                print(f"  ✗ 添加字段失败 param_mappings.mapped_from: {e}")
        else:
            print("  - 字段已存在: param_mappings.mapped_from")

        conn.commit()

    print("\n" + "=" * 60)
    print("迁移完成!")
    print("=" * 60)
    print("新增字段说明:")
    print("  - direction: 方向 (input/output)")
    print("  - field_type: 字段类型 (text/audio/number/boolean/json)")
    print("  - mapped_from: 映射源字段")


if __name__ == '__main__':
    migrate()
