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
from shared.utils.config_manager import config_manager
from shared.config.service_ports import REPORT_SERVICE_GRPC_PORT
from report_service.interfaces.grpc.servicers import ReportServicer

logger = logging.getLogger(__name__)


def start_grpc_server(port: int = REPORT_SERVICE_GRPC_PORT) -> grpc.Server:
    """启动 report_service 的 gRPC server。

    Args:
        port: gRPC 监听端口，默认 50068

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.report_service_workers
    _max_workers = config_manager.get_value('grpc', 'report_service_workers', 10)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
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
