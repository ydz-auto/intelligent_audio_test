# -*- coding: utf-8 -*-
"""auth_service 应用层 —— Access Token 命令/查询处理器（CQRS Handler）。

设计要点（对齐 auth_handlers.py 既有骨架，INT-1140）：
- AccessTokenCommandHandler 处理所有写命令，通过 access_token_repository
  操作 AccessTokenAggregate；AccessTokenQueryHandler 处理所有读查询；
- Handler 不直接 import 任何 PO，仅与领域实体打交道；
- Handler 不返回 HTTP 响应格式，由 interfaces 层负责包装响应；
- 领域校验失败抛 AuthDomainError（携带 AuthErrorCode）；
- 校验通过后 ValidateAccessToken 更新 last_used_at/last_used_ip（旁路副作用，
  commit 由 interfaces 层工作单元决定）。

归属：auth_service（用户与权限上下文）
"""
from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from auth_service.config.config import Config
from auth_service.domain.entities.access_token import (
    AccessTokenAggregate,
    AccessTokenStatus,
    generate_token,
    hash_token,
    token_hint_of,
    utc8_now,
)
from auth_service.domain.exceptions import AuthDomainError
from auth_service.domain.services.auth_service import (
    validate_access_token_name,
    validate_access_token_scopes,
    validate_access_token_status,
)
from auth_service.infrastructure.persistence.access_token_repository import (
    access_token_repository,
)
from auth_service.infrastructure.persistence.user_repository import (
    user_repository,
    role_repository,
)
from auth_service.application.commands.access_token_commands import (
    CreateAccessTokenCommand,
    DeleteAccessTokenCommand,
    UpdateAccessTokenCommand,
)
from auth_service.application.queries.access_token_queries import (
    GetAccessTokenByHashQuery,
    GetAccessTokenQuery,
    ListAccessTokensQuery,
    ValidateAccessTokenQuery,
)
from shared.models.common_enums import AuthErrorCode


def _raise_if(condition: bool, message: str,
              error_code: AuthErrorCode) -> None:
    """条件成立时抛 AuthDomainError（减少 if/raise 样板）。"""
    if condition:
        raise AuthDomainError(message, error_code)


def _known_permission_codes() -> set:
    """当前 RBAC 权限码全集（permissions 表 + 通配 '*'）。

    供 scopes 校验用；实时拉取，保持领域校验纯函数无 IO。
    """
    codes = {p.code for p in role_repository.list_permissions()}
    codes.add('*')
    return codes


def _normalize_scopes(scopes: Optional[List[str]]) -> List[str]:
    """校验并归一 scopes：空列表/None=继承用户全部权限（存空列表）。"""
    known = _known_permission_codes()
    return validate_access_token_scopes(scopes, known)


def _resolve_effective_scopes(token: AccessTokenAggregate,
                              user_id: int) -> List[str]:
    """计算 token 生效 scopes：非空=按清单；空=实时拉取用户全部权限。"""
    if token.scopes:
        return list(token.scopes)
    return user_repository.get_user_permissions(user_id) or []


class AccessTokenCommandHandler:
    """Access Token 命令处理器 —— 写操作。

    通过 access_token_repository / user_repository / role_repository 持久化，
    不直接操作 PO。事务边界由调用方（interfaces 层）决定 commit 时机。
    """

    def handle_create(self, cmd: CreateAccessTokenCommand) -> Tuple[int, str]:
        """创建 Access Token，返回 (token_id, 明文 token)。

        明文仅本函数返回一次，库中只落 SHA-256 哈希 + 末 4 位 hint。
        """
        # 1. 名称
        validate_access_token_name(cmd.name)
        # 2. 归属用户必须存在（对齐 /auth/self 语义）
        user = user_repository.get_by_id(cmd.user_id)
        if user is None:
            raise AuthDomainError(
                f'用户不存在: id={cmd.user_id}', AuthErrorCode.USER_NOT_FOUND,
            )
        # 3. scopes 合法性（空列表=继承用户全部权限）
        scopes = _normalize_scopes(cmd.scopes)
        # 4. 每用户 token 上限（0/负数=不限制）
        max_tokens = int(getattr(Config, 'ACCESS_TOKEN_MAX_PER_USER', 20))
        if max_tokens > 0:
            current = access_token_repository.count_active_by_user(cmd.user_id)
            if current >= max_tokens:
                raise AuthDomainError(
                    f'每用户 token 数量已达上限（{max_tokens}），'
                    f'请先删除或停用旧 token',
                    AuthErrorCode.ACCESS_TOKEN_LIMIT_REACHED,
                )
        # 5. 过期时间：未显式指定（default_expiry=True）取配置默认有效期
        expires_at = cmd.expires_at
        if cmd.default_expiry:
            days = int(getattr(Config, 'ACCESS_TOKEN_DEFAULT_EXPIRY_DAYS', 30))
            expires_at = utc8_now() + timedelta(days=days)
        # 6. 生成明文 token + 哈希 + hint
        plaintext = generate_token()
        aggregate = AccessTokenAggregate(
            user_id=cmd.user_id,
            name=cmd.name.strip(),
            token_hash=hash_token(plaintext),
            token_hint=token_hint_of(plaintext),
            scopes=scopes,
            expires_at=expires_at,
            status=AccessTokenStatus.ENABLED.value,
        )
        token_id = access_token_repository.add(aggregate)
        return token_id, plaintext

    def handle_update(self, cmd: UpdateAccessTokenCommand) -> None:
        """更新 Access Token（None=不修改；scopes 空列表=清空继承全部）。"""
        token = access_token_repository.get_by_id(cmd.token_id, cmd.user_id)
        _raise_if(token is None,
                  f'Access Token 不存在: id={cmd.token_id}',
                  AuthErrorCode.ACCESS_TOKEN_NOT_FOUND)
        if cmd.name is not None:
            validate_access_token_name(cmd.name)
            token.name = cmd.name.strip()
        if cmd.scopes is not None:
            token.scopes = _normalize_scopes(cmd.scopes)
        if cmd.status is not None:
            validate_access_token_status(cmd.status)
            token.status = cmd.status
        if cmd.update_expires_at:
            token.expires_at = cmd.expires_at
        access_token_repository.save(token)

    def handle_delete(self, cmd: DeleteAccessTokenCommand) -> None:
        """软删除 Access Token（置 deleted_at，保留行供审计）。"""
        deleted = access_token_repository.soft_delete(
            cmd.token_id, cmd.user_id)
        if not deleted:
            raise AuthDomainError(
                f'Access Token 不存在: id={cmd.token_id}',
                AuthErrorCode.ACCESS_TOKEN_NOT_FOUND,
            )


