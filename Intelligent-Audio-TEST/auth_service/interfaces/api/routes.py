# -*- coding: utf-8 -*-
"""auth_service HTTP 路由（FastAPI APIRouter）

定义认证服务的 HTTP API 端点，每个路由调用 application 层 handler。
"""
from __future__ import annotations

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
    GetUserByOAuthQuery,
    GetUserByUsernameQuery,
    GetUserPermissionsQuery,
    GetUserQuery,
    ListRolesQuery,
    ListUsersQuery,
)

router = APIRouter(prefix='/api/auth', tags=['auth'])

_command_handler = AuthCommandHandler()
_query_handler = AuthQueryHandler()


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

@router.post('/register')
def register_user(req: RegisterUserRequest):
    """注册用户"""
    cmd = RegisterUserCommand(
        username=req.username,
        email=req.email,
        password=req.password,
        role_id=req.role_id,
    )
    user_id = _command_handler.handle_register_user(cmd)
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
    user_id = _command_handler.handle_create_user(cmd)
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
    _command_handler.handle_update_status(cmd)
    return {'success': True, 'message': 'ok'}


@router.delete('/users/{user_id}')
def delete_user(user_id: int):
    """删除用户（软删除）"""
    cmd = DeleteUserCommand(user_id=user_id)
    _command_handler.handle_delete_user(cmd)
    return {'success': True, 'message': 'ok'}


# ---- 权限管理 ----

@router.post('/users/{user_id}/permissions')
def grant_permission(user_id: int, req: PermissionRequest):
    """授予权限"""
    cmd = GrantPermissionCommand(user_id=user_id, permission=req.permission)
    _command_handler.handle_grant_permission(cmd)
    return {'success': True, 'message': 'ok'}


@router.delete('/users/{user_id}/permissions')
def revoke_permission(user_id: int, req: PermissionRequest):
    """撤销权限"""
    cmd = RevokePermissionCommand(user_id=user_id, permission=req.permission)
    _command_handler.handle_revoke_permission(cmd)
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
