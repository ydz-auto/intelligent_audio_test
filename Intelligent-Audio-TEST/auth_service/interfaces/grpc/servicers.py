# -*- coding: utf-8 -*-
"""auth_service gRPC servicer

继承 proto 生成的 AuthServiceServicer 基类，通过 application 层 handler 处理业务逻辑，
不直接操作 PO。

失败语义（INT-30）：管理 RPC 校验失败时 AuthDomainError 携带 AuthErrorCode，
_fail 将 error_code 写入 data（{"error_code": "..."}），api_gateway 据此映射
HTTP 400/403/404/409。事务约定：写命令成功后由 servicer commit（interfaces 层
为工作单元边界），失败 rollback，session 清理仍由 DbScopeInterceptor 兜底。
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


def _fail(message: str, error_code=None) -> auth_pb.AuthResponse:
    """失败响应

    Args:
        message: 失败描述。
        error_code: AuthErrorCode 成员（可选）；提供时 data 返回
            {"error_code": "<成员值>"} 供网关映射 HTTP 状态码。
    """
    data = ''
    if error_code is not None:
        data = json.dumps({'error_code': error_code.value}, ensure_ascii=False)
    return auth_pb.AuthResponse(success=False, message=message, data=data)


def _datetime_str(value) -> str:
    """datetime → ISO 字符串（None → ''）。"""
    if value is None:
        return ''
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _user_to_dict(user, overrides=None) -> dict:
    """UserAggregate → dict

    Args:
        overrides: 权限 override 明细 [{permission_id, code, granted}]；
            仅详情查询传入（列表查询不额外查询 override）。
    """
    d = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role_id': user.role_id,
        'role_name': user.role_name,
        'status': user.status,
        'is_active': user.is_active(),
        'permissions': list(user.permissions),
        'oauth_provider': user.oauth_provider,
        'oauth_subject': user.oauth_subject,
        'created_at': _datetime_str(user.created_at),
        'updated_at': _datetime_str(user.updated_at),
        'last_login_at': _datetime_str(user.last_login_at),
    }
    if overrides is not None:
        d['overrides'] = overrides
    return d


def _role_to_dict(role) -> dict:
    """RoleEntity → dict"""
    return {
        'id': role.id,
        'name': role.name,
        'description': role.description,
        'permissions': list(role.permissions),
        'is_system': bool(role.is_system),
    }


def _permission_to_dict(perm) -> dict:
    """PermissionEntity → dict"""
    return {
        'id': perm.id,
        'name': perm.code,
        'description': perm.description,
    }


def _provider_to_public_dict(provider) -> dict:
    """OAuthProviderEntity → 登录页公开 dict（无任何凭证字段）。"""
    return provider.to_public_dict()


def _provider_to_admin_dict(provider) -> dict:
    """OAuthProviderEntity → 管理端 dict（掩去 client_secret）。"""
    return provider.to_admin_dict()


def _provider_to_full_dict(provider) -> dict:
    """OAuthProviderEntity → 完整 dict（含 client_secret，仅服务间内部链路）。"""
    d = provider.to_admin_dict()
    d['client_secret'] = provider.client_secret
    return d


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

    def _commit(self) -> None:
        """提交当前线程 DB 会话（写命令成功后调用）。"""
        from shared.models.database import get_db_session
        get_db_session().commit()

    def _rollback(self) -> None:
        """回滚当前线程 DB 会话（写命令失败后调用）。"""
        try:
            from shared.models.database import get_db_session
            get_db_session().rollback()
        except Exception:
            logger.debug('rollback 失败', exc_info=True)

    def _error_response(self, e: Exception, op: str) -> auth_pb.AuthResponse:
        """领域异常 → 携带 error_code 的失败响应；其余异常按未知错误处理。"""
        from auth_service.domain.exceptions import AuthDomainError
        if isinstance(e, AuthDomainError):
            return _fail(e.message, e.error_code)
        logger.error('%s 失败: %s', op, e, exc_info=True)
        return _fail(str(e))

    # ---- 用户查询 ----

    def GetUser(self, request, context=None) -> auth_pb.AuthResponse:
        """按 ID 获取用户（详情：含 role_name / 时间戳 / overrides 明细）"""
        try:
            from auth_service.application.queries.auth_queries import (
                GetUserQuery, ListUserOverridesQuery,
            )
            q = GetUserQuery(user_id=getattr(request, 'user_id', 0))
            user = self.query_handler.handle_get_user(q)
            overrides = self.query_handler.handle_list_user_overrides(
                ListUserOverridesQuery(user_id=user.id))
            return _ok(_user_to_dict(user, overrides=overrides))
        except Exception as e:
            return self._error_response(e, 'GetUser')

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
        """列出用户（分页 + status/keyword/role_id 过滤）"""
        try:
            from auth_service.application.queries.auth_queries import (
                ListUsersQuery,
            )
            q = ListUsersQuery(
                page=getattr(request, 'page', 1),
                page_size=getattr(request, 'page_size', 20),
                status=getattr(request, 'status', '') or None,
                keyword=getattr(request, 'keyword', '') or None,
                role_id=getattr(request, 'role_id', 0) or None,
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
        """列出所有角色（含权限码列表与 is_system）"""
        try:
            from auth_service.application.queries.auth_queries import ListRolesQuery
            q = ListRolesQuery()
            roles = self.query_handler.handle_list_roles(q)
            return _ok({'roles': [_role_to_dict(r) for r in roles]})
        except Exception as e:
            logger.error("ListRoles 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def ListPermissions(self, request, context=None) -> auth_pb.AuthResponse:
        """列出全部权限点"""
        try:
            from auth_service.application.queries.auth_queries import (
                ListPermissionsQuery,
            )
            perms = self.query_handler.handle_list_permissions(
                ListPermissionsQuery())
            return _ok({'permissions': [_permission_to_dict(p) for p in perms]})
        except Exception as e:
            logger.error("ListPermissions 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def GetRole(self, request, context=None) -> auth_pb.AuthResponse:
        """按角色 ID 获取角色（含权限码列表）"""
        try:
            from auth_service.application.queries.auth_queries import GetRoleQuery
            role = self.query_handler.handle_get_role(
                GetRoleQuery(role_id=getattr(request, 'role_id', 0)))
            return _ok(_role_to_dict(role))
        except Exception as e:
            return self._error_response(e, 'GetRole')

    # ---- 用户管理（写操作）----

    def CreateUser(self, request, context=None) -> auth_pb.AuthResponse:
        """创建用户（OAuth 方式或本地注册，含密码与角色解析）"""
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
                role_name=getattr(request, 'role_name', ''),
                password=getattr(request, 'password', ''),
                operator_id=getattr(request, 'operator_id', 0),
                registered=bool(getattr(request, 'registered', False)),
            )
            user_id = self.command_handler.handle_create_user(cmd)
            self._commit()
            return _ok({'user_id': user_id}, '创建成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'CreateUser')

    def UpdateUserStatus(self, request, context=None) -> auth_pb.AuthResponse:
        """更新用户状态"""
        try:
            from auth_service.application.commands.auth_commands import (
                UpdateUserStatusCommand,
            )
            cmd = UpdateUserStatusCommand(
                user_id=getattr(request, 'user_id', 0),
                status=getattr(request, 'status', 'active'),
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_update_status(cmd)
            self._commit()
            return _ok({}, '更新成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'UpdateUserStatus')

    def UpdateUser(self, request, context=None) -> auth_pb.AuthResponse:
        """更新用户资料（username/email/status/password，空串=不修改）"""
        try:
            from auth_service.application.commands.auth_commands import (
                UpdateUserCommand,
            )
            cmd = UpdateUserCommand(
                user_id=getattr(request, 'user_id', 0),
                username=getattr(request, 'username', '') or None,
                email=getattr(request, 'email', '') or None,
                status=getattr(request, 'status', '') or None,
                password=getattr(request, 'password', '') or None,
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_update_user(cmd)
            self._commit()
            return _ok({}, '更新成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'UpdateUser')

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
            self._commit()
            return _ok({}, '更新成功')
        except Exception as e:
            self._rollback()
            logger.error("UpdateLastLogin 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def GrantPermission(self, request, context=None) -> auth_pb.AuthResponse:
        """授予用户附加权限（差量 upsert override，真实落 user_permissions 表）"""
        try:
            from auth_service.application.commands.auth_commands import (
                GrantPermissionCommand,
            )
            cmd = GrantPermissionCommand(
                user_id=getattr(request, 'user_id', 0),
                permission=getattr(request, 'permission', ''),
                operator_id=getattr(request, 'operator_id', 0),
            )
            permission_id = self.command_handler.handle_grant_permission(cmd)
            self._commit()
            return _ok({'permission_id': permission_id}, '授权成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'GrantPermission')

    def RevokePermission(self, request, context=None) -> auth_pb.AuthResponse:
        """差量撤销用户权限（permission_id 优先）"""
        try:
            from auth_service.application.commands.auth_commands import (
                RevokePermissionCommand,
            )
            cmd = RevokePermissionCommand(
                user_id=getattr(request, 'user_id', 0),
                permission=getattr(request, 'permission', ''),
                permission_id=getattr(request, 'permission_id', 0) or None,
                operator_id=getattr(request, 'operator_id', 0),
            )
            action = self.command_handler.handle_revoke_permission(cmd)
            self._commit()
            return _ok({'action': action}, '撤销成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'RevokePermission')

    def SetUserRole(self, request, context=None) -> auth_pb.AuthResponse:
        """设置用户角色"""
        try:
            from auth_service.application.commands.auth_commands import (
                SetUserRoleCommand,
            )
            cmd = SetUserRoleCommand(
                user_id=getattr(request, 'user_id', 0),
                role_id=getattr(request, 'role_id', 0),
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_set_user_role(cmd)
            self._commit()
            return _ok({}, '分配角色成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'SetUserRole')

    def DeleteUser(self, request, context=None) -> auth_pb.AuthResponse:
        """删除用户（软删除）"""
        try:
            from auth_service.application.commands.auth_commands import (
                DeleteUserCommand,
            )
            cmd = DeleteUserCommand(
                user_id=getattr(request, 'user_id', 0),
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_delete_user(cmd)
            self._commit()
            return _ok({}, '删除成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'DeleteUser')

    # ---- 角色管理（写操作）----

    def CreateRole(self, request, context=None) -> auth_pb.AuthResponse:
        """创建自定义角色"""
        try:
            from auth_service.application.commands.auth_commands import (
                CreateRoleCommand,
            )
            cmd = CreateRoleCommand(
                name=getattr(request, 'name', ''),
                description=getattr(request, 'description', ''),
                permission_codes=list(getattr(request, 'permission_codes', [])),
                operator_id=getattr(request, 'operator_id', 0),
            )
            role_id = self.command_handler.handle_create_role(cmd)
            self._commit()
            return _ok({'role_id': role_id}, '创建成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'CreateRole')

    def UpdateRole(self, request, context=None) -> auth_pb.AuthResponse:
        """更新角色信息（name/description 空串=不修改）"""
        try:
            from auth_service.application.commands.auth_commands import (
                UpdateRoleCommand,
            )
            cmd = UpdateRoleCommand(
                role_id=getattr(request, 'role_id', 0),
                name=getattr(request, 'name', '') or None,
                description=getattr(request, 'description', '') or None,
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_update_role(cmd)
            self._commit()
            return _ok({}, '更新成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'UpdateRole')

    def SetRolePermissions(self, request, context=None) -> auth_pb.AuthResponse:
        """全量替换角色权限"""
        try:
            from auth_service.application.commands.auth_commands import (
                SetRolePermissionsCommand,
            )
            cmd = SetRolePermissionsCommand(
                role_id=getattr(request, 'role_id', 0),
                permission_codes=list(getattr(request, 'permission_codes', [])),
                operator_id=getattr(request, 'operator_id', 0),
            )
            codes = self.command_handler.handle_set_role_permissions(cmd)
            self._commit()
            return _ok({'permission_codes': codes}, '角色权限已更新')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'SetRolePermissions')

    def DeleteRole(self, request, context=None) -> auth_pb.AuthResponse:
        """删除角色（系统角色/仍被引用的角色拒绝）"""
        try:
            from auth_service.application.commands.auth_commands import (
                DeleteRoleCommand,
            )
            cmd = DeleteRoleCommand(
                role_id=getattr(request, 'role_id', 0),
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_delete_role(cmd)
            self._commit()
            return _ok({}, '删除成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'DeleteRole')

    # ---- 登录体系改造（INT-51）----

    def LoginWithPassword(self, request, context=None) -> auth_pb.AuthResponse:
        """用户名+密码登录校验（bcrypt 在 auth_service 内完成）"""
        try:
            from auth_service.application.queries.auth_queries import (
                VerifyCredentialsQuery,
            )
            user = self.query_handler.handle_verify_credentials(
                VerifyCredentialsQuery(
                    username=getattr(request, 'username', ''),
                    password=getattr(request, 'password', ''),
                ))
            if user is None:
                return _fail('用户名或密码错误')
            if not user.is_active():
                return _fail('用户已被禁用')
            return _ok(_user_to_dict(user))
        except Exception as e:
            logger.error("LoginWithPassword 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def ListOAuthProviders(self, request, context=None) -> auth_pb.AuthResponse:
        """列出 OAuth 提供方（管理端，含禁用；client_secret 掩去）"""
        try:
            from auth_service.application.queries.auth_queries import (
                ListOAuthProvidersQuery,
            )
            providers = self.query_handler.handle_list_oauth_providers(
                ListOAuthProvidersQuery(
                    include_disabled=bool(
                        getattr(request, 'include_disabled', True)),
                ))
            return _ok({'providers': [_provider_to_admin_dict(p)
                                      for p in providers]})
        except Exception as e:
            logger.error("ListOAuthProviders 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def GetOAuthProvider(self, request, context=None) -> auth_pb.AuthResponse:
        """按 ID 获取提供方（管理端，client_secret 掩去）"""
        try:
            from auth_service.application.queries.auth_queries import (
                GetOAuthProviderQuery,
            )
            provider = self.query_handler.handle_get_oauth_provider(
                GetOAuthProviderQuery(
                    provider_id=getattr(request, 'provider_id', 0)))
            return _ok(_provider_to_admin_dict(provider))
        except Exception as e:
            return self._error_response(e, 'GetOAuthProvider')

    def GetOAuthProviderBySlug(self, request, context=None) -> auth_pb.AuthResponse:
        """按 slug 获取提供方（登录链路，含 client_secret 供网关换 token）"""
        try:
            from auth_service.application.queries.auth_queries import (
                GetOAuthProviderBySlugQuery,
            )
            provider = self.query_handler.handle_get_oauth_provider_by_slug(
                GetOAuthProviderBySlugQuery(
                    slug=getattr(request, 'slug', '')))
            if provider is None:
                return _fail('提供方不存在',
                             AuthErrorCode.OAUTH_PROVIDER_NOT_FOUND)
            if not provider.enabled:
                return _fail('提供方未启用')
            return _ok(_provider_to_full_dict(provider))
        except Exception as e:
            logger.error("GetOAuthProviderBySlug 失败: %s", e, exc_info=True)
            return self._error_response(e, 'GetOAuthProviderBySlug')

    def ListEnabledOAuthProviders(self, request,
                                  context=None) -> auth_pb.AuthResponse:
        """已启用提供方列表（登录页动态渲染，公开数据）"""
        try:
            from auth_service.application.queries.auth_queries import (
                ListOAuthProvidersQuery,
            )
            providers = self.query_handler.handle_list_oauth_providers(
                ListOAuthProvidersQuery(include_disabled=False))
            return _ok({'providers': [_provider_to_public_dict(p)
                                      for p in providers]})
        except Exception as e:
            logger.error("ListEnabledOAuthProviders 失败: %s", e, exc_info=True)
            return _fail(str(e))

    def CreateOAuthProvider(self, request, context=None) -> auth_pb.AuthResponse:
        """创建自定义 OAuth 提供方"""
        try:
            from auth_service.application.commands.auth_commands import (
                CreateOAuthProviderCommand,
            )
            cmd = CreateOAuthProviderCommand(
                name=getattr(request, 'name', ''),
                slug=getattr(request, 'slug', ''),
                client_id=getattr(request, 'client_id', ''),
                client_secret=getattr(request, 'client_secret', ''),
                authorize_url=getattr(request, 'authorize_url', ''),
                token_url=getattr(request, 'token_url', ''),
                userinfo_url=getattr(request, 'userinfo_url', ''),
                icon=getattr(request, 'icon', ''),
                enabled=bool(getattr(request, 'enabled', False)),
                scopes=getattr(request, 'scopes', ''),
                user_id_field=getattr(request, 'user_id_field', ''),
                username_field=getattr(request, 'username_field', ''),
                display_name_field=getattr(request, 'display_name_field', ''),
                email_field=getattr(request, 'email_field', ''),
                operator_id=getattr(request, 'operator_id', 0),
            )
            provider_id = self.command_handler.handle_create_oauth_provider(cmd)
            self._commit()
            return _ok({'provider_id': provider_id}, '创建成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'CreateOAuthProvider')

    def UpdateOAuthProvider(self, request, context=None) -> auth_pb.AuthResponse:
        """更新提供方（空串字段=不修改；client_secret 空串=保留原值）"""
        try:
            from auth_service.application.commands.auth_commands import (
                UpdateOAuthProviderCommand,
            )
            update_enabled = bool(getattr(request, 'update_enabled', False))
            cmd = UpdateOAuthProviderCommand(
                provider_id=getattr(request, 'provider_id', 0),
                name=getattr(request, 'name', '') or None,
                slug=getattr(request, 'slug', '') or None,
                icon=getattr(request, 'icon', '') or None,
                enabled=(bool(getattr(request, 'enabled', False))
                         if update_enabled else None),
                client_id=getattr(request, 'client_id', '') or None,
                client_secret=getattr(request, 'client_secret', '') or None,
                authorize_url=getattr(request, 'authorize_url', '') or None,
                token_url=getattr(request, 'token_url', '') or None,
                userinfo_url=getattr(request, 'userinfo_url', '') or None,
                scopes=getattr(request, 'scopes', '') or None,
                user_id_field=getattr(request, 'user_id_field', '') or None,
                username_field=getattr(request, 'username_field', '') or None,
                display_name_field=(getattr(request, 'display_name_field', '')
                                    or None),
                email_field=getattr(request, 'email_field', '') or None,
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_update_oauth_provider(cmd)
            self._commit()
            return _ok({}, '更新成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'UpdateOAuthProvider')

    def DeleteOAuthProvider(self, request, context=None) -> auth_pb.AuthResponse:
        """删除提供方"""
        try:
            from auth_service.application.commands.auth_commands import (
                DeleteOAuthProviderCommand,
            )
            cmd = DeleteOAuthProviderCommand(
                provider_id=getattr(request, 'provider_id', 0),
                operator_id=getattr(request, 'operator_id', 0),
            )
            self.command_handler.handle_delete_oauth_provider(cmd)
            self._commit()
            return _ok({}, '删除成功')
        except Exception as e:
            self._rollback()
            return self._error_response(e, 'DeleteOAuthProvider')
