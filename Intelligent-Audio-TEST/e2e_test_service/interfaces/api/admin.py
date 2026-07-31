# -*- coding: utf-8 -*-
"""E2E 测试管理 REST API。

提供 HTTP 接口供运维/管理端使用，委托给应用层的命令/查询处理器。
gRPC 接口仍由 grpc/servicers.py 处理。

路由注册方式：
    from e2e_test_service.interfaces.api.admin import router
    app.include_router(router, prefix='/e2e', tags=['e2e-admin'])
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from e2e_test_service.application.commands.e2e_commands import (
    StartE2ETestCommand,
    StopE2ETestCommand,
)
from e2e_test_service.application.commands.handlers import (
    StartE2ETestHandler,
    StopE2ETestHandler,
)
from e2e_test_service.application.queries.e2e_queries import (
    GetDeviceStatusQuery,
    GetTestProgressQuery,
)
from e2e_test_service.application.queries.handlers import (
    GetDeviceStatusHandler,
    GetTestProgressHandler,
)


router = APIRouter()


# ---- 请求/响应模型 ----

class StartE2ETestRequest(BaseModel):
    task_id: str = Field(..., description="任务 ID")
    tc_rel_id: str = Field(..., description="测试用例关联 ID")
    device_ids: list = Field(default_factory=list, description="设备 ID 列表")


class StopE2ETestRequest(BaseModel):
    task_id: str = Field(..., description="任务 ID")


class DeviceStatusRequest(BaseModel):
    task_id: str
    device_id: str


class TestProgressRequest(BaseModel):
    task_id: str


# ---- 路由 ----

@router.post("/start")
def start_e2e_test(req: StartE2ETestRequest):
    """启动 E2E 测试"""
    command = StartE2ETestCommand(
        task_id=req.task_id,
        tc_rel_id=req.tc_rel_id,
        device_ids=req.device_ids,
    )
    handler = StartE2ETestHandler()
    result = handler.handle(command)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('message', ''))
    return result


@router.post("/stop")
def stop_e2e_test(req: StopE2ETestRequest):
    """停止 E2E 测试"""
    command = StopE2ETestCommand(task_id=req.task_id)
    handler = StopE2ETestHandler()
    return handler.handle(command)


@router.get("/device-status")
def get_device_status(task_id: str, device_id: str):
    """获取设备状态"""
    query = GetDeviceStatusQuery(task_id=task_id, device_id=device_id)
    handler = GetDeviceStatusHandler()
    return handler.handle(query)


@router.get("/progress")
def get_test_progress(task_id: str):
    """获取测试进度"""
    query = GetTestProgressQuery(task_id=task_id)
    handler = GetTestProgressHandler()
    return handler.handle(query)
