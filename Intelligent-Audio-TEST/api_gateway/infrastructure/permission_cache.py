# -*- coding: utf-8 -*-
"""JWT 请求的实时权限解析（网关侧，短 TTL 进程内缓存）。

背景：JWT 是无状态快照，登录时把 permissions 写进 payload；角色权限变更后
旧 token 仍携带旧权限，原实现必须重新登录才生效。本模块在 JWT 验签后向
auth_service 拉取用户**当前**权限，用短 TTL 缓存控制 RPC 频率：

- 命中缓存 → 直接返回（最长延迟一个 TTL）；
- 未命中/过期 → GetUserPermissions，成功写入缓存（空权限也缓存）；
- RPC 失败 → 回落 JWT 快照（可用性优先，不阻断请求），失败结果不缓存；
- TTL 配置为 0 → 关闭实时化，完全沿用 JWT 快照（回滚开关）。

权限变更入口（角色权限全量替换、用户角色分配、附加权限授予/撤销）与
缓存同属一个网关进程，变更成功后调用 invalidate_permissions() 清缓存，
下一次请求立即拿到新权限。

归属：api_gateway infrastructure 层；跨服务一律 auth_service gRPC（ACL），
不直连 DB、不绕过 AuthMiddleware。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# user_id → (过期 monotonic 时间, 权限码列表)
_cache: Dict[int, Tuple[float, List[str]]] = {}
_lock = threading.Lock()


def _ttl_seconds() -> float:
    from api_gateway.config.config import Config
    return float(Config.AUTH_PERMISSION_CACHE_TTL_SECONDS)


def _rpc_timeout_seconds() -> float:
    from api_gateway.config.config import Config
    return float(Config.AUTH_PERMISSION_RPC_TIMEOUT_SECONDS)


def _fetch_permissions(user_id: int) -> Optional[List[str]]:
    """经 auth_service 拉取用户当前生效权限；失败返回 None（调用方回落快照）。"""
    try:
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        from shared.proto import auth_service_pb2 as auth_pb
        from shared.utils.grpc_json import loads as _loads

        resp = auth_config_service.stub.GetUserPermissions(
            auth_pb.GetUserPermissionsRequest(user_id=user_id),
            timeout=_rpc_timeout_seconds(),
        )
        if not resp.success:
            logger.warning('实时权限拉取失败，回落 JWT 快照: user_id=%s, %s',
                           user_id, resp.message)
            return None
        data = _loads(resp.data, {}) or {}
        return list(data.get('permissions') or [])
    except Exception:
        logger.warning('实时权限拉取异常，回落 JWT 快照: user_id=%s',
                       user_id, exc_info=True)
        return None


def resolve_permissions(user_id: int, fallback: List[str]) -> List[str]:
    """当前生效权限（实时优先，异常回落 JWT 快照）。

    Args:
        user_id: 用户 ID；0/空表示未认证，直接返回 fallback。
        fallback: JWT payload 里的权限快照，RPC 不可用时使用。
    """
    ttl = _ttl_seconds()
    if ttl <= 0 or not user_id:
        return list(fallback or [])

    now = time.monotonic()
    with _lock:
        cached = _cache.get(user_id)
        if cached and cached[0] > now:
            return list(cached[1])

    permissions = _fetch_permissions(user_id)
    if permissions is None:
        return list(fallback or [])

    with _lock:
        _cache[user_id] = (now + ttl, permissions)
    return list(permissions)


def invalidate_permissions(user_id: Optional[int] = None) -> None:
    """清实时权限缓存：None=全清（角色级变更），指定 user_id=单用户失效。"""
    with _lock:
        if user_id is None:
            _cache.clear()
        else:
            _cache.pop(user_id, None)
