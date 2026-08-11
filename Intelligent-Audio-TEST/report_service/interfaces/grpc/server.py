# -*- coding: utf-8 -*-
"""report_service gRPC server 启动模块。

端口：50068
注册 servicer：
- ReportConfigService（报告 CRUD / 生成 / 查询：CreateReport / UpdateReport /
  DeleteReport / BatchActionReports / ListReports / GetReportDetail /
  GetReportByTask / GenerateReport / UpdateReportStatus）
"""

from __future__ import annotations

import logging
from concurrent import futures

import grpc

from shared.proto import report_service_pb2_grpc as report_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from report_service.interfaces.grpc.servicers import ReportServicer

logger = logging.getLogger(__name__)


def start_grpc_server(port: int = 50068) -> grpc.Server:
    """启动 report_service 的 gRPC server。

    Args:
        port: gRPC 监听端口，默认 50068

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )

    report_grpc.add_ReportConfigServiceServicer_to_server(ReportServicer(), server)

    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("report_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
