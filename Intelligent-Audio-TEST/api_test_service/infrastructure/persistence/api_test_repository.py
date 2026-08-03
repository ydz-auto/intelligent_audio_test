# -*- coding: utf-8 -*-
"""API 测试仓储 — 持久化访问 TaskAPI / API / Task 关联数据。

封装 DB 访问细节，向上层（application/interfaces）提供领域可读的接口。
通过 shared.models.database.db 的 scoped_session 访问数据库。
"""
from typing import List, Optional

from shared.models.database import get_db_session
from shared.models.models import TaskAPI, API, Task


class APITestRepository:
    """API 测试仓储

    提供按 task_id 查询关联 API / TaskCase 的只读访问能力。
    写入仍由 core 层执行器负责（执行器内部持有完整事务流程）。
    """

    def find_api_ids_by_task(self, task_id: int) -> List[int]:
        """查询任务关联的 API ID 列表"""
        session = get_db_session()
        try:
            rows = (
                session.query(TaskAPI.api_id)
                .filter(TaskAPI.task_id == task_id)
                .all()
            )
            return [row[0] for row in rows]
        finally:
            # scoped_session 由请求/线程生命周期统一 remove，此处不主动 remove
            pass

    def find_task_by_id(self, task_id: int) -> Optional[Task]:
        """根据 ID 查询测试任务"""
        session = get_db_session()
        try:
            return session.query(Task).filter(Task.id == task_id).first()
        finally:
            pass

    def find_api_by_id(self, api_id: int) -> Optional[API]:
        """根据 ID 查询 API"""
        session = get_db_session()
        try:
            return session.query(API).filter(API.id == api_id).first()
        finally:
            pass

    def task_exists(self, task_id: int) -> bool:
        """判断任务是否存在"""
        session = get_db_session()
        try:
            return (
                session.query(Task.id)
                .filter(Task.id == task_id)
                .first()
                is not None
            )
        finally:
            pass


# 模块级实例，便于直接注入
api_test_repository = APITestRepository()
