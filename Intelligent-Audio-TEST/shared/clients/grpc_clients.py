# -*- coding: utf-8 -*-
"""gRPC 客户端工厂

集中管理所有跨服务的 gRPC stub 客户端，采用懒加载 + channel 复用模式。

每个服务（e2e_test_service / task_service / api_test_service / evaluation_service /
adapter_service / algorithm_service）只创建一个 channel，
所有 stub 共享同一 channel。客户端拦截器自动附加到每个 channel。

- e2e_test_service gRPC server（端口 50051）：ExecutionService
- audio_service gRPC server（端口 50052）：AudioService / PlaybackService / AudioConfigService
- device_service gRPC server（端口 50053）：DeviceService / DeviceResultService / EnvDeviceService / DeviceConfigService / PlaybackConfigService / SPLConfigService
- task_service gRPC server（端口 50061）：ExecutionService / TaskConfigService / TestCaseConfigService / TagConfigService / AlgorithmConfigService
- api_test_service gRPC server（端口 50071）：APITestService
- evaluation_service gRPC server（端口 50091）：EvaluationService / EvaluationConfigService
- adapter_service gRPC server（端口 50081）：AdapterService
- algorithm_service gRPC server（端口 50067）：AlgorithmGroupService / AlgorithmDefinitionService
- report_service gRPC server（端口 50068）：ReportConfigService
- auth_service gRPC server（端口 50069）：AuthService
"""
import grpc
from functools import lru_cache

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.grpc_interceptors import client_log_interceptor

# 服务地址
E2E_GRPC_ADDR = f"{BaseConfig.E2E_TEST_SERVICE_HOST}:{BaseConfig.E2E_TEST_SERVICE_GRPC_PORT}"
AUDIO_GRPC_ADDR = f"{BaseConfig.AUDIO_SERVICE_HOST}:{BaseConfig.AUDIO_SERVICE_GRPC_PORT}"
DEVICE_GRPC_ADDR = f"{BaseConfig.DEVICE_SERVICE_HOST}:{BaseConfig.DEVICE_SERVICE_GRPC_PORT}"
TASK_GRPC_ADDR = f"{BaseConfig.TASK_SERVICE_HOST}:{BaseConfig.TASK_SERVICE_GRPC_PORT}"
API_TEST_GRPC_ADDR = f"{BaseConfig.API_TEST_SERVICE_HOST}:{BaseConfig.API_TEST_SERVICE_GRPC_PORT}"
EVALUATION_GRPC_ADDR = f"{BaseConfig.EVALUATION_SERVICE_HOST}:{BaseConfig.EVALUATION_SERVICE_GRPC_PORT}"
ALGORITHM_GRPC_ADDR = f"{BaseConfig.ALGORITHM_SERVICE_HOST}:{BaseConfig.ALGORITHM_SERVICE_GRPC_PORT}"
REPORT_GRPC_ADDR = f"{BaseConfig.REPORT_SERVICE_HOST}:{BaseConfig.REPORT_SERVICE_GRPC_PORT}"
AUTH_GRPC_ADDR = f"{BaseConfig.AUTH_SERVICE_HOST}:{BaseConfig.AUTH_SERVICE_GRPC_PORT}"

# 客户端拦截器列表
_CLIENT_INTERCEPTORS = [client_log_interceptor]


# ==================== channel 复用 ====================

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


# ==================== e2e_test_service stubs ====================

@lru_cache(maxsize=1)
def get_e2e_execution_service_stub():
    """ExecutionService stub（e2e_test_service）：启动/停止 E2E 任务、获取状态"""
    from shared.proto import e2e_test_service_pb2_grpc
    return e2e_test_service_pb2_grpc.ExecutionServiceStub(_get_e2e_channel())


# ==================== audio_service stubs ====================

@lru_cache(maxsize=1)
def get_audio_service_stub():
    """AudioService stub：播放/停止音频、获取播放状态、获取音频信息、SPL 测量、物理设备"""
    from shared.proto import audio_service_pb2_grpc
    return audio_service_pb2_grpc.AudioServiceStub(_get_audio_channel())


@lru_cache(maxsize=1)
def get_playback_service_stub():
    """PlaybackService stub：开始/停止播放编排"""
    from shared.proto import audio_service_pb2_grpc
    return audio_service_pb2_grpc.PlaybackServiceStub(_get_audio_channel())


@lru_cache(maxsize=1)
def get_audio_config_service_stub():
    """AudioConfigService stub：音频 CRUD（元数据更新/标注/批量操作/删除/算法关联/标签/列表/详情/流播放/目录树/上传/合并/导入/转换/预览）"""
    from shared.proto import audio_service_pb2_grpc
    return audio_service_pb2_grpc.AudioConfigServiceStub(_get_audio_channel())


# ==================== device_service stubs ====================

@lru_cache(maxsize=1)
def get_device_service_stub():
    """DeviceService stub：创建/销毁设备驱动、注册/注销/获取任务事件、驱动扫描/解锁/模式控制"""
    from shared.proto import device_service_pb2_grpc
    return device_service_pb2_grpc.DeviceServiceStub(_get_device_channel())


@lru_cache(maxsize=1)
def get_device_result_service_stub():
    """DeviceResultService stub：采集/重新提取设备结果"""
    from shared.proto import device_service_pb2_grpc
    return device_service_pb2_grpc.DeviceResultServiceStub(_get_device_channel())


@lru_cache(maxsize=1)
def get_env_device_service_stub():
    """EnvDeviceService stub：控制环境设备（导轨旋转等）"""
    from shared.proto import device_service_pb2_grpc
    return device_service_pb2_grpc.EnvDeviceServiceStub(_get_device_channel())


@lru_cache(maxsize=1)
def get_device_config_service_stub():
    """DeviceConfigService stub：设备 CRUD（创建/更新/删除/列表/详情/状态/扫描/测试/驱动关键字/健康检查/可用序列号）"""
    from shared.proto import device_service_pb2_grpc
    return device_service_pb2_grpc.DeviceConfigServiceStub(_get_device_channel())


