# -*- coding: utf-8 -*-
"""
task_service gRPC server 启动模块。

端口：51061
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
from shared.infrastructure.config import BaseConfig
from shared.infrastructure.grpc_interceptors import (
    server_db_scope_interceptor, server_log_interceptor, server_user_context_interceptor,
)
from shared.utils.config_manager import config_manager
from shared.config.service_ports import TASK_SERVICE_GRPC_PORT
from task_service.interfaces.grpc import (
    ExecutionServiceServicer,
    TaskConfigServiceServicer,
    PublishedTaskConfigServiceServicer,
    TestCaseConfigServiceServicer,
    TagConfigServiceServicer,
    AlgorithmConfigServiceServicer,
    TaskDataServiceServicer,
    DataTransferServiceServicer,
    CherryPickServiceServicer,
    ReviewServiceServicer,
    EvaluationStrategyServiceServicer,
)

logger = logging.getLogger(__name__)


def start_grpc_server(port=TASK_SERVICE_GRPC_PORT):
    """启动 task_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 51061

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # gRPC 线程池大小配置化：优先读取 concurrency_config.json 中的 grpc.task_service_workers
    _max_workers = config_manager.get_value('grpc', 'task_service_workers', 10)
    # grpcio 默认收发上限 4MiB，恰为聚合查询响应上限（INT-1224：用例标签视图
    # view=tag perPage=50 真实库实测 4.07MiB → RESOURCE_EXHAUSTED），显式放大；
    # 客户端 channel 侧需同步设置（shared/clients/_grpc_channels.py）。
    _max_message_bytes = BaseConfig.GRPC_MAX_MESSAGE_MB * 1024 * 1024
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        options=[
            ('grpc.max_receive_message_length', _max_message_bytes),
            ('grpc.max_send_message_length', _max_message_bytes),
        ],
        interceptors=[server_db_scope_interceptor, server_log_interceptor,
                      server_user_context_interceptor],
    )
    task_grpc.add_ExecutionServiceServicer_to_server(ExecutionServiceServicer(), server)
    task_grpc.add_TaskConfigServiceServicer_to_server(TaskConfigServiceServicer(), server)
    task_grpc.add_PublishedTaskConfigServiceServicer_to_server(PublishedTaskConfigServiceServicer(), server)
    task_grpc.add_TestCaseConfigServiceServicer_to_server(TestCaseConfigServiceServicer(), server)
    task_grpc.add_TagConfigServiceServicer_to_server(TagConfigServiceServicer(), server)
    task_grpc.add_AlgorithmConfigServiceServicer_to_server(AlgorithmConfigServiceServicer(), server)
    task_grpc.add_TaskDataServiceServicer_to_server(TaskDataServiceServicer(), server)
    task_grpc.add_DataTransferServiceServicer_to_server(DataTransferServiceServicer(), server)
    task_grpc.add_CherryPickServiceServicer_to_server(CherryPickServiceServicer(), server)
    task_grpc.add_ReviewServiceServicer_to_server(ReviewServiceServicer(), server)
    task_grpc.add_EvaluationStrategyServiceServicer_to_server(EvaluationStrategyServiceServicer(), server)
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
