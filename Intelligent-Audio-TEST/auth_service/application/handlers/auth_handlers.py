# -*- coding: utf-8 -*-
"""auth_service 应用层 —— 命令/查询处理器（CQRS Handler）。

设计要点：
- AuthCommandHandler 处理所有写命令，通过 user_repository 操作 UserAggregate；
- AuthQueryHandler 处理所有读查询，通过 user_repository / role_repository 返回领域实体；
- Handler 不直接 import 任何 PO（持久化对象），仅与领域实体打交道，
  保证应用层与 ORM/持久化解耦；
- Handler 不返回 HTTP 响应格式（不耦合 success_response/error_response），
  只返回领域对象或基础类型，由上层 interfaces 层负责包装响应。

归属：auth_service（用户与权限上下文）
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from auth_service.domain.entities.user import UserAggregate
from auth_service.domain.entities.role import RoleEntity
from auth_service.infrastructure.persistence.user_repository import (
    user_repository,
    role_repository,
)
from auth_service.application.commands.auth_commands import (
    RegisterUserCommand,
    UpdateUserStatusCommand,
    GrantPermissionCommand,
    RevokePermissionCommand,
    CreateUserCommand,
    DeleteUserCommand,
)
from auth_service.application.queries.auth_queries import (
    GetUserQuery,
    GetUserByUsernameQuery,
    GetUserByOAuthQuery,
    ListUsersQuery,
    GetUserPermissionsQuery,
    ListRolesQuery,
)


class AuthCommandHandler:
    """认证命令处理器 —— 处理所有用户与权限相关写操作。

    通过 user_repository 持久化，不直接操作 PO。
    事务边界由调用方（如 interfaces 层的工作单元）决定 commit 时机，
    repository 写操作仅 flush。
    """

    def handle_register_user(self, cmd: RegisterUserCommand) -> int:
        """注册本地账号用户，返回新用户 ID。

        password 为明文密码；密码哈希由 infrastructure 层负责
        （UserAggregate 不持有密码字段，命令只承载意图）。
        """
        aggregate = UserAggregate(
            username=cmd.username,
            email=cmd.email,
            role_id=cmd.role_id,
            status='active',
        )
        # 密码哈希持久化由 infrastructure 层补充实现，
        # 此处仅完成领域聚合创建与基本字段落库。
        return user_repository.add(aggregate)

    def handle_update_status(self, cmd: UpdateUserStatusCommand) -> None:
        """更新用户状态。用户不存在则静默无操作。"""
        user_repository.update_status(cmd.user_id, cmd.status)

    def handle_grant_permission(self, cmd: GrantPermissionCommand) -> None:
        """向用户授予附加权限码（通过聚合根行为 + 仓储保存）。"""
        aggregate = user_repository.get_by_id(cmd.user_id)
        if aggregate is None:
            return
        aggregate.grant_permission(cmd.permission)
        user_repository.save(aggregate)

    def handle_revoke_permission(self, cmd: RevokePermissionCommand) -> None:
        """撤销用户附加权限码（通过聚合根行为 + 仓储保存）。"""
        aggregate = user_repository.get_by_id(cmd.user_id)
        if aggregate is None:
            return
        aggregate.revoke_permission(cmd.permission)
        user_repository.save(aggregate)

    def handle_create_user(self, cmd: CreateUserCommand) -> int:
        """创建用户（OAuth 登录场景，无密码），返回新用户 ID。"""
        aggregate = UserAggregate(
            username=cmd.username,
            email=cmd.email,
            oauth_provider=cmd.oauth_provider,
            oauth_subject=cmd.oauth_subject,
            role_id=cmd.role_id,
            status='active',
        )
        return user_repository.add(aggregate)

    def handle_delete_user(self, cmd: DeleteUserCommand) -> bool:
        """软删除用户，返回是否成功删除。"""
        return user_repository.soft_delete(cmd.user_id)


class AuthQueryHandler:
    """认证查询处理器 —— 处理所有用户与权限相关读操作。

    通过 user_repository / role_repository 查询，返回领域实体，
    不泄漏 PO 结构。
    """

    def handle_get_user(self, query: GetUserQuery) -> Optional[UserAggregate]:
        """按用户 ID 查询用户聚合（含生效权限）。"""
        return user_repository.get_by_id(query.user_id)

    def handle_get_user_by_username(
        self, query: GetUserByUsernameQuery
    ) -> Optional[UserAggregate]:
        """按用户名查询用户聚合。"""
        return user_repository.get_by_username(query.username)

    def handle_get_user_by_oauth(
        self, query: GetUserByOAuthQuery
    ) -> Optional[UserAggregate]:
        """按 OAuth 提供商与外部主体 ID 查询用户聚合。"""
        return user_repository.get_by_oauth(query.provider, query.subject)

    def handle_list_users(
        self, query: ListUsersQuery
    ) -> Tuple[int, List[UserAggregate]]:
        """分页查询用户列表，返回 (总数, 当前页用户聚合列表)。

        status 为 None 表示不过滤状态。
        """
        return user_repository.list_users(
            page=query.page,
            page_size=query.page_size,
            status=query.status,
        )

    def handle_get_user_permissions(
        self, query: GetUserPermissionsQuery
    ) -> List[str]:
        """获取用户生效权限码列表。"""
        return user_repository.get_user_permissions(query.user_id)

    def handle_list_roles(self, query: ListRolesQuery) -> List[RoleEntity]:
        """列出全部角色（含权限码列表）。"""
        return role_repository.get_all()
