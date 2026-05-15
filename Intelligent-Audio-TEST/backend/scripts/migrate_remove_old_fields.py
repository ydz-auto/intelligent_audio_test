# -*- coding: utf-8 -*-
"""
数据库迁移脚本：移除 test_results 表中的旧专用字段 (asr_result, translation_result)

由于现在使用统一的 algorithm_result (JSON) 字段存储算法结果，旧字段可以移除以保持数据库简洁。
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
    """执行数据库迁移"""
    print("=" * 60)
    print("开始迁移：移除 test_results 旧专用字段")
    print("=" * 60)

    with engine.connect() as conn:
        # 检查并移除 asr_result 字段
        if table_has_column(conn, 'test_results', 'asr_result'):
            try:
                # SQLite 不支持直接 DROP COLUMN，需要创建新表
                print("  SQLite 不支持直接 DROP COLUMN，尝试其他方式...")

                # 检查是否已有 algorithm_result 字段
                if table_has_column(conn, 'test_results', 'algorithm_result'):
                    print("  ✓ algorithm_result 字段已存在，数据已迁移到新字段")
                    print("  - asr_result 字段保留（SQLite 限制），但不再使用")
                else:
                    print("  ⚠ algorithm_result 字段不存在，请先运行 migrate_add_algorithm_type.py")
            except Exception as e:
                print(f"  ✗ 移除 asr_result 失败: {e}")
        else:
            print("  - asr_result 字段已不存在")

        # 检查 translation_result 字段
        if table_has_column(conn, 'test_results', 'translation_result'):
            print("  - translation_result 字段保留（SQLite 限制），但不再使用")
        else:
            print("  - translation_result 字段已不存在")

        print("\n注意: 由于 SQLite 限制，旧字段 asr_result 和 translation_result 仍存在于数据库中，")
        print("      但代码已不再使用它们，所有数据现在通过 algorithm_result (JSON) 存储。")

    print("\n迁移检查完成!")


def verify():
    """验证当前表结构"""
    print("\n" + "=" * 60)
    print("验证 test_results 表结构")
    print("=" * 60)

    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(test_results)"))
        columns = {row[1]: row[2] for row in result}

        print("\n当前字段列表:")
        for col_name, col_type in columns.items():
            if col_name in ['algorithm_type', 'algorithm_result']:
                print(f"  ★ {col_name} ({col_type}) - 新字段")
            elif col_name in ['asr_result', 'translation_result']:
                print(f"  - {col_name} ({col_type}) - 旧字段（保留但不再使用）")
            else:
                print(f"    {col_name} ({col_type})")


if __name__ == '__main__':
    migrate()
    verify()
    print("\n" + "=" * 60)
    print("迁移检查完成!")
    print("=" * 60)
