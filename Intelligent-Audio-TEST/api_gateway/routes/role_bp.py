"""角色与权限点管理路由 — interfaces 层（INT-30）

全部挂 /api/v1/auth 前缀，admin 独占端点（require_permission 标注，
spec §3.16）；权限点仅只读暴露（由 seed_rbac.py 管理）。
"""
from fastapi import APIRouter

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.auth.role_management_service import (
    RoleManagementService,
)
from api_gateway.routes._response import to_response

router = APIRouter()


def _dispatch(result):
    """统一包装 (payload, http_code) 元组"""
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.get('/roles')
def list_roles(_: None = require_permission('role:read')):
    """全部角色（含 permissions 码列表 + is_system）"""
    return _dispatch(RoleManagementService.list_roles())


@router.get('/roles/{role_id}')
def get_role(role_id: int, _: None = require_permission('role:read')):
    """角色详情（含权限码列表）"""
    return _dispatch(RoleManagementService.get_role(role_id))


@router.get('/permissions')
def list_permissions(_: None = require_permission('permission:read')):
    """全量权限点（只读）"""
    return _dispatch(RoleManagementService.list_permissions())


@router.post('/roles')
def create_role(_: None = require_permission('role:create')):
    """创建自定义角色（name 唯一；is_system 固定 false）"""
    return _dispatch(RoleManagementService.create_role())


@router.put('/roles/{role_id}')
def update_role(role_id: int, _: None = require_permission('role:update')):
    """更新角色信息（name/description 空串=不修改）"""
    return _dispatch(RoleManagementService.update_role(role_id))


@router.post('/roles/{role_id}/permissions')
def set_role_permissions(role_id: int, _: None = require_permission('role:update')):
    """全量替换角色权限（admin 角色的 '*' 不可移除）"""
    return _dispatch(RoleManagementService.set_role_permissions(role_id))


@router.delete('/roles/{role_id}')
def delete_role(role_id: int, _: None = require_permission('role:delete')):
    """删除角色（系统角色 400；被用户引用 409）"""
    return _dispatch(RoleManagementService.delete_role(role_id))
