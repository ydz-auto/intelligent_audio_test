# -*- coding: utf-8 -*-
"""FastAPI routes for the DDD-style HTTP interface of api_adapter_service.

Key endpoints (delegated to application-layer command/query handlers):
- POST   /api/adapter/tasks                          — create & run a dialog task
- GET    /api/adapter/tasks/{task_id}/status          — query task status
- GET    /api/adapter/tasks/{task_id}/result          — query task final result
- DELETE /api/adapter/sessions/{session_id}           — close/destroy a session

说明：本模块与已有的 ``routes/api.py`` 并存，但严格遵循 DDD 四层
架构——只调用 ``application.commands.handlers`` /
``application.queries.handlers`` 中已存在的处理器单例，不直接访问
``services/`` 或 ``adapters/`` 等基础设施层。
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api_adapter_service.application.commands.dialog_commands import (
    CloseSessionCommand,
    CreateDialogTaskCommand,
)
from api_adapter_service.application.commands.handlers import (
    close_session_handler,
    create_dialog_task_handler,
)
from api_adapter_service.application.queries.dialog_queries import (
    GetFinalResultQuery,
    GetTaskStatusQuery,
)
from api_adapter_service.application.queries.handlers import (
    get_final_result_handler,
    get_task_status_handler,
)

router = APIRouter()


def _json(data: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(content=data, status_code=status)


# ── Dialog task (synchronous) ──────────────────────────────────────

@router.post('/api/adapter/tasks')
async def create_dialog_task(request: Request):
    """创建并执行一轮对话任务（同步）。

    请求体格式与已有 ``routes/api.py`` 的 ``/api/v1/tasks`` 一致，
    便于前端平滑迁移。
    """
    data = await request.json()
    if not data:
        return _json({'code': 4000, 'msg': 'request body is required'}, 400)

    try:
        cmd = CreateDialogTaskCommand.from_request(data)
    except ValueError as e:
        return _json({'code': 4000, 'msg': str(e)}, 400)

    try:
        result = create_dialog_task_handler.handle(cmd)
        status = 200 if result.get('code') == 0 else 500
        return _json(result, status)
    except Exception as e:  # noqa: BLE001
        return _json({'code': 5000, 'msg': f'Task processing failed: {e}'}, 500)


# ── Task status / result queries ───────────────────────────────────

@router.get('/api/adapter/tasks/{task_id}/status')
def get_task_status(task_id: str):
    """查询任务状态。"""
    query = GetTaskStatusQuery(task_id=task_id)
    result = get_task_status_handler.handle(query)
    status = 200 if result.get('code') == 0 else 404
    return _json(result, status)


@router.get('/api/adapter/tasks/{task_id}/result')
def get_final_result(task_id: str):
    """查询任务最终结果（对话或流式）。"""
    query = GetFinalResultQuery(task_id=task_id)
    result = get_final_result_handler.handle(query)
    status = 200 if result.get('code') == 0 else 404
    return _json(result, status)


# ── Session management ─────────────────────────────────────────────

@router.delete('/api/adapter/sessions/{session_id}')
def close_session(session_id: str):
    """关闭/销毁会话。"""
    cmd = CloseSessionCommand(session_id=session_id)
    result = close_session_handler.handle(cmd)
    status = 200 if result.get('code') == 0 else 500
    return _json(result, status)
