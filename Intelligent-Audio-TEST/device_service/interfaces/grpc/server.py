# -*- coding: utf-8 -*-
"""device_service gRPC server 启动模块。

注册 device_service 相关 servicer（定义于 interfaces/grpc/servicers.py）：
- DeviceServiceServicer
- DeviceResultServiceServicer
- EnvDeviceServiceServicer
- DeviceConfigServiceServicer
- PlaybackConfigServiceServicer
- SPLConfigServiceServicer

端口：50053
"""

import logging
from concurrent import futures

import grpc

from shared.proto import device_service_pb2_grpc as device_grpc
from shared.infrastructure.grpc_interceptors import server_log_interceptor, server_db_scope_interceptor
from device_service.interfaces.grpc.servicers import (
    DeviceServiceServicer,
    DeviceResultServiceServicer,
    EnvDeviceServiceServicer,
    DeviceConfigServiceServicer,
    PlaybackConfigServiceServicer,
    SPLConfigServiceServicer,
)

# 注入 LoggingPort 实现（domain 层通过 ABC 代理访问日志）
from shared.infrastructure.logging_adapter import inject as _inject_logging_port
_inject_logging_port()

logger = logging.getLogger(__name__)


def start_grpc_server(port=50053):
    """启动 device_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50053

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    # 初始化数据库连接池（device_service 无 FastAPI lifespan，在此处初始化）
    from shared.models.database import init_db
    init_db(pool_size=5)

    # 启动软删除硬清理守护线程（只清理本服务 owned 表 devices/spl_mappings 及子表）
    from device_service.infrastructure.persistence.soft_delete_cleaner import get_cleaner as get_soft_delete_cleaner
    _cleaner = get_soft_delete_cleaner()
    _cleaner.start()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=5),
        interceptors=[server_db_scope_interceptor, server_log_interceptor],
    )
    device_grpc.add_DeviceServiceServicer_to_server(DeviceServiceServicer(), server)
    device_grpc.add_DeviceResultServiceServicer_to_server(DeviceResultServiceServicer(), server)
    device_grpc.add_EnvDeviceServiceServicer_to_server(EnvDeviceServiceServicer(), server)
    device_grpc.add_DeviceConfigServiceServicer_to_server(DeviceConfigServiceServicer(), server)
    device_grpc.add_PlaybackConfigServiceServicer_to_server(PlaybackConfigServiceServicer(), server)
    device_grpc.add_SPLConfigServiceServicer_to_server(SPLConfigServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("device_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
