# -*- coding: utf-8 -*-
"""e2e_test_service gRPC server 启动模块。

P2.5.7 拆分后仅注册 E2E 执行相关 servicer。
Audio / Device / SPL servicer 已迁出至各自服务的 server：
- audio_service/interfaces/grpc/server.py
- device_service/interfaces/grpc/server.py

端口：50051
"""

import logging
from concurrent import futures

import grpc

from shared.proto import e2e_test_service_pb2_grpc as e2e_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from shared.utils.config_manager import config_manager
from shared.config.service_ports import E2E_TEST_GRPC_PORT
from e2e_test_service.interfaces.grpc.servicers import ExecutionServiceServicer

logger = logging.getLogger(__name__)


def start_grpc_server(port=E2E_TEST_GRPC_PORT):
    """启动 e2e_test_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50051

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.e2e_test_service_workers
    _max_workers = config_manager.get_value('grpc', 'e2e_test_service_workers', 5)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    e2e_grpc.add_ExecutionServiceServicer_to_server(ExecutionServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("e2e_test_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
