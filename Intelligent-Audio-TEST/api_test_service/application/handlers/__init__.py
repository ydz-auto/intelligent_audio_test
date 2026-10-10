# -*- coding: utf-8 -*-
"""应用层处理器聚合导出 — 命令处理器 + 查询处理器。"""
from api_test_service.application.handlers.command_handlers import (
    CreateAPITestCommandHandler,
    StartAPITestCommandHandler,
    StopAPITestCommandHandler,
    CreateAPICommandHandler,
    UpdateAPICommandHandler,
    DeleteAPICommandHandler,
    create_api_test_handler,
    start_api_test_handler,
    stop_api_test_handler,
    create_api_handler,
    update_api_handler,
    delete_api_handler,
)
from api_test_service.application.handlers.query_handlers import (
    GetAPITestStatusQueryHandler,
    GetAPIQueryHandler,
    ListAPIsQueryHandler,
    get_api_test_status_handler,
    get_api_handler,
    list_apis_handler,
)

__all__ = [
    # 命令处理器
    "CreateAPITestCommandHandler",
    "StartAPITestCommandHandler",
    "StopAPITestCommandHandler",
    "CreateAPICommandHandler",
    "UpdateAPICommandHandler",
    "DeleteAPICommandHandler",
    "create_api_test_handler",
    "start_api_test_handler",
    "stop_api_test_handler",
    "create_api_handler",
    "update_api_handler",
    "delete_api_handler",
    # 查询处理器
    "GetAPITestStatusQueryHandler",
    "GetAPIQueryHandler",
    "ListAPIsQueryHandler",
    "get_api_test_status_handler",
    "get_api_handler",
    "list_apis_handler",
]
