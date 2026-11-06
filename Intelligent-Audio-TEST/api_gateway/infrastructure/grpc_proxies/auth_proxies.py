"""认证服务代理：_AuthConfigProxy 及单例 auth_config_service。

封装 auth_service.AuthService 的 stub 调用，
作为 api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
"""
from shared.clients.grpc_clients import get_auth_service_stub


class _AuthConfigProxy:
    """AuthService 代理：暴露 stub 供 application 层使用"""

    @property
    def stub(self):
        """获取 AuthService stub"""
        return get_auth_service_stub()


# 认证服务代理模块级单例
auth_config_service = _AuthConfigProxy()
