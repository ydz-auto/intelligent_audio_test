# -*- coding: utf-8 -*-
"""
task_service gRPC server 启动模块。

端口：50061
注册 servicer：
- ExecutionService
- TaskConfigService
- TestCaseConfigService
- TagConfigService
- AlgorithmConfigService
- TaskDataService（P1.5 新增，跨服务数据查询）

注：EvaluationConfigService 已迁移至 evaluation_service。
"""

import logging
from concurrent import futures

import grpc

from shared.proto import task_service_pb2_grpc as task_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from task_service.interfaces.grpc import (
    ExecutionServiceServicer,
    TaskConfigServiceServicer,
    TestCaseConfigServiceServicer,
    TagConfigServiceServicer,
    AlgorithmConfigServiceServicer,
    TaskDataServiceServicer,
)

logger = logging.getLogger(__name__)


def start_grpc_server(port=50061):
    """启动 task_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50061

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    task_grpc.add_ExecutionServiceServicer_to_server(ExecutionServiceServicer(), server)
    task_grpc.add_TaskConfigServiceServicer_to_server(TaskConfigServiceServicer(), server)
    task_grpc.add_TestCaseConfigServiceServicer_to_server(TestCaseConfigServiceServicer(), server)
    task_grpc.add_TagConfigServiceServicer_to_server(TagConfigServiceServicer(), server)
    task_grpc.add_AlgorithmConfigServiceServicer_to_server(AlgorithmConfigServiceServicer(), server)
    task_grpc.add_TaskDataServiceServicer_to_server(TaskDataServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("task_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
