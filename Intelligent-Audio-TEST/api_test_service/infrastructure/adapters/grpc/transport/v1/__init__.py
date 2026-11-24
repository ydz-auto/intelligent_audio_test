# -*- coding: utf-8 -*-
"""gRPC 传输件 v1 — 动态 descriptor 客户端统一导入面。

grpc_client：unary / server-stream / bidi 调用、proto 编译加载与错误码映射。
"""
from api_test_service.infrastructure.adapters.grpc.transport.v1.grpc_client import (
    GrpcBidiSession,
    GrpcCallError,
    GrpcClient,
    GrpcMethod,
    GrpcProtoError,
    compile_proto,
    load_compiled_proto,
    message_to_payload,
)

__all__ = [
    'GrpcBidiSession',
    'GrpcCallError',
    'GrpcClient',
    'GrpcMethod',
    'GrpcProtoError',
    'compile_proto',
    'load_compiled_proto',
    'message_to_payload',
]
