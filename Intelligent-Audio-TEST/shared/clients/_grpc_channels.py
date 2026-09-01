# -*- coding: utf-8 -*-
"""gRPC 客户端基础：服务地址、拦截器、channel 复用工厂（从 grpc_clients.py 拆分，P4-4）。

每个服务只创建一个共享 channel，所有 stub 复用同一 channel，
客户端拦截器自动附加到每个 channel。
"""
import grpc
from functools import lru_cache

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.grpc_interceptors import client_log_interceptor

# ==================== 服务地址 ====================

E2E_GRPC_ADDR = f"{BaseConfig.E2E_TEST_SERVICE_HOST}:{BaseConfig.E2E_TEST_SERVICE_GRPC_PORT}"
AUDIO_GRPC_ADDR = f"{BaseConfig.AUDIO_SERVICE_HOST}:{BaseConfig.AUDIO_SERVICE_GRPC_PORT}"
DEVICE_GRPC_ADDR = f"{BaseConfig.DEVICE_SERVICE_HOST}:{BaseConfig.DEVICE_SERVICE_GRPC_PORT}"
TASK_GRPC_ADDR = f"{BaseConfig.TASK_SERVICE_HOST}:{BaseConfig.TASK_SERVICE_GRPC_PORT}"
API_TEST_GRPC_ADDR = f"{BaseConfig.API_TEST_SERVICE_HOST}:{BaseConfig.API_TEST_SERVICE_GRPC_PORT}"
EVALUATION_GRPC_ADDR = f"{BaseConfig.EVALUATION_SERVICE_HOST}:{BaseConfig.EVALUATION_SERVICE_GRPC_PORT}"
ALGORITHM_GRPC_ADDR = f"{BaseConfig.ALGORITHM_SERVICE_HOST}:{BaseConfig.ALGORITHM_SERVICE_GRPC_PORT}"
REPORT_GRPC_ADDR = f"{BaseConfig.REPORT_SERVICE_HOST}:{BaseConfig.REPORT_SERVICE_GRPC_PORT}"
AUTH_GRPC_ADDR = f"{BaseConfig.AUTH_SERVICE_HOST}:{BaseConfig.AUTH_SERVICE_GRPC_PORT}"
ADAPTER_GRPC_ADDR = f"{BaseConfig.ADAPTER_SERVICE_HOST}:{BaseConfig.ADAPTER_SERVICE_GRPC_PORT}"

# 客户端拦截器列表
_CLIENT_INTERCEPTORS = [client_log_interceptor]


# ==================== channel 复用工厂 ====================

@lru_cache(maxsize=1)
def _get_e2e_channel():
    """e2e_test_service 共享 channel（P2.5 后仅 ExecutionService）"""
    chan = grpc.insecure_channel(E2E_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_audio_channel():
    """audio_service 共享 channel"""
    chan = grpc.insecure_channel(AUDIO_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_device_channel():
    """device_service 共享 channel"""
    chan = grpc.insecure_channel(DEVICE_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_task_channel():
    """task_service 共享 channel"""
    chan = grpc.insecure_channel(TASK_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_api_test_channel():
    """api_test_service 共享 channel"""
    chan = grpc.insecure_channel(API_TEST_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_evaluation_channel():
    """evaluation_service 共享 channel"""
    chan = grpc.insecure_channel(EVALUATION_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_adapter_channel():
    """adapter_service 共享 channel"""
    chan = grpc.insecure_channel(ADAPTER_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_algorithm_channel():
    """algorithm_service 共享 channel"""
    chan = grpc.insecure_channel(ALGORITHM_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_report_channel():
    """report_service 共享 channel"""
    chan = grpc.insecure_channel(REPORT_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_auth_channel():
    """auth_service 共享 channel"""
    chan = grpc.insecure_channel(AUTH_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)
