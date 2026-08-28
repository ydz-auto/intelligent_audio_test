# -*- coding: utf-8 -*-
"""
api_test_service gRPC server 启动模块。

端口：50071
注册 servicer：
- APITestService
"""

import logging
from concurrent import futures

import grpc

from shared.proto import api_test_service_pb2_grpc as api_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from shared.utils.config_manager import config_manager
from shared.config.service_ports import API_TEST_SERVICE_GRPC_PORT
from api_test_service.interfaces.grpc.servicers import APITestServiceServicer

logger = logging.getLogger(__name__)


def start_grpc_server(port=API_TEST_SERVICE_GRPC_PORT):
    """启动 api_test_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50071

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.api_test_service_workers
    _max_workers = config_manager.get_value('grpc', 'api_test_service_workers', 8)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    api_grpc.add_APITestServiceServicer_to_server(APITestServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("api_test_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
