# -*- coding: utf-8 -*-
"""应用层处理器 (Handlers) - CQRS 命令/查询处理器聚合入口。

按 DDD 结构将命令处理器和查询处理器集中到独立 handlers/ 目录，
由本 __init__ 统一导出模块级单例，供 interfaces 层注入。
"""
from task_service.application.handlers.command_handlers import (
    TaskCommandHandler,
    task_command_handler,
)
from task_service.application.handlers.query_handlers import (
    TaskQueryHandler,
    task_query_handler,
)

__all__ = [
    'TaskCommandHandler',
    'task_command_handler',
    'TaskQueryHandler',
    'task_query_handler',
]
