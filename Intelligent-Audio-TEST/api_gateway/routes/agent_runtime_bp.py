# -*- coding: utf-8 -*-
"""Agent 运行底座代理（INT-2451，方案 §3 / §11）。

职责边界（§3.1）：身份、租户、限流、审计留在网关；本路由只做
「鉴权后的透明转发」，不得绕过 AuthMiddleware —— 路由挂在正常中间件链
下，AUTH_MODE=prod 时无 token 直接 401，未走到这里。

转发身份头（agent_service 只消费这些头，不自行解析 JWT）：
    X-User-Id / X-Tenant-Id / X-User-Permissions

SSE：先向上游做一次 run 快照预检（归属 / 存在性 / 状态），非 200 原样返回
（非本人 → 404，不泄漏存在性），再透传事件流；`Last-Event-ID` 与
`?cursor=` 原字节转发。
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from api_gateway.config.config import Config

logger = logging.getLogger(__name__)

router = APIRouter()

# 测试注入点（httpx.MockTransport）；生产为 None
_transport_override: Optional[httpx.BaseTransport] = None

_JSON_TIMEOUT_HEADERS = ('Content-Type', 'Cache-Control')
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


async def _forward(request: Request, method: str) -> Response:
    body = await request.body() if method in ('POST', 'PUT', 'PATCH') else b''
    return await run_in_threadpool(_forward_json, request, method, body)


def _stream_events(request: Request, run_id: str):
    """SSE 透传：预检归属 → 透传上游字节流。"""

    def generate():
        read_timeout = Config.AGENT_SERVICE_SSE_READ_TIMEOUT_SECONDS
        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT_SECONDS,
            read=(read_timeout if read_timeout > 0 else None),
            write=Config.AGENT_SERVICE_TIMEOUT_SECONDS, pool=_CONNECT_TIMEOUT_SECONDS)
        try:
            with _client(timeout) as client:
                with client.stream('GET', _upstream_url(request),
                                   headers=_forward_headers(request)) as upstream:
                    if upstream.status_code >= 400:
                        # 预检后上游仍返回错误（如中途越权）：以 SSE error 帧收口
                        yield ('event: error\n'
                               'data: {"code": "UPSTREAM_ERROR"}\n\n')
                        return
                    for chunk in upstream.iter_raw():
                        if chunk:
                            yield chunk
        except httpx.HTTPError:
            logger.warning('agent SSE 转发中断 run=%s', run_id, exc_info=True)
            yield ('event: error\n'
                   'data: {"code": "UPSTREAM_UNAVAILABLE"}\n\n')

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


@router.get('/skills')
async def proxy_skills(request: Request):
    """当前用户可见 Skill 列表（INT-2452；权限由 agent_service 按身份头过滤）。"""
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
