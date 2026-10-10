# -*- coding: utf-8 -*-
"""FastAPI routes for the DDD-style HTTP interface of api_adapter_service.

Key endpoints (delegated to application-layer command/query handlers):
- POST   /api/adapter/tasks                          — create & run a dialog task
- GET    /api/adapter/tasks/{task_id}/status          — query task status
- GET    /api/adapter/tasks/{task_id}/result          — query task final result
- DELETE /api/adapter/sessions/{session_id}           — close/destroy a session

单轮（非 session）被测协议（INT-106，与 api_test_service 单轮执行器默认
api_paths 及 tests/integration/test_task_execute_real_chain.py 契约一致）：
- POST   /api/create_task                — async create single-turn task
- GET    /api/get_status/{task_id}        — implemented in routes/api.py
- GET    /api/get_final_result/{task_id}  — implemented in routes/api.py
- DELETE /api/delete_task/{task_id}       — delete task
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
    create_single_turn_task_handler,
)
from api_adapter_service.application.commands.single_turn_commands import (
    CreateSingleTurnTaskCommand,
)
from api_adapter_service.application.queries.dialog_queries import (
    GetFinalResultQuery,
    GetTaskStatusQuery,
)
from api_adapter_service.application.queries.handlers import (
    get_final_result_handler,
    get_task_status_handler,
)
from api_adapter_service.services.task_manager import task_manager

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


# ── Single-turn (non-session) protocol ─────────────────────────────

@router.post('/api/create_task')
async def create_single_turn_task(request: Request):
    """创建并异步执行单轮任务，立即返回 data.task_id。

    请求体为单轮执行器按字段映射平铺的参数（audio_path/audio_url、
    vendor 等）；音频存储引用（oss:// 等）由应用层经统一存储层解析。
    """
    try:
        data = await request.json()
    except Exception:
        return _json({'code': 4000, 'msg': 'request body is required'}, 400)

    try:
        cmd = CreateSingleTurnTaskCommand.from_request(data)
    except ValueError as e:
        return _json({'code': 4000, 'msg': str(e)}, 400)

    result = create_single_turn_task_handler.handle(cmd)
    status = 200 if result.get('code') == 0 else 400
    return _json(result, status)


@router.delete('/api/delete_task/{task_id}')
def delete_single_turn_task(task_id: str):
    """删除任务及其结果。"""
    task_manager.delete_task(task_id)
    return _json({'code': 0, 'msg': f'task {task_id} deleted'})


# ── Session management ─────────────────────────────────────────────

@router.delete('/api/adapter/sessions/{session_id}')
def close_session(session_id: str):
    """关闭/销毁会话。"""
    cmd = CloseSessionCommand(session_id=session_id)
    result = close_session_handler.handle(cmd)
    status = 200 if result.get('code') == 0 else 500
    return _json(result, status)
