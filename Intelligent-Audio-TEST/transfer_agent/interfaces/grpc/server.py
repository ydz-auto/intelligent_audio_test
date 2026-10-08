# -*- coding: utf-8 -*-
"""transfer_agent gRPC server 启动模块。

端口：50101（shared/config/service_ports.py 集中管理）
注册 servicer：
- TransferAgentServicer（传输会话/分片/状态/完成/审计查询）
"""
from __future__ import annotations

import logging
from concurrent import futures

import grpc

from shared.infrastructure.grpc_interceptors import (
    server_db_scope_interceptor, server_log_interceptor,
)
from shared.proto import transfer_agent_pb2_grpc as transfer_grpc
from shared.config.service_ports import TRANSFER_AGENT_GRPC_PORT
from shared.utils.config_manager import config_manager
from transfer_agent.config.config import Config
from transfer_agent.interfaces.grpc.servicer import TransferAgentServicer

logger = logging.getLogger(__name__)


def start_grpc_server(port=TRANSFER_AGENT_GRPC_PORT):
    """启动 transfer_agent 的 gRPC server。

    Args:
        port: gRPC 监听端口，默认 50101

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    _max_workers = config_manager.get_value('grpc', 'transfer_agent_workers', 10)
    # grpcio 默认收发上限 4MiB，恰等于默认满片大小（分片数据+元数据必超限），
    # 显式放大到 TRANSFER_GRPC_MAX_MESSAGE_MB（客户端 stub 侧需同步设置）
    _max_message_bytes = Config.TRANSFER_GRPC_MAX_MESSAGE_MB * 1024 * 1024
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_max_workers),
        options=[
            ('grpc.max_receive_message_length', _max_message_bytes),
            ('grpc.max_send_message_length', _max_message_bytes),
        ],
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    transfer_grpc.add_TransferAgentServiceServicer_to_server(TransferAgentServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info('transfer_agent gRPC server started on port %s', port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
