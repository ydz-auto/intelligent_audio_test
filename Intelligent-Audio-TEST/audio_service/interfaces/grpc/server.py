# -*- coding: utf-8 -*-
"""audio_service gRPC server 启动模块。

注册 audio_service 相关 servicer（定义于 interfaces/grpc/servicers.py）：
- AudioServiceServicer
- PlaybackServiceServicer
- AudioConfigServiceServicer

端口：50052
"""

import logging
from concurrent import futures

import grpc

from shared.proto import audio_service_pb2_grpc as audio_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from audio_service.interfaces.grpc.servicers import (
    AudioServiceServicer,
    PlaybackServiceServicer,
    AudioConfigServiceServicer,
)

logger = logging.getLogger(__name__)


def start_grpc_server(port=50052):
    """启动 audio_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50052

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # 初始化数据库连接池（audio_service 无 FastAPI lifespan，在此处初始化）
    from shared.models.database import init_db
    init_db(pool_size=5)

    # 启动软删除硬清理守护线程（只清理本服务 owned 表 audios 及子表）
    from audio_service.infrastructure.persistence.soft_delete_cleaner import get_cleaner as get_soft_delete_cleaner
    _cleaner = get_soft_delete_cleaner()
    _cleaner.start()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=5),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    audio_grpc.add_AudioServiceServicer_to_server(AudioServiceServicer(), server)
    audio_grpc.add_PlaybackServiceServicer_to_server(PlaybackServiceServicer(), server)
    audio_grpc.add_AudioConfigServiceServicer_to_server(AudioConfigServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("audio_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
