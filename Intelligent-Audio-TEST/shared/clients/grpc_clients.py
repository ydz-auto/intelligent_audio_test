# -*- coding: utf-8 -*-
"""gRPC 客户端工厂

集中管理所有跨服务的 gRPC stub 客户端，采用懒加载 + channel 复用模式。

每个服务（e2e_test_service / task_service / api_test_service）只创建一个 channel，
所有 stub 共享同一 channel。客户端拦截器自动附加到每个 channel。

- e2e_test_service gRPC server（端口 50051）：AudioService / DeviceService / PlaybackService / DeviceResultService / EnvDeviceService / ExecutionService
- task_service gRPC server（端口 50061）：ExecutionService
- api_test_service gRPC server（端口 50071）：APITestService
"""
import grpc
from functools import lru_cache

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.grpc_interceptors import client_log_interceptor

# 服务地址
E2E_GRPC_ADDR = f"{BaseConfig.E2E_TEST_SERVICE_HOST}:{BaseConfig.E2E_TEST_SERVICE_GRPC_PORT}"
TASK_GRPC_ADDR = f"{BaseConfig.TASK_SERVICE_HOST}:{BaseConfig.TASK_SERVICE_GRPC_PORT}"
API_TEST_GRPC_ADDR = f"{BaseConfig.API_TEST_SERVICE_HOST}:{BaseConfig.API_TEST_SERVICE_GRPC_PORT}"

# 客户端拦截器列表
_CLIENT_INTERCEPTORS = [client_log_interceptor]


# ==================== channel 复用 ====================

@lru_cache(maxsize=1)
def _get_e2e_channel():
    """e2e_test_service 共享 channel"""
    chan = grpc.insecure_channel(E2E_GRPC_ADDR)
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


# ==================== e2e_test_service stubs ====================

@lru_cache(maxsize=1)
def get_audio_service_stub():
    """AudioService stub：播放/停止音频、获取播放状态、获取音频信息、SPL 测量、物理设备"""
    from shared.proto import e2e_service_pb2_grpc
    return e2e_service_pb2_grpc.AudioServiceStub(_get_e2e_channel())


@lru_cache(maxsize=1)
def get_device_service_stub():
    """DeviceService stub：创建/销毁设备驱动、注册/注销/获取任务事件、驱动扫描/解锁/模式控制"""
    from shared.proto import e2e_service_pb2_grpc
    return e2e_service_pb2_grpc.DeviceServiceStub(_get_e2e_channel())


@lru_cache(maxsize=1)
def get_playback_service_stub():
    """PlaybackService stub：开始/停止播放编排"""
    from shared.proto import e2e_service_pb2_grpc
    return e2e_service_pb2_grpc.PlaybackServiceStub(_get_e2e_channel())


@lru_cache(maxsize=1)
def get_device_result_service_stub():
    """DeviceResultService stub：采集/重新提取设备结果"""
    from shared.proto import e2e_service_pb2_grpc
    return e2e_service_pb2_grpc.DeviceResultServiceStub(_get_e2e_channel())


@lru_cache(maxsize=1)
def get_env_device_service_stub():
    """EnvDeviceService stub：控制环境设备（导轨旋转等）"""
    from shared.proto import e2e_service_pb2_grpc
    return e2e_service_pb2_grpc.EnvDeviceServiceStub(_get_e2e_channel())


@lru_cache(maxsize=1)
def get_e2e_execution_service_stub():
    """ExecutionService stub（e2e_test_service）：启动/停止 E2E 任务、获取状态"""
    from shared.proto import e2e_service_pb2_grpc
    return e2e_service_pb2_grpc.ExecutionServiceStub(_get_e2e_channel())


# ==================== task_service stubs ====================

@lru_cache(maxsize=1)
def get_execution_service_stub():
    """ExecutionService stub：创建/启动/停止/暂停/恢复任务、重新评估、获取引擎信息"""
    from shared.proto import task_service_pb2_grpc
    return task_service_pb2_grpc.ExecutionServiceStub(_get_task_channel())


# ==================== api_test_service stubs ====================

@lru_cache(maxsize=1)
def get_api_test_service_stub():
    """APITestService stub：创建/启动/停止 API 测试、获取 API 测试状态"""
    from shared.proto import api_test_service_pb2_grpc
    return api_test_service_pb2_grpc.APITestServiceStub(_get_api_test_channel())


# ==================== adapter_service stubs ====================

ADAPTER_GRPC_ADDR = f"{BaseConfig.ADAPTER_SERVICE_HOST}:{BaseConfig.ADAPTER_SERVICE_GRPC_PORT}"


@lru_cache(maxsize=1)
def _get_adapter_channel():
    """adapter_service 共享 channel"""
    chan = grpc.insecure_channel(ADAPTER_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def get_adapter_service_stub():
    """AdapterService stub：发送单轮测试请求"""
    from shared.proto import adapter_service_pb2_grpc
    return adapter_service_pb2_grpc.AdapterServiceStub(_get_adapter_channel())


# ==================== 便捷封装 ====================

def submit_evaluate_case(task_id, result_id, test_case_id, algorithm_result, eval_params):
    """通过 gRPC 调用 task_service 的 ExecutionService.EvaluateCase

    供 api_test_service（以及任何迁移到 shared 的执行器）跨服务提交评估请求。

    Args:
        task_id: 任务ID
        result_id: 测试结果ID
        test_case_id: 测试用例ID
        algorithm_result: 算法结果字典
        eval_params: 评估参数字典 (algorithm_type, test_type, round_number, ...)
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_execution_service_stub()
    req = task_pb.EvaluateCaseRequest(
        task_id=str(task_id),
        result_id=str(result_id),
        test_case_id=str(test_case_id),
        algorithm_result=_json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
        eval_params=_json.dumps(eval_params or {}, ensure_ascii=False, default=str),
    )
    resp = stub.EvaluateCase(req)
    if not resp.success:
        raise RuntimeError(f"EvaluateCase gRPC 调用失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}
