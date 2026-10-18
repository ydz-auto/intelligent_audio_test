# -*- coding: utf-8 -*-
"""用户管理网关服务（INT-30）。

对齐 DDD：网关不直接操作 DB，经 auth_config_service ACL 代理调
auth_service gRPC；管理写接口响应统一注入权限生效延迟 notice。
错误映射见 management_common（AuthErrorCode → 400/403/404/409）。
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Tuple

from api_gateway.application.services.auth.management_common import (
    call_auth_rpc,
    current_operator_id,
    with_notice,
)
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import error_response, success_response
from shared.models.common_enums import AuthErrorCode
from shared.proto import auth_service_pb2 as auth_pb

logger = logging.getLogger(__name__)

# 注册默认角色（按角色名解析，角色由 seed_rbac 管理）
_REGISTER_DEFAULT_ROLE = 'guest'

# 注册参数缺失文案（INT-186 单一来源：按实际缺失字段区分，替换对缺
# 密文场景误导的「请输入用户名、邮箱和密码」；测试引用同源断言）
REGISTER_ERR_MISSING_CIPHERTEXT = (
    '密码需加密提交：缺少加密后的密码密文字段（{fields}）；'
    '请先经 /auth/login/encryption-key 获取公钥，对密码 RSA 加密后提交'
)
REGISTER_ERR_MISSING_BASIC_FIELDS = 'username 与 password 为必填项'

# 自助改密缺失密文字段文案（INT-794，对齐 INT-186 注册缺密文逐字段点名口径）
CHANGE_PASSWORD_ERR_MISSING_CIPHERTEXT = (
    '原密码与新密码需加密提交：缺少加密后的密码密文字段（{fields}）；'
    '请先经 /auth/login/encryption-key 获取公钥，对密码 RSA 加密后提交'
)
CHANGE_PASSWORD_ERR_MISSING_FIELDS = '当前密码与新密码为必填项'

# 注册口径（INT-285 成员裁定，对齐 V9.7.10 基线回归口径）：
# ① 邮箱必填（注册后可按邮箱登录，旧库 New API 同语义）；
# ② 密码最短长度配置化（默认 6 位，与前端 LoginPage minlength 一致；
#    .env 可上调，如 AUTH_PASSWORD_MIN_LENGTH=8）。
REGISTER_ERR_MISSING_EMAIL = 'email 为必填项'
AUTH_PASSWORD_MIN_LENGTH = int(os.environ.get('AUTH_PASSWORD_MIN_LENGTH', '6'))
REGISTER_ERR_PASSWORD_TOO_SHORT = (
    f'密码长度不能少于 {AUTH_PASSWORD_MIN_LENGTH} 位')


class UserManagementService:
    """用户管理服务：注册 / 查询 / 建改删 / 角色分配 / 附加权限授予撤销"""

    # ---------- 注册（白名单） ----------

    @staticmethod
    def register() -> Tuple[Dict, int]:
        """自助注册（无权限校验）：username/password/email 必填，默认角色 guest。

        INT-51：注册开关 AUTH_REGISTRATION_ENABLED 配置化，
        关闭后端点 403；任意 AUTH_MODE 可用（prod 密码登录同步放开）。
        INT-147：密码 RSA 加密传输对齐旧库（password_encrypted +
        encryption_key_id；解密失败 400「注册参数无效」）。
        INT-186：缺密文字段 400 文案按实际缺失字段区分（指向密码密文
        缺失，不再误导 username/email/password）；密文缺失逐字段点名。
        INT-285：邮箱必填 + 密码最短长度（AUTH_PASSWORD_MIN_LENGTH，
        默认 6 位与前端一致）在网关统一校验。
        """
        from api_gateway.config.config import Config
        if not Config.AUTH_REGISTRATION_ENABLED:
            return error_response('注册未开放',
                                  code=ErrorCode.OPERATION_FAILED, http_code=403)
        body = _json_body()
        username = (body.get('username') or '').strip()
        password = body.get('password') or ''
        if Config.AUTH_PASSWORD_ENCRYPTION_ENABLED:
            from api_gateway.application.services.auth.password_encryption import (
                PasswordEncryptionError, PasswordEncryptionService,
            )
            password_encrypted = body.get('password_encrypted') or ''
            encryption_key_id = body.get('encryption_key_id') or ''
            missing_cipher = [name for name, value in (
                ('password_encrypted', password_encrypted),
                ('encryption_key_id', encryption_key_id),
            ) if not value]
            if missing_cipher:
                return error_response(
                    REGISTER_ERR_MISSING_CIPHERTEXT.format(
                        fields='、'.join(missing_cipher)),
                    code=ErrorCode.INVALID_PARAMS, http_code=400)
            try:
                password = PasswordEncryptionService.decrypt_password(
                    password_encrypted, encryption_key_id,
                    Config.AUTH_RSA_KEY_PATH,
                    Config.AUTH_RSA_FALLBACK_KEY_PATH)
            except PasswordEncryptionError:
                return error_response('注册参数无效',
                                      code=ErrorCode.INVALID_PARAMS,
                                      http_code=400)
        if not username or not password:
            return error_response(REGISTER_ERR_MISSING_BASIC_FIELDS,
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        email = (body.get('email') or '').strip()
        if not email:
            # INT-285 口径②：邮箱必填（对齐基线注册接口要求）
            return error_response(REGISTER_ERR_MISSING_EMAIL,
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        if len(password) < AUTH_PASSWORD_MIN_LENGTH:
            # INT-285 口径①：密码最短长度（默认 6 位，与前端 minlength 一致）
            return error_response(REGISTER_ERR_PASSWORD_TOO_SHORT,
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc('CreateUser', auth_pb.CreateUserRequest(
            username=username,
            email=email,
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
        # INT-297：分页信封统一为 {items, page, pages, per_page, total}
        total = data.get('total', 0)
        return success_response({
            'items': data.get('items', []),
            'total': total,
            'page': page,
            'per_page': page_size,
            'pages': data.get('pages', (total + page_size - 1) // page_size if page_size else 1),
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
            display_name=(body.get('display_name') or '').strip() or None,
            operator_id=current_operator_id(),
        ), default_error='创建用户失败')
        if fail:
            return fail
        return with_notice(success_response(
            {'user_id': data.get('user_id')}, '创建成功', http_code=201))

    @staticmethod
    def update_user(user_id: int) -> Tuple[Dict, int]:
        """更新用户资料（body 键缺省=不修改；status∈active/inactive/locked）。

        display_name（INT-697）：仅当 body 含 display_name 键时赋值——
        缺省键=不修改、空串=清空落 NULL、非空=设置。不得用
        body.get('display_name') or '' 惯用法（会把缺省键误判为空串而清空）。
        """
        body = _json_body()
        request_kwargs = dict(
            user_id=user_id,
            username=body.get('username') or '',
            email=body.get('email') or '',
            status=body.get('status') or '',
            password=body.get('password') or '',
            operator_id=current_operator_id(),
        )
        if 'display_name' in body:
            request_kwargs['display_name'] = body['display_name']
        data, fail = call_auth_rpc(
            'UpdateUser', auth_pb.UpdateUserRequest(**request_kwargs),
            default_error='更新用户失败')
        if fail:
            return fail
        return with_notice(success_response(None, '更新成功'))

    @staticmethod
    def change_password() -> Tuple[Dict, int]:
        """当前登录用户自助修改密码（INT-794 方案 A）。

        鉴权为「当前登录用户本人」（JWT user_id 注入，不走 admin user:update）。
        - body：current_password_encrypted + new_password_encrypted +
          encryption_key_id（复用登录 RSA 公钥体系；加密开关关闭时回退明文
          current_password / new_password，与注册/登录同口径）；
        - 两密文经 PasswordEncryptionService 解密，缺失/解密失败 → 400；
        - 新密码最短长度复用 AUTH_PASSWORD_MIN_LENGTH（默认 6）→ 400；
        - 调 auth_service ChangePassword RPC（服务端 bcrypt 校验原密码并哈希
          落库）；原密码错误 → 401 + code:106 AUTH_CREDENTIALS_INVALID
          （code_overrides 覆盖，与登录链防枚举语义一致）；
        - 成功 → 200 + PASSWORD_CHANGE_NOTICE（提示清 token 重新登录）。
        """
        from api_gateway.application.services.auth.management_common import (
            PASSWORD_CHANGE_NOTICE,
        )
        from api_gateway.config.config import Config
        body = _json_body()
        user_id = current_operator_id()
        if not user_id:
            return error_response('未登录或令牌已过期',
                                  code=ErrorCode.UNAUTHORIZED, http_code=401)
        current_password_encrypted = body.get('current_password_encrypted') or ''
        new_password_encrypted = body.get('new_password_encrypted') or ''
        encryption_key_id = body.get('encryption_key_id') or ''
        if Config.AUTH_PASSWORD_ENCRYPTION_ENABLED:
            from api_gateway.application.services.auth.password_encryption import (
                PasswordEncryptionError, PasswordEncryptionService,
            )
            missing_cipher = [name for name, value in (
                ('current_password_encrypted', current_password_encrypted),
                ('new_password_encrypted', new_password_encrypted),
                ('encryption_key_id', encryption_key_id),
            ) if not value]
            if missing_cipher:
                return error_response(
                    CHANGE_PASSWORD_ERR_MISSING_CIPHERTEXT.format(
                        fields='、'.join(missing_cipher)),
                    code=ErrorCode.INVALID_PARAMS, http_code=400)
            try:
                current_password = PasswordEncryptionService.decrypt_password(
                    current_password_encrypted, encryption_key_id,
                    Config.AUTH_RSA_KEY_PATH,
                    Config.AUTH_RSA_FALLBACK_KEY_PATH)
                new_password = PasswordEncryptionService.decrypt_password(
                    new_password_encrypted, encryption_key_id,
                    Config.AUTH_RSA_KEY_PATH,
                    Config.AUTH_RSA_FALLBACK_KEY_PATH)
            except PasswordEncryptionError:
                return error_response('加密载荷无效',
                                      code=ErrorCode.INVALID_PARAMS,
                                      http_code=400)
        else:
            current_password = body.get('current_password') or ''
            new_password = body.get('new_password') or ''
        if not current_password or not new_password:
            return error_response(CHANGE_PASSWORD_ERR_MISSING_FIELDS,
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        if len(new_password) < AUTH_PASSWORD_MIN_LENGTH:
            # INT-285 口径①：密码最短长度（默认 6，与注册/前端 minlength 同源）
            return error_response(REGISTER_ERR_PASSWORD_TOO_SHORT,
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc(
            'ChangePassword', auth_pb.ChangePasswordRequest(
                user_id=user_id,
                current_password=current_password,
                new_password=new_password,
            ), default_error='修改密码失败',
            code_overrides={
                AuthErrorCode.AUTH_CREDENTIALS_INVALID:
                    (ErrorCode.AUTH_CREDENTIALS_INVALID, 401),
            })
        if fail:
            return fail
        return with_notice(
            success_response(None, '密码修改成功，请重新登录'),
            notice=PASSWORD_CHANGE_NOTICE,
        )

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
