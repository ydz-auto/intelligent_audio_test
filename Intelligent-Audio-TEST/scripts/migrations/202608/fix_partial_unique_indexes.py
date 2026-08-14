# -*- coding: utf-8 -*-
"""
修复软删除与唯一约束冲突：将 UniqueConstraint 替换为 PostgreSQL 部分唯一索引
=============================================================================

问题：
  多张表同时使用软删除(deleted/is_deleted)和 UniqueConstraint，
  导致软删除后的记录仍占据唯一约束位置，新数据无法插入相同的键值。

解决方案：
  将 UniqueConstraint 替换为 partial unique index (WHERE deleted = false)，
  使软删除记录不再参与唯一性检查。

用法：
    cd backend/scripts/migrations/202608
    python fix_partial_unique_indexes.py           # 预览（dry-run）
    python fix_partial_unique_indexes.py --apply   # 实际执行
"""
import os
import sys
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

# 迁移定义：(表名, 旧约束名, 索引列, WHERE 条件)
MIGRATIONS = [
    {
        'table': 'algorithm_device_params',
        'old_constraint': 'uq_algorithm_device_param_direction',
        'index_name': 'uq_algorithm_device_param_direction',
        'columns': 'algorithm_type, param_code, direction',
        'where': 'deleted = false',
    },
    {
        'table': 'algorithm_api_params',
        'old_constraint': 'uq_algorithm_api_param_direction',
        'index_name': 'uq_algorithm_api_param_direction',
        'columns': 'algorithm_type, param_code, direction',
        'where': 'deleted = false',
    },
    {
        'table': 'algorithm_reference_params',
        'old_constraint': 'uq_algorithm_reference_param_code',
        'index_name': 'uq_algorithm_reference_param_code',
        'columns': 'algorithm_type, code',
        'where': 'deleted = false',
    },
    {
        'table': 'evaluation_dimension_params',
        'old_constraint': 'uq_dimension_param_code_direction',
        'index_name': 'uq_dimension_param_code_direction',
        'columns': 'dimension_id, param_code, param_direction',
        'where': 'deleted = false',
    },
    {
        'table': 'param_mappings',
        'old_constraint': 'uq_algorithm_source_to_dimension',
        'index_name': 'uq_algorithm_source_to_dimension',
        'columns': 'algorithm_type, source, source_param, dimension_id',
        'where': 'deleted = false',
    },
    {
        'table': 'algorithm_dimension_relations',
        'old_constraint': 'uq_algorithm_dimension',
        'index_name': 'uq_algorithm_dimension',
        'columns': 'algorithm_type, dimension_id',
        'where': 'deleted = false',
    },
    {
        'table': 'case_algorithm_params',
        'old_constraint': 'uq_case_algorithm_param_code',
        'index_name': 'uq_case_algorithm_param_code',
        'columns': 'algorithm_type, param_code',
        'where': 'deleted = false',
    },
    {
        'table': 'playback_devices',
        'old_constraint': 'uq_device_channel',
        'index_name': 'uq_device_channel',
        'columns': 'device_unique_id, channel_index',
        'where': 'is_deleted = 0',
    },
    {
        'table': 'audio_algorithm_relations',
        'old_constraint': 'uq_audio_algorithm',
        'index_name': 'uq_audio_algorithm',
        'columns': 'audio_id, algorithm_type',
        'where': 'deleted = false',
    },
    {
        'table': 'algorithm_groups',
        'old_constraint': None,  # Column级 unique=True，约束名自动生成
        'index_name': 'uq_algorithm_group_name',
        'columns': 'name',
        'where': 'deleted = false',
    },
    # 注意：algorithm_definitions.type 不纳入迁移
    # 该列被多个 FK 引用，PostgreSQL FK 依赖唯一约束保证引用完整性
    # 部分唯一索引无法用于 FK，且 type 作为算法标识不应在软删除后复用
]


def constraint_exists(conn, table, constraint_name):
    result = conn.execute(text(
        f"SELECT 1 FROM pg_constraint "
        f"WHERE conname = :name AND conrelid = '{table}'::regclass"
    ), {'name': constraint_name})
    return result.fetchone() is not None


def find_unique_constraints(conn, table):
    """查找表上所有唯一约束，返回 [(constraint_name, [columns])]"""
    result = conn.execute(text(
        f"SELECT conname, array_agg(attname ORDER BY ord) "
        f"FROM (SELECT c.conname, a.attname, row_number() OVER (PARTITION BY c.conname ORDER BY a.attnum) AS ord "
        f"      FROM pg_constraint c "
        f"      JOIN pg_class t ON t.oid = c.conrelid "
        f"      JOIN pg_namespace n ON n.oid = t.relnamespace "
        f"      JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
        f"      WHERE t.relname = :table AND c.contype = 'u') sub "
        f"GROUP BY conname"
    ), {'table': table})
    return [(row[0], list(row[1])) for row in result.fetchall()]


def index_exists(conn, index_name):
    result = conn.execute(text("""
        SELECT 1 FROM pg_indexes WHERE indexname = :name
    """), {'name': index_name})
    return result.fetchone() is not None


def main():
    apply = '--apply' in sys.argv

    print("=" * 60)
    print("部分唯一索引迁移（修复软删除与唯一约束冲突）")
    print(f"模式: {'实际执行 (--apply)' if apply else '预览 (dry-run)'}")
    print("=" * 60)

    engine = create_engine(POSTGRES_URI)

    with engine.connect() as conn:
        for m in MIGRATIONS:
            table = m['table']
            old_constraint = m['old_constraint']
            index_name = m['index_name']
            columns = m['columns']
            where = m['where']

            print(f"\n--- 表: {table} ---")

            # 查找需要删除的旧唯一约束
            constraints_to_drop = []
            if old_constraint:
                # 显式命名的约束
                if constraint_exists(conn, table, old_constraint):
                    constraints_to_drop.append(old_constraint)
                    print(f"  旧约束 {old_constraint}: 存在，需要删除")
                else:
                    print(f"  旧约束 {old_constraint}: 不存在（可能已迁移）")
            else:
                # Column 级 unique=True，约束名自动生成，按列名匹配
                target_cols = [c.strip() for c in columns.split(',')]
                for cname, ccols in find_unique_constraints(conn, table):
                    if ccols == target_cols:
                        constraints_to_drop.append(cname)
                        print(f"  旧约束 {cname}: 存在（列 {ccols} 匹配），需要删除")
                if not constraints_to_drop:
                    print(f"  旧约束: 未找到匹配列 ({columns}) 的唯一约束")

            idx_exists = index_exists(conn, index_name)
            if idx_exists:
                print(f"  旧索引 {index_name}: 存在，需要先删除")

            print(f"  目标: CREATE UNIQUE INDEX {index_name} ON {table} ({columns}) WHERE {where}")

            if apply:
                for cname in constraints_to_drop:
                    conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {cname}"))
                    conn.commit()
                    print(f"  [OK] 已删除旧约束: {cname}")

                # DROP CONSTRAINT 会自动删除背后的索引，用 IF EXISTS 兜底
                conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                conn.commit()
                print(f"  [OK] 已清理旧索引: {index_name}")

                conn.execute(text(
                    f"CREATE UNIQUE INDEX {index_name} ON {table} ({columns}) WHERE {where}"
                ))
                conn.commit()
                print(f"  [OK] 已创建部分唯一索引: {index_name}")
            else:
                print(f"  [SKIP] dry-run 模式，未执行")

        if not apply:
            print("\n" + "=" * 60)
            print("预览完成，加上 --apply 参数执行实际迁移")

    print("\n完成！")


if __name__ == '__main__':
    main()
