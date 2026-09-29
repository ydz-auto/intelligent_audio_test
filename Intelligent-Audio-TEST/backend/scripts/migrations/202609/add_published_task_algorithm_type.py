"""
published_tasks 增加 algorithm_type 冗余列 + 历史数据回填

背景：
    已发布任务列表此前无算法列，无法按算法筛选。现 PublishedTask 模型新增
    algorithm_type 列并在发布/创建新版本时写入，本脚本负责：
    1. ALTER TABLE 加列 + 索引（幂等）
    2. 回填历史已发布任务：
       - 优先取发布快照 snapshot_config->>'algorithmType'（发布时冻结值）
       - 快照无值时回落到来源日常任务 test_tasks.algorithm_type

使用方法（在项目根目录执行）：
    python backend/scripts/migrations/202609/add_published_task_algorithm_type.py --dry-run   # 预览
    python backend/scripts/migrations/202609/add_published_task_algorithm_type.py             # 执行
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


def add_column_and_index(dry_run=False):
    """加列与索引（幂等，IF NOT EXISTS）"""
    statements = [
        "ALTER TABLE published_tasks ADD COLUMN IF NOT EXISTS algorithm_type VARCHAR(50)",
        "CREATE INDEX IF NOT EXISTS idx_published_task_algorithm_type ON published_tasks(algorithm_type)",
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
    print(f"开始回填 published_tasks.algorithm_type（{'dry-run 预览' if dry_run else '实际执行'}）")
    print("=" * 60)

    # 1) 快照冻结值优先（JSON ->> 提取，兼容 algorithmType 与 algorithm_type 两种键名）
    snapshot_sql = text("""
        UPDATE published_tasks p
        SET algorithm_type = COALESCE(
            NULLIF(p.snapshot_config->>'algorithmType', ''),
            NULLIF(p.snapshot_config->>'algorithm_type', '')
        )
        WHERE (p.algorithm_type IS NULL OR p.algorithm_type = '')
          AND (NULLIF(p.snapshot_config->>'algorithmType', '') IS NOT NULL
               OR NULLIF(p.snapshot_config->>'algorithm_type', '') IS NOT NULL)
    """)
    if dry_run:
        count = db.session.execute(text("""
            SELECT COUNT(*) FROM published_tasks p
            WHERE (p.algorithm_type IS NULL OR p.algorithm_type = '')
              AND (NULLIF(p.snapshot_config->>'algorithmType', '') IS NOT NULL
                   OR NULLIF(p.snapshot_config->>'algorithm_type', '') IS NOT NULL)
        """)).scalar()
        print(f"[dry-run] 可由发布快照回填的记录数: {count}")
    else:
        result = db.session.execute(snapshot_sql)
        print(f"由发布快照回填记录数: {result.rowcount}")

    # 2) 快照无值时回落到来源日常任务
    source_sql = text("""
        UPDATE published_tasks p
        SET algorithm_type = t.algorithm_type
        FROM test_tasks t
        WHERE p.source_task_id = t.id
          AND (p.algorithm_type IS NULL OR p.algorithm_type = '')
          AND t.algorithm_type IS NOT NULL AND t.algorithm_type <> ''
    """)
    if dry_run:
        count = db.session.execute(text("""
            SELECT COUNT(*) FROM published_tasks p
            JOIN test_tasks t ON p.source_task_id = t.id
            WHERE (p.algorithm_type IS NULL OR p.algorithm_type = '')
              AND t.algorithm_type IS NOT NULL AND t.algorithm_type <> ''
        """)).scalar()
        print(f"[dry-run] 可由来源任务回填的记录数: {count}")
    else:
        result = db.session.execute(source_sql)
        print(f"由来源任务回填记录数: {result.rowcount}")

    if not dry_run:
        db.session.commit()

    remaining = db.session.execute(text("""
        SELECT COUNT(*) FROM published_tasks
        WHERE algorithm_type IS NULL OR algorithm_type = ''
    """)).scalar()
    print("-" * 60)
    print(f"剩余无法推导（快照与来源任务均无算法信息）的记录数: {remaining}")
    if dry_run:
        print("（dry-run 模式未写入数据库）")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='published_tasks 加 algorithm_type 列并回填历史数据')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不写入数据库')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        add_column_and_index(dry_run=args.dry_run)
        backfill(dry_run=args.dry_run)
