# -*- coding: utf-8 -*-
"""auth_service HTTP 路由（FastAPI APIRouter）

定义认证服务的 HTTP API 端点，每个路由调用 application 层 handler。

事务约定（INT-315，与 gRPC servicer 同口径）：仓储层按约定只 flush，
interfaces 层为工作单元边界——写命令成功后由本路由 commit，失败 rollback
（HTTP 请求级 session scope 由 DbSessionScopeMiddleware 负责清理，不经
本中间件的进程回落线程级 scope）。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from auth_service.application.commands.auth_commands import (
    CreateUserCommand,
    DeleteUserCommand,
    GrantPermissionCommand,
    RegisterUserCommand,
    RevokePermissionCommand,
    UpdateUserStatusCommand,
)
from auth_service.application.handlers.auth_handlers import (
    AuthCommandHandler,
    AuthQueryHandler,
)
from auth_service.application.queries.auth_queries import (
    GetAuthModeQuery,
    GetUserByOAuthQuery,
    GetUserByUsernameQuery,
    GetUserPermissionsQuery,
    GetUserQuery,
    ListRolesQuery,
    ListUsersQuery,
)

from shared.models.common_enums import AuthErrorCode

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/auth', tags=['auth'])

_command_handler = AuthCommandHandler()
_query_handler = AuthQueryHandler()


def _commit() -> None:
    """提交当前 scope DB 会话（写命令成功后调用，与 gRPC servicer._commit 同口径）。"""
    from shared.models.database import get_db_session
    get_db_session().commit()


def _rollback() -> None:
    """回滚当前 scope DB 会话（写命令失败后调用，与 gRPC servicer._rollback 同口径）。"""
    try:
        from shared.models.database import get_db_session
        get_db_session().rollback()
    except Exception:
        logger.debug('rollback 失败', exc_info=True)


def _fail(e: Exception, op: str, status_by_code: Optional[dict] = None):
    """写命令异常收尾：rollback 后转 HTTPException。

    AuthDomainError 按调用方给定的 error_code → HTTP 状态码映射返回
    （对齐 api_gateway AuthErrorCode 映射口径）；其余异常按 500 处理。
    """
    from auth_service.domain.exceptions import AuthDomainError
    _rollback()
    if isinstance(e, AuthDomainError):
        status = (status_by_code or {}).get(e.error_code, 400)
        raise HTTPException(status_code=status, detail=e.message) from e
    logger.error('%s 失败: %s', op, e, exc_info=True)
    raise HTTPException(status_code=500, detail=str(e)) from e


# ---- 请求/响应模型 ----

class RegisterUserRequest(BaseModel):
    username: str = Field(..., description='用户名')
    email: str = Field('', description='邮箱')
    password: str = Field('', description='明文密码')
    role_id: Optional[int] = Field(None, description='角色 ID')


class CreateUserRequest(BaseModel):
    username: str = Field(..., description='用户名')
    email: Optional[str] = Field(None, description='邮箱')
    oauth_provider: Optional[str] = Field(None, description='OAuth 提供商')
    oauth_subject: Optional[str] = Field(None, description='OAuth 主体 ID')
    role_id: Optional[int] = Field(None, description='角色 ID')


class UpdateUserStatusRequest(BaseModel):
    status: str = Field('active', description='用户状态')


class PermissionRequest(BaseModel):
    permission: str = Field(..., description='权限码')


class ValidateTokenRequest(BaseModel):
    payload: dict = Field(..., description='JWT 载荷')


class CheckPermissionRequest(BaseModel):
    permissions: List[str] = Field(default_factory=list, description='用户权限列表')
    required_permission: str = Field('', description='所需权限码')


# ---- 用户注册/创建 ----

# AuthErrorCode → HTTP 状态码（对齐 api_gateway management_common._ERROR_HTTP_STATUS
# 中用户域子集；其余/未归类错误码一律 400）
_USER_ERR_STATUS = {
    AuthErrorCode.USER_NOT_FOUND: 404,
    AuthErrorCode.USERNAME_DUPLICATED: 400,
    AuthErrorCode.PERMISSION_NOT_FOUND: 404,
    AuthErrorCode.SELF_OPERATION_FORBIDDEN: 403,
}


@router.post('/register')
def register_user(req: RegisterUserRequest):
    """注册用户"""
    cmd = RegisterUserCommand(
        username=req.username,
        email=req.email,
        password=req.password,
        role_id=req.role_id,
    )
    try:
        user_id = _command_handler.handle_register_user(cmd)
        _commit()
    except Exception as e:
        _fail(e, 'register_user', _USER_ERR_STATUS)
    return {'success': True, 'message': 'ok', 'data': {'user_id': user_id}}


@router.post('/users')
def create_user(req: CreateUserRequest):
    """创建用户（OAuth 方式）"""
    cmd = CreateUserCommand(
        username=req.username,
        email=req.email,
        oauth_provider=req.oauth_provider,
        oauth_subject=req.oauth_subject,
        role_id=req.role_id,
    )
    try:
        user_id = _command_handler.handle_create_user(cmd)
        _commit()
    except Exception as e:
        _fail(e, 'create_user', _USER_ERR_STATUS)
    return {'success': True, 'message': 'ok', 'data': {'user_id': user_id}}


# ---- 用户查询 ----

@router.get('/users')
def list_users(
    page: int = Query(1, ge=1, description='页码'),
    page_size: int = Query(20, ge=1, le=100, description='每页条数'),
    status: Optional[str] = Query(None, description='用户状态过滤'),
):
    """列出用户"""
    q = ListUsersQuery(page=page, page_size=page_size, status=status)
    total, users = _query_handler.handle_list_users(q)
    return {
        'success': True,
        'message': 'ok',
        'data': {
            'total': total,
            'users': [{'id': u.id, 'username': u.username,
                       'email': u.email, 'status': u.status}
                      for u in users],
        },
    }


@router.get('/users/{user_id}')
def get_user(user_id: int):
    """按 ID 获取用户"""
    q = GetUserQuery(user_id=user_id)
    user = _query_handler.handle_get_user(q)
    if user is None:
        raise HTTPException(status_code=404, detail='用户不存在')
    return {
        'success': True,
        'message': 'ok',
        'data': {'id': user.id, 'username': user.username,
                 'email': user.email, 'status': user.status},
    }


@router.get('/users/by_username/{username}')
def get_user_by_username(username: str):
    """按用户名获取用户"""
    q = GetUserByUsernameQuery(username=username)
    user = _query_handler.handle_get_user_by_username(q)
    if user is None:
        raise HTTPException(status_code=404, detail='用户不存在')
    return {
        'success': True,
        'message': 'ok',
        'data': {'id': user.id, 'username': user.username,
                 'email': user.email, 'status': user.status},
    }


# ---- 用户状态管理 ----

@router.put('/users/{user_id}/status')
def update_user_status(user_id: int, req: UpdateUserStatusRequest):
    """更新用户状态"""
    cmd = UpdateUserStatusCommand(user_id=user_id, status=req.status)
    try:
        _command_handler.handle_update_status(cmd)
        _commit()
    except Exception as e:
        _fail(e, 'update_user_status', _USER_ERR_STATUS)
    return {'success': True, 'message': 'ok'}


@router.delete('/users/{user_id}')
def delete_user(user_id: int):
    """删除用户（软删除）"""
    cmd = DeleteUserCommand(user_id=user_id)
    try:
        _command_handler.handle_delete_user(cmd)
        _commit()
    except Exception as e:
        _fail(e, 'delete_user', _USER_ERR_STATUS)
    return {'success': True, 'message': 'ok'}


# ---- 权限管理 ----

@router.post('/users/{user_id}/permissions')
def grant_permission(user_id: int, req: PermissionRequest):
    """授予权限"""
    cmd = GrantPermissionCommand(user_id=user_id, permission=req.permission)
    try:
        _command_handler.handle_grant_permission(cmd)
        _commit()
    except Exception as e:
        _fail(e, 'grant_permission', _USER_ERR_STATUS)
    return {'success': True, 'message': 'ok'}


@router.delete('/users/{user_id}/permissions')
def revoke_permission(user_id: int, req: PermissionRequest):
    """撤销权限"""
    cmd = RevokePermissionCommand(user_id=user_id, permission=req.permission)
    try:
        _command_handler.handle_revoke_permission(cmd)
        _commit()
    except Exception as e:
        _fail(e, 'revoke_permission', _USER_ERR_STATUS)
    return {'success': True, 'message': 'ok'}


@router.get('/users/{user_id}/permissions')
def get_user_permissions(user_id: int):
    """获取用户权限列表"""
    q = GetUserPermissionsQuery(user_id=user_id)
    perms = _query_handler.handle_get_user_permissions(q)
    return {'success': True, 'message': 'ok', 'data': {'permissions': perms}}


# ---- 角色查询 ----

@router.get('/roles')
def list_roles():
    """列出所有角色"""
    q = ListRolesQuery()
    roles = _query_handler.handle_list_roles(q)
    return {
        'success': True,
        'message': 'ok',
        'data': {'roles': [{'id': r.id, 'name': r.name,
                            'description': r.description}
                           for r in roles]},
    }


# ---- 认证校验 ----

@router.get('/mode')
def get_auth_mode():
    """当前生效认证模式（INT-180 启动自检，公开只读）。

    仅回枚举 mode 值（off|dev|prod），无其他配置项；前端侧实际消费
    网关 /api/v1/auth/mode（认证强制点在网关），本端点服务 auth_service
    边界自身的可观测性。
    """
    mode = _query_handler.handle_get_auth_mode(GetAuthModeQuery())
    return {'success': True, 'message': 'ok', 'data': {'auth_mode': mode}}


@router.post('/validate-token')
def validate_token(req: ValidateTokenRequest):
    """验证 token payload"""
    from auth_service.domain.services.auth_service import (
        validate_token_payload,
    )
    is_valid = validate_token_payload(req.payload)
    return {'success': True, 'message': 'ok', 'data': {'valid': is_valid}}


@router.post('/check-permission')
def check_permission(req: CheckPermissionRequest):
    """检查用户是否拥有指定权限"""
    from auth_service.domain.services.auth_service import (
        check_permission,
    )
    has_perm = check_permission(req.permissions, req.required_permission)
    return {'success': True, 'message': 'ok', 'data': {'has_permission': has_perm}}
