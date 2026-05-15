# -*- coding: utf-8 -*-
"""
用例参考参数异步刷新任务

职责：
- 提供异步批量刷新用例 reference_params 的能力
- 支持查询任务进度
"""

import threading
import logging
import uuid
from datetime import datetime, timezone, timedelta
from backend.models.database import db
from backend.models.models import TestCase

logger = logging.getLogger(__name__)


class ReferenceRefreshTask:
    """
    用例参考参数刷新任务

    用法：
        task = ReferenceRefreshTask(case_ids)
        thread = threading.Thread(target=task.run, daemon=True)
        thread.start()
        # 或直接调用 task.run() 同步执行
    """

    def __init__(self, case_ids: list):
        self.case_ids = case_ids
        self.task_id = str(uuid.uuid4())
        self.updated_count = 0
        self.failed_count = 0
        self.failed_cases = []
        self.status = 'pending'
        self.started_at = None
        self.completed_at = None

    def run(self):
        """在新线程中执行刷新任务"""
        self.status = 'running'
        self.started_at = datetime.now(timezone(timedelta(hours=8)))

        try:
            from backend.controllers.testcase_controller import TestCaseController

            test_cases = TestCase.query.filter(
                TestCase.id.in_(self.case_ids),
                TestCase.deleted == False
            ).all()

            logger.info(f"[ReferenceRefreshTask-{self.task_id}] 开始刷新 {len(test_cases)} 个用例")

            for tc in test_cases:
                try:
                    TestCaseController.refresh_reference_texts(tc)
                    tc.updated_at = datetime.now(timezone(timedelta(hours=8)))
                    db.session.add(tc)
                    self.updated_count += 1

                    if self.updated_count % 10 == 0:
                        db.session.commit()
                        logger.info(f"[ReferenceRefreshTask-{self.task_id}] 已刷新 {self.updated_count} 个用例")
                except Exception as e:
                    self.failed_count += 1
                    self.failed_cases.append({
                        'case_id': tc.id,
                        'error': str(e)
                    })
                    logger.error(f"[ReferenceRefreshTask-{self.task_id}] 刷新用例 {tc.id} 失败: {e}")

            db.session.commit()
            self.status = 'completed'
            self.completed_at = datetime.now(timezone(timedelta(hours=8)))

            logger.info(f"[ReferenceRefreshTask-{self.task_id}] 完成! 成功: {self.updated_count}, 失败: {self.failed_count}")

        except Exception as e:
            self.status = 'failed'
            self.completed_at = datetime.now(timezone(timedelta(hours=8)))
            logger.error(f"[ReferenceRefreshTask-{self.task_id}] 任务执行失败: {e}")

    def get_progress(self) -> dict:
        """获取任务进度"""
        total = len(self.case_ids)
        progress = 0
        if total > 0:
            processed = self.updated_count + self.failed_count
            progress = int(processed / total * 100)

        return {
            'task_id': self.task_id,
            'status': self.status,
            'total': total,
            'updated': self.updated_count,
            'failed': self.failed_count,
            'progress': progress,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'failed_cases': self.failed_cases[:10]
        }


_refresh_tasks = {}


def submit_reference_refresh_task(case_ids: list) -> str:
    """
    提交用例参考刷新任务

    Args:
        case_ids: 用例ID列表

    Returns:
        task_id: 任务ID，用于查询进度
    """
    task_id = str(uuid.uuid4())

    task = ReferenceRefreshTask(case_ids)
    task.task_id = task_id
    _refresh_tasks[task_id] = task

    from backend.utils.execution_engine import execution_engine
    execution_engine.api_task_pool.submit(task.run)

    logger.info(f"[submit_reference_refresh_task] 任务已提交: {task_id}, 用例数: {len(case_ids)}")

    return task_id


def get_reference_refresh_task_status(task_id: str) -> dict:
    """
    获取刷新任务状态

    Args:
        task_id: 任务ID

    Returns:
        任务状态字典
    """
    task = _refresh_tasks.get(task_id)
    if not task:
        return {
            'task_id': task_id,
            'status': 'not_found',
            'message': f'任务 {task_id} 不存在或已过期'
        }

    return task.get_progress()


def cleanup_finished_tasks(max_age_hours: int = 24):
    """
    清理已完成的旧任务，避免内存泄漏

    Args:
        max_age_hours: 任务保留时间（小时）
    """
    current_time = datetime.now(timezone(timedelta(hours=8)))
    to_remove = []

    for task_id, task in _refresh_tasks.items():
        if task.status in ('completed', 'failed'):
            if task.completed_at:
                age = (current_time - task.completed_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_remove.append(task_id)

    for task_id in to_remove:
        del _refresh_tasks[task_id]

    if to_remove:
        logger.info(f"[cleanup_finished_tasks] 已清理 {len(to_remove)} 个旧任务")
