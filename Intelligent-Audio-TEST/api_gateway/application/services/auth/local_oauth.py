"""
本地开发 OAuth Provider — application 层

对齐 DDD 重构方案第八章「开发模式 LocalOAuthProvider」。
dev 模式登录 UI 已统一由前端 LoginPage.vue 处理，
本模块只负责凭证校验与自动创建用户。

改造说明：原直连 UserRepository（DB）改为通过 gRPC 调用 auth_service。
"""
import logging

from api_gateway.domain.value_objects.auth_value_objects import UserInfo
from api_gateway.config.config import Config

logger = logging.getLogger(__name__)


class LocalOAuthProvider:
    """本地开发 OAuth — 用户名/密码登录"""

    @staticmethod
    def verify_credentials(username: str, password: str) -> UserInfo:
        """
        校验用户名/密码，返回 UserInfo。
        开发模式下：用户不存在则自动创建，密码与 .env 默认值匹配即放行。
        """
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        from shared.proto import auth_service_pb2 as auth_pb
        from shared.utils.grpc_json import loads as _loads

        stub = auth_config_service.stub

        # 开发模式：默认凭证直接放行
        if (username == Config.DEV_DEFAULT_USERNAME
                and password == Config.DEV_DEFAULT_PASSWORD):
            resp = stub.GetUserByUsername(auth_pb.GetUserByUsernameRequest(
                username=username,
            ))
            if resp.success and resp.data:
                data = _loads(resp.data, {}) or {}
                if data:
                    return UserInfo(username=data.get('username', username))

            # 用户不存在，创建
            resp = stub.CreateUser(auth_pb.CreateUserRequest(
                username=username,
            ))
            if resp.success:
                return UserInfo(username=username)

            logger.warning('自动创建用户失败: %s', resp.message)
            return UserInfo(username=username)

        # 非默认凭证：通过 gRPC 查用户，DB 中有用户就放行
        resp = stub.GetUserByUsername(auth_pb.GetUserByUsernameRequest(
            username=username,
        ))
        if resp.success and resp.data:
            data = _loads(resp.data, {}) or {}
            if data and data.get('is_active'):
                return UserInfo(username=data.get('username', username))

        raise ValueError('用户名或密码错误')
