"""用户管理路由 — interfaces 层（INT-30）

全部挂 /api/v1/auth 前缀；除 POST /register（白名单，仅 dev）外
均为 admin 独占端点（require_permission 标注，spec §3.16）。
"""
from fastapi import APIRouter, HTTPException

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.auth.user_management_service import (
    UserManagementService,
)
from api_gateway.routes._response import to_response

router = APIRouter()


def _dispatch(result):
    """统一包装 (payload, http_code) 元组；400 以下状态码交由 HTTPException 语义"""
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.post('/register')
def register():
    """dev 模式自注册（白名单无权限校验；AUTH_MODE != dev → 403）"""
    return _dispatch(UserManagementService.register())


@router.get('/users')
def list_users(_: None = require_permission('user:read')):
    """用户列表（分页 ≤100，status/keyword/role_id 过滤）"""
    return _dispatch(UserManagementService.list_users())


@router.get('/users/{user_id}')
def get_user(user_id: int, _: None = require_permission('user:read')):
    """用户详情（含 role_name / 生效权限 / overrides 明细）"""
    return _dispatch(UserManagementService.get_user(user_id))


@router.post('/users')
def create_user(_: None = require_permission('user:create')):
    """admin 建用户（任意 AUTH_MODE）"""
    return _dispatch(UserManagementService.create_user())


@router.put('/users/{user_id}')
def update_user(user_id: int, _: None = require_permission('user:update')):
    """更新用户资料（username/email/status/password，缺省键不修改）"""
    return _dispatch(UserManagementService.update_user(user_id))


@router.delete('/users/{user_id}')
def delete_user(user_id: int, _: None = require_permission('user:delete')):
    """软删除用户（不可删自己）"""
    return _dispatch(UserManagementService.delete_user(user_id))


@router.post('/users/{user_id}/role')
def set_user_role(user_id: int, _: None = require_permission('user:assign_role')):
    """分配用户角色（不可改自己角色）"""
    return _dispatch(UserManagementService.set_user_role(user_id))


@router.post('/users/{user_id}/permissions')
def grant_permission(user_id: int,
                     _: None = require_permission('user:grant_permission')):
    """授予用户附加权限码（'*' 拒绝）"""
    return _dispatch(UserManagementService.grant_permission(user_id))


@router.delete('/users/{user_id}/permissions/{permission_id}')
def revoke_permission(user_id: int, permission_id: int,
                      _: None = require_permission('user:grant_permission')):
    """差量撤销用户权限（基线覆盖撤销 / 附加授予收回 / 幂等 no-op）"""
    return _dispatch(UserManagementService.revoke_permission(user_id, permission_id))
