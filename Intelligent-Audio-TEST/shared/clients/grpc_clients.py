"""gRPC 客户端工厂

集中管理所有跨服务的 gRPC stub 客户端，采用懒加载模式。
- e2e_test_service gRPC server（端口 50051）：AudioService / DeviceService / PlaybackService / DeviceResultService / EnvDeviceService
- task_service gRPC server（端口 50061）：ExecutionService
"""
import grpc
from functools import lru_cache

from shared.infrastructure.config import BaseConfig

# 服务地址
E2E_GRPC_ADDR = f"{BaseConfig.E2E_TEST_SERVICE_HOST}:{BaseConfig.E2E_TEST_SERVICE_GRPC_PORT}"
TASK_GRPC_ADDR = f"{BaseConfig.TASK_SERVICE_HOST}:{BaseConfig.TASK_SERVICE_GRPC_PORT}"


@lru_cache(maxsize=1)
def get_audio_service_stub():
    """AudioService stub：播放/停止音频、获取播放状态、获取音频信息、SPL 测量"""
    from shared.proto import e2e_service_pb2_grpc
    channel = grpc.insecure_channel(E2E_GRPC_ADDR)
    return e2e_service_pb2_grpc.AudioServiceStub(channel)


@lru_cache(maxsize=1)
def get_device_service_stub():
    """DeviceService stub：创建/销毁设备驱动、注册/注销/获取任务事件"""
    from shared.proto import e2e_service_pb2_grpc
    channel = grpc.insecure_channel(E2E_GRPC_ADDR)
    return e2e_service_pb2_grpc.DeviceServiceStub(channel)


@lru_cache(maxsize=1)
def get_playback_service_stub():
    """PlaybackService stub：开始/停止播放编排"""
    from shared.proto import e2e_service_pb2_grpc
    channel = grpc.insecure_channel(E2E_GRPC_ADDR)
    return e2e_service_pb2_grpc.PlaybackServiceStub(channel)


@lru_cache(maxsize=1)
def get_device_result_service_stub():
    """DeviceResultService stub：采集/重新提取设备结果"""
    from shared.proto import e2e_service_pb2_grpc
    channel = grpc.insecure_channel(E2E_GRPC_ADDR)
    return e2e_service_pb2_grpc.DeviceResultServiceStub(channel)


@lru_cache(maxsize=1)
def get_env_device_service_stub():
    """EnvDeviceService stub：控制环境设备（导轨旋转等）"""
    from shared.proto import e2e_service_pb2_grpc
    channel = grpc.insecure_channel(E2E_GRPC_ADDR)
    return e2e_service_pb2_grpc.EnvDeviceServiceStub(channel)


@lru_cache(maxsize=1)
def get_execution_service_stub():
    """ExecutionService stub：创建/启动/停止任务、获取状态、重新评估、获取引擎信息"""
    from shared.proto import task_service_pb2_grpc
    channel = grpc.insecure_channel(TASK_GRPC_ADDR)
    return task_service_pb2_grpc.ExecutionServiceStub(channel)
