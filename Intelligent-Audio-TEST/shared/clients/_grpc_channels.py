# -*- coding: utf-8 -*-
"""gRPC 客户端基础：服务地址、拦截器、channel 复用工厂（从 grpc_clients.py 拆分，P4-4）。

每个服务只创建一个共享 channel，所有 stub 复用同一 channel，
客户端拦截器自动附加到每个 channel。
"""
import grpc
from functools import lru_cache

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.grpc_interceptors import (
    client_deadline_interceptor,
    client_log_interceptor,
    client_user_context_interceptor,
    client_worker_context_interceptor,
)

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

# 客户端拦截器列表：grpc.intercept_channel 按 reversed 顺序包裹（grpc/_interceptor.py），
# 列表首位最外层（日志最先拦截、记录原始调用与总耗时），末位最内层（deadline
# 拦截器紧邻真实 channel 注入默认超时）。
_CLIENT_INTERCEPTORS = [client_log_interceptor, client_worker_context_interceptor,
                        client_user_context_interceptor, client_deadline_interceptor]


# ==================== channel 公共选项 ====================

def _channel_options() -> list:
    """共享 channel 选项：放大 gRPC 收发消息上限（INT-1292）。

    grpcio 客户端默认收包上限 4MiB，大响应 RPC（任务导出 23MB 包、报告/评估
    只读导出）在客户端收不下 → RESOURCE_EXHAUSTED（CLIENT: Received message
    larger than max）。服务端 send 上限默认不受 4MB 限制（实测可发送 >30MB），
    故只需客户端侧放开。值来自共享配置 GRPC_MAX_MESSAGE_MB（默认 64MB：
    INT-1292 实测任务 419 导出跨服务响应 ExportDimensionsForTasks 23.4MB /
    ExportReportsForTasks 20.4MB，16MB——对齐 transfer_agent 分片口径
    TRANSFER_GRPC_MAX_MESSAGE_MB——仍收不下；64MB 覆盖最大实测单响应并留余量）。
    """
    max_bytes = max(int(BaseConfig.GRPC_MAX_MESSAGE_MB), 1) * 1024 * 1024
    return [
        ('grpc.max_receive_message_length', max_bytes),
        ('grpc.max_send_message_length', max_bytes),
    ]


# ==================== channel 复用工厂 ====================

@lru_cache(maxsize=1)
def _get_e2e_channel():
    """e2e_test_service 共享 channel（P2.5 后仅 ExecutionService）"""
    chan = grpc.insecure_channel(E2E_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_audio_channel():
    """audio_service 共享 channel"""
    chan = grpc.insecure_channel(AUDIO_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_device_channel():
    """device_service 共享 channel"""
    chan = grpc.insecure_channel(DEVICE_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_task_channel():
    """task_service 共享 channel"""
    chan = grpc.insecure_channel(TASK_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_api_test_channel():
    """api_test_service 共享 channel"""
    chan = grpc.insecure_channel(API_TEST_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_evaluation_channel():
    """evaluation_service 共享 channel"""
    chan = grpc.insecure_channel(EVALUATION_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_algorithm_channel():
    """algorithm_service 共享 channel"""
    chan = grpc.insecure_channel(ALGORITHM_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_report_channel():
    """report_service 共享 channel"""
    chan = grpc.insecure_channel(REPORT_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def _get_auth_channel():
    """auth_service 共享 channel"""
    chan = grpc.insecure_channel(AUTH_GRPC_ADDR, options=_channel_options())
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)
