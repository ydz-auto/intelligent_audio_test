# -*- coding: utf-8 -*-
"""
e2e_test_service gRPC server 启动模块。

端口：50051
注册 servicer：
- AudioService
- DeviceService
- PlaybackService
- DeviceResultService
- EnvDeviceService
"""

import logging
from concurrent import futures

import grpc

from shared.proto import e2e_service_pb2_grpc as e2e_grpc
from e2e_test_service.grpc.servicers import (
    AudioServiceServicer,
    DeviceServiceServicer,
    PlaybackServiceServicer,
    DeviceResultServiceServicer,
    EnvDeviceServiceServicer,
)

logger = logging.getLogger(__name__)


def start_grpc_server(port=50051):
    """启动 e2e_test_service 的 gRPC server

    Args:
        port: gRPC 监听端口，默认 50051

    Returns:
        grpc.Server: 已启动的 server 实例，调用方持有引用以防被 GC 回收
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))
    e2e_grpc.add_AudioServiceServicer_to_server(AudioServiceServicer(), server)
    e2e_grpc.add_DeviceServiceServicer_to_server(DeviceServiceServicer(), server)
    e2e_grpc.add_PlaybackServiceServicer_to_server(PlaybackServiceServicer(), server)
    e2e_grpc.add_DeviceResultServiceServicer_to_server(DeviceResultServiceServicer(), server)
    e2e_grpc.add_EnvDeviceServiceServicer_to_server(EnvDeviceServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info("e2e_test_service gRPC server started on port %s", port)
    return server


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _server = start_grpc_server()
    try:
        _server.wait_for_termination()
    except KeyboardInterrupt:
        _server.stop(0)
