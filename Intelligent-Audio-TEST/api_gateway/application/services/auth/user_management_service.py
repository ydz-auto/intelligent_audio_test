# -*- coding: utf-8 -*-
"""用户管理网关服务（INT-30）。

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

# 注册默认角色（按角色名解析，角色由 seed_rbac 管理）
_REGISTER_DEFAULT_ROLE = 'guest'


class UserManagementService:
    """用户管理服务：注册 / 查询 / 建改删 / 角色分配 / 附加权限授予撤销"""

    # ---------- 注册（白名单） ----------

    @staticmethod
    def register() -> Tuple[Dict, int]:
        """自助注册（无权限校验）：username/password 必填，默认角色 guest。

        INT-51：注册开关 AUTH_REGISTRATION_ENABLED 配置化，
        关闭后端点 403；任意 AUTH_MODE 可用（prod 密码登录同步放开）。
        """
        from api_gateway.config.config import Config
        if not Config.AUTH_REGISTRATION_ENABLED:
            return error_response('注册未开放',
                                  code=ErrorCode.OPERATION_FAILED, http_code=403)
        body = _json_body()
        username = (body.get('username') or '').strip()
        password = body.get('password') or ''
        if not username or not password:
            return error_response('username 与 password 为必填项',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc('CreateUser', auth_pb.CreateUserRequest(
            username=username,
            email=(body.get('email') or '').strip(),
            password=password,
            role_name=_REGISTER_DEFAULT_ROLE,
            registered=True,
        ), default_error='注册失败')
        if fail:
            return fail
        return with_notice(success_response(
            {'user_id': data.get('user_id')}, '注册成功', http_code=201))

    # ---------- 查询 ----------

    @staticmethod
    def list_users() -> Tuple[Dict, int]:
        """用户列表（分页 ≤100，支持 status/keyword/role_id 过滤）。"""
        from api_gateway.infrastructure.request_adapter import request
        try:
            page = max(int(request.args.get('page', 1)), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(max(int(request.args.get('page_size', 20)), 1), 100)
        except (TypeError, ValueError):
            page_size = 20
        status = (request.args.get('status') or '').strip()
        keyword = (request.args.get('keyword') or '').strip()
        try:
            role_id = int(request.args.get('role_id', 0) or 0)
        except (TypeError, ValueError):
            role_id = 0
        data, fail = call_auth_rpc('ListUsers', auth_pb.ListUsersRequest(
            page=page, page_size=page_size, status=status,
            keyword=keyword, role_id=role_id,
        ), default_error='查询用户列表失败')
        if fail:
            return fail
        return success_response({
            'total': data.get('total', 0),
            'users': data.get('users', []),
        })

    @staticmethod
    def get_user(user_id: int) -> Tuple[Dict, int]:
        """用户详情：用户信息 + role_name + 生效权限 + overrides 明细。"""
        data, fail = call_auth_rpc('GetUser', auth_pb.GetUserRequest(
            user_id=user_id), default_error='查询用户详情失败')
        if fail:
            return fail
        return success_response(data)

    # ---------- 用户增改删 ----------

    @staticmethod
    def create_user() -> Tuple[Dict, int]:
        """admin 建用户（任意 AUTH_MODE）：username 必填；password/role_id 可选。"""
        body = _json_body()
        username = (body.get('username') or '').strip()
        if not username:
            return error_response('username 为必填项',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc('CreateUser', auth_pb.CreateUserRequest(
            username=username,
            email=(body.get('email') or '').strip(),
            password=body.get('password') or '',
            role_id=int(body.get('role_id') or 0),
            operator_id=current_operator_id(),
        ), default_error='创建用户失败')
        if fail:
            return fail
        return with_notice(success_response(
            {'user_id': data.get('user_id')}, '创建成功', http_code=201))

    @staticmethod
    def update_user(user_id: int) -> Tuple[Dict, int]:
        """更新用户资料（body 键缺省=不修改；status∈active/inactive/locked）。"""
        body = _json_body()
        data, fail = call_auth_rpc('UpdateUser', auth_pb.UpdateUserRequest(
            user_id=user_id,
            username=body.get('username') or '',
            email=body.get('email') or '',
            status=body.get('status') or '',
            password=body.get('password') or '',
            operator_id=current_operator_id(),
        ), default_error='更新用户失败')
        if fail:
            return fail
        return with_notice(success_response(None, '更新成功'))

    @staticmethod
    def delete_user(user_id: int) -> Tuple[Dict, int]:
        """软删除用户（不可删自己）。"""
        _, fail = call_auth_rpc('DeleteUser', auth_pb.DeleteUserRequest(
            user_id=user_id, operator_id=current_operator_id(),
        ), default_error='删除用户失败')
        if fail:
            return fail
        return with_notice(success_response(None, '删除成功'))

    # ---------- 角色分配 / 附加权限 ----------

    @staticmethod
    def set_user_role(user_id: int) -> Tuple[Dict, int]:
        """分配用户角色（不可改自己角色）。"""
        body = _json_body()
        role_id = int(body.get('role_id') or 0)
        if not role_id:
            return error_response('role_id 为必填项',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        _, fail = call_auth_rpc('SetUserRole', auth_pb.SetUserRoleRequest(
            user_id=user_id, role_id=role_id,
            operator_id=current_operator_id(),
        ), default_error='分配角色失败')
        if fail:
            return fail
        return with_notice(success_response(None, '分配角色成功'))

    @staticmethod
    def grant_permission(user_id: int) -> Tuple[Dict, int]:
        """授予用户附加权限码（'*' 拒绝）。"""
        body = _json_body()
        permission = (body.get('permission') or '').strip()
        if not permission:
            return error_response('permission 为必填项',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc('GrantPermission', auth_pb.GrantPermissionRequest(
            user_id=user_id, permission=permission,
            operator_id=current_operator_id(),
        ), default_error='授权失败')
        if fail:
            return fail
        return with_notice(success_response(None, '授权成功'))

    @staticmethod
    def revoke_permission(user_id: int, permission_id: int) -> Tuple[Dict, int]:
        """差量撤销用户权限（角色基线权限覆盖撤销 / 附加授予收回 / 幂等 no-op）。"""
        data, fail = call_auth_rpc(
            'RevokePermission', auth_pb.RevokePermissionRequest(
                user_id=user_id, permission_id=permission_id,
                operator_id=current_operator_id(),
            ), default_error='撤销权限失败')
        if fail:
            return fail
        return with_notice(success_response(None, '撤销成功'))


def _json_body() -> Dict:
    """预解析 JSON body（RequestAdapterMiddleware 注入）。"""
    from api_gateway.infrastructure.request_adapter import request
    body = request.get_json()
    return body if isinstance(body, dict) else {}
