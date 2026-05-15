# -*- coding: utf-8 -*-
"""
数据库迁移脚本：为 test_results 和 test_result_dimensions 表添加 algorithm_type 字段

支持多种算法类型：translation, asr, tts, speaker_recognition 等
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
    print("开始数据库迁移：添加 algorithm_type 字段")
    print("=" * 60)

    with engine.connect() as conn:
        # 1. 检查并添加 test_results.algorithm_type 字段
        if not table_has_column(conn, 'test_results', 'algorithm_type'):
            conn.execute(text("""
                ALTER TABLE test_results ADD COLUMN algorithm_type VARCHAR(50)
            """))
            # 设置默认值
            conn.execute(text("""
                UPDATE test_results SET algorithm_type = 'translation' WHERE algorithm_type IS NULL
            """))
            print("  ✓ test_results 表添加 algorithm_type 字段")
        else:
            print("  - test_results.algorithm_type 字段已存在")

        # 2. 检查并添加 test_results.algorithm_result 字段
        if not table_has_column(conn, 'test_results', 'algorithm_result'):
            conn.execute(text("""
                ALTER TABLE test_results ADD COLUMN algorithm_result TEXT
            """))
            print("  ✓ test_results 表添加 algorithm_result 字段")
        else:
            print("  - test_results.algorithm_result 字段已存在")

        # 3. 检查并添加 test_result_dimensions.algorithm_type 字段
        if not table_has_column(conn, 'test_result_dimensions', 'algorithm_type'):
            conn.execute(text("""
                ALTER TABLE test_result_dimensions ADD COLUMN algorithm_type VARCHAR(50)
            """))
            # 设置默认值
            conn.execute(text("""
                UPDATE test_result_dimensions SET algorithm_type = 'translation' WHERE algorithm_type IS NULL
            """))
            print("  ✓ test_result_dimensions 表添加 algorithm_type 字段")
        else:
            print("  - test_result_dimensions.algorithm_type 字段已存在")

        conn.commit()
        print("\n数据库迁移完成!")


def verify():
    """验证迁移结果"""
    print("\n" + "=" * 60)
    print("验证迁移结果")
    print("=" * 60)

    with engine.connect() as conn:
        # 验证 test_results 表
        print("\ntest_results 表结构:")
        result = conn.execute(text("PRAGMA table_info(test_results)"))
        columns = [row[1] for row in result]
        for col in columns:
            marker = "★" if col in ['algorithm_type', 'algorithm_result'] else " "
            print(f"  {marker} {col}")

        # 验证 test_result_dimensions 表
        print("\ntest_result_dimensions 表结构:")
        result = conn.execute(text("PRAGMA table_info(test_result_dimensions)"))
        columns = [row[1] for row in result]
        for col in columns:
            marker = "★" if col == 'algorithm_type' else " "
            print(f"  {marker} {col}")

        # 显示数据统计
        print("\n数据统计:")
        result = conn.execute(text("SELECT COUNT(*) FROM test_results"))
        test_results_count = result.fetchone()[0]
        print(f"  test_results 总记录数: {test_results_count}")

        result = conn.execute(text("SELECT COUNT(*) FROM test_results WHERE algorithm_type IS NOT NULL"))
        with_algo_type = result.fetchone()[0]
        print(f"  有 algorithm_type 的记录: {with_algo_type}")

        result = conn.execute(text("SELECT COUNT(*) FROM test_result_dimensions"))
        dim_count = result.fetchone()[0]
        print(f"  test_result_dimensions 总记录数: {dim_count}")

        result = conn.execute(text("SELECT COUNT(*) FROM test_result_dimensions WHERE algorithm_type IS NOT NULL"))
        dim_with_algo = result.fetchone()[0]
        print(f"  有 algorithm_type 的记录: {dim_with_algo}")


if __name__ == '__main__':
    migrate()
    verify()
    print("\n" + "=" * 60)
    print("迁移验证完成!")
    print("=" * 60)
