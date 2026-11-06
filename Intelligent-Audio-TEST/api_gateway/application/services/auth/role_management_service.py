# -*- coding: utf-8 -*-
"""角色/权限点管理网关服务（INT-30）。

对齐 DDD：网关不直接操作 DB，经 auth_config_service ACL 代理调
auth_service gRPC；管理写接口响应统一注入权限生效延迟 notice。
错误映射见 management_common（AuthErrorCode → 400/403/404/409）。
"""
from __future__ import annotations

import logging
from typing import Dict, Tuple

from api_gateway.application.services.auth.management_common import (
    call_auth_rpc,
    current_operator_id,
    with_notice,
)
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import error_response, success_response
from shared.proto import auth_service_pb2 as auth_pb

logger = logging.getLogger(__name__)


class RoleManagementService:
    """角色管理服务：角色查询/增改删、角色权限全量替换、权限点只读暴露"""

    # ---------- 查询 ----------

    @staticmethod
    def list_roles() -> Tuple[Dict, int]:
        """全部角色（含 permissions 码列表 + is_system）。"""
        data, fail = call_auth_rpc('ListRoles', auth_pb.ListRolesRequest(),
                                   default_error='查询角色列表失败')
        if fail:
            return fail
        return success_response({'roles': data.get('roles', [])})

    @staticmethod
    def get_role(role_id: int) -> Tuple[Dict, int]:
        """角色详情（含权限码列表）。"""
        data, fail = call_auth_rpc('GetRole', auth_pb.GetRoleRequest(
            role_id=role_id), default_error='查询角色详情失败')
        if fail:
            return fail
        return success_response(data)

    @staticmethod
    def list_permissions() -> Tuple[Dict, int]:
        """全量权限点（只读，权限点由 seed_rbac.py 管理）。"""
        data, fail = call_auth_rpc('ListPermissions',
                                   auth_pb.ListPermissionsRequest(),
                                   default_error='查询权限点失败')
        if fail:
            return fail
        return success_response({'permissions': data.get('permissions', [])})

    # ---------- 角色增改删 ----------

    @staticmethod
    def create_role() -> Tuple[Dict, int]:
        """创建自定义角色（name 唯一；is_system 固定 False；未知权限码 400）。"""
        body = _json_body()
        name = (body.get('name') or '').strip()
        if not name:
            return error_response('name 为必填项',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc('CreateRole', auth_pb.CreateRoleRequest(
            name=name,
            description=body.get('description') or '',
            permission_codes=[str(c) for c in (body.get('permission_codes') or [])],
            operator_id=current_operator_id(),
        ), default_error='创建角色失败')
        if fail:
            return fail
        return with_notice(success_response(
            {'role_id': data.get('role_id')}, '创建成功', http_code=201))

    @staticmethod
    def update_role(role_id: int) -> Tuple[Dict, int]:
        """更新角色信息（name/description 空串=不修改；name 唯一校验）。"""
        body = _json_body()
        _, fail = call_auth_rpc('UpdateRole', auth_pb.UpdateRoleRequest(
            role_id=role_id,
            name=(body.get('name') or '').strip(),
            description=body.get('description') or '',
            operator_id=current_operator_id(),
        ), default_error='更新角色失败')
        if fail:
            return fail
        return with_notice(success_response(None, '更新成功'))

    @staticmethod
    def set_role_permissions(role_id: int) -> Tuple[Dict, int]:
        """全量替换角色权限（admin 角色的 '*' 不可移除）。"""
        body = _json_body()
        if not isinstance(body.get('permission_codes'), list):
            return error_response('permission_codes 为必填列表',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc(
            'SetRolePermissions', auth_pb.SetRolePermissionsRequest(
                role_id=role_id,
                permission_codes=[str(c) for c in body['permission_codes']],
                operator_id=current_operator_id(),
            ), default_error='更新角色权限失败')
        if fail:
            return fail
        return with_notice(success_response(None, '角色权限已更新'))

    @staticmethod
    def delete_role(role_id: int) -> Tuple[Dict, int]:
        """删除角色（系统角色 400；仍被用户引用 409；连带删 role_permissions）。"""
        _, fail = call_auth_rpc('DeleteRole', auth_pb.DeleteRoleRequest(
            role_id=role_id, operator_id=current_operator_id(),
        ), default_error='删除角色失败')
        if fail:
            return fail
        return with_notice(success_response(None, '删除成功'))


def _json_body() -> Dict:
    """预解析 JSON body（RequestAdapterMiddleware 注入）。"""
    from api_gateway.infrastructure.request_adapter import request
    body = request.get_json()
    return body if isinstance(body, dict) else {}
