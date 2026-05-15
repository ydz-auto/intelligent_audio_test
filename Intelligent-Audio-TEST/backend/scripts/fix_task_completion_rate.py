import sys
import os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
parent_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, parent_dir)

from app import create_app
from backend.models.database import db
from backend.models.models import Task, TaskCase

app = create_app('default')

with app.app_context():
    print("开始修正任务完成率数据...")

    tasks = Task.query.filter_by(deleted=False).all()
    total_tasks = len(tasks)
    fixed_count = 0
    error_count = 0

    for task in tasks:
        try:
            actual_completed = TaskCase.query.filter_by(
                task_id=task.id,
                status='completed'
            ).count()

            actual_failed = TaskCase.query.filter_by(
                task_id=task.id,
                status='failed'
            ).count()

            old_completed = task.completed_cases
            old_failed = task.failed_cases

            task.completed_cases = actual_completed
            task.failed_cases = actual_failed

            if old_completed != actual_completed or old_failed != actual_failed:
                fixed_count += 1
                print(f"  任务 [{task.id}] {task.name}: "
                      f"completed {old_completed}->{actual_completed}, "
                      f"failed {old_failed}->{actual_failed}")

        except Exception as e:
            error_count += 1
            print(f"  任务 [{task.id}] 修正失败: {e}")

    db.session.commit()
    print(f"\n修正完成！共处理 {total_tasks} 个任务，修正 {fixed_count} 个，失败 {error_count} 个")
