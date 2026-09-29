"""
test_reports 增加 algorithm_type 冗余列 + 历史数据回填

背景：
    报告列表此前无算法列，按算法筛选依赖运行时 JOIN test_tasks（且对比类报告
    task_id 为 NULL 无法命中）。现 Report 模型新增 algorithm_type 列并在创建时写入，
    本脚本负责：
    1. ALTER TABLE 加列 + 索引（幂等）
    2. 回填历史报告：
       - 有关联任务：取 task.algorithm_type（需先执行 backfill_task_algorithm_type.py）
       - 无关联任务（对比/二次对比）：取 report_cases 中出现最多的非空 algorithm_type

使用方法（在项目根目录执行）：
    python backend/scripts/migrations/202609/add_report_algorithm_type.py --dry-run   # 预览
    python backend/scripts/migrations/202609/add_report_algorithm_type.py             # 执行
"""

import sys
import os
import argparse
from collections import Counter

# 上溯 4 级：202609 → migrations → scripts → backend → 项目根目录（backend 的包导入需要）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))
sys.path.insert(0, _ROOT)

from sqlalchemy import text
from backend.app import create_app
from backend.models.database import db


def add_column_and_index(dry_run=False):
    """加列与索引（幂等，IF NOT EXISTS）"""
    statements = [
        "ALTER TABLE test_reports ADD COLUMN IF NOT EXISTS algorithm_type VARCHAR(50)",
        "CREATE INDEX IF NOT EXISTS idx_report_algorithm_type ON test_reports(algorithm_type)",
    ]
    for stmt in statements:
        if dry_run:
            print(f"[dry-run] {stmt}")
            continue
        db.session.execute(text(stmt))
    if not dry_run:
        db.session.commit()
    print("列 algorithm_type 与索引就绪（或已存在）")


def backfill(dry_run=False):
    print("=" * 60)
    print(f"开始回填 test_reports.algorithm_type（{'dry-run 预览' if dry_run else '实际执行'}）")
    print("=" * 60)

    # 1) 有关联任务的报告：取任务的 algorithm_type
    task_sql = text("""
        UPDATE test_reports r
        SET algorithm_type = t.algorithm_type
        FROM test_tasks t
        WHERE r.task_id = t.id
          AND (r.algorithm_type IS NULL OR r.algorithm_type = '')
          AND t.algorithm_type IS NOT NULL AND t.algorithm_type <> ''
    """)
    if dry_run:
        count = db.session.execute(text("""
            SELECT COUNT(*) FROM test_reports r
            JOIN test_tasks t ON r.task_id = t.id
            WHERE (r.algorithm_type IS NULL OR r.algorithm_type = '')
              AND t.algorithm_type IS NOT NULL AND t.algorithm_type <> ''
        """)).scalar()
        print(f"[dry-run] 可由关联任务回填的报告数: {count}")
    else:
        result = db.session.execute(task_sql)
        print(f"由关联任务回填报告数: {result.rowcount}")

    # 2) 无关联任务的报告（对比/二次对比）：从明细表 report_cases 推导出现最多的非空算法
    orphan_ids = db.session.execute(text("""
        SELECT id FROM test_reports
        WHERE task_id IS NULL
          AND (algorithm_type IS NULL OR algorithm_type = '')
    """)).scalars().all()

    derived = 0
    for report_id in orphan_ids:
        rows = db.session.execute(text("""
            SELECT algorithm_type, COUNT(*) AS cnt
            FROM report_cases
            WHERE report_id = :rid AND algorithm_type IS NOT NULL AND algorithm_type <> ''
            GROUP BY algorithm_type ORDER BY cnt DESC
        """), {'rid': report_id}).all()
        algorithm_type = rows[0][0] if rows else None
        if not algorithm_type:
            continue
        print(f"  报告 #{report_id} -> {algorithm_type}")
        if not dry_run:
            db.session.execute(
                text("UPDATE test_reports SET algorithm_type = :algo WHERE id = :rid"),
                {'algo': algorithm_type, 'rid': report_id}
            )
        derived += 1

    if not dry_run:
        db.session.commit()
    print("-" * 60)
    print(f"由明细表回填对比类报告数: {derived}（其余无算法明细的报告保持为空）")
    if dry_run:
        print("（dry-run 模式未写入数据库）")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='test_reports 加 algorithm_type 列并回填历史数据')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不写入数据库')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        add_column_and_index(dry_run=args.dry_run)
        backfill(dry_run=args.dry_run)
