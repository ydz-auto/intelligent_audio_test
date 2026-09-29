"""
历史任务 algorithm_type 回填脚本

背景：
    test_tasks.algorithm_type 列在任务创建/合并逻辑修复前从未写入（恒为 NULL），
    导致按算法筛选任务列表 / 报告列表时返回空数据。

功能：
    对 algorithm_type 为空的任务，从其关联用例（task_case_relations → test_cases）
    的 algorithm_type 中取出现最多的非空值回填，与
    TaskController._resolve_algorithm_type 的推导口径保持一致。

使用方法（在项目根目录执行）：
    python backend/scripts/migrations/202609/backfill_task_algorithm_type.py --dry-run   # 预览
    python backend/scripts/migrations/202609/backfill_task_algorithm_type.py             # 执行
"""

import sys
import os
import argparse
from collections import Counter

# 上溯 4 级：202609 → migrations → scripts → backend → 项目根目录（backend 的包导入需要）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))
sys.path.insert(0, _ROOT)

from backend.app import create_app
from backend.models.database import db
from backend.models.models import Task, TaskCase, TestCase


def resolve_algorithm_type(case_ids):
    """从用例集合推导算法类型：取出现最多的非空 algorithm_type（与任务创建口径一致）"""
    if not case_ids:
        return None
    rows = db.session.query(TestCase.algorithm_type).filter(
        TestCase.id.in_(list(case_ids)),
        TestCase.algorithm_type.isnot(None),
        TestCase.algorithm_type != ''
    ).all()
    values = [r[0] for r in rows]
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def backfill(dry_run=False):
    print("=" * 60)
    print(f"开始回填 test_tasks.algorithm_type（{'dry-run 预览' if dry_run else '实际执行'}）")
    print("=" * 60)

    pending_tasks = Task.query.filter(
        Task.deleted == False,  # noqa: E712
        db.or_(Task.algorithm_type.is_(None), Task.algorithm_type == '')
    ).all()
    print(f"待回填任务数: {len(pending_tasks)}")

    updated = 0
    skipped = 0
    for task in pending_tasks:
        case_rows = db.session.query(TaskCase.test_case_id).filter_by(task_id=task.id).all()
        algorithm_type = resolve_algorithm_type([r[0] for r in case_rows])
        if not algorithm_type:
            skipped += 1
            continue
        print(f"  任务 #{task.id} [{task.type}] {task.name[:40]} -> {algorithm_type}")
        if not dry_run:
            task.algorithm_type = algorithm_type
        updated += 1

    if not dry_run:
        db.session.commit()

    print("-" * 60)
    print(f"完成: {'预览' if dry_run else '回填'} {updated} 个任务，"
          f"跳过（关联用例无算法信息）{skipped} 个")
    if dry_run:
        print("（dry-run 模式未写入数据库）")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='回填历史任务的 algorithm_type')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不写入数据库')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        backfill(dry_run=args.dry_run)
