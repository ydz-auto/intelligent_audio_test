"""Report Studio 服务代理：_ReportStudioProxy 及单例 report_studio_service。

封装 report_service.ReportStudioService 的 stub 调用，
作为 api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
"""
from shared.clients.grpc_clients import get_report_studio_service_stub


class _ReportStudioProxy:
    """ReportStudioService 代理：暴露 stub 供 application 层使用"""

    @property
    def stub(self):
        """获取 ReportStudioService stub"""
        return get_report_studio_service_stub()


# Report Studio 代理模块级单例
report_studio_service = _ReportStudioProxy()
