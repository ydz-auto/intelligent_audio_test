# -*- coding: utf-8 -*-
"""Agent 运行底座代理（INT-2451，方案 §3 / §11）。

职责边界（§3.1）：身份、租户、限流、审计留在网关；本路由只做
「鉴权后的透明转发」，不得绕过 AuthMiddleware —— 路由挂在正常中间件链
下，AUTH_MODE=prod 时无 token 直接 401，未走到这里。

转发身份头（agent_service 只消费这些头，不自行解析 JWT）：
    X-User-Id / X-Tenant-Id / X-User-Permissions

SSE：先向上游做一次 run 快照预检（归属 / 存在性 / 状态），非 200 原样返回
（非本人 → 404，不泄漏存在性），再透传事件流；`Last-Event-ID` 与
`?cursor=` 原字节转发。转发中断 / 上游错误时由网关合成一帧 error 事件，
与 §11 同口径：带 `id:` 且 data 内含 `run_id / sequence / type / timestamp`，
前端只按一套契约解析（不另写第二套）。
"""
import json
import logging
from typing import List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.config.config import Config
from api_gateway.routes.agent_guard import require_agent_enabled
from shared.skill_package import SKILL_IMPORT_INVALID_CODE
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)

# INT-2456：总开关默认关闭，关闭时本组路由 503 AGENT_DISABLED、不转发上游。
router = APIRouter(dependencies=[Depends(require_agent_enabled)])

# 测试注入点（httpx.MockTransport）；生产为 None
_transport_override: Optional[httpx.BaseTransport] = None

# 原样回传的上游响应头：JSON 与 Skill 导出 zip 共用（zip 需要
# Content-Disposition 才能带文件名；非 zip 响应没有该头，不影响）
_JSON_TIMEOUT_HEADERS = ('Content-Type', 'Cache-Control', 'Content-Disposition')
_CONNECT_TIMEOUT_SECONDS = 5.0


def _agent_base() -> str:
    return Config.AGENT_SERVICE_URL.rstrip('/')


def _client(timeout) -> httpx.Client:
    kwargs = {'timeout': timeout}
    if _transport_override is not None:
        kwargs['transport'] = _transport_override
    return httpx.Client(**kwargs)


def _forward_headers(request: Request) -> dict:
    headers = {}
    authorization = request.headers.get('Authorization')
    if authorization:
        headers['Authorization'] = authorization
    user_id = getattr(request.state, 'user_id', None)
    if user_id is not None:
        headers['X-User-Id'] = str(user_id)
    headers['X-Tenant-Id'] = Config.AGENT_DEFAULT_TENANT_ID
    permissions = getattr(request.state, 'permissions', None) or []
    if permissions:
        headers['X-User-Permissions'] = ','.join(permissions)
    # INT-2551：管理员角色标记（与 AuthMiddleware 的 is_admin 判定同一口径）。
    # 无条件覆盖：客户端伪造的 X-User-Is-Admin 一律作废，agent_service 用它
    # 复核「租户管理员」双条件里的角色那一半。
    headers['X-User-Is-Admin'] = (
        'true' if '*' in permissions else 'false')
    for name in ('Content-Type', 'Idempotency-Key', 'Last-Event-ID', 'Accept'):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    return headers


def _upstream_url(request: Request, path: Optional[str] = None) -> str:
    query = request.url.query
    return (f"{_agent_base()}{path or request.url.path}"
            + (f'?{query}' if query else ''))


def _to_response(upstream: httpx.Response) -> Response:
    headers = {
        name: upstream.headers[name]
        for name in _JSON_TIMEOUT_HEADERS if name in upstream.headers
    }
    return Response(content=upstream.content, status_code=upstream.status_code,
                    headers=headers)


def _forward_json(request: Request, method: str, body: bytes,
                  path: Optional[str] = None) -> Response:
    try:
        with _client(httpx.Timeout(Config.AGENT_SERVICE_TIMEOUT_SECONDS)) as client:
            upstream = client.request(
                method, _upstream_url(request, path),
                headers=_forward_headers(request), content=body or None)
    except httpx.HTTPError:
        logger.warning('agent_service 转发失败 %s %s', method,
                       request.url.path, exc_info=True)
        return JSONResponse(status_code=503,
                            content={'detail': 'agent service unavailable'})
    return _to_response(upstream)


