# -*- coding: utf-8 -*-
"""algorithm_service gRPC server 启动模块。

端口：50067
注册 servicer：
- AlgorithmGroupService（算法分组 CRUD：Create/Update/Delete/Get/List）
- AlgorithmDefinitionService（算法定义 CRUD + 参数/映射/维度关联查询）
- AlgorithmQueryService（算法领域查询：配置/字段映射/用例参数/参考参数，CQRS 读侧）

proto 已接入，servicer 继承自 algorithm_service_pb2_grpc 的 servicer 基类，
本模块调用 add_<ServicerName>Servicer_to_server 完成 servicer 注册。
"""
from __future__ import annotations

import logging
from concurrent import futures

import grpc

from shared.infrastructure.grpc_interceptors import (
    server_log_interceptor,
    server_db_scope_interceptor,
)
from shared.utils.config_manager import config_manager
from shared.config.service_ports import ALGORITHM_SERVICE_GRPC_PORT
from shared.proto import algorithm_service_pb2_grpc as _pb_grpc
from algorithm_service.interfaces.grpc.servicers import (
    AlgorithmGroupServicer,
    AlgorithmDefinitionServicer,
)
from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
    AlgorithmQueryServicer,
)

logger = logging.getLogger(__name__)


def start_grpc_server(port: int = ALGORITHM_SERVICE_GRPC_PORT):
    """启动 algorithm_service 的 gRPC server。

    1. 创建 grpc.server(ThreadPoolExecutor)
    2. 注册 AlgorithmGroupServicer / AlgorithmDefinitionServicer
    3. server.add_insecure_port(f'[::]:{port}')
    4. server.start()

    Args:
        port: gRPC 监听端口，默认 50067

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.algorithm_service_workers
    _max_workers = config_manager.get_value('grpc', 'algorithm_service_workers', 10)
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    _pb_grpc.add_AlgorithmGroupServiceServicer_to_server(
        AlgorithmGroupServicer(), server
    )
    _pb_grpc.add_AlgorithmDefinitionServiceServicer_to_server(
        AlgorithmDefinitionServicer(), server
    )
    _pb_grpc.add_AlgorithmQueryServiceServicer_to_server(
        AlgorithmQueryServicer(), server
    )
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("algorithm_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(grace=0)
