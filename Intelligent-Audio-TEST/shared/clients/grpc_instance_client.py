# -*- coding: utf-8 -*-
"""实例级 gRPC 客户端 —— 按注册表地址直连特定服务实例（INT-61 会话亲和路由）。

shared/clients/_grpc_channels.py 的共享 channel 面向服务名（DNS / 负载均衡），
本模块面向「注册表中的特定实例」：

- task_service 派发侧按 session:bind 绑定路由 CreateAPITest（认领即绑定，架构设计 §5.2）
- api_test_service 亲和门禁把绑定在其它存活实例的启动/停止/状态请求转发到持有实例

channel 按 (host, port) 缓存复用，拦截器与共享工厂同构
（日志拦截在外、deadline 拦截在内，见 _grpc_channels._CLIENT_INTERCEPTORS 注释）。
"""
import grpc
from functools import lru_cache

from shared.infrastructure.grpc_interceptors import (
    client_deadline_interceptor,
    client_log_interceptor,
    client_worker_context_interceptor,
)

_INSTANCE_INTERCEPTORS = [client_log_interceptor, client_worker_context_interceptor, client_deadline_interceptor]


@lru_cache(maxsize=16)
def _get_channel(addr):
    chan = grpc.insecure_channel(addr)
    return grpc.intercept_channel(chan, *_INSTANCE_INTERCEPTORS)


@lru_cache(maxsize=16)
def get_api_test_service_stub_for_instance(host, grpc_port):
    """APITestService stub 直连特定 api_test_service 实例（绕过服务名负载均衡）"""
    from shared.proto import api_test_service_pb2_grpc
    return api_test_service_pb2_grpc.APITestServiceStub(
        _get_channel(f"{host}:{grpc_port}"))
