# -*- coding: utf-8 -*-
"""HTTP 管理接口 — API 测试服务的运维/admin 端点。

通过 FastAPI Router 暴露启动/停止/查询能力，内部委托给 application 层处理器。
"""
from fastapi import APIRouter, HTTPException, status

from api_test_service.application.commands.api_test_commands import (
    CreateAPITestCommand,
    StopAPITestCommand,
)
from api_test_service.application.handlers import (
    create_api_test_handler,
    stop_api_test_handler,
)
from api_test_service.application.queries.api_test_queries import GetAPITestStatusQuery
from api_test_service.application.handlers import get_api_test_status_handler

router = APIRouter(prefix="/admin/api-tests", tags=["api-test-admin"])


@router.post("/tasks/{task_id}/start")
def start_api_test(task_id: int, case_ids: list[int] = None,
                   api_ids: list[int] = None):
    """启动一个 API 测试任务"""
    command = CreateAPITestCommand(
        task_id=task_id,
        case_ids=case_ids or [],
        api_ids=api_ids or [],
    )
    result = create_api_test_handler.handle(command)
    if not result.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "启动 API 测试任务失败"),
        )
    return result


@router.post("/tasks/{task_id}/stop")
def stop_api_test(task_id: int):
    """停止一个正在运行的 API 测试任务"""
    command = StopAPITestCommand(task_id=task_id)
    return stop_api_test_handler.handle(command)


@router.get("/tasks/{task_id}/status")
def get_api_test_status(task_id: int):
    """查询 API 测试任务状态"""
    query = GetAPITestStatusQuery(task_id=task_id)
    return get_api_test_status_handler.handle(query)
