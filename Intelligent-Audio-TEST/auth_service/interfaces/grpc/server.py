# -*- coding: utf-8 -*-
"""auth_service gRPC server 启动模块。

端口：50069
注册 servicer：
- AuthServicer（用户管理 + 认证校验）
"""
from __future__ import annotations

import logging
from concurrent import futures

import grpc
from shared.infrastructure.grpc_interceptors import (
    server_log_interceptor, server_db_scope_interceptor,
)
from shared.proto import auth_service_pb2_grpc as auth_grpc
from auth_service.interfaces.grpc.servicers import AuthServicer

logger = logging.getLogger(__name__)


def start_grpc_server(port=50069):
    """启动 auth_service 的 gRPC server。

    Args:
        port: gRPC 监听端口，默认 50069

    Returns:
        grpc.Server: 已启动的 server 实例
    """
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    auth_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("auth_service gRPC server started on port %s", port)
    return server
