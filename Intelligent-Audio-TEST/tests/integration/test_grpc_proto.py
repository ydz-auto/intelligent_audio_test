# -*- coding: utf-8 -*-
"""gRPC proto 编译产物验证（集成测试）。

验证 shared/proto 下的 *_pb2.py 与 *_pb2_grpc.py 可正常导入，
即 proto 文件已正确编译为 Python 模块。
"""
import importlib

import pytest

# 所有服务 proto 模块（_pb2 主体 + _pb2_grpc 桩）
PROTO_MODULES = [
    'shared.proto.auth_service_pb2',
    'shared.proto.auth_service_pb2_grpc',
    'shared.proto.e2e_test_service_pb2',
    'shared.proto.e2e_test_service_pb2_grpc',
    'shared.proto.device_service_pb2',
    'shared.proto.device_service_pb2_grpc',
    'shared.proto.audio_service_pb2',
    'shared.proto.audio_service_pb2_grpc',
    'shared.proto.report_service_pb2',
    'shared.proto.report_service_pb2_grpc',
    'shared.proto.algorithm_service_pb2',
    'shared.proto.algorithm_service_pb2_grpc',
    'shared.proto.task_service_pb2',
    'shared.proto.task_service_pb2_grpc',
    'shared.proto.evaluation_service_pb2',
    'shared.proto.evaluation_service_pb2_grpc',
    'shared.proto.e2e_service_pb2',
    'shared.proto.e2e_service_pb2_grpc',
    'shared.proto.api_test_service_pb2',
    'shared.proto.api_test_service_pb2_grpc',
    'shared.proto.adapter_service_pb2',
    'shared.proto.adapter_service_pb2_grpc',
]


@pytest.mark.parametrize("module_name", PROTO_MODULES)
def test_proto_module_importable(module_name):
    """每个 proto 编译产物模块可被导入。"""
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_task_service_pb2_has_messages():
    """task_service_pb2 包含关键消息类。"""
    from shared.proto import task_service_pb2
    assert hasattr(task_service_pb2, 'CreateTaskRequest')
    assert hasattr(task_service_pb2, 'StartTaskRequest')
    assert hasattr(task_service_pb2, 'StopTaskRequest')
    assert hasattr(task_service_pb2, 'TaskStatusResponse')


def test_task_service_pb2_message_instantiation():
    """task_service_pb2 消息可实例化。"""
    from shared.proto import task_service_pb2
    msg = task_service_pb2.CreateTaskRequest(task_id='123',
                                              task_config='{}')
    assert msg.task_id == '123'
    assert msg.task_config == '{}'


def test_evaluation_service_pb2_has_messages():
    """evaluation_service_pb2 包含评估消息类。"""
    from shared.proto import evaluation_service_pb2
    assert hasattr(evaluation_service_pb2, 'EvaluateCaseRequest')
    assert hasattr(evaluation_service_pb2, 'EvaluateCaseResponse')
    assert hasattr(evaluation_service_pb2, 'ReevaluateRequest')


def test_evaluation_service_pb2_message_instantiation():
    """evaluation_service_pb2 消息可实例化。"""
    from shared.proto import evaluation_service_pb2
    msg = evaluation_service_pb2.EvaluateCaseRequest(
        task_id='t1', result_id='r1', test_case_id='c1')
    assert msg.task_id == 't1'
    assert msg.test_case_id == 'c1'


def test_task_service_pb2_grpc_has_service_stubs():
    """task_service_pb2_grpc 包含服务桩类。"""
    from shared.proto import task_service_pb2_grpc
    assert hasattr(task_service_pb2_grpc, 'ExecutionServiceStub') \
        or hasattr(task_service_pb2_grpc, 'ExecutionServiceServicer')
    assert hasattr(task_service_pb2_grpc, 'TaskConfigServiceStub') \
        or hasattr(task_service_pb2_grpc, 'TaskConfigServiceServicer')


def test_evaluation_service_pb2_grpc_has_service_stubs():
    """evaluation_service_pb2_grpc 包含服务桩类。"""
    from shared.proto import evaluation_service_pb2_grpc
    assert hasattr(evaluation_service_pb2_grpc, 'EvaluationServiceStub') \
        or hasattr(evaluation_service_pb2_grpc, 'EvaluationServiceServicer')
