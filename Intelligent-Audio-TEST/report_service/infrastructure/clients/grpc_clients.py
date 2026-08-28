# -*- coding: utf-8 -*-
"""report_service gRPC 客户端辅助函数集合

集中管理报告生成引擎所需的全部跨服务 gRPC 查询函数。
report_service 自成体系，不依赖 api_gateway 任何模块，所有跨服务数据
均通过 shared.clients.grpc_clients 提供的 stub 直接调用。

涉及的服务及 stub：
- task_service.TaskDataService           —— get_task_data_service_stub
- task_service.TestCaseConfigService     —— get_testcase_config_service_stub
- task_service.TagConfigService          —— get_tag_config_service_stub
- task_service.AlgorithmConfigService    —— get_algorithm_config_service_stub
- evaluation_service.EvaluationDataService —— get_evaluation_data_service_stub
- evaluation_service.EvaluationConfigService —— get_evaluation_config_service_stub
- device_service.DeviceConfigService     —— get_device_config_service_stub
- device_service.PlaybackConfigService   —— get_playback_config_service_stub
- audio_service.AudioConfigService       —— get_audio_config_service_stub
- api_test_service.APITestService         —— get_api_test_service_stub

约定：
- 所有 gRPC helper 函数均以 _grpc_ 前缀命名，保持与历史调用方一致。
- 查询失败（异常或 success=False）返回空集合或 None，不抛异常。
- 延迟导入 stub / proto，避免模块加载期循环依赖。
- 使用 shared.utils.grpc_json.loads 进行 JSON 反序列化。

DDD 迁移（2026-08-08）：跨服务 gRPC 逻辑迁入 infrastructure/acl/ 下的
ACL 仓储，返回 dataclass DTO（经 dict_to_dto / dict_list_to_dto 转换）。
本模块的 _grpc_* 函数保留为历史调用方的兼容层，委托 ACL 仓储并通过
shared.utils.dto_utils.dto_to_dict 还原为 dict，签名与返回值不变。
"""

import logging as _logging

from report_service.infrastructure.acl import (
    AlgorithmConfigAclRepositoryImpl as _AlgoImpl,
    ApiTestAclRepositoryImpl as _ApiImpl,
    AudioConfigAclRepositoryImpl as _AudioImpl,
    DeviceConfigAclRepositoryImpl as _DeviceImpl,
    EvaluationConfigAclRepositoryImpl as _EvalCfgImpl,
    EvaluationDataAclRepositoryImpl as _EvalDataImpl,
    PlaybackConfigAclRepositoryImpl as _PlaybackImpl,
    TagConfigAclRepositoryImpl as _TagImpl,
    TaskDataAclRepositoryImpl as _TaskDataImpl,
    TaskMergeRelationAclRepositoryImpl as _MergeImpl,
    TestCaseConfigAclRepositoryImpl as _TestCaseImpl,
)
from shared.utils.dto_utils import dto_to_dict as _dto_to_dict

_logger = _logging.getLogger(__name__)

# ACL 仓储单例
_task_data = _TaskDataImpl()
_eval_data = _EvalDataImpl()
_eval_cfg = _EvalCfgImpl()
_algo = _AlgoImpl()
_testcase = _TestCaseImpl()
_tag = _TagImpl()
_device = _DeviceImpl()
_playback = _PlaybackImpl()
_audio = _AudioImpl()
_api = _ApiImpl()
_merge = _MergeImpl()


# ======================================================================
# TaskDataService —— task 关联数据查询
# ======================================================================

def _grpc_get_task_devices(task_id):
    """通过 gRPC (task_service.TaskDataService) 查询 task 关联设备，返回 list[dict]。"""
    return [_dto_to_dict(d) for d in _task_data.get_task_devices(task_id)]


def _grpc_get_task_apis(task_id):
    """通过 gRPC (task_service.TaskDataService) 查询 task 关联 API，返回 list[dict]。"""
    return [_dto_to_dict(d) for d in _task_data.get_task_apis(task_id)]


def _grpc_get_tasks_by_ids(task_ids):
    """通过 gRPC (task_service.TaskDataService) 批量查询 Task，返回 list[dict]。"""
    return [_dto_to_dict(d) for d in _task_data.get_tasks_by_ids(task_ids)]


def _grpc_get_test_results_by_task_ids(task_ids):
    """通过 gRPC (task_service.TaskDataService) 按 task_id 批量查询 TestResult，返回 list[dict]。"""
    return [_dto_to_dict(d) for d in _task_data.get_test_results_by_task_ids(task_ids)]


def _grpc_get_test_result_by_id(result_id):
    """通过 gRPC (task_service.TaskDataService) 按 ID 查询单个 TestResult，返回 dict 或 None。"""
    return _dto_to_dict(_task_data.get_test_result_by_id(result_id))


