# -*- coding: utf-8 -*-
"""TaskMergeRelationRepository — 任务合并关系仓储实现。

实现 domain/repositories/task_merge_repository.py 中定义的
TaskMergeRelationRepositoryABC，提供按 task_id 查询合并关系的能力。

task_id 同时匹配 merged_task_id 与 source_task_id，返回 dict 列表。
每个方法内部管理 DB session 生命周期（try/finally close）。
"""
from typing import Any, Dict, List

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models.task_models import TaskMergeRelation
from task_service.domain.repositories.task_merge_repository import (
    TaskMergeRelationRepositoryABC,
)


class TaskMergeRelationRepository(TaskMergeRelationRepositoryABC):
    """任务合并关系仓储实现。"""

    def get_by_task_id(self, task_id: int) -> List[Dict[str, Any]]:
        """查询 TaskMergeRelation（task_id 同时匹配 merged_task_id 与 source_task_id）。

        Args:
            task_id: 任务 ID，同时作为合并任务 ID 或源任务 ID 进行匹配。

        Returns:
            dict 列表，每项形如：
            {id, merged_task_id, source_task_id, source_result_count}
        """
        session = get_db_session()
        try:
            rows = (
                session.query(TaskMergeRelation)
                .filter(
                    (TaskMergeRelation.merged_task_id == task_id)
                    | (TaskMergeRelation.source_task_id == task_id)
                )
                .all()
            )
            return [
                {
                    'id': row.id,
                    'merged_task_id': row.merged_task_id,
                    'source_task_id': row.source_task_id,
                    'source_result_count': row.source_result_count,
                }
                for row in rows
            ]
        finally:
            session.close()


# 模块级单例
task_merge_relation_repository = TaskMergeRelationRepository()
