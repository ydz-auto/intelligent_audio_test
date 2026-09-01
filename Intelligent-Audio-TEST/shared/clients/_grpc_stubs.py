# -*- coding: utf-8 -*-
"""各服务 gRPC stub 工厂函数（从 grpc_clients.py 拆分，P4-4）。

按服务分组的 stub 懒加载工厂，全部基于 _grpc_channels 中的共享 channel。
"""
from functools import lru_cache

from shared.clients._grpc_channels import (
    _get_e2e_channel,
    _get_audio_channel,
    _get_device_channel,
    _get_task_channel,
    _get_api_test_channel,
    _get_evaluation_channel,
    _get_adapter_channel,
    _get_algorithm_channel,
    _get_report_channel,
    _get_auth_channel,
)


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
def get_auth_service_stub():
    """AuthService stub：用户管理 + 权限查询 + 认证校验

    RPC（与 auth_service/interfaces/grpc/servicers.AuthServicer 对齐）：
    GetUser / GetUserByUsername / GetUserByOAuth / CreateUser /
    UpdateLastLogin / GetUserPermissions / ListRoles / ListUsers /
    UpdateUserStatus / GrantPermission / RevokePermission / DeleteUser
    """
    from shared.proto import auth_service_pb2_grpc
    return auth_service_pb2_grpc.AuthServiceStub(_get_auth_channel())