def _grpc_get_task_case_ids(task_id):
    """通过 gRPC (task_service.TaskDataService) 查询 task 关联的 test_case_id 列表。"""
    return [_dto_to_dict(d) for d in _task_data.get_task_case_ids(task_id)]


def _grpc_get_task_case_ids_batch(task_ids):
    """通过 gRPC 批量查询多个 task 关联的 test_case_id 列表。"""
    return [_dto_to_dict(d) for d in _task_data.get_task_case_ids_batch(task_ids)]


def _grpc_get_test_results_by_task_and_case(test_case_ids, task_ids=None):
    """通过 gRPC (task_service.TaskDataService) 按 test_case_id + task_id 批量查询 TestResult。

    由于 gRPC 接口按 task_id 查询，此处遍历 task_ids 拉取后按 test_case_id 过滤。
    返回 list[dict]。
    """
    return [_dto_to_dict(d) for d in _task_data.get_test_results_by_task_and_case(test_case_ids, task_ids)]


# ======================================================================
# EvaluationDataService —— 维度评估结果查询
# ======================================================================

def _grpc_get_dimension_results_by_result_ids(result_ids):
    """通过 gRPC (evaluation_service.EvaluationDataService) 批量查询维度评估结果。

    返回 {result_id: [item_dict, ...]} 映射，item_dict 含
    dimension_id / dimension_name / dimension_value / api_raw_response 等字段。
    """
    raw = _eval_data.get_dimension_results_by_result_ids(result_ids)
    return {rid: [_dto_to_dict(d) for d in items] for rid, items in raw.items()}


# ======================================================================
# EvaluationConfigService —— 维度配置查询
# ======================================================================

def _grpc_list_dimensions_all():
    """通过 gRPC (evaluation_service.EvaluationConfigService) 查询所有启用的维度列表。

    返回 list[dict]，每个 dict 含 id / name / weight / score_unit /
    decimal_places / statistic_method 等字段。
    """
    return [_dto_to_dict(d) for d in _eval_cfg.list_dimensions_all()]


def _grpc_get_dimension_by_ids(dim_ids):
    """通过 gRPC (evaluation_service.EvaluationConfigService) 按 ID 批量查询维度。

    返回 {dim_id_str: dimension_dict} 映射。
    """
    raw = _eval_cfg.get_dimension_by_ids(dim_ids)
    return {k: _dto_to_dict(v) for k, v in raw.items()}


# ======================================================================
# AlgorithmConfigService —— 维度参数查询
# ======================================================================

def _grpc_get_dimension_params(dimension_id):
    """通过 gRPC (task_service.AlgorithmConfigService) 查询维度参数列表。

    返回 list[dict]，每个 dict 含 param_code / field_path / field_type /
    agg_role / output_role / visible_in_report / param_direction 等字段。
    """
    return [_dto_to_dict(d) for d in _algo.get_dimension_params(dimension_id)]


def _grpc_algo_normalize_algorithm_params(algorithm_params=None):
    """通过 gRPC (algorithm_service.AlgorithmQueryService) 规范化算法参数为 dict。"""
    return _dto_to_dict(_algo.normalize_algorithm_params(algorithm_params))


def _grpc_algo_get_reference_params_for_report(reference_params_col=None):
    """通过 gRPC (algorithm_service.AlgorithmQueryService) 获取报告用参考参数 dict。"""
    return _dto_to_dict(_algo.get_reference_params_for_report(reference_params_col))


def _grpc_algo_get_field_mapping(algorithm_type=None):
    """通过 gRPC (algorithm_service.AlgorithmQueryService) 获取算法字段映射快照。"""
    return _dto_to_dict(_algo.get_full_field_mapping(algorithm_type or ''))


# ======================================================================
# TestCaseConfigService —— 测试用例查询
# ======================================================================

def _grpc_list_testcases_by_ids(test_case_ids):
    """通过 gRPC (task_service.TestCaseConfigService) 按 ID 批量查询测试用例。

    返回 {id: dict} 映射。由于 TestCaseConfigService 没有按 ID 批量查询的 RPC，
    此处通过 ListTestCases 大分页拉取后过滤。
    """
    raw = _testcase.list_testcases_by_ids(test_case_ids)
    return {k: _dto_to_dict(v) for k, v in raw.items()}


# ======================================================================
# TagConfigService —— 标签分类查询
# ======================================================================

def _grpc_get_tag_category(category_id):
    """通过 gRPC (task_service.TagConfigService) 查询单个 TagCategory，返回 dict 或 None。"""
    return _dto_to_dict(_tag.get_tag_category(category_id))


# ======================================================================
# DeviceConfigService —— 设备查询
# ======================================================================

def _grpc_get_device(device_id):
    """通过 gRPC (device_service.DeviceConfigService) 查询单个 Device，返回 dict 或 None。"""
    return _dto_to_dict(_device.get_device(device_id))


