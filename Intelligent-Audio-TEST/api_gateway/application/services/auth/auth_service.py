"""
认证核心服务 — application 层

对齐 DDD 重构方案第八章「AuthService」。
统一入口：编排 OAuth Provider → gRPC 用户查找/创建 → TokenService。
"""
import logging
from typing import Optional

from api_gateway.config.config import Config
from api_gateway.domain.entities.auth_entities import AuthUser
from api_gateway.domain.value_objects.auth_value_objects import UserInfo
from api_gateway.application.services.auth.token_service import TokenService
from api_gateway.application.services.auth.local_oauth import LocalOAuthProvider
from api_gateway.application.services.auth.huawei_oauth import HuaweiOAuthProvider

logger = logging.getLogger(__name__)


class AuthService:
    """认证服务：编排 OAuth 登录 → 用户查找/创建 → JWT 签发"""

    # ---- 登录入口 ----

    @staticmethod
    def get_login_entry() -> str:
        """返回登录入口 URL（dev: 前端登录页; prod: 华为云授权 URL）"""
        if Config.AUTH_MODE == 'dev':
            return '/#/login'  # 前端 Vue 登录页路由
        return HuaweiOAuthProvider.get_login_url()

    @staticmethod
    def login_with_password(username: str, password: str) -> dict:
        """
        开发模式：用户名/密码登录

        Returns: {access_token, token_type, user}
        """
        if Config.AUTH_MODE != 'dev':
            raise PermissionError('仅开发模式支持本地密码登录')

        user_info = LocalOAuthProvider.verify_credentials(username, password)
        return AuthService._issue_token(user_info)

    @staticmethod
    def handle_callback(code: str, state: str = '') -> dict:
        """
        生产模式：OAuth 回调

        Returns: {access_token, token_type, user}
        """
        if Config.AUTH_MODE != 'prod':
            raise PermissionError('仅生产模式支持 OAuth 回调')

        user_info = HuaweiOAuthProvider.handle_callback(code, state)
        return AuthService._issue_token(user_info)

    # ---- Token 操作 ----

    @staticmethod
    def refresh_token(token: str) -> dict:
        """刷新 JWT"""
        new_token = TokenService.refresh(token)
        return {'access_token': new_token, 'token_type': 'Bearer'}

    @staticmethod
    def get_current_user_info(request_state) -> dict:
        """从 request.state 获取当前用户信息"""
        return {
            'user_id': getattr(request_state, 'user_id', None),
            'username': getattr(request_state, 'username', ''),
            'role_id': getattr(request_state, 'role_id', None),
            'permissions': getattr(request_state, 'permissions', []),
        }

    # ---- 内部方法 ----

    @staticmethod
    def _issue_token(user_info: UserInfo) -> dict:
        """查找/创建用户 → 签发 JWT → 返回响应"""
        user = AuthService._find_or_create_user(user_info)
        if not user.is_active:
            raise PermissionError('用户已被禁用')

        token = TokenService.create_token(
            user_id=user.id,
            username=user.username,
            role_id=user.role_id or 0,
            permissions=user.permissions,
        )

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
    def _find_or_create_user(user_info: UserInfo) -> AuthUser:
        """查找或创建用户（通过 gRPC 调用 auth_service）"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        from shared.proto import auth_service_pb2 as auth_pb
        from shared.utils.grpc_json import loads as _loads

        stub = auth_config_service.stub

        # 1. 按 OAuth 外部 ID 查找
        if user_info.external_id:
            resp = stub.GetUserByOAuth(auth_pb.GetUserByOAuthRequest(
                provider='huawei', subject=user_info.external_id,
            ))
            if resp.success and resp.data:
                data = _loads(resp.data, {}) or {}
                if data:
                    return _to_auth_user(data)

        # 2. 按用户名查找
        resp = stub.GetUserByUsername(auth_pb.GetUserByUsernameRequest(
            username=user_info.username,
        ))
        if resp.success and resp.data:
            data = _loads(resp.data, {}) or {}
            if data:
                return _to_auth_user(data)

        # 3. 自动创建新用户
        resp = stub.CreateUser(auth_pb.CreateUserRequest(
            username=user_info.username,
            email=user_info.email or '',
            oauth_provider='huawei' if user_info.external_id else '',
            oauth_subject=user_info.external_id or '',
        ))
        if resp.success and resp.data:
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
                username=user_info.username,
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
