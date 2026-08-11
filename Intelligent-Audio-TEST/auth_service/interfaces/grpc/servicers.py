# -*- coding: utf-8 -*-
"""auth_service gRPC servicer

继承 proto 生成的 AuthServiceServicer 基类，通过 application 层 handler 处理业务逻辑，
不直接操作 PO。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from shared.proto import auth_service_pb2 as auth_pb
from shared.proto import auth_service_pb2_grpc as auth_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


def _ok(data: Any, message: str = 'ok') -> auth_pb.AuthResponse:
    """成功响应"""
    return auth_pb.AuthResponse(
        success=True,
        message=message,
        data=json.dumps(data, ensure_ascii=False, default=str) if not isinstance(data, str) else data,
    )


def _fail(message: str) -> auth_pb.AuthResponse:
    """失败响应"""
    return auth_pb.AuthResponse(success=False, message=message, data='')


def _user_to_dict(user) -> dict:
    """UserAggregate → dict"""
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role_id': user.role_id,
        'role_name': '',
        'status': user.status,
        'is_active': user.is_active(),
        'permissions': list(user.permissions),
        'oauth_provider': user.oauth_provider,
        'oauth_subject': user.oauth_subject,
    }


class AuthServicer(auth_grpc.AuthServiceServicer):
    """认证服务 gRPC servicer。

    方法通过 application 层 AuthCommandHandler / AuthQueryHandler 处理，
    不直接操作 PO。
    """

    def __init__(self):
        self._command_handler = None
        self._query_handler = None

    @property
    def command_handler(self):
        """延迟初始化命令处理器，避免导入期触发 DB 连接"""
        if self._command_handler is None:
            from auth_service.application.handlers.auth_handlers import (
                AuthCommandHandler,
            )
            self._command_handler = AuthCommandHandler()
        return self._command_handler

    @property
    def query_handler(self):
        """延迟初始化查询处理器"""
        if self._query_handler is None:
            from auth_service.application.handlers.auth_handlers import (
                AuthQueryHandler,
            )
            self._query_handler = AuthQueryHandler()
        return self._query_handler

    # ---- 用户查询 ----

    def GetUser(self, request, context=None) -> auth_pb.AuthResponse:
        """按 ID 获取用户"""
        try:
            from auth_service.application.queries.auth_queries import GetUserQuery
            q = GetUserQuery(user_id=getattr(request, 'user_id', 0))
            user = self.query_handler.handle_get_user(q)
            if user is None:
                return _fail('用户不存在')
            return _ok(_user_to_dict(user))
        except Exception as e:
            logger.error("GetUser 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def GetUserByUsername(self, request, context=None) -> auth_pb.AuthResponse:
        """按用户名获取用户"""
        try:
            from auth_service.application.queries.auth_queries import (
                GetUserByUsernameQuery,
            )
            q = GetUserByUsernameQuery(
                username=getattr(request, 'username', ''),
            )
            user = self.query_handler.handle_get_user_by_username(q)
            if user is None:
                return _fail('用户不存在')
            return _ok(_user_to_dict(user))
        except Exception as e:
            logger.error("GetUserByUsername 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def GetUserByOAuth(self, request, context=None) -> auth_pb.AuthResponse:
        """按 OAuth 获取用户"""
        try:
            from auth_service.application.queries.auth_queries import (
                GetUserByOAuthQuery,
            )
            q = GetUserByOAuthQuery(
                provider=getattr(request, 'provider', ''),
                subject=getattr(request, 'subject', ''),
            )
            user = self.query_handler.handle_get_user_by_oauth(q)
            if user is None:
                return _fail('用户不存在')
            return _ok(_user_to_dict(user))
        except Exception as e:
            logger.error("GetUserByOAuth 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def ListUsers(self, request, context=None) -> auth_pb.AuthResponse:
        """列出用户"""
        try:
            from auth_service.application.queries.auth_queries import (
                ListUsersQuery,
            )
            q = ListUsersQuery(
                page=getattr(request, 'page', 1),
                page_size=getattr(request, 'page_size', 20),
                status=getattr(request, 'status', '') or None,
            )
            total, users = self.query_handler.handle_list_users(q)
            return _ok({
                'total': total,
                'users': [_user_to_dict(u) for u in users],
            })
        except Exception as e:
            logger.error("ListUsers 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def GetUserPermissions(self, request, context=None) -> auth_pb.AuthResponse:
        """获取用户权限列表"""
        try:
            from auth_service.application.queries.auth_queries import (
                GetUserPermissionsQuery,
            )
            q = GetUserPermissionsQuery(
                user_id=getattr(request, 'user_id', 0),
            )
            perms = self.query_handler.handle_get_user_permissions(q)
            return _ok({'permissions': perms})
        except Exception as e:
            logger.error("GetUserPermissions 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def ListRoles(self, request, context=None) -> auth_pb.AuthResponse:
        """列出所有角色"""
        try:
            from auth_service.application.queries.auth_queries import ListRolesQuery
            q = ListRolesQuery()
            roles = self.query_handler.handle_list_roles(q)
            return _ok({
                'roles': [{'id': r.id, 'name': r.name,
                           'description': r.description,
                           'permissions': list(r.permissions)}
                          for r in roles]
            })
        except Exception as e:
            logger.error("ListRoles 失败: %s", e, exc_info=True)
            return _fail(str(e))

    # ---- 用户管理（写操作）----

    def CreateUser(self, request, context=None) -> auth_pb.AuthResponse:
        """创建用户（OAuth 方式）"""
        try:
            from auth_service.application.commands.auth_commands import (
                CreateUserCommand,
            )
            cmd = CreateUserCommand(
                username=getattr(request, 'username', ''),
                email=getattr(request, 'email', ''),
                oauth_provider=getattr(request, 'oauth_provider', '') or None,
                oauth_subject=getattr(request, 'oauth_subject', '') or None,
                role_id=getattr(request, 'role_id', 0) or None,
            )
            user_id = self.command_handler.handle_create_user(cmd)
            return _ok({'user_id': user_id}, '创建成功')
        except Exception as e:
            logger.error("CreateUser 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def UpdateUserStatus(self, request, context=None) -> auth_pb.AuthResponse:
        """更新用户状态"""
        try:
            from auth_service.application.commands.auth_commands import (
                UpdateUserStatusCommand,
            )
            cmd = UpdateUserStatusCommand(
                user_id=getattr(request, 'user_id', 0),
                status=getattr(request, 'status', 'active'),
            )
            self.command_handler.handle_update_status(cmd)
            return _ok({}, '更新成功')
        except Exception as e:
            logger.error("UpdateUserStatus 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def UpdateLastLogin(self, request, context=None) -> auth_pb.AuthResponse:
        """更新最后登录时间/IP"""
        try:
            from auth_service.infrastructure.persistence.user_repository import (
                user_repository,
            )
            user_repository.update_last_login(
                getattr(request, 'user_id', 0),
                getattr(request, 'ip', '') or None,
            )
            return _ok({}, '更新成功')
        except Exception as e:
            logger.error("UpdateLastLogin 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def GrantPermission(self, request, context=None) -> auth_pb.AuthResponse:
        """授予权限"""
        try:
            from auth_service.application.commands.auth_commands import (
                GrantPermissionCommand,
            )
            cmd = GrantPermissionCommand(
                user_id=getattr(request, 'user_id', 0),
                permission=getattr(request, 'permission', ''),
            )
            self.command_handler.handle_grant_permission(cmd)
            return _ok({}, '授权成功')
        except Exception as e:
            logger.error("GrantPermission 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def RevokePermission(self, request, context=None) -> auth_pb.AuthResponse:
        """撤销权限"""
        try:
            from auth_service.application.commands.auth_commands import (
                RevokePermissionCommand,
            )
            cmd = RevokePermissionCommand(
                user_id=getattr(request, 'user_id', 0),
                permission=getattr(request, 'permission', ''),
            )
            self.command_handler.handle_revoke_permission(cmd)
            return _ok({}, '撤销成功')
        except Exception as e:
            logger.error("RevokePermission 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def DeleteUser(self, request, context=None) -> auth_pb.AuthResponse:
        """删除用户（软删除）"""
        try:
            from auth_service.application.commands.auth_commands import (
                DeleteUserCommand,
            )
            cmd = DeleteUserCommand(
                user_id=getattr(request, 'user_id', 0),
            )
            self.command_handler.handle_delete_user(cmd)
            return _ok({}, '删除成功')
        except Exception as e:
            logger.error("DeleteUser 失败: %s", e, exc_info=True)
            return _fail(str(e))