def _grpc_get_devices_by_ids(device_ids):
    """通过 gRPC 批量查询 Device（device_service.DeviceConfigService），返回 {id: dict} 映射。"""
    raw = _device.get_devices_by_ids(device_ids)
    return {k: _dto_to_dict(v) for k, v in raw.items()}


# ======================================================================
# PlaybackConfigService —— 播放设备查询
# ======================================================================

def _grpc_get_playback_device(device_id):
    """通过 gRPC (device_service.PlaybackConfigService) 查询单个 PlaybackDevice，返回 dict 或 None。"""
    return _dto_to_dict(_playback.get_playback_device(device_id))


def _grpc_get_playback_devices_by_ids(device_ids):
    """通过 gRPC 批量查询 PlaybackDevice，返回 {id: dict} 映射。"""
    raw = _playback.get_playback_devices_by_ids(device_ids)
    return {k: _dto_to_dict(v) for k, v in raw.items()}


# ======================================================================
# AudioConfigService —— 音频查询
# ======================================================================

def _grpc_get_audio(audio_id):
    """通过 gRPC (audio_service.AudioConfigService) 查询单个 Audio，返回 dict 或 None。"""
    return _dto_to_dict(_audio.get_audio(audio_id))


def _grpc_get_audios_by_ids(audio_ids):
    """通过 gRPC 批量查询 Audio（audio_service.AudioConfigService），返回 {id: dict} 映射。"""
    raw = _audio.get_audios_by_ids(audio_ids)
    return {k: _dto_to_dict(v) for k, v in raw.items()}


# ======================================================================
# APITestService —— API 配置查询
# ======================================================================

def _grpc_get_api(api_id):
    """通过 gRPC (api_test_service.APITestService) 查询单个 API，返回 dict 或 None。"""
    return _dto_to_dict(_api.get_api(api_id))


def _grpc_get_apis_by_ids(api_ids):
    """通过 gRPC 批量查询 API（api_test_service.APITestService），返回 {id: dict} 映射。"""
    raw = _api.get_apis_by_ids(api_ids)
    return {k: _dto_to_dict(v) for k, v in raw.items()}


# ======================================================================
# TaskMergeRelation —— 任务合并关系查询
# ======================================================================

def _grpc_get_task_merge_relations(merged_task_id):
    """通过 gRPC 查询 TaskMergeRelation（按 merged_task_id，客户端过滤）。"""
    return [_dto_to_dict(d) for d in _merge.get_task_merge_relations(merged_task_id)]


def _grpc_get_task_merge_relations_by_source(source_task_id):
    """通过 gRPC 查询 TaskMergeRelation（按 source_task_id，客户端过滤）。"""
    return [_dto_to_dict(d) for d in _merge.get_task_merge_relations_by_source(source_task_id)]


# ======================================================================
# 维度对象 dict/ORM 兼容访问器（纯属性读取，无 gRPC 调用）
# ======================================================================

def _dim_id(dim):
    """从维度对象（dict 或 ORM）读取 id。"""
    if isinstance(dim, dict):
        return dim.get('id')
    return getattr(dim, 'id', None)


def _dim_name(dim):
    """从维度对象（dict 或 ORM）读取 name。"""
    if isinstance(dim, dict):
        return dim.get('name')
    return getattr(dim, 'name', None)


def _dim_weight(dim):
    """从维度对象读取 weight。"""
    if isinstance(dim, dict):
        return dim.get('weight')
    return getattr(dim, 'weight', None)


def _dim_statistic_method(dim):
    """从维度对象读取 statistic_method。"""
    if isinstance(dim, dict):
        return dim.get('statistic_method')
    return getattr(dim, 'statistic_method', None)


def _dim_score_unit(dim):
    """从维度对象读取 score_unit。"""
    if isinstance(dim, dict):
        return dim.get('score_unit')
    return getattr(dim, 'score_unit', None)


def _dim_decimal_places(dim):
    """从维度对象读取 decimal_places。"""
    if isinstance(dim, dict):
        return dim.get('decimal_places')
    return getattr(dim, 'decimal_places', None)


def _dim_result_dim_id(dr):
    """从维度结果对象读取 dimension_id。"""
    if isinstance(dr, dict):
        return dr.get('dimension_id') or dr.get('id')
    return getattr(dr, 'dimension_id', None) or getattr(dr, 'id', None)


def _dim_result_value(dr):
    """从维度结果对象读取 dimension_value。"""
    if isinstance(dr, dict):
        return dr.get('dimension_value') or dr.get('value')
    return getattr(dr, 'dimension_value', None)


def _dim_result_raw_response(dr):
    """从维度结果对象读取 api_raw_response。"""
    if isinstance(dr, dict):
        return dr.get('api_raw_response')
    return getattr(dr, 'api_raw_response', None)
