# -*- coding: utf-8 -*-
"""evaluation_service gRPC server 启动模块。

端口：50091
注册 servicer：
- EvaluationService（评估执行：EvaluateCase / Reevaluate / ReevaluateMultiRound / ReevaluateSingle）
- EvaluationConfigService（维度 CRUD）
- EvaluationDataService（TestResultDimension 查询/删除，供 task_service 跨服务调用）
"""

import logging
from concurrent import futures

import grpc

from shared.proto import evaluation_service_pb2_grpc as eval_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from evaluation_service.interfaces.grpc.servicers import (
    EvaluationServiceServicer,
    EvaluationConfigServiceServicer,
    EvaluationDataServiceServicer,
)

logger = logging.getLogger(__name__)


def start_grpc_server(port=50091):
    """启动 evaluation_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50091

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    eval_grpc.add_EvaluationServiceServicer_to_server(EvaluationServiceServicer(), server)
    eval_grpc.add_EvaluationConfigServiceServicer_to_server(EvaluationConfigServiceServicer(), server)
    eval_grpc.add_EvaluationDataServiceServicer_to_server(EvaluationDataServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("evaluation_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
