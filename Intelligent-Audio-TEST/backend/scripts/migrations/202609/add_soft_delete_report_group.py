"""
报告与用例分组改为软删除：新增 deleted 标志列 + 分组唯一约束改为部分唯一索引

背景：
    此前报告与用例分组的删除均为硬删除（分组级联删除会物理删除下属用例）。
    现将 test_reports / test_case_groups 均增加 deleted 逻辑删除标志：
    1. test_case_groups 加 deleted 列；
       原 (name, algorithm_type) 唯一约束改为部分唯一索引
       （WHERE deleted = false），使软删除后的同名分组可复用。
    2. test_reports 加 deleted 列。

使用方法（在项目根目录执行）：
    python backend/scripts/migrations/202609/add_soft_delete_report_group.py --dry-run   # 预览
    python backend/scripts/migrations/202609/add_soft_delete_report_group.py             # 执行
"""

import sys
import os
import argparse

# 上溯 4 级：202609 → migrations → scripts → backend → 项目根目录（backend 的包导入需要）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))
sys.path.insert(0, _ROOT)

from sqlalchemy import text
from backend.app import create_app
from backend.models.database import db


def add_deleted_columns(dry_run=False):
    """加 deleted 列（幂等，IF NOT EXISTS）"""
    statements = [
        "ALTER TABLE test_case_groups ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE test_reports ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    for stmt in statements:
        if dry_run:
            print(f"[dry-run] {stmt}")
            continue
        db.session.execute(text(stmt))
    if not dry_run:
        db.session.commit()
    print("列 deleted 就绪（或已存在）")


def rebuild_group_unique_index(dry_run=False):
    """分组唯一约束 (name, algorithm_type) -> 部分唯一索引（排除已软删除）"""
    # 1. 若存在旧约束则删除
    check_constraint = text("""
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_group_name_algorithm'
          AND conrelid = 'test_case_groups'::regclass
          AND contype = 'u'
    """)
    has_constraint = db.session.execute(check_constraint).scalar()
    if has_constraint:
        stmt = "ALTER TABLE test_case_groups DROP CONSTRAINT uq_group_name_algorithm"
        if dry_run:
            print(f"[dry-run] {stmt}")
        else:
            db.session.execute(text(stmt))
            db.session.commit()
            print("已删除旧唯一约束 uq_group_name_algorithm")
    else:
        print("旧唯一约束不存在，跳过")

    # 2. 预检：创建部分唯一索引前排查存量重复分组
    #    dry-run 模式下 ALTER 未执行，deleted 列可能尚不存在，此时按全量分组校验
    has_deleted_col = db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'test_case_groups' AND column_name = 'deleted'
    """)).scalar()
    dup_sql = text("""
        SELECT name, algorithm_type, COUNT(*) AS cnt
        FROM test_case_groups
        WHERE deleted = false
        GROUP BY name, algorithm_type
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 50
    """)
    if not has_deleted_col:
        dup_sql = text("""
            SELECT name, algorithm_type, COUNT(*) AS cnt
            FROM test_case_groups
            GROUP BY name, algorithm_type
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
            LIMIT 50
        """)
    duplicates = db.session.execute(dup_sql).all()
    if duplicates:
        print("检测到未删除分组的 (name, algorithm_type) 重复，无法创建部分唯一索引：")
        for name, algorithm_type, cnt in duplicates:
            print(f"  - name={name!r}, algorithm_type={algorithm_type!r}, 数量={cnt}")
        print("请先人工合并重复分组后重试。")
        raise SystemExit(1)

    # 3. 创建部分唯一索引（同名分组软删除后可复用）
    index_sql = text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_name_algorithm
        ON test_case_groups(name, algorithm_type)
        WHERE deleted = false
    """)
    if dry_run:
        print(f"[dry-run] {index_sql}")
    else:
        db.session.execute(index_sql)
        db.session.commit()
    print("部分唯一索引 uq_group_name_algorithm (WHERE deleted = false) 就绪（或已存在）")


def verify(dry_run=False):
    print("=" * 60)
    print(f"校验结果（{'dry-run 预览' if dry_run else '实际执行'}）")
    print("=" * 60)

    group_col = db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'test_case_groups' AND column_name = 'deleted'
    """)).scalar()
    report_col = db.session.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'test_reports' AND column_name = 'deleted'
    """)).scalar()
    index_exists = db.session.execute(text("""
        SELECT COUNT(*) FROM pg_indexes
        WHERE indexname = 'uq_group_name_algorithm'
          AND tablename = 'test_case_groups'
    """)).scalar()

    print(f"  test_case_groups.deleted 列: {'存在' if group_col else '缺失'}")
    print(f"  test_reports.deleted 列: {'存在' if report_col else '缺失'}")
    print(f"  test_case_groups 部分唯一索引: {'存在' if index_exists else '缺失'}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='报告与用例分组增加软删除标志列')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不写入数据库')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        add_deleted_columns(dry_run=args.dry_run)
        rebuild_group_unique_index(dry_run=args.dry_run)
        verify(dry_run=args.dry_run)
