"""报告服务代理：_ReportConfigProxy 及单例 report_config_service。

封装 report_service.ReportConfigService 的 stub 调用，
作为 api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
"""
from shared.clients.grpc_clients import get_report_config_service_stub


class _ReportConfigProxy:
    """ReportConfigService 代理：暴露 stub 供 application 层使用"""

    @property
    def stub(self):
        """获取 ReportConfigService stub"""
        return get_report_config_service_stub()


# 报告配置代理模块级单例
report_config_service = _ReportConfigProxy()
