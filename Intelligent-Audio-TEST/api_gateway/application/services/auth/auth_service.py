"""
认证核心服务 — application 层

对齐 DDD 重构方案第八章「AuthService」。
统一入口：编排 OAuth Provider → gRPC 用户查找/创建 → TokenService。
"""
import logging
import re
from typing import Optional

from api_gateway.config.config import Config
from api_gateway.domain.entities.auth_entities import AuthUser
from api_gateway.domain.value_objects.auth_value_objects import UserInfo
from api_gateway.application.services.auth.token_service import TokenService
from api_gateway.application.services.auth.local_oauth import LocalOAuthProvider

logger = logging.getLogger(__name__)

# 自我资料邮箱格式（INT-792）：网关侧前置校验，auth_service 服务端二次校验
_EMAIL_PATTERN = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


def _is_valid_email(email: str) -> bool:
    """邮箱格式粗校验（网关侧；长度/精确规则由 auth_service 服务端兜底）。"""
    return bool(_EMAIL_PATTERN.match(email))


class AuthService:
    """认证服务：编排 OAuth 登录 → 用户查找/创建 → JWT 签发"""

    # ---- 登录入口 ----

    @staticmethod
    def get_auth_mode() -> str:
        """当前生效认证模式（INT-180 启动自检：公开端点 /auth/mode 数据源）。

        取 AuthMiddleware 实际执行的网关自身 AUTH_MODE——认证强制点在
        网关，值必须与强制点同源，不得转手他服务环境再转述。
        """
        from shared.constants.auth_mode import normalize_auth_mode
        return normalize_auth_mode(Config.AUTH_MODE)

    @staticmethod
    def get_login_entry() -> str:
        """返回登录入口 URL（dev: 前端登录页; prod: 预置提供方授权 URL）"""
        if Config.AUTH_MODE == 'dev':
            return '/#/login'  # 前端 Vue 登录页路由
        # 生产模式：华为云预置提供方（DB 优先，无记录回退环境配置）
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderService,
        )
        config = OAuthProviderService.get_provider_config('huawei')
        if config is not None:
            return OAuthProviderService.build_authorize_url(
                config, Config.HW_OAUTH_REDIRECT_URI)
        # 禁用/未配置不回退旧硬编码授权页 —— 禁用开关必须生效（INT-51
        # 审计 P1-2，事件响应切断 SSO 的手段）；账号密码登录仍可用
        return '/#/login'

    @staticmethod
    def login_with_password(username: str, password: str) -> dict:
        """
        用户名/密码登录（自助注册用户与默认引导用户，INT-51 起全模式可用）

        Returns: {access_token, token_type, user}
        """
        user_info = LocalOAuthProvider.verify_credentials(username, password)
        return AuthService._issue_token(user_info, provider='')

    @staticmethod
    def handle_callback(code: str, state: str = '') -> dict:
        """
        OAuth 回调（华为云预置提供方，兼容旧 /api/v1/auth/callback 入口）

        Returns: {access_token, token_type, user}
        """
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderService, OAuthProviderError,
        )
        redirect_uri = Config.HW_OAUTH_REDIRECT_URI
        try:
            user_info = OAuthProviderService.handle_callback(
                'huawei', code, state, redirect_uri)
        except OAuthProviderError as e:
            raise PermissionError(str(e)) from e
        return AuthService._issue_token(user_info, provider='huawei')

    # ---- Token 操作 ----

    @staticmethod
    def refresh_token(token: str) -> dict:
        """刷新 JWT"""
        new_token = TokenService.refresh(token)
        return {'access_token': new_token, 'token_type': 'Bearer'}

    @staticmethod
    def get_current_user_info(request_state) -> dict:
        """从 request.state 获取当前用户信息（INT-792：/auth/me 扩展 email）。

        方案 B + 失败回退：经 auth_service GetUser 实时合并 email——
        与自我资料更新实时一致，前端无需重登；auth_service 抖动或用户
        已删除时回退 request.state 口径（email 缺省空串），/auth/me
        保持可用不连带 5xx（现纯内存读无此依赖）。
        """
        result = {
            'user_id': getattr(request_state, 'user_id', None),
            'username': getattr(request_state, 'username', ''),
            'role_id': getattr(request_state, 'role_id', None),
            'permissions': getattr(request_state, 'permissions', []),
            'email': '',
        }
        user_id = result['user_id']
        if not user_id:
            return result
        try:
            from api_gateway.infrastructure.grpc_proxies import auth_config_service
            from shared.proto import auth_service_pb2 as auth_pb
            from shared.utils.grpc_json import loads as _loads
            resp = auth_config_service.stub.GetUser(
                auth_pb.GetUserRequest(user_id=int(user_id)))
            if resp.success and resp.data:
                data = _loads(resp.data, {}) or {}
                email = data.get('email')
                if email:
                    result['email'] = email
        except Exception:
            logger.warning('GetUser 获取 email 失败，回退 request.state',
                           exc_info=True)
        return result

    @staticmethod
    def update_self_profile(request_state) -> dict:
        """当前登录用户更新自我资料（INT-792：PUT /auth/self，仅 email）。

        - 鉴权：request.state.user_id 为本人（operator_id 同值），
          不要求 user:update（那是 admin 管他人）；
        - 可编辑字段仅 email；body 携带 username 等其他字段 → 400 拒绝；
        - email 空串=不修改（对齐 admin UpdateUser 空串语义）；
        - 邮箱格式网关侧校验（auth_service 服务端二次校验）。
        """
        from api_gateway.infrastructure.request_adapter import request
        from api_gateway.application.services.auth.management_common import (
            call_auth_rpc,
        )
        from shared.proto import auth_service_pb2 as auth_pb
        from api_gateway.utils.error_codes import ErrorCode
        from api_gateway.utils.response import error_response, success_response

        user_id = int(getattr(request_state, 'user_id', 0) or 0)
        if not user_id:
            return error_response('未认证，无法更新个人资料',
                                  code=ErrorCode.UNAUTHORIZED, http_code=401)
        body = request.get_json()
        if not isinstance(body, dict):
            return error_response('请求体格式错误',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        unknown = set(body.keys()) - {'email'}
        if unknown:
            return error_response(
                f'不可修改字段: {", ".join(sorted(unknown))}（仅支持 email）',
                code=ErrorCode.INVALID_PARAMS, http_code=400)
        email = (body.get('email') or '').strip()
        if email and not _is_valid_email(email):
            return error_response('邮箱格式不正确',
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        data, fail = call_auth_rpc(
            'UpdateSelfProfile', auth_pb.UpdateSelfProfileRequest(
                user_id=user_id, email=email, operator_id=user_id),
            default_error='更新个人资料失败')
        if fail:
            return fail
        return success_response(None, '更新成功')

    # ---- 内部方法 ----

    @staticmethod
    def _issue_token(user_info: UserInfo, provider: str = '') -> dict:
        """查找/创建用户 → 签发 JWT → 返回响应"""
        user = AuthService._find_or_create_user(user_info, provider=provider)
        if not user.is_active:
            raise PermissionError('用户已被禁用')

        token = TokenService.create_token(
            user_id=user.id,
            username=user.username,
            role_id=user.role_id or 0,
            permissions=user.permissions,
        )

        # INT-406：登录成功落 AUTH_LOGIN 审计（旁路，失败不阻断；含操作人，
        # 时间由审计通道自动打点）。password 登录 provider=''，归一为 'password'
        # 便于审计查询区分登录通道。
        from api_gateway.application.services.auth.auth_audit import write_auth_audit
        from shared.models.common_enums import AuditEvent
        write_auth_audit(AuditEvent.AUTH_LOGIN, 'auth_login', {
            'operator_id': user.id,
            'operator': user.username,
            'target_id': user.id,
            'provider': provider or 'password',
        })

        return {
            'access_token': token,
            'token_type': 'Bearer',
            'user': {
                'id': user.id,
                'username': user.username,
                'role_id': user.role_id,
                'role_name': user.role_name,
                'permissions': user.permissions,
            },
        }

    @staticmethod
    def _find_or_create_user(user_info: UserInfo,
                             provider: str = 'huawei') -> AuthUser:
        """查找或创建用户（通过 gRPC 调用 auth_service）

        provider 为 OAuth 提供方 slug（'huawei' 预置 / 自定义 slug），
        空串表示本地密码登录（无 OAuth 外部标识）。
        """
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        from shared.proto import auth_service_pb2 as auth_pb
        from shared.utils.grpc_json import loads as _loads

        stub = auth_config_service.stub
        from api_gateway.application.services.auth.oauth_provider_service import (
            PRESET_HUAWEI_SLUG,
        )

        # 1. 按 OAuth 外部 ID 查找
        if user_info.external_id:
            resp = stub.GetUserByOAuth(auth_pb.GetUserByOAuthRequest(
                provider=provider, subject=user_info.external_id,
            ))
            if resp.success and resp.data:
                data = _loads(resp.data, {}) or {}
                if data:
                    return _to_auth_user(data)

        # 2. 按用户名查找 —— 仅限本地密码登录（凭据已在入口验过）与预置
        #    huawei（企业受控 IdP，用户名即员工身份，存量账户绑定语义）。
        #    自定义提供方一律不合并：IdP 用户名可自选，按用户名签发既有
        #    账户 JWT 即同名账户接管（INT-51 审计 P1-1；对齐 newAPI：
        #    新身份一律新账户，仅按 provider+subject 绑定）。
        is_oauth = bool(user_info.external_id)
        if not is_oauth or provider == PRESET_HUAWEI_SLUG:
            resp = stub.GetUserByUsername(auth_pb.GetUserByUsernameRequest(
                username=user_info.username,
            ))
            if resp.success and resp.data:
                data = _loads(resp.data, {}) or {}
                if data:
                    return _to_auth_user(data)

        # 3. 自动创建新用户；自定义提供方 OAuth 新身份 username 被既有
        #    账户占用时降级 {slug}_{username} 重试（不合并既有账户）
        create_candidates = [user_info.username]
        if is_oauth and provider != PRESET_HUAWEI_SLUG:
            create_candidates.append(f'{provider}_{user_info.username}')
        resp = None
        for created_username in create_candidates:
            resp = stub.CreateUser(auth_pb.CreateUserRequest(
                username=created_username,
                email=user_info.email or '',
                oauth_provider=provider if user_info.external_id else '',
                oauth_subject=user_info.external_id or '',
            ))
            if resp.success and resp.data:
                break
        if resp is not None and resp.success and resp.data:
            data = _loads(resp.data, {}) or {}
            # 新建用户需要再查一次拿权限
            new_id = data.get('user_id')
            if new_id:
                resp2 = stub.GetUser(auth_pb.GetUserRequest(user_id=int(new_id)))
                if resp2.success and resp2.data:
                    data2 = _loads(resp2.data, {}) or {}
                    if data2:
                        return _to_auth_user(data2)
            # 降级：返回最小信息
            return AuthUser(
                id=data.get('user_id', 0),
                username=created_username,
                role_id=None,
                role_name='',
                permissions=[],
                is_active=True,
            )

        raise RuntimeError('用户查找/创建失败')


def _to_auth_user(data: dict) -> AuthUser:
    """gRPC 返回的 dict → AuthUser 领域实体"""
    return AuthUser(
        id=data.get('id', 0),
        username=data.get('username', ''),
        role_id=data.get('role_id'),
        role_name=data.get('role_name', ''),
        permissions=data.get('permissions', []),
        is_active=data.get('is_active', True),
    )
