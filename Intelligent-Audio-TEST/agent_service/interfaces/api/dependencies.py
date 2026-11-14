# -*- coding: utf-8 -*-
"""接口层依赖：调用方身份（由网关注入）与容器。

鉴权 / 租户 / 限流 / 审计留在 api_gateway（方案 §3.1）；本服务只消费网关
转发来的身份头，并对所有资源做 owner + tenant 归属校验。归属不符统一
404 —— 不泄漏 run / session 是否存在。
"""
from typing import NamedTuple, Optional, Tuple

from fastapi import HTTPException, Request

from agent_service.config.config import Config
from shared.constants.permissions import has_admin_credential


class Identity(NamedTuple):
    user_id: int
    tenant_id: str
    permissions: Tuple[str, ...]
    # INT-2551：网关按认证身份解析出的管理员角色标记（``X-User-Is-Admin``），
    # 与 ``shared.infrastructure.user_context`` 的 admin 判定同一口径。
    # 服务端据此复核「租户管理员」双条件里的角色那一半；客户端伪造无效
    # （网关转发时覆盖）。
    is_admin: bool = False


def _parse_flag(raw: Optional[str]) -> Optional[bool]:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return None


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
    # 缺头时按「管理员级授予 = 管理员」回落（网关未升级 / 直连本服务的开发
    # 态）：通配 ``*`` 或显式 ``agent:skill:admin`` 都算（与网关同一判定，
    # INT-2594 P3）。头部存在则以它为准 —— 显式 ``false`` 不会被翻案。
    is_admin = _parse_flag(request.headers.get('X-User-Is-Admin'))
    if is_admin is None:
        is_admin = has_admin_credential(permissions)
    return Identity(user_id=user_id, tenant_id=tenant_id,
                    permissions=permissions, is_admin=is_admin)


def get_container(request: Request):
    container = getattr(request.app.state, 'container', None)
    if container is None:
        raise HTTPException(status_code=503, detail='agent_service 未就绪')
    return container
