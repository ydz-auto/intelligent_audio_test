# -*- coding: utf-8 -*-
"""接口层依赖：调用方身份（由网关注入）与容器。

鉴权 / 租户 / 限流 / 审计留在 api_gateway（方案 §3.1）；本服务只消费网关
转发来的身份头，并对所有资源做 owner + tenant 归属校验。归属不符统一
404 —— 不泄漏 run / session 是否存在。
"""
from typing import NamedTuple, Tuple

from fastapi import HTTPException, Request

from agent_service.config.config import Config


class Identity(NamedTuple):
    user_id: int
    tenant_id: str
    permissions: Tuple[str, ...]


def get_identity(request: Request) -> Identity:
    raw_user = request.headers.get('X-User-Id', '').strip()
    if not raw_user:
        if Config.AUTH_REQUIRED:
            raise HTTPException(status_code=401, detail='缺少调用方身份')
        raw_user = '0'
    try:
        user_id = int(raw_user)
    except ValueError:
        raise HTTPException(status_code=401, detail='调用方身份非法')
    tenant_id = (request.headers.get('X-Tenant-Id') or
                 Config.DEFAULT_TENANT_ID).strip() or Config.DEFAULT_TENANT_ID
    permissions = tuple(
        item.strip()
        for item in (request.headers.get('X-User-Permissions') or '').split(',')
        if item.strip()
    )
    return Identity(user_id=user_id, tenant_id=tenant_id,
                    permissions=permissions)


def get_container(request: Request):
    container = getattr(request.app.state, 'container', None)
    if container is None:
        raise HTTPException(status_code=503, detail='agent_service 未就绪')
    return container
