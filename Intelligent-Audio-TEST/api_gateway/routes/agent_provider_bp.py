# -*- coding: utf-8 -*-
"""用户模型供应商代理（INT-2488，§6.4 / §11）。

职责边界（§3.1）：鉴权 / 租户 / 限流 / 审计留在网关；本路由只做「鉴权后的
透明转发」，并把身份头（X-User-Id / X-Tenant-Id / X-User-Permissions）交给
agent_service。权限码 ``agent:provider:manage``（AUTH_MODE=off 时 admin 通配）。

审计只记 provider_id 与操作类型：请求体（含明文 Key）绝不进日志。
"""
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from api_gateway.application.services.agent.agent_provider_audit import (
    write_agent_provider_audit,
)
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.routes.agent_guard import require_agent_enabled
from api_gateway.routes.agent_runtime_bp import _forward

logger = logging.getLogger(__name__)

# INT-2456：provider 管理同属 Agent 功能面，总开关关闭时一并 503。
router = APIRouter(dependencies=[Depends(require_agent_enabled)])

MANAGE_PERMISSION = 'agent:provider:manage'


def _audit(request: Request, event, provider_id, operation: str,
           response: Response) -> None:
    if 200 <= response.status_code < 300:
        write_agent_provider_audit(
            event, request=request, provider_id=provider_id,
            operation=operation, status_code=response.status_code)


def _created_provider_id(response: Response) -> str:
    try:
        payload = json.loads(bytes(response.body).decode('utf-8'))
    except (ValueError, TypeError):
        return ''
    return str(payload.get('id') or '') if isinstance(payload, dict) else ''


# ---------------------------------------------------------------- providers

@router.get('/providers')
async def proxy_list_providers(
        request: Request,
        _: None = require_permission(MANAGE_PERMISSION)) -> Response:
    return await _forward(request, 'GET')


@router.post('/providers')
async def proxy_create_provider(
        request: Request,
        _: None = require_permission(MANAGE_PERMISSION)) -> Response:
    from shared.models.common_enums import AuditEvent
    response = await _forward(request, 'POST')
    _audit(request, AuditEvent.AGENT_PROVIDER_CREATED,
           _created_provider_id(response), 'create', response)
    return response


@router.put('/providers/{provider_id}')
async def proxy_update_provider(
        provider_id: str, request: Request,
        _: None = require_permission(MANAGE_PERMISSION)) -> Response:
    from shared.models.common_enums import AuditEvent
    response = await _forward(request, 'PUT')
    _audit(request, AuditEvent.AGENT_PROVIDER_UPDATED, provider_id,
           'update', response)
    return response


@router.delete('/providers/{provider_id}')
async def proxy_delete_provider(
        provider_id: str, request: Request,
        _: None = require_permission(MANAGE_PERMISSION)) -> Response:
    from shared.models.common_enums import AuditEvent
    response = await _forward(request, 'DELETE')
    _audit(request, AuditEvent.AGENT_PROVIDER_DELETED, provider_id,
           'delete', response)
    return response


@router.post('/providers/{provider_id}/verify')
async def proxy_verify_provider(
        provider_id: str, request: Request,
        _: None = require_permission(MANAGE_PERMISSION)) -> Response:
    from shared.models.common_enums import AuditEvent
    response = await _forward(request, 'POST')
    _audit(request, AuditEvent.AGENT_PROVIDER_VERIFIED, provider_id,
           'verify', response)
    return response


@router.post('/providers/{provider_id}/set-default')
async def proxy_set_default_provider(
        provider_id: str, request: Request,
        _: None = require_permission(MANAGE_PERMISSION)) -> Response:
    from shared.models.common_enums import AuditEvent
    response = await _forward(request, 'POST')
    _audit(request, AuditEvent.AGENT_PROVIDER_DEFAULT_SET, provider_id,
           'set_default', response)
    return response


# ---------------------------------------------------------------- catalog

@router.get('/model-catalog')
async def proxy_model_catalog(
        request: Request,
        _: None = require_permission(MANAGE_PERMISSION)) -> Response:
    return await _forward(request, 'GET')
