# -*- coding: utf-8 -*-
"""查询处理器 — 委托给已有的 core/api_test_service.py，不重写逻辑。

API 配置 CRUD 查询处理器（GetAPI/ListAPIs）则直接通过
api_test_repository 操作聚合根，不直接 import PO，保持领域隔离。
"""
from api_test_service.application.queries.api_test_queries import (
    GetAPITestStatusQuery,
    GetAPIQuery,
    ListAPIsQuery,
)
from api_test_service.core.api_test_service import api_test_service as _service
from api_test_service.infrastructure.persistence.api_test_repository import api_test_repository
from api_test_service.application.handlers.command_handlers import _aggregate_to_dict


class GetAPITestStatusQueryHandler:
    """处理 GetAPITestStatusQuery — 查询 API 测试任务状态

    委托给 APITestService.get_task_status(task_id)。
    """

    def handle(self, query: GetAPITestStatusQuery) -> dict:
        return _service.get_task_status(task_id=query.task_id)


# ========== API 配置 CRUD 查询处理器（通过 repository 操作聚合根）==========


class GetAPIQueryHandler:
    """处理 GetAPIQuery — 查询单个 API 配置详情

    通过 api_test_repository.get_api 加载 APIAggregate 聚合根。
    """

    def handle(self, query: GetAPIQuery) -> dict:
        try:
            aggregate = api_test_repository.get_api(query.api_id)
            if aggregate is None:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}
            return {
                'success': True,
                'message': 'Success',
                'data': _aggregate_to_dict(aggregate),
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


class ListAPIsQueryHandler:
    """处理 ListAPIsQuery — 分页查询 API 配置列表

    通过 api_test_repository.list_apis 分页查询 APIAggregate 聚合根列表。
    """

    def handle(self, query: ListAPIsQuery) -> dict:
        try:
            result = api_test_repository.list_apis(
                page=query.page,
                per_page=query.per_page,
                keyword=query.keyword,
                status=query.status,
                algorithm_type=query.algorithm_type,
            )
            data = {
                'items': [_aggregate_to_dict(aggregate) for aggregate in result['items']],
                'total': result['total'],
                'page': result['page'],
                'per_page': result['per_page'],
                'pages': result['pages'],
            }
            return {
                'success': True,
                'message': 'Success',
                'data': data,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


# 便于直接调用的模块级实例
get_api_test_status_handler = GetAPITestStatusQueryHandler()
get_api_handler = GetAPIQueryHandler()
list_apis_handler = ListAPIsQueryHandler()
