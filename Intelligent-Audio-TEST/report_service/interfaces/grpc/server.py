# -*- coding: utf-8 -*-
"""report_service gRPC server 启动模块。

端口：51068
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
from shared.infrastructure.config import BaseConfig
from shared.infrastructure.grpc_interceptors import (
    server_db_scope_interceptor, server_log_interceptor, server_user_context_interceptor,
)
from shared.utils.config_manager import config_manager
from shared.config.service_ports import REPORT_SERVICE_GRPC_PORT
from report_service.interfaces.grpc.servicers import (
    ReportServicer,
    BenchmarkServicer,
    StudioServicer,
)

logger = logging.getLogger(__name__)


def _server_options() -> list:
    """gRPC 收发消息上限（与共享客户端 channel、audio/task_service 服务端同口径）。

    grpcio 服务端默认收包上限 4MiB：Report Studio 的 markdown 正文整段经
    ``StudioDocumentRequest.data`` 转发（文件型独立报告导入，INT-1763 §6.2），
    网关按 ``REPORT_STUDIO_UPLOAD_MAX_MB``（50MB）放行后，服务端仍卡在 4MiB 就
    回 RESOURCE_EXHAUSTED，网关无对应映射 → HTTP 500（应 200 或 413）。既有的
    Studio 大 markdown 编辑同样会静默失败，故按 ``BaseConfig.GRPC_MAX_MESSAGE_MB``
    显式放大，与客户端 channel 保持一致。
    """
    max_bytes = max(int(BaseConfig.GRPC_MAX_MESSAGE_MB), 1) * 1024 * 1024
    return [
        ('grpc.max_receive_message_length', max_bytes),
        ('grpc.max_send_message_length', max_bytes),
    ]


def start_grpc_server(port: int = REPORT_SERVICE_GRPC_PORT) -> grpc.Server:
    """启动 report_service 的 gRPC server。

    Args:
        port: gRPC 监听端口，默认 51068

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # 初始化数据库连接池（report_service 无 FastAPI lifespan，在此处初始化）
    from shared.models.database import init_db
    init_db(pool_size=5)

    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.report_service_workers
    _max_workers = config_manager.get_value('grpc', 'report_service_workers', 10)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        options=_server_options(),
        interceptors=[server_db_scope_interceptor, server_log_interceptor,
                     server_user_context_interceptor],
    )

    report_grpc.add_ReportConfigServiceServicer_to_server(ReportServicer(), server)
    report_grpc.add_BenchmarkConfigServiceServicer_to_server(BenchmarkServicer(), server)
    report_grpc.add_ReportStudioServiceServicer_to_server(StudioServicer(), server)

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
