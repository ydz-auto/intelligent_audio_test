from shared.clients.grpc_clients import (
    algo_get_device_params,
    algo_get_api_params,
    algo_get_param_mapping,
)
from shared.infrastructure.base_executor import BaseExecutor
from e2e_test_service.application.services.e2e_device_manager import E2EDeviceManager
from e2e_test_service.application.services.e2e_collector import E2ECollector
from e2e_test_service.application.services.e2e_aggregator import E2EAggregator
from e2e_test_service.application.services.e2e_executor.preparation_mixin import PreparationMixin
from e2e_test_service.application.services.e2e_executor.rounds_loop_mixin import RoundsLoopMixin
from e2e_test_service.application.services.e2e_executor.finalization_mixin import FinalizationMixin
# 跨服务调用：通过 ACL 仓储访问 device_service / playback_service
from e2e_test_service.infrastructure.acl import (
    DeviceAclRepositoryImpl,
    PlaybackAclRepositoryImpl,
)


class E2EExecutor(PreparationMixin, RoundsLoopMixin, FinalizationMixin, BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self._playback_timestamps = {}
        self._audio_local_paths = {}  # {audio_id: {target_rate: local_path, "original": local_path}}（准备阶段预下载+重采样）
        # 委托组件
        self._device_manager = E2EDeviceManager(self)
        self._collector = E2ECollector(self)
        self._aggregator = E2EAggregator(self)
        # ACL 仓储
        self._device_repo = DeviceAclRepositoryImpl()
        self._playback_repo = PlaybackAclRepositoryImpl()

    def execute_e2e_case(self, task_id, tc_rel_id):
        """执行E2E测试用例"""
        self._log(
            level='DEBUG',
            content=f"E2E用例执行方法开始: task_id={task_id}, tc_rel_id={tc_rel_id}",
            task_id=task_id
        )

        if not task_id or not tc_rel_id:
            error_msg = "任务ID和测试用例关联ID不能为空"
            self._log(level='ERROR', content=f"E2E 用例执行失败: {error_msg}", task_id=task_id)
            if tc_rel_id:
                self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status='failed', status='failed', error_message=error_msg)
            return False

        data_result = self._validate_and_get_data(task_id, tc_rel_id)
        if not data_result['success']:
            error_msg = data_result.get('error', '获取基础数据失败')
            self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status='failed', status='failed', error_message=error_msg)
            return False

        data = data_result['data']
        return self._execute_e2e_with_rounds(task_id, tc_rel_id, data)

    def _execute_e2e_with_rounds(self, task_id, tc_rel_id, data):
        """新格式执行：支持多轮（rounds）的 E2E 执行"""
        case_name = data['case_name']
        case_config = data['case_config']
        case_reference_params = data.get('case_reference_params', [])
        test_case_id = data['test_case_id']
        algorithm_type = data.get('algorithm_type', 'translation')

        # 初始化 case_field_values
        # 通过 gRPC 获取 device/api 参数与映射，内联实现 get_case_fields 逻辑
        device_params = algo_get_device_params(algorithm_type)
        api_params = algo_get_api_params(algorithm_type)
        all_params = (device_params or []) + (api_params or [])
        case_fields = {}
        for param in all_params:
            param_code = param.get('code', '')
            param_type = param.get('param_type', '')
            source = param.get('source', '')
            if source == 'case_table' or param_type in ['direction', 'language']:
                case_fields[param_code] = param_code
        mappings = algo_get_param_mapping(algorithm_type, 'case') or []
        for mapping in mappings:
            source_param = mapping.get('source_param', '')
            target_key = mapping.get('target_key', source_param)
            source = mapping.get('source', '')
            if source == 'case_table':
                case_fields[target_key] = source_param
        case_field_values = {key: data.get(key) for key in case_fields.keys()}

        self.current_case_field_values = case_field_values
        self.current_test_case_id = test_case_id
        self._thread_ctx.current_test_case_id = test_case_id

        rounds = case_config.get('rounds', [])

        device_info_list = None
        try:
            self._log(
                level='INFO',
                content=f"开始执行E2E用例（rounds格式，共{len(rounds)}轮）: {case_name}",
                task_id=task_id, test_case_id=test_case_id
            )

            self._handle_control(task_id)
            self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status='running')
            stop_event, pause_event = self._get_control_events(task_id)
            # 通过 ACL 仓储注册任务事件
            self._device_repo.register_task_events(
                task_id, stop_event.is_set() if stop_event else False,
                pause_event.is_set() if pause_event else True,
            )

            # ── 阶段一：循环前准备 ──
            device_info_list, result_id = self._prepare_rounds(
                task_id, tc_rel_id, data, case_config, algorithm_type,
                case_field_values, rounds, test_case_id
            )

            # ── 阶段二：多轮循环 ──
            all_round_results, rounds_data, execution_success, last_adjusted_ref_params = \
                self._run_rounds_loop(
                    task_id, tc_rel_id, data, case_config, case_name,
                    algorithm_type, test_case_id, rounds,
                    device_info_list, result_id, case_reference_params
                )

            if not all_round_results:
                error_msg = "所有轮次均未产生有效结果"
                self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status='failed', status='failed', error_message=error_msg)
                return False

            # ── 阶段三：循环后聚合 + 评估 ──
            success = self._finalize_rounds(
                task_id, tc_rel_id, data, case_config, case_name,
                algorithm_type, test_case_id, result_id,
                all_round_results, execution_success,
                case_reference_params, last_adjusted_ref_params,
                device_info_list
            )

            return success
        except Exception as e:
            import traceback
            error_msg = f"用例执行异常: {str(e)}"
            self._log(level='ERROR', content=f"用例 {case_name} 执行异常: {str(e)}\n{traceback.format_exc()}",
                      task_id=task_id, test_case_id=getattr(self, 'current_test_case_id', None))
            self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status='failed', status='failed', error_message=error_msg)
            return False
        finally:
            # ── 阶段四：设备驱动 teardown（与 initialize 对称）──
            if device_info_list:
                try:
                    self._device_manager.teardown_devices(
                        device_info_list, task_id, test_case_id=test_case_id
                    )
                except Exception as teardown_err:
                    self._log(
                        level='WARNING',
                        content=f"设备 teardown 异常（忽略）: {teardown_err}",
                        task_id=task_id, test_case_id=test_case_id
                    )
