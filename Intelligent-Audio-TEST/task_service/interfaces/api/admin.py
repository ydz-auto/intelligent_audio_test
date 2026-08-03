# -*- coding: utf-8 -*-
"""任务管理 API（内部管理端点）。

基于 FastAPI APIRouter，由 app.py 挂载到主应用。
端点委托给应用层命令/查询处理器，不直接访问基础设施。

路由前缀: /admin/tasks
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional

from task_service.application.commands.handlers import task_command_handler
from task_service.application.queries.handlers import task_query_handler
from task_service.application.commands.task_commands import (
    CreateTaskCommand,
    StartTaskCommand,
    StopTaskCommand,
    PauseTaskCommand,
    ResumeTaskCommand,
    RemoveFromQueueCommand,
    ReevaluateTaskCommand,
    MergeTasksCommand,
)
from task_service.application.queries.task_queries import (
    GetTaskQuery,
    ListTasksQuery,
    GetTaskProgressQuery,
    GetTaskCasesQuery,
)

router = APIRouter(prefix='/admin/tasks', tags=['task-admin'])


# ---- 请求模型 ----

class CreateTaskRequest(BaseModel):
    name: str
    type: str = 'api'
    description: str = ''
    config: dict = Field(default_factory=dict)
    algorithm_type: Optional[str] = None
    algorithm_params: dict = Field(default_factory=dict)
    case_ids: List[str] = Field(default_factory=list)
    device_ids: List[int] = Field(default_factory=list)
    api_ids: List[int] = Field(default_factory=list)
    created_by: Optional[int] = None


class MergeTasksRequest(BaseModel):
    source_task_ids: List[int]
    merged_task_name: str
    merged_task_type: str = 'api'
    description: str = ''
    created_by: Optional[int] = None


class ReevaluateRequest(BaseModel):
    reextract_device_output: bool = True
    reevaluate_type: str = 'all'


# ---- 写操作端点 ----

@router.post('', summary='创建任务')
def create_task(req: CreateTaskRequest):
    """创建任务（不自动启动）。"""
    cmd = CreateTaskCommand(
        name=req.name,
        task_type=req.type,
        description=req.description,
        config=req.config,
        algorithm_type=req.algorithm_type,
        algorithm_params=req.algorithm_params,
        case_ids=req.case_ids,
        device_ids=req.device_ids,
        api_ids=req.api_ids,
        created_by=req.created_by,
    )
    success, message, data = task_command_handler.handle_create_task(cmd)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'success': True, 'message': message, 'data': data}


@router.post('/{task_id}/start', summary='启动任务')
def start_task(task_id: int):
    cmd = StartTaskCommand(task_id=task_id)
    success, message, data = task_command_handler.handle_start_task(cmd)
    return {'success': success, 'message': message, 'data': data}


@router.post('/{task_id}/stop', summary='停止任务')
def stop_task(task_id: int):
    cmd = StopTaskCommand(task_id=task_id)
    success, message, data = task_command_handler.handle_stop_task(cmd)
    return {'success': success, 'message': message, 'data': data}


@router.post('/{task_id}/pause', summary='暂停任务')
def pause_task(task_id: int):
    cmd = PauseTaskCommand(task_id=task_id)
    success, message, data = task_command_handler.handle_pause_task(cmd)
    return {'success': success, 'message': message, 'data': data}


@router.post('/{task_id}/resume', summary='恢复任务')
def resume_task(task_id: int):
    cmd = ResumeTaskCommand(task_id=task_id)
    success, message, data = task_command_handler.handle_resume_task(cmd)
    return {'success': success, 'message': message, 'data': data}


@router.delete('/{task_id}/queue', summary='从队列移除任务')
def remove_from_queue(task_id: int):
    cmd = RemoveFromQueueCommand(task_id=task_id)
    success, message, data = task_command_handler.handle_remove_from_queue(cmd)
    return {'success': success, 'message': message, 'data': data}


@router.post('/{task_id}/reevaluate', summary='重新评估任务')
def reevaluate_task(task_id: int, req: ReevaluateRequest):
    cmd = ReevaluateTaskCommand(
        task_id=task_id,
        reextract_device_output=req.reextract_device_output,
        reevaluate_type=req.reevaluate_type,
    )
    success, message, data = task_command_handler.handle_reevaluate_task(cmd)
    return {'success': success, 'message': message, 'data': data}


@router.post('/merge', summary='合并任务')
def merge_tasks(req: MergeTasksRequest):
    cmd = MergeTasksCommand(
        source_task_ids=req.source_task_ids,
        merged_task_name=req.merged_task_name,
        merged_task_type=req.merged_task_type,
        description=req.description,
        created_by=req.created_by,
    )
    success, message, data = task_command_handler.handle_merge_tasks(cmd)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'success': True, 'message': message, 'data': data}


# ---- 读操作端点 ----

@router.get('', summary='任务列表')
def list_tasks(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    algorithm_type: Optional[str] = Query(None),
    created_by: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_deleted: bool = Query(False),
):
    query = ListTasksQuery(
        status=status,
        task_type=type,
        algorithm_type=algorithm_type,
        created_by=created_by,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
    )
    return task_query_handler.handle_list_tasks(query)


@router.get('/{task_id}', summary='任务详情')
def get_task(task_id: int, include_cases: bool = Query(False)):
    query = GetTaskQuery(task_id=task_id, include_cases=include_cases)
    result = task_query_handler.handle_get_task(query)
    if result is None:
        raise HTTPException(status_code=404, detail=f'任务 {task_id} 不存在')
    return result


@router.get('/{task_id}/progress', summary='任务进度')
def get_task_progress(task_id: int):
    query = GetTaskProgressQuery(task_id=task_id)
    result = task_query_handler.handle_get_task_progress(query)
    if result is None:
        raise HTTPException(status_code=404, detail=f'任务 {task_id} 不存在')
    return result


@router.get('/{task_id}/cases', summary='任务用例列表')
def get_task_cases(
    task_id: int,
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = GetTaskCasesQuery(
        task_id=task_id, status=status,
        page=page, page_size=page_size,
    )
    return task_query_handler.handle_get_task_cases(query)


def setup_admin_routes(app):
    """将管理路由挂载到 FastAPI 应用。

    在 app.py 的 create_app 中调用：
        from task_service.interfaces.api.admin import setup_admin_routes
        setup_admin_routes(app)
    """
    app.include_router(router)