@lru_cache(maxsize=1)
def get_playback_config_service_stub():
    """PlaybackConfigService stub：播放设备 CRUD（创建/更新/删除/列表/详情/扫描/状态/关联SPL/测试/停止）"""
    from shared.proto import device_service_pb2_grpc
    return device_service_pb2_grpc.PlaybackConfigServiceStub(_get_device_channel())


@lru_cache(maxsize=1)
def get_spl_config_service_stub():
    """SPLConfigService stub：SPL 映射 CRUD（创建/更新/删除/列表/详情/历史/校准数据/统计/按设备/校准/播放测试音/停止测试音）"""
    from shared.proto import device_service_pb2_grpc
    return device_service_pb2_grpc.SPLConfigServiceStub(_get_device_channel())


# ==================== task_service stubs ====================

@lru_cache(maxsize=1)
def get_execution_service_stub():
    """ExecutionService stub：创建/启动/停止/暂停/恢复任务、获取引擎信息、通知进度/用例完成"""
    from shared.proto import task_service_pb2_grpc
    return task_service_pb2_grpc.ExecutionServiceStub(_get_task_channel())


@lru_cache(maxsize=1)
def get_task_config_service_stub():
    """TaskConfigService stub：任务 CRUD（创建/更新/删除/列表/详情/进度/统计/用例详情/用例结果/启动/重试/控制/停止/重新提取/批量操作/合并）"""
    from shared.proto import task_service_pb2_grpc
    return task_service_pb2_grpc.TaskConfigServiceStub(_get_task_channel())


@lru_cache(maxsize=1)
def get_testcase_config_service_stub():
    """TestCaseConfigService stub：测试用例 CRUD（创建/更新/删除/复制/批量操作/更新参考参数/列表/详情/统计/标签/参考参数）"""
    from shared.proto import task_service_pb2_grpc
    return task_service_pb2_grpc.TestCaseConfigServiceStub(_get_task_channel())


@lru_cache(maxsize=1)
def get_tag_config_service_stub():
    """TagConfigService stub：标签及标签分类 CRUD（创建/更新/删除/批量更新分类/列表/详情/按分类查询）"""
    from shared.proto import task_service_pb2_grpc
    return task_service_pb2_grpc.TagConfigServiceStub(_get_task_channel())


@lru_cache(maxsize=1)
def get_algorithm_config_service_stub():
    """AlgorithmConfigService stub：算法定义/分组/参数/用例参数/参考参数/映射/维度关联 CRUD + 批量操作"""
    from shared.proto import task_service_pb2_grpc
    return task_service_pb2_grpc.AlgorithmConfigServiceStub(_get_task_channel())


@lru_cache(maxsize=1)
def get_task_data_service_stub():
    """TaskDataService stub（P1.5 新增）：跨服务数据查询

    供 evaluation_service / api_test_service / e2e_test_service 跨服务读 task_service 数据：
    - GetTestResultById / GetTaskCaseByIds / GetTaskById / GetTaskDevices / GetTaskApis
    - SubmitResult / UpdateTaskCaseStatus
    - GetTaskStats / GetTestCaseStats（聚合统计 count/group_by，供 stats_cache / home_service 用）
    """
    from shared.proto import task_service_pb2_grpc
    return task_service_pb2_grpc.TaskDataServiceStub(_get_task_channel())


@lru_cache(maxsize=1)
def get_evaluation_service_stub():
    """EvaluationService stub：评估单个用例（EvaluateCase）、重新评估（Reevaluate / ReevaluateMultiRound / ReevaluateSingle）

    注：已从 task_service.ExecutionService 迁移至 evaluation_service.EvaluationService。
    """
    from shared.proto import evaluation_service_pb2_grpc
    return evaluation_service_pb2_grpc.EvaluationServiceStub(_get_evaluation_channel())


@lru_cache(maxsize=1)
def get_evaluation_config_service_stub():
    """EvaluationConfigService stub：评估维度/分类 CRUD + 批量操作 + 分值计算 + 健康检查

    注：已从 task_service 迁移至 evaluation_service，使用 evaluation_service proto。
    """
    from shared.proto import evaluation_service_pb2_grpc
    return evaluation_service_pb2_grpc.EvaluationConfigServiceStub(_get_evaluation_channel())


@lru_cache(maxsize=1)
def get_evaluation_data_service_stub():
    """EvaluationDataService stub：跨服务查询/删除 TestResultDimension

    供 task_service 跨服务访问 evaluation_service 自有 PO（TestResultDimension）。
    """
    from shared.proto import evaluation_service_pb2_grpc
    return evaluation_service_pb2_grpc.EvaluationDataServiceStub(_get_evaluation_channel())


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


# ==================== algorithm_service stubs ====================
# algorithm_service 的 proto 已接入（shared/proto/algorithm_service.proto 及
# algorithm_service_pb2 / algorithm_service_pb2_grpc 已生成）。servicer 继承
# proto 基类并实现全部 RPC（见 algorithm_service/interfaces/grpc/servicers.py）。
# task_service 的 AlgorithmConfigServiceServicer 与 task_service/application/algorithm/*
# 旧 CRUD 为兼容保留，待调用方全部切换后删除。

