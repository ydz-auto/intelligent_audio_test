# -*- coding: utf-8 -*-
"""gRPC 客户端工厂（聚合导出模块，P4-4 大文件拆分）

集中管理所有跨服务的 gRPC stub 客户端，采用懒加载 + channel 复用模式。

P4-4 拆分说明：原单文件 1395 行，已按职责拆分为 3 个内部模块，本文件
保持 `from shared.clients.grpc_clients import ...` 的全部导入路径不变：

- _grpc_channels.py：服务地址 + channel 复用工厂（_get_xxx_channel）
- _grpc_stubs.py：各服务 stub 懒加载工厂（get_xxx_service_stub）
- _grpc_task_data.py：task_service / evaluation_service 便捷封装
- _grpc_algo_audio.py：algorithm_service / audio_service 便捷封装

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
# ==================== channel 复用 ====================
from shared.clients._grpc_channels import (
    E2E_GRPC_ADDR,
    AUDIO_GRPC_ADDR,
    DEVICE_GRPC_ADDR,
    TASK_GRPC_ADDR,
    API_TEST_GRPC_ADDR,
    EVALUATION_GRPC_ADDR,
    ALGORITHM_GRPC_ADDR,
    REPORT_GRPC_ADDR,
    AUTH_GRPC_ADDR,
    ADAPTER_GRPC_ADDR,
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

# ==================== 各服务 stub 工厂 ====================
from shared.clients._grpc_stubs import (
    get_e2e_execution_service_stub,
    get_audio_service_stub,
    get_playback_service_stub,
    get_audio_config_service_stub,
    get_device_service_stub,
    get_device_result_service_stub,
    get_env_device_service_stub,
    get_device_config_service_stub,
    get_playback_config_service_stub,
    get_spl_config_service_stub,
    get_execution_service_stub,
    get_task_config_service_stub,
    get_testcase_config_service_stub,
    get_tag_config_service_stub,
    get_algorithm_config_service_stub,
    get_task_data_service_stub,
    get_evaluation_service_stub,
    get_evaluation_config_service_stub,
    get_evaluation_data_service_stub,
    get_api_test_service_stub,
    get_adapter_service_stub,
    get_algorithm_group_service_stub,
    get_algorithm_definition_service_stub,
    get_algorithm_query_service_stub,
    get_report_config_service_stub,
    get_auth_service_stub,
)

# ==================== task_service / evaluation_service 便捷封装 ====================
from shared.clients._grpc_task_data import (
    submit_evaluate_case,
    submit_reevaluate,
    submit_result,
    update_task_case_status,
    notify_task_progress,
    notify_case_completed,
    get_task_by_id,
    get_task_devices,
    get_task_apis,
    get_task_cases_by_ids,
    list_tasks_config,
    get_task_merge_relations,
    list_logs,
    batch_create_logs,
    get_log_stats,
    list_logs_after_id,
    get_logs_for_export,
    get_log_count,
    update_logs_mark,
    clear_logs,
    archive_logs,
    list_testcase_groups,
    get_testcase_groups_by_ids,
    get_testcase_groups_by_names,
    get_testcase_group_by_id,
    get_testcase_group_by_name,
    create_testcase_group,
    get_task_stats,
    get_testcase_stats,
)

# ==================== algorithm_service / audio_service 便捷封装 ====================
from shared.clients._grpc_algo_audio import (
    call_algo_config_rpc,
    list_reference_params,
    get_audios_by_ids,
    get_audio_by_id,
    audio_prepare_audios,
    _call_algo_query_rpc,
    algo_get_algorithm_config,
    algo_get_all_algorithms,
    algo_get_device_params,
    algo_get_api_params,
    algo_get_case_params,
    algo_get_reference_params_list,
    algo_get_param_mapping,
    algo_get_evaluation_dimension_params,
    algo_get_algorithm_definition,
    algo_reload_config,
    algo_get_field_mappings,
    algo_get_evaluation_field_mappings,
    algo_build_api_request_data,
    algo_convert_field_value,
    algo_get_output_fields,
    algo_get_reference_output_fields,
    algo_extract_result_fields,
    algo_get_timeline_fields,
    algo_get_full_field_mapping,
    algo_map_api_results,
    algo_extract_round_results,
    algo_extract_case_all_params,
    algo_normalize_algorithm_params,
    algo_normalize_algorithm_params_to_list,
    algo_get_round_algo_params,
    algo_get_algo_param,
    algo_build_case_form_schema,
    algo_generate_reference_params,
    algo_load_reference_params_file,
    algo_get_reference_text,
    algo_get_all_reference_params,
    algo_get_reference_params_for_report,
)
