# -*- coding: utf-8 -*-
"""report_service gRPC 客户端层

集中导出报告生成引擎所需的全部跨服务 gRPC 查询函数。
report_service 自成体系，不依赖 api_gateway 任何模块。
"""

from report_service.infrastructure.clients.grpc_clients import (
    # ---- TaskDataService：task 关联数据查询 ----
    _grpc_get_task_devices,
    _grpc_get_task_apis,
    _grpc_get_tasks_by_ids,
    _grpc_get_test_results_by_task_ids,
    _grpc_get_test_result_by_id,
    _grpc_get_task_case_ids,
    _grpc_get_task_case_ids_batch,
    _grpc_get_test_results_by_task_and_case,
    # ---- EvaluationDataService：维度评估结果查询 ----
    _grpc_get_dimension_results_by_result_ids,
    # ---- EvaluationConfigService：维度配置查询 ----
    _grpc_list_dimensions_all,
    _grpc_get_dimension_by_ids,
    # ---- AlgorithmConfigService：维度参数查询 ----
    _grpc_get_dimension_params,
    # ---- TestCaseConfigService：测试用例查询 ----
    _grpc_list_testcases_by_ids,
    # ---- TagConfigService：标签分类查询 ----
    _grpc_get_tag_category,
    # ---- DeviceConfigService：设备查询 ----
    _grpc_get_device,
    _grpc_get_devices_by_ids,
    # ---- PlaybackConfigService：播放设备查询 ----
    _grpc_get_playback_device,
    _grpc_get_playback_devices_by_ids,
    # ---- AudioConfigService：音频查询 ----
    _grpc_get_audio,
    _grpc_get_audios_by_ids,
    # ---- APITestService：API 配置查询 ----
    _grpc_get_api,
    _grpc_get_apis_by_ids,
    # ---- TaskMergeRelation：任务合并关系查询 ----
    _grpc_get_task_merge_relations,
    _grpc_get_task_merge_relations_by_source,
    # ---- 维度对象 dict/ORM 兼容访问器 ----
    _dim_id,
    _dim_name,
    _dim_weight,
    _dim_statistic_method,
    _dim_score_unit,
    _dim_decimal_places,
    _dim_result_dim_id,
    _dim_result_value,
    _dim_result_raw_response,
)

__all__ = [
    # TaskDataService
    '_grpc_get_task_devices',
    '_grpc_get_task_apis',
    '_grpc_get_tasks_by_ids',
    '_grpc_get_test_results_by_task_ids',
    '_grpc_get_test_result_by_id',
    '_grpc_get_task_case_ids',
    '_grpc_get_task_case_ids_batch',
    '_grpc_get_test_results_by_task_and_case',
    # EvaluationDataService
    '_grpc_get_dimension_results_by_result_ids',
    # EvaluationConfigService
    '_grpc_list_dimensions_all',
    '_grpc_get_dimension_by_ids',
    # AlgorithmConfigService
    '_grpc_get_dimension_params',
    # TestCaseConfigService
    '_grpc_list_testcases_by_ids',
    # TagConfigService
    '_grpc_get_tag_category',
    # DeviceConfigService
    '_grpc_get_device',
    '_grpc_get_devices_by_ids',
    # PlaybackConfigService
    '_grpc_get_playback_device',
    '_grpc_get_playback_devices_by_ids',
    # AudioConfigService
    '_grpc_get_audio',
    '_grpc_get_audios_by_ids',
    # APITestService
    '_grpc_get_api',
    '_grpc_get_apis_by_ids',
    # TaskMergeRelation
    '_grpc_get_task_merge_relations',
    '_grpc_get_task_merge_relations_by_source',
    # 维度对象访问器
    '_dim_id',
    '_dim_name',
    '_dim_weight',
    '_dim_statistic_method',
    '_dim_score_unit',
    '_dim_decimal_places',
    '_dim_result_dim_id',
    '_dim_result_value',
    '_dim_result_raw_response',
]