async def _read_body_limited(request: Request, limit: int) -> Optional[bytes]:
    """有界读取请求体（INT-2549 返工 P3）。

    先按 ``Content-Length`` 预判，再流式累加兜底（chunked 或无该头时同样
    不会无界读入内存）；超限返回 ``None``，调用方回 413。
    """
    declared = request.headers.get('content-length')
    if declared and declared.isdigit() and int(declared) > limit:
        return None
    chunks: List[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b''.join(chunks)


async def _forward(request: Request, method: str, *,
                   max_body_bytes: Optional[int] = None) -> Response:
    if method in ('POST', 'PUT', 'PATCH'):
        if max_body_bytes is None:
            body = await request.body()
        else:
            body = await _read_body_limited(request, max_body_bytes)
            if body is None:
                return JSONResponse(
                    status_code=413,
                    content={
                        'detail': (f'上传包超过网关上限 {max_body_bytes} 字节'
                                   '（未读入内存）'),
                        'code': SKILL_IMPORT_INVALID_CODE,
                    })
    else:
        body = b''
    return await run_in_threadpool(_forward_json, request, method, body)


def _resume_sequence(request: Request) -> int:
    """客户端续传游标：``Last-Event-ID`` 与 ``?cursor=`` 取较大者。"""
    sequence = 0
    for value in (request.headers.get('Last-Event-ID'),
                  request.query_params.get('cursor')):
        if not value:
            continue
        try:
            sequence = max(sequence, int(value))
        except (TypeError, ValueError):
            continue
    return sequence


def _track_sequence(chunk: bytes, buffer: bytes,
                    sequence: int) -> Tuple[int, bytes]:
    """从透传的原始字节里跟踪最后一个 ``id:``（跨 chunk 的半行留到下次）。"""
    buffer += chunk
    while b'\n' in buffer:
        line, buffer = buffer.split(b'\n', 1)
        if line.startswith(b'id:'):
            try:
                sequence = max(sequence, int(line[3:].strip()))
            except (TypeError, ValueError):
                continue
    return sequence, buffer


def _sse_error_frame(run_id: str, sequence: int, code: str,
                     message: str) -> bytes:
    """合成 error 帧，字段与 agent_service 的 §11 帧完全一致。

    ``id`` 取「已下发的最后一个 sequence」而不是 +1：这一帧没有对应落库事件，
    客户端续传时从 ``sequence`` 之后继续，就不会跳过上游后续的真实事件。
    """
    payload = {
        'run_id': run_id,
        'sequence': sequence,
        'type': 'error',
        'timestamp': utcnow().isoformat(),
        'code': code,
        'message': message,
    }
    data = json.dumps(payload, ensure_ascii=False)
    return (f'id: {sequence}\n'
            f'event: error\n'
            f'data: {data}\n\n').encode('utf-8')


def _stream_events(request: Request, run_id: str):
    """SSE 透传：预检归属 → 透传上游字节流。"""

    def generate():
        read_timeout = Config.AGENT_SERVICE_SSE_READ_TIMEOUT_SECONDS
        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT_SECONDS,
            read=(read_timeout if read_timeout > 0 else None),
            write=Config.AGENT_SERVICE_TIMEOUT_SECONDS, pool=_CONNECT_TIMEOUT_SECONDS)
        sequence = _resume_sequence(request)
        buffer = b''
        try:
            with _client(timeout) as client:
                with client.stream('GET', _upstream_url(request),
                                   headers=_forward_headers(request)) as upstream:
                    if upstream.status_code >= 400:
                        # 预检后上游仍返回错误（如中途越权）：以同口径 error 帧收口
                        yield _sse_error_frame(
                            run_id, sequence, 'UPSTREAM_ERROR',
                            f'上游事件流返回 {upstream.status_code}')
                        return
                    for chunk in upstream.iter_raw():
                        if chunk:
                            sequence, buffer = _track_sequence(
                                chunk, buffer, sequence)
                            yield chunk
        except httpx.HTTPError:
            logger.warning('agent SSE 转发中断 run=%s', run_id, exc_info=True)
            yield _sse_error_frame(
                run_id, sequence, 'UPSTREAM_UNAVAILABLE',
                '上游事件流转发中断，请按 Last-Event-ID 续传')

    return generate()