@lru_cache(maxsize=1)
def _get_algorithm_channel():
    """algorithm_service 共享 channel"""
    chan = grpc.insecure_channel(ALGORITHM_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def get_algorithm_group_service_stub():
    """AlgorithmGroupService stub：算法分组 CRUD

    RPC（与 algorithm_service/interfaces/grpc/servicers.AlgorithmGroupServicer 对齐）：
    CreateAlgorithmGroup / UpdateAlgorithmGroup / DeleteAlgorithmGroup /
    GetAlgorithmGroup / ListAlgorithmGroups
    """
    from shared.proto import algorithm_service_pb2_grpc
    return algorithm_service_pb2_grpc.AlgorithmGroupServiceStub(_get_algorithm_channel())


@lru_cache(maxsize=1)
def get_algorithm_definition_service_stub():
    """AlgorithmDefinitionService stub：算法定义/参数/映射/维度关联 CRUD

    RPC（与 algorithm_service/interfaces/grpc/servicers.AlgorithmDefinitionServicer 对齐）：
    CreateAlgorithm / UpdateAlgorithm / DeleteAlgorithm /
    ListAlgorithms / GetAlgorithm / GetAlgorithmOptions /
    ListParams / GetParam / ListCaseParams / ListReferenceParams /
    ListMappings / GetDimensionParams / GetAlgorithmDimensions /
    CreateDimensionRelation / UpdateDimensionRelation / DeleteDimensionRelation /
    DeleteRelationsByDimension / GetRelationsByDimension / SyncDimensionRelations /
    CreateDimensionParam / DeleteDimensionParamsByDirection / FindAudioDimensionIds /
    SyncParamMappings / ListParamMappingsForDimension /
    ImportAlgorithms / ReloadAlgorithmConfig
    """
    from shared.proto import algorithm_service_pb2_grpc
    return algorithm_service_pb2_grpc.AlgorithmDefinitionServiceStub(_get_algorithm_channel())


@lru_cache(maxsize=1)
def get_algorithm_query_service_stub():
    """AlgorithmQueryService stub：算法领域查询（CQRS 读侧，迁移自 shared/algorithm）

    RPC（与 algorithm_service/interfaces/grpc/algorithm_query_servicer.AlgorithmQueryServicer 对齐）：
    GetAlgorithmConfig / GetAllAlgorithmsList / GetAlgorithmParamsMerged /
    GetDeviceParamsList / GetApiParamsList / GetCaseParamsList / GetReferenceParamsList /
    GetParamMappingForComponent / GetEvaluationDimensionParams / GetAlgorithmDefinitionInfo / ReloadConfig /
    GetFieldMappings / GetEvaluationFieldMappings / BuildApiRequestData / ConvertFieldValue /
    GetOutputFields / GetReferenceOutputFields / ExtractResultFields / GetTimelineFields /
    GetFullFieldMapping / MapApiResults / ExtractRoundResults /
    ExtractCaseAllParams / NormalizeAlgorithmParams / NormalizeAlgorithmParamsToList /
    GetRoundAlgoParams / GetAlgoParam / BuildCaseFormSchema /
    GenerateReferenceParams / LoadReferenceParamsFile / GetReferenceTextValue /
    GetAllReferenceParams / GetReferenceParamsForReport
    """
    from shared.proto import algorithm_service_pb2_grpc
    return algorithm_service_pb2_grpc.AlgorithmQueryServiceStub(_get_algorithm_channel())


# ==================== report_service stubs ====================

@lru_cache(maxsize=1)
def _get_report_channel():
    """report_service 共享 channel"""
    chan = grpc.insecure_channel(REPORT_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def get_report_config_service_stub():
    """ReportConfigService stub：报告 CRUD + 查询

    RPC（与 report_service/interfaces/grpc/servicers.ReportServicer 对齐）：
    CreateReport / UpdateReport / DeleteReport / BatchActionReports /
    ListReports / GetReportDetail / GetReportByTask /
    GenerateReport / UpdateReportStatus
    """
    from shared.proto import report_service_pb2_grpc
    return report_service_pb2_grpc.ReportConfigServiceStub(_get_report_channel())


# ==================== auth_service stubs ====================

@lru_cache(maxsize=1)
def _get_auth_channel():
    """auth_service 共享 channel"""
    chan = grpc.insecure_channel(AUTH_GRPC_ADDR)
    return grpc.intercept_channel(chan, *_CLIENT_INTERCEPTORS)


@lru_cache(maxsize=1)
def get_auth_service_stub():
    """AuthService stub：用户管理 + 权限查询 + 认证校验

    RPC（与 auth_service/interfaces/grpc/servicers.AuthServicer 对齐）：
    GetUser / GetUserByUsername / GetUserByOAuth / CreateUser /
    UpdateLastLogin / GetUserPermissions / ListRoles / ListUsers /
    UpdateUserStatus / GrantPermission / RevokePermission / DeleteUser
    """
    from shared.proto import auth_service_pb2_grpc
    return auth_service_pb2_grpc.AuthServiceStub(_get_auth_channel())


# ==================== 便捷封装 ====================

def submit_evaluate_case(task_id, result_id, test_case_id, algorithm_result, eval_params):
    """通过 gRPC 调用 evaluation_service 的 EvaluationService.EvaluateCase

    供 api_test_service / e2e_test_service 等执行器跨服务提交评估请求。
    已从 task_service.ExecutionService 迁移至 evaluation_service.EvaluationService。

    Args:
        task_id: 任务ID
        result_id: 测试结果ID
        test_case_id: 测试用例ID
        algorithm_result: 算法结果字典
        eval_params: 评估参数字典 (algorithm_type, test_type, round_number, ...)
    """
    import json as _json
    from shared.proto import evaluation_service_pb2 as eval_pb
    stub = get_evaluation_service_stub()
    req = eval_pb.EvaluateCaseRequest(
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


def submit_reevaluate(task_id, reextract_device_output=True, reevaluate_type='all'):
    """通过 gRPC 调用 evaluation_service 的 EvaluationService.Reevaluate

    供 task_service 提交任务级重新评估（已从 task_service.core.reevaluation_executor 迁移至
    evaluation_service.application.handlers.reevaluation_executor）。

    Args:
        task_id: 任务ID
        reextract_device_output: 是否重新提取设备输出
        reevaluate_type: 重新评估类型 ('all' / 'failed')

    Returns:
        dict: {success, message, data}
    """
    import json as _json
    from shared.proto import evaluation_service_pb2 as eval_pb
    stub = get_evaluation_service_stub()
    req = eval_pb.ReevaluateRequest(
        task_id=str(task_id),
        reextract_device_output=reextract_device_output,
        reevaluate_type=reevaluate_type or 'all',
    )
    resp = stub.Reevaluate(req)
    return {
        'success': resp.success,
        'message': resp.message,
        'data': _json.loads(resp.data) if resp.data else {},
    }


def submit_result(task_id, result_data):
    """通过 gRPC 调用 task_service.TaskDataService.SubmitResult 写入 TestResult

    供 api_test_service / e2e_test_service 执行完成后跨服务写入测试结果，
    替代直连 DB 的 INSERT INTO test_results。

    Args:
        task_id: 任务ID
        result_data: TestResult 字段字典，包含 test_case_id / device_id / api_id /
                      algorithm_type / execution_status / response_time /
                      algorithm_result / execution_steps / result_data /
                      result_data_path / error_message

    Returns:
        int: 新建 TestResult 的 result_id
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.SubmitResultRequest(
        task_id=int(task_id),
        result_data=_json.dumps(result_data or {}, ensure_ascii=False, default=str),
    )
    resp = stub.SubmitResult(req)
    if not resp.success:
        raise RuntimeError(f"SubmitResult gRPC 调用失败: {resp.message}")
    data = _json.loads(resp.data) if resp.data else {}
    return data.get('result_id')


def update_task_case_status(task_id, case_id, status=None, execution_status=None,
                            evaluation_status=None, error_message=None):
    """通过 gRPC 调用 task_service.TaskDataService.UpdateTaskCaseStatus 更新 TaskCase 状态

    供 api_test_service / e2e_test_service 执行完成后更新 TaskCase 执行状态，
    替代直连 DB 的 db.session.query(TaskCase).update(...)。

    Args:
        task_id: 任务ID
        case_id: 测试用例ID
        status: 可选，TaskCase.status (pending/completed/failed/skipped)
        execution_status: 可选，执行状态 (pending/running/completed/stopped/failed)
        evaluation_status: 可选，评估状态
        error_message: 可选，错误信息

    Returns:
        bool: 是否有字段被更新
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.UpdateTaskCaseStatusRequest(
        task_id=int(task_id),
        case_id=str(case_id),
        status=status or '',
        execution_status=execution_status or '',
        evaluation_status=evaluation_status or '',
        error_message=error_message or '',
    )
    resp = stub.UpdateTaskCaseStatus(req)
    if not resp.success:
        raise RuntimeError(f"UpdateTaskCaseStatus gRPC 调用失败: {resp.message}")
    data = _json.loads(resp.data) if resp.data else {}
    return data.get('updated', False)


def notify_task_progress(task_id, force=False):
    """通过 gRPC 调用 task_service.ExecutionService.NotifyProgress

    供 evaluation_service 评估完成后通知 task_service 发送进度更新。

    Args:
        task_id: 任务ID
        force: 是否强制更新，跳过节流逻辑
    """
    from shared.proto import task_service_pb2 as task_pb
    stub = get_execution_service_stub()
    req = task_pb.NotifyProgressRequest(task_id=str(task_id), force=force)
    resp = stub.NotifyProgress(req)
    if not resp.success:
        import logging
        logging.getLogger(__name__).warning(f"NotifyProgress gRPC 调用失败: {resp.message}")


def notify_case_completed(task_id):
    """通过 gRPC 调用 task_service.ExecutionService.NotifyCaseCompleted

    供 evaluation_service 评估完成后通知 task_service 唤醒等待线程。

    Args:
        task_id: 任务ID
    """
    from shared.proto import task_service_pb2 as task_pb
    stub = get_execution_service_stub()
    req = task_pb.NotifyCaseCompletedRequest(task_id=str(task_id))
    resp = stub.NotifyCaseCompleted(req)
    if not resp.success:
        import logging
        logging.getLogger(__name__).warning(f"NotifyCaseCompleted gRPC 调用失败: {resp.message}")


def get_task_by_id(task_id):
    """通过 gRPC 按 ID 查询 Task

    返回 dict 或 None: {id, name, type, status, total_cases, ...}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskByIdRequest(task_id=int(task_id))
    resp = stub.GetTaskById(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskById gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else None


def get_task_devices(task_id):
    """通过 gRPC 查询 Task 关联的设备列表

    返回 dict: {'items': [{id, name, ...}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskDevicesRequest(task_id=int(task_id))
    resp = stub.GetTaskDevices(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskDevices gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_apis(task_id):
    """通过 gRPC 查询 Task 关联的 API 列表

    返回 dict: {'items': [{id, name, ...}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskApisRequest(task_id=int(task_id))
    resp = stub.GetTaskApis(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskApis gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_cases_by_ids(task_id, case_ids=None):
    """通过 gRPC 按 task_id + case_ids 查询 TaskCase 列表

    返回 dict: {'items': [{test_case_id, execution_status, ...}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskCaseByIdsRequest(
        task_id=int(task_id),
        case_ids=[str(c) for c in case_ids] if case_ids else [],
    )
    resp = stub.GetTaskCaseByIds(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskCaseByIds gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_tasks_config(page=1, per_page=20, status=None, type=None,
                     algorithm_type=None, search=None, start_date=None, end_date=None):
    """通过 gRPC 调用 TaskConfigService.ListTasks 查询任务列表

    返回 dict: {'items': [...], 'total': N, 'page': P, 'per_page': PP}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_config_service_stub()
    req = task_pb.ListTasksRequest(
        page=page,
        per_page=per_page,
        status=status or '',
        type=type or '',
        algorithm_type=algorithm_type or '',
        search=search or '',
        start_date=start_date or '',
        end_date=end_date or '',
    )
    resp = stub.ListTasks(req)
    if not resp.success:
        raise RuntimeError(f"ListTasks gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_merge_relations(task_id):
    """通过 gRPC 查询 TaskMergeRelation（按 task_id）

    供 api_gateway 报告对比等场景跨服务查询合并关系，替代直连 DB。
    返回 dict：{'items': [{id, merged_task_id, source_task_id, source_result_count}, ...]}

    Args:
        task_id: 任务ID（同时匹配 merged_task_id 与 source_task_id）

    Returns:
        dict: {'items': [...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTaskMergeRelationsRequest(task_id=int(task_id))
    resp = stub.GetTaskMergeRelations(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskMergeRelations gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_logs(task_id=None, level=None, page=1, per_page=20, start_date=None, end_date=None):
    """通过 gRPC 查询 Log 列表（分页 + 过滤）

    供 api_gateway 日志查询跨服务读取 task_service 的 Log，替代直连 DB。
    返回 dict：{'items': [...], 'total': N, 'page': P, 'per_page': PP}

    Args:
        task_id: 可选，按任务ID过滤
        level: 可选，按日志级别过滤
        page: 页码，默认 1
        per_page: 每页条数，默认 20
        start_date: 可选，开始日期（ISO 字符串）
        end_date: 可选，结束日期（ISO 字符串）

    Returns:
        dict: {'items': [...], 'total': N, 'page': P, 'per_page': PP}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ListLogsRequest(
        task_id=int(task_id) if task_id else 0,
        level=level or '',
        page=page,
        per_page=per_page,
        start_date=start_date or '',
        end_date=end_date or '',
    )
    resp = stub.ListLogs(req)
    if not resp.success:
        raise RuntimeError(f"ListLogs gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def batch_create_logs(logs_list):
    """通过 gRPC 批量写入日志（替代 shared/utils/log_handler 直连 DB）

    供 log_handler 后台 worker 调用。返回写入后的 id 列表。

    Args:
        logs_list: 日志 dict 列表 [{time, level, category, module, source, content, ...}, ...]

    Returns:
        list[int]: 写入后的 id 列表
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.BatchCreateLogsRequest(
        logs_json=_json.dumps(logs_list, default=str),
    )
    resp = stub.BatchCreateLogs(req)
    if not resp.success:
        raise RuntimeError(f"BatchCreateLogs gRPC 失败: {resp.message}")
    data = _json.loads(resp.data) if resp.data else {}
    return data.get('ids', [])


def get_log_stats(level=None, module=None, category=None, mark=None,
                  device_id=None, task_id=None, keyword=None,
                  content_include=None, content_exclude=None,
                  start_time=None, end_time=None, algorithm_type=None):
    """通过 gRPC 查询日志统计（group_by level + count）

    供 api_gateway log_query_service.get_stats 调用，替代直连 DB。
    返回 dict：{'total': N, 'debug': N, 'info': N, 'warning': N, 'error': N, 'critical': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetLogStatsRequest(
        level=level or '',
        module=module or '',
        category=category or '',
        mark=mark or '',
        device_id=int(device_id) if device_id else 0,
        task_id=int(task_id) if task_id else 0,
        keyword=keyword or '',
        content_include=content_include or '',
        content_exclude=content_exclude or '',
        start_time=start_time or '',
        end_time=end_time or '',
        algorithm_type=algorithm_type or '',
    )
    resp = stub.GetLogStats(req)
    if not resp.success:
        raise RuntimeError(f"GetLogStats gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_logs_after_id(last_id, limit=100):
    """通过 gRPC 增量查询日志（id > last_id）

    供 api_gateway log_query_service.refresh_logs 调用，替代直连 DB。
    返回 dict：{'items': [...], 'max_id': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ListLogsAfterIdRequest(last_id=last_id, limit=limit)
    resp = stub.ListLogsAfterId(req)
    if not resp.success:
        raise RuntimeError(f"ListLogsAfterId gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_logs_for_export(log_ids=None, level=None, module=None):
    """通过 gRPC 按条件查询日志（导出用）

    供 api_gateway log_query_service.export_logs 调用，替代直连 DB。
    返回 dict：{'items': [{id, time, level, module, content, mark}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetLogsForExportRequest(
        log_ids=list(log_ids) if log_ids else [],
        level=level or '',
        module=module or '',
    )
    resp = stub.GetLogsForExport(req)
    if not resp.success:
        raise RuntimeError(f"GetLogsForExport gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_log_count(start_date=None):
    """通过 gRPC 查询日志总数（含按日期范围 hot 日志计数）

    供 api_gateway log_query_service.get_archive_status 调用，替代直连 DB。
    返回 dict：{'total': N, 'hot': N, 'cold': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetLogCountRequest(start_date=start_date or '')
    resp = stub.GetLogCount(req)
    if not resp.success:
        raise RuntimeError(f"GetLogCount gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def update_logs_mark(log_ids, mark):
    """通过 gRPC 批量更新日志标记

    供 api_gateway log_command_service.mark_logs 调用，替代直连 DB。
    返回 dict：{'updated': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.UpdateLogsMarkRequest(
        log_ids=list(log_ids),
        mark=mark or '',
    )
    resp = stub.UpdateLogsMark(req)
    if not resp.success:
        raise RuntimeError(f"UpdateLogsMark gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def clear_logs(before_datetime=None, keep_marked=False):
    """通过 gRPC 批量清除日志

    供 api_gateway log_command_service.clear_logs 调用，替代直连 DB。
    返回 dict：{'deleted': N}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ClearLogsRequest(
        before_datetime=before_datetime or '',
        keep_marked=keep_marked,
    )
    resp = stub.ClearLogs(req)
    if not resp.success:
        raise RuntimeError(f"ClearLogs gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def archive_logs(days=30, dry_run=False):
    """通过 gRPC 归档日志（按天数）

    供 api_gateway log_command_service.archive_logs 调用，替代直连 DB。
    返回 dict：{'archived_count': N, 'deleted_count': N, 'remaining_count': N, 'groups': {...}}
    dry_run 时返回 {'cold_logs_count': N, 'cutoff_date': str}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ArchiveLogsRequest(days=days, dry_run=dry_run)
    resp = stub.ArchiveLogs(req)
    if not resp.success:
        raise RuntimeError(f"ArchiveLogs gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def list_testcase_groups(algorithm_type=None, search=None):
    """通过 gRPC 查询 TestCaseGroup 列表

    供 api_gateway 分组管理跨服务读取 task_service 的 TestCaseGroup，替代直连 DB。
    返回 dict：{'items': [{id, name, description, algorithm_type}, ...]}

    Args:
        algorithm_type: 可选，按算法类型过滤
        search: 可选，按名称模糊搜索

    Returns:
        dict: {'items': [...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.ListTestCaseGroupsRequest(
        algorithm_type=algorithm_type or '',
        search=search or '',
    )
    resp = stub.ListTestCaseGroups(req)
    if not resp.success:
        raise RuntimeError(f"ListTestCaseGroups gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_groups_by_ids(group_ids):
    """通过 gRPC 按 ID 列表批量查询 TestCaseGroup

    返回 dict: {'items': [{id, name, description, algorithm_type}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupsByIdsRequest(group_ids=[str(g) for g in group_ids])
    resp = stub.GetTestCaseGroupsByIds(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupsByIds gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_groups_by_names(group_names):
    """通过 gRPC 按名称列表批量查询 TestCaseGroup

    返回 dict: {'items': [{id, name, description, algorithm_type}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupsByNamesRequest(group_names=list(group_names))
    resp = stub.GetTestCaseGroupsByNames(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupsByNames gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_group_by_id(group_id):
    """通过 gRPC 按 ID 查询单个 TestCaseGroup

    返回 dict 或 None: {id, name, description, algorithm_type}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupByIdRequest(group_id=str(group_id))
    resp = stub.GetTestCaseGroupById(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupById gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else None


def get_testcase_group_by_name(group_name):
    """通过 gRPC 按名称查询单个 TestCaseGroup

    返回 dict 或 None: {id, name, description, algorithm_type}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.GetTestCaseGroupByNameRequest(group_name=group_name)
    resp = stub.GetTestCaseGroupByName(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseGroupByName gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else None


def create_testcase_group(name, description='', algorithm_type='', group_id=None):
    """通过 gRPC 创建 TestCaseGroup

    返回 dict: {id, name, description, algorithm_type}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.CreateTestCaseGroupRequest(
        name=name,
        description=description or '',
        algorithm_type=algorithm_type or '',
        group_id=group_id or '',
    )
    resp = stub.CreateTestCaseGroup(req)
    if not resp.success:
        raise RuntimeError(f"CreateTestCaseGroup gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_task_stats(status=None, algorithm_type=None, group_by=None):
    """通过 gRPC 调用 task_service.TaskDataService.GetTaskStats 聚合统计 Task

    供 stats_cache / home_service 跨服务聚合统计 task_service 的 Task，替代直连 DB
    的 `func.count(Task.id).filter(...)` 查询。

    Args:
        status: 可选，按任务状态过滤（pending/queued/running/evaluating/completed/...）
        algorithm_type: 可选，按算法类型过滤
        group_by: 可选，分组字段（status / algorithm_type / type）；为空返回 total

    Returns:
        dict: {'total': N} 或 {'items': [{'key': str, 'count': int}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.TaskAggStatsRequest(
        status=status or '',
        algorithm_type=algorithm_type or '',
        group_by=group_by or '',
    )
    resp = stub.GetTaskStats(req)
    if not resp.success:
        raise RuntimeError(f"GetTaskStats gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


def get_testcase_stats(algorithm_type=None, group_id=None, group_by=None):
    """通过 gRPC 调用 task_service.TaskDataService.GetTestCaseStats 聚合统计 TestCase

    供 stats_cache / home_service 跨服务聚合统计 task_service 的 TestCase，替代直连 DB
    的 `func.count(TestCase.id).filter(...)` 查询。

    Args:
        algorithm_type: 可选，按算法类型过滤
        group_id: 可选，按分组 ID 过滤
        group_by: 可选，分组字段（algorithm_type / group_id）；为空返回 total

    Returns:
        dict: {'total': N} 或 {'items': [{'key': str, 'count': int}, ...]}
    """
    import json as _json
    from shared.proto import task_service_pb2 as task_pb
    stub = get_task_data_service_stub()
    req = task_pb.TestCaseAggStatsRequest(
        algorithm_type=algorithm_type or '',
        group_id=int(group_id) if group_id else 0,
        group_by=group_by or '',
    )
    resp = stub.GetTestCaseStats(req)
    if not resp.success:
        raise RuntimeError(f"GetTestCaseStats gRPC 失败: {resp.message}")
    return _json.loads(resp.data) if resp.data else {}


# ==================== algorithm config / audio 便捷封装 ====================
# 以下函数供各服务调用 algorithm_service.AlgorithmQueryService，替代原 shared/algorithm 包。

def call_algo_config_rpc(method_name: str, **kwargs):
    """通用调用 task_service.AlgorithmConfigService RPC，返回解析后的 data（dict/list）

    Args:
        method_name: RPC 方法名（如 'ListAlgorithms'）
        **kwargs: 请求字段

    Returns:
        解析后的 data 字段（dict 或 list），失败返回 None
    """
    from typing import Any
    from shared.utils.log_handler import log_not_emit
    try:
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_algorithm_config_service_stub()
        req_cls = getattr(task_pb, f'{method_name}Request')
        req = req_cls(**kwargs)
        resp = getattr(stub, method_name)(req)
        if not resp.success:
            log_not_emit('WARNING', 'grpc_clients',
                         f'gRPC {method_name} failed: {resp.message}', category='algorithm')
            return None
        return _loads(resp.data, {})
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'gRPC {method_name} exception: {e}', category='algorithm')
        return None


def list_reference_params(algorithm_type: str):
    """通过 gRPC 获取参考参数列表（algorithm_service.ListReferenceParams）

    Returns:
        参考参数 dict 列表，失败返回空列表
    """
    from typing import Dict, Any
    from shared.utils.log_handler import log_not_emit
    try:
        from shared.proto import algorithm_service_pb2 as _algo_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_algorithm_definition_service_stub()
        req = _algo_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type or '')
        resp = stub.ListReferenceParams(req)
        if resp.success:
            return (_loads(resp.data, {}) or {}).get('parameters', []) or []
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'list_reference_params failed: {e}', category='algorithm')
    return []


def get_audios_by_ids(audio_ids):
    """通过 gRPC 批量获取音频数据（audio_service.GetAudiosByIds）

    Returns:
        {audio_id: {...}, ...} 或空 dict
    """
    from typing import Dict, Any
    from shared.utils.log_handler import log_not_emit
    if not audio_ids:
        return {}
    try:
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_audio_config_service_stub()
        req = e2e_pb.GetAudiosByIdsRequest(audio_ids=','.join(str(aid) for aid in audio_ids))
        resp = stub.GetAudiosByIds(req)
        data = _loads(resp.data, {})
        audio_map = {}
        for item in data.get('items', []):
            aid = item.get('id')
            audio_map[aid] = item
        return audio_map
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'get_audios_by_ids failed: {e}', category='algorithm')
        return {}


def get_audio_by_id(audio_id):
    """通过 gRPC 获取单个音频（audio_service.GetAudio）

    Returns:
        音频 dict 或 None
    """
    from typing import Dict, Any, Optional
    from shared.utils.log_handler import log_not_emit
    if not audio_id:
        return None
    try:
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        stub = get_audio_config_service_stub()
        resp = stub.GetAudio(e2e_pb.GetAudioRequest(audio_id=int(audio_id)))
        if not resp.success:
            return None
        return _loads(resp.data, {}) or {}
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'get_audio_by_id failed: {e}', category='algorithm')
        return None


def audio_prepare_audios(audio_ids, playback_device_ids):
    """通过 gRPC 预下载并按设备目标采样率重采样音频（audio_service.PrepareAudios）

    Args:
        audio_ids: 音频 ID 列表 [int, ...]
        playback_device_ids: 播放设备 ID 列表 [int|str, ...]

    Returns:
        嵌套映射 {audio_id: {target_rate: local_path, "original": local_path}} 或空 dict
    """
    from shared.utils.log_handler import log_not_emit
    if not audio_ids:
        return {}
    try:
        from shared.proto import audio_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads, dumps as _dumps
        stub = get_audio_service_stub()
        req = e2e_pb.PrepareAudiosRequest(
            data=_dumps({
                'audio_ids': list(audio_ids),
                'playback_device_ids': list(playback_device_ids or []),
            }),
        )
        resp = stub.PrepareAudios(req)
        if not resp.success:
            log_not_emit('WARNING', 'grpc_clients',
                         f'PrepareAudios failed: {resp.message}', category='algorithm')
            return {}
        return _loads(resp.data, {}) or {}
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'audio_prepare_audios failed: {e}', category='algorithm')
        return {}


# ==================== algorithm query 便捷封装（迁移自 shared/algorithm）====================

def _call_algo_query_rpc(method_name: str, **kwargs):
    """通用调用 algorithm_service.AlgorithmQueryService RPC，返回解析后的 data

    Args:
        method_name: RPC 方法名
        **kwargs: 请求字段

    Returns:
        解析后的 data 字段（dict/list），失败返回 None
    """
    from shared.utils.log_handler import log_not_emit
    try:
        from shared.utils.grpc_json import loads as _loads
        stub = get_algorithm_query_service_stub()
        req_cls = getattr(_algo_pb, f'{method_name}Request') if False else None  # placeholder
        from shared.proto import algorithm_service_pb2 as _algo_pb2
        req_cls = getattr(_algo_pb2, f'{method_name}Request')
        req = req_cls(**kwargs)
        resp = getattr(stub, method_name)(req)
        if not resp.success:
            log_not_emit('WARNING', 'grpc_clients',
                         f'AlgorithmQuery {method_name} failed: {resp.message}', category='algorithm')
            return None
        return _loads(resp.data, {})
    except Exception as e:
        log_not_emit('ERROR', 'grpc_clients',
                     f'AlgorithmQuery {method_name} exception: {e}', category='algorithm')
        return None


def algo_get_algorithm_config(algorithm_type: str):
    """获取算法定义配置（含 device/api/case params + mappings）"""
    return _call_algo_query_rpc('GetAlgorithmConfig', algorithm_type=algorithm_type or '')


def algo_get_all_algorithms():
    """获取所有在线算法列表"""
    return _call_algo_query_rpc('GetAllAlgorithmsList') or []


def algo_get_device_params(algorithm_type: str):
    """获取设备参数列表"""
    return _call_algo_query_rpc('GetDeviceParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_api_params(algorithm_type: str):
    """获取 API 参数列表"""
    return _call_algo_query_rpc('GetApiParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_case_params(algorithm_type: str):
    """获取用例参数列表"""
    return _call_algo_query_rpc('GetCaseParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_reference_params_list(algorithm_type: str):
    """获取参考参数列表"""
    return _call_algo_query_rpc('GetReferenceParamsList', algorithm_type=algorithm_type or '') or []


def algo_get_param_mapping(algorithm_type: str, component_type: str):
    """获取参数映射"""
    return _call_algo_query_rpc('GetParamMappingForComponent',
                               algorithm_type=algorithm_type or '',
                               component_type=component_type or '') or []


def algo_get_evaluation_dimension_params(dimension_id: int):
    """获取评估维度参数"""
    return _call_algo_query_rpc('GetEvaluationDimensionParams', dimension_id=int(dimension_id)) or []


def algo_get_algorithm_definition(algorithm_type: str):
    """获取算法定义信息"""
    return _call_algo_query_rpc('GetAlgorithmDefinitionInfo', algorithm_type=algorithm_type or '')


def algo_reload_config():
    """重新加载算法配置缓存"""
    return _call_algo_query_rpc('ReloadConfig')


def algo_get_field_mappings(algorithm_type: str):
    """获取字段定义（original + mapped）"""
    return _call_algo_query_rpc('GetFieldMappings', algorithm_type=algorithm_type or '') or {}


def algo_get_evaluation_field_mappings(algorithm_type: str):
    """获取评估字段映射"""
    return _call_algo_query_rpc('GetEvaluationFieldMappings', algorithm_type=algorithm_type or '') or {}


def algo_build_api_request_data(algorithm_type: str, device_params=None, api_params=None, case_config=None, **kwargs):
    """构建 API 请求参数"""
    import json as _json
    data = _json.dumps({
        'device_params': device_params or {},
        'api_params': api_params or {},
        'case_config': case_config or {},
        'kwargs': kwargs,
    }, ensure_ascii=False)
    return _call_algo_query_rpc('BuildApiRequestData', algorithm_type=algorithm_type or '', data=data) or {}


def algo_convert_field_value(transform_type: str, value):
    """转换字段值"""
    import json as _json
    return _call_algo_query_rpc('ConvertFieldValue',
                               transform_type=transform_type or 'none',
                               data=_json.dumps({'value': value}, ensure_ascii=False))


def algo_get_output_fields(algorithm_type: str, test_type: str = None):
    """获取结果输出字段"""
    return _call_algo_query_rpc('GetOutputFields',
                               algorithm_type=algorithm_type or '',
                               test_type=test_type or '') or []


def algo_get_reference_output_fields(algorithm_type: str):
    """获取参考输出字段"""
    return _call_algo_query_rpc('GetReferenceOutputFields', algorithm_type=algorithm_type or '') or []


def algo_extract_result_fields(algorithm_type: str, algorithm_result=None, result_data=None):
    """从算法结果中提取字段"""
    import json as _json
    return _call_algo_query_rpc('ExtractResultFields',
                               algorithm_type=algorithm_type or '',
                               algorithm_result=_json.dumps(algorithm_result or {}, ensure_ascii=False),
                               result_data=_json.dumps(result_data or {}, ensure_ascii=False)) or {}


def algo_get_timeline_fields(algorithm_type: str):
    """获取时间线字段"""
    return _call_algo_query_rpc('GetTimelineFields', algorithm_type=algorithm_type or '') or []


def algo_get_full_field_mapping(algorithm_type: str):
    """获取完整字段映射"""
    return _call_algo_query_rpc('GetFullFieldMapping', algorithm_type=algorithm_type or '') or {}


def algo_map_api_results(algorithm_type: str, raw_results=None, test_type: str = None):
    """映射 API 结果"""
    import json as _json
    return _call_algo_query_rpc('MapApiResults',
                               algorithm_type=algorithm_type or '',
                               raw_results=_json.dumps(raw_results or {}, ensure_ascii=False),
                               test_type=test_type or '') or {}


def algo_extract_round_results(algorithm_result=None, test_type: str = None):
    """提取轮次结果"""
    import json as _json
    return _call_algo_query_rpc('ExtractRoundResults',
                               algorithm_result=_json.dumps(algorithm_result or {}, ensure_ascii=False),
                               test_type=test_type or '') or []


def algo_extract_case_all_params(case_config=None):
    """提取用例全部参数"""
    import json as _json
    return _call_algo_query_rpc('ExtractCaseAllParams',
                               case_config=_json.dumps(case_config or {}, ensure_ascii=False)) or {}


def algo_normalize_algorithm_params(algorithm_params=None):
    """规范化算法参数为 dict"""
    import json as _json
    return _call_algo_query_rpc('NormalizeAlgorithmParams',
                               algorithm_params=_json.dumps(algorithm_params or {}, ensure_ascii=False)) or {}


def algo_normalize_algorithm_params_to_list(algorithm_params=None):
    """规范化算法参数为 list"""
    import json as _json
    return _call_algo_query_rpc('NormalizeAlgorithmParamsToList',
                               algorithm_params=_json.dumps(algorithm_params or [], ensure_ascii=False)) or []


def algo_get_round_algo_params(algorithm_params_col=None, round_number: int = 0):
    """获取指定轮次算法参数"""
    import json as _json
    return _call_algo_query_rpc('GetRoundAlgoParams',
                               algorithm_params_col=_json.dumps(algorithm_params_col or [], ensure_ascii=False),
                               round_number=int(round_number)) or {}


def algo_get_algo_param(algorithm_params=None, field_code: str = ''):
    """从参数列表获取指定字段值"""
    import json as _json
    result = _call_algo_query_rpc('GetAlgoParam',
                                  algorithm_params=_json.dumps(algorithm_params or [], ensure_ascii=False),
                                  field_code=field_code)
    return result.get('value') if result else None


def algo_build_case_form_schema(algorithm_type: str):
    """构建用例表单 schema"""
    return _call_algo_query_rpc('BuildCaseFormSchema', algorithm_type=algorithm_type or '') or {}


def algo_generate_reference_params(test_case_config=None, round_data=None):
    """生成参考参数"""
    import json as _json
    data = _json.dumps({
        'test_case_config': test_case_config or {},
        'round_data': round_data or {},
    }, ensure_ascii=False)
    return _call_algo_query_rpc('GenerateReferenceParams', data=data) or []


def algo_load_reference_params_file(filepath: str = ''):
    """从 OSS 加载参考参数"""
    return _call_algo_query_rpc('LoadReferenceParamsFile', filepath=filepath or '') or []


def algo_get_reference_text(reference_params_col=None, code: str = ''):
    """获取参考文本"""
    import json as _json
    result = _call_algo_query_rpc('GetReferenceTextValue',
                                  reference_params_col=_json.dumps(reference_params_col or [], ensure_ascii=False),
                                  code=code or '')
    return result.get('text', '') if result else ''


def algo_get_all_reference_params(reference_params_col=None):
    """获取所有参考参数"""
    import json as _json
    return _call_algo_query_rpc('GetAllReferenceParams',
                               reference_params_col=_json.dumps(reference_params_col or [], ensure_ascii=False)) or []


def algo_get_reference_params_for_report(reference_params_col=None):
    """获取报告用参考参数"""
    import json as _json
    return _call_algo_query_rpc('GetReferenceParamsForReport',
                               reference_params_col=_json.dumps(reference_params_col or [], ensure_ascii=False)) or {}
