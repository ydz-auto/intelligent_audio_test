"""
本地开发 OAuth Provider — application 层

对齐 DDD 重构方案第八章「开发模式 LocalOAuthProvider」。
dev 模式登录 UI 已统一由前端 LoginPage.vue 处理，
本模块只负责凭证校验与自动创建用户。

改造说明：原直连 UserRepository（DB）改为通过 gRPC 调用 auth_service。
INT-51 改造：非默认凭证走 LoginWithPassword（auth_service 内 bcrypt
校验 password_hash），自助注册用户可用 用户名+密码 登录。
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

        - 默认凭证：引导路径（INT-36 语义不变）——用户不存在则
          以 DEV_DEFAULT_ROLE 角色自动创建；
        - 其他凭证：经 gRPC LoginWithPassword 由 auth_service 校验
          password_hash（自助注册用户 / 管理员建号用户均可登录）。
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

            # 用户不存在，创建；默认凭证用户绑定 DEV_DEFAULT_ROLE 指定的角色
            # （INT-36：此前创建时不带角色，dev 模式首个用户无任何权限）
            resp = stub.CreateUser(auth_pb.CreateUserRequest(
                username=username,
                role_name=Config.DEV_DEFAULT_ROLE,
            ))
            if resp.success:
                return UserInfo(username=username)

            # 创建失败必须中断登录：若放行，下游 _find_or_create_user 会以
            # 无角色兜底建号，重新引入首个用户无权限的问题
            logger.warning('自动创建用户失败: %s', resp.message)
            raise ValueError(f'默认用户自动创建失败: {resp.message}')

        # 非默认凭证：auth_service 内 bcrypt 校验（INT-51）
        resp = stub.LoginWithPassword(auth_pb.LoginWithPasswordRequest(
            username=username,
            password=password,
        ))
        if resp.success and resp.data:
            data = _loads(resp.data, {}) or {}
            if data and data.get('is_active', True):
                return UserInfo(username=data.get('username', username))

        raise ValueError('用户名或密码错误')