# ---------------------------------------------------------------- routes

@router.post('/sessions')
async def proxy_create_session(request: Request):
    return await _forward(request, 'POST')


@router.get('/sessions/{session_id}')
async def proxy_get_session(session_id: str, request: Request):
    return await _forward(request, 'GET')


@router.post('/sessions/{session_id}/runs')
async def proxy_create_run(session_id: str, request: Request):
    return await _forward(request, 'POST')


@router.get('/runs/{run_id}')
async def proxy_get_run(run_id: str, request: Request):
    return await _forward(request, 'GET')


@router.post('/runs/{run_id}/cancel')
async def proxy_cancel_run(run_id: str, request: Request):
    return await _forward(request, 'POST')


@router.get('/runs/{run_id}/approvals')
async def proxy_approvals(run_id: str, request: Request):
    return await _forward(request, 'GET')


@router.post('/approvals/{approval_id}/decision')
async def proxy_approval_decision(approval_id: str, request: Request):
    """写操作审批决议（INT-2466，§11）。

    身份 / 租户 / 权限由网关注入；审批单归属与决策互斥由 agent_service
    判定（非本人 run 的审批单 404，并发审批只有一个生效）。
    """
    return await _forward(request, 'POST')


@router.get('/runs/{run_id}/context-snapshots')
async def proxy_context_snapshots(run_id: str, request: Request):
    """上下文压缩快照（INT-2454；调试模式下由 agent_service 带回备忘）。"""
    return await _forward(request, 'GET')


# GET /skills 的代理已迁到 ``agent_skill_bp``（INT-2549：同一路径要带
# scope/status 过滤与自定义 Skill 字段，只保留一处路由，不写双口径）。


# ---------------------------------------------------------------- 长期记忆（INT-2490）
# 路径由 agent_service 按身份头构造（tenant / owner），网关不接收任何路径参数；
# break-glass 读取在网关侧先卡专用权限（RBAC 尚无该码 = fail-closed），
# agent_service 侧再做一次同样的校验并留审计。

MEMORY_BREAK_GLASS_PERMISSION = 'memory:break_glass'


@router.get('/memory/metadata')
async def proxy_memory_metadata(request: Request):
    """本人记忆元数据（条数 / 更新时间 / 用量），不含正文。"""
    return await _forward(request, 'GET')


@router.get('/memory/proposals')
async def proxy_memory_proposals(request: Request):
    """待审批的记忆写入提案（含预演内容）。"""
    return await _forward(request, 'GET')


@router.post('/memory/proposals/{approval_id}/approve')
async def proxy_memory_approve(approval_id: str, request: Request):
    return await _forward(request, 'POST')


@router.post('/memory/proposals/{approval_id}/reject')
async def proxy_memory_reject(approval_id: str, request: Request):
    return await _forward(request, 'POST')


@router.get('/memory/break-glass')
async def proxy_memory_break_glass(
        request: Request,
        _: None = require_permission(MEMORY_BREAK_GLASS_PERMISSION)):
    """管理端 break-glass 读取正文：必须持专用权限，读取留审计。"""
    return await _forward(request, 'GET')


@router.get('/runs/{run_id}/events')
async def proxy_run_events(run_id: str, request: Request):
    # 预检：归属 / 存在性 / 状态由 agent_service 判定，非 200 原样返回
    preflight = await run_in_threadpool(
        _forward_json, request, 'GET', b'', f'/api/v1/agent/runs/{run_id}')
    if preflight.status_code != 200:
        return preflight
    return StreamingResponse(
        _stream_events(request, run_id),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
