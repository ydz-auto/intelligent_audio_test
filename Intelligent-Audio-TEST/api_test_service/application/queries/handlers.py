# -*- coding: utf-8 -*-
"""查询处理器 — 委托给已有的 core/api_test_service.py，不重写逻辑。"""
from api_test_service.application.queries.api_test_queries import GetAPITestStatusQuery
from api_test_service.core.api_test_service import api_test_service as _service


class GetAPITestStatusQueryHandler:
    """处理 GetAPITestStatusQuery — 查询 API 测试任务状态

    委托给 APITestService.get_task_status(task_id)。
    """

    def handle(self, query: GetAPITestStatusQuery) -> dict:
        return _service.get_task_status(task_id=query.task_id)


# 便于直接调用的模块级实例
get_api_test_status_handler = GetAPITestStatusQueryHandler()
