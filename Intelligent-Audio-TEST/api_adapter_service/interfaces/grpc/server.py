# -*- coding: utf-8 -*-
"""
api_adapter_service gRPC server 启动模块。

端口：50081
注册 servicer：
- AdapterService
"""

import logging
from concurrent import futures

import grpc

from shared.proto import adapter_service_pb2_grpc as adapter_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor
from shared.utils.config_manager import config_manager
from shared.config.service_ports import API_ADAPTER_SERVICE_GRPC_PORT
from api_adapter_service.interfaces.grpc.servicers import AdapterServiceServicer

logger = logging.getLogger(__name__)


def start_grpc_server(port=API_ADAPTER_SERVICE_GRPC_PORT):
    """启动 api_adapter_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50081

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.api_adapter_service_workers
    _max_workers = config_manager.get_value('grpc', 'api_adapter_service_workers', 8)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        interceptors=[server_log_interceptor],
    )
    adapter_grpc.add_AdapterServiceServicer_to_server(AdapterServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("api_adapter_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