class AccessTokenQueryHandler:
    """Access Token 查询处理器 —— 读操作。

    ValidateAccessToken 校验通过后更新 last_used_at/last_used_ip
    （旁路副作用，commit 由 interfaces 层决定）。
    """

    def handle_list(self, query: ListAccessTokensQuery) -> List[AccessTokenAggregate]:
        """列出用户未软删 token（掩码由接口层负责）。"""
        return access_token_repository.list_by_user(query.user_id)

    def handle_get(self, query: GetAccessTokenQuery) -> AccessTokenAggregate:
        """按 ID 获取 token 详情（归属校验），不存在抛 ACCESS_TOKEN_NOT_FOUND。"""
        token = access_token_repository.get_by_id(query.token_id, query.user_id)
        _raise_if(token is None,
                  f'Access Token 不存在: id={query.token_id}',
                  AuthErrorCode.ACCESS_TOKEN_NOT_FOUND)
        return token

    def handle_get_by_hash(
        self, query: GetAccessTokenByHashQuery
    ) -> Optional[AccessTokenAggregate]:
        """按 SHA-256 哈希获取 token（服务间内部查询，无副作用）。"""
        return access_token_repository.get_by_hash(query.token_hash)

    def handle_validate(self, query: ValidateAccessTokenQuery) -> Dict:
        """校验明文 token（BE2 网关鉴权分支调用）。

        成功：更新 last_used_at/last_used_ip，返回 token 信息与生效 scopes。
        失败（不存在/软删/禁用/过期）抛 AuthDomainError 携带对应 error_code，
        interfaces 层按 401 语义映射。
        """
        token_hash = hash_token(query.token)
        token = access_token_repository.get_by_hash(token_hash)
        if token is None or token.deleted_at is not None:
            raise AuthDomainError(
                'Access Token 无效', AuthErrorCode.ACCESS_TOKEN_INVALID,
            )
        if token.status != AccessTokenStatus.ENABLED.value:
            raise AuthDomainError(
                'Access Token 已禁用', AuthErrorCode.ACCESS_TOKEN_DISABLED,
            )
        if token.is_expired():
            raise AuthDomainError(
                'Access Token 已过期', AuthErrorCode.ACCESS_TOKEN_EXPIRED,
            )
        # 旁路副作用：记录最后使用时间/IP（commit 由 servicer 负责）
        used_at = utc8_now()
        access_token_repository.update_last_used(token.id, query.ip, used_at)
        token.last_used_at = used_at
        token.last_used_ip = query.ip
        effective_scopes = _resolve_effective_scopes(token, token.user_id)
        return {
            'id': token.id,
            'user_id': token.user_id,
            'name': token.name,
            'token_hint': token.token_hint,
            'status': token.status,
            'scopes': effective_scopes,
            'expires_at': token.expires_at,
            'last_used_at': used_at,
            'last_used_ip': token.last_used_ip,
        }


# ── 模块级单例 ──────────────────────────────────────────────────────

access_token_command_handler = AccessTokenCommandHandler()
access_token_query_handler = AccessTokenQueryHandler()
