# -*- coding: utf-8 -*-
"""查询处理器：委托给已有的 services/task_manager。"""

from api_adapter_service.application.queries.dialog_queries import (
    GetTaskStatusQuery,
    GetFinalResultQuery,
)
from api_adapter_service.services.task_manager import task_manager
from api_adapter_service.services.session_store import session_store


class GetTaskStatusHandler:
    """查询任务状态。"""

    def handle(self, query: GetTaskStatusQuery) -> dict:
        task = task_manager.get_task(query.task_id)
        if not task:
            return {'code': 4004, 'msg': 'task not found'}

        return {
            'code': 0,
            'data': {
                'task_id': query.task_id,
                'status': task['status'],
                'error_message': task.get('error_message'),
            },
        }


class GetFinalResultHandler:
    """查询任务最终结果（对话或流式）。"""

    def handle(self, query: GetFinalResultQuery) -> dict:
        result = task_manager.get_final_result(query.task_id)
        if not result:
            return {'code': 4004, 'msg': 'result not found'}

        return {'code': 0, 'data': result}


# 查询处理器单例
get_task_status_handler = GetTaskStatusHandler()
get_final_result_handler = GetFinalResultHandler()
