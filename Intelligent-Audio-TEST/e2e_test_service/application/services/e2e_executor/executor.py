from shared.infrastructure.base_executor import BaseExecutor, TaskStopSignal
from shared.utils.status_constants import ExecutionStatus, TaskCaseStatus, EvaluationStatus
from shared.constants.ui_capture import UiCaptureSkipReason, UiCaptureStepStatus
from e2e_test_service.application.services.e2e_device_manager import E2EDeviceManager
from e2e_test_service.application.services.e2e_collector import E2ECollector
from e2e_test_service.application.services.e2e_aggregator import E2EAggregator
from e2e_test_service.application.services.e2e_executor.preparation_mixin import PreparationMixin
from e2e_test_service.application.services.e2e_executor.rounds_loop_mixin import RoundsLoopMixin
from e2e_test_service.application.services.e2e_executor.finalization_mixin import FinalizationMixin
# 跨服务调用：通过 ACL 仓储访问 device_service / playback_service / device_result_service
from e2e_test_service.infrastructure.acl import (
    AlgorithmAclRepositoryImpl,
    DeviceAclRepositoryImpl,
    DeviceResultAclRepositoryImpl,
    PlaybackAclRepositoryImpl,
    TaskDataAclRepositoryImpl,
)


class E2EExecutor(PreparationMixin, RoundsLoopMixin, FinalizationMixin, BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self._playback_timestamps = {}
        self._audio_local_paths = {}  # {audio_id: {target_rate: local_path, "original": local_path}}（准备阶段预下载+重采样）
        # INT-296：用例级 UI 抓取层降级标记（explicit_degrade 模式下由
        # E2EDeviceManager.initialize_devices 写入；None = 无降级）
        self._ui_capture_degraded = None
        self._ui_capture_degraded_note = None
        # 委托组件
        self._device_manager = E2EDeviceManager(self)
        self._collector = E2ECollector(self)
        self._aggregator = E2EAggregator(self)
        # ACL 仓储
        self._device_repo = DeviceAclRepositoryImpl()
        self._playback_repo = PlaybackAclRepositoryImpl()
        self._device_result_repo = DeviceResultAclRepositoryImpl()
        self._task_data_repo = TaskDataAclRepositoryImpl()

    def set_ui_capture_degraded(self, degraded, task_id=None, test_case_id=None):
        """记录用例级 UI 抓取层降级并构建轮次留痕结构（INT-296，仅 explicit_degrade 模式可达）

        Args:
            degraded: [{device_name, degrade_reason}] 列表（来自 device_service
                ui_capabilities 结构化透传）
        """
        self._ui_capture_degraded = list(degraded or [])
        reasons = sorted({d.get('degrade_reason') for d in self._ui_capture_degraded
                          if d.get('degrade_reason')})
        note = {
            'status': UiCaptureStepStatus.SKIPPED.value,
            'skip_reason': UiCaptureSkipReason.ENVIRONMENT_EXCLUDED.value,
        }
        if reasons:
            note['degrade_reason'] = reasons[0] if len(reasons) == 1 else reasons
        devices = [d.get('device_name') for d in self._ui_capture_degraded if d.get('device_name')]
        if devices:
            note['devices'] = devices
        self._ui_capture_degraded_note = note
        self._log(level='WARNING',
                  content=(f"UI 抓取层显式降级（环境排除）: reason={'|'.join(reasons) or 'unknown'}，"
                           f"用例内的 UI 抓取步骤将标记 skipped 并留痕；"
                           f"采集/放音/录屏/回传/评估/报告链不受影响"),
                  task_id=task_id, test_case_id=test_case_id)

    def reset_ui_capture_degraded(self):
        """用例开始前清空降级标记（防执行线程跨用例残留）"""
        self._ui_capture_degraded = None
        self._ui_capture_degraded_note = None

    def _get_result_mapper(self):
        """返回 DeviceResult ACL 仓储，供 ResultsMixin 使用"""
        return self._device_result_repo

    def _get_algorithm_acl(self):
        """返回 algorithm_service ACL 仓储，供 DbMixin 使用"""
        return AlgorithmAclRepositoryImpl

    def _get_task_data_acl(self):
        """返回 task_service ACL 仓储，供 DbMixin 使用"""
        return self._task_data_repo

    def _record_eval_submit_failure(self, message, task_id=None, test_case_id=None):
        """记录评估提交失败（INT-169）：不中止执行链，仅留痕供收口"""
        self._eval_submit_failures.append(message)
        self._log(level='ERROR', content=f"{message}（执行链不判失败，执行口径保持）",
                  task_id=task_id, test_case_id=test_case_id)

    def _finalize_eval_submit_failures(self, task_id, test_case_id, tc_rel_id=None):
        """评估提交失败终态收口（INT-169，对齐 INT-123 API 链口径）

        execution_status 不动（执行完成事实已由 process_results 落库），仅补
        evaluation_status=FAILED 并留痕原因，复合 status 由 task_service 按
        derive_task_case_status(completed, failed) 推导，保留
        「执行成功、评估失败」的事实边界，避免 TaskCase 永挂 evaluating。
        INT-604：tc_rel_id 多路由下按路由行精确命中。
        """
        failures = getattr(self, '_eval_submit_failures', None)
        if not failures:
            return
        error_msg = '；'.join(failures)
        try:
            self._task_data_repo.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                evaluation_status=EvaluationStatus.FAILED,
                error_message=error_msg,
                tc_rel_id=tc_rel_id,
            )
        except Exception as status_err:
            self._log(level='WARNING',
                      content=f"评估提交失败终态回写失败（忽略）: {status_err}",
                      task_id=task_id, test_case_id=test_case_id)

    def _close_failed_test_result(self, result_id, algorithm_type, total_rounds,
                                  rounds_data, error_message, task_id):
        """失败早退路径收口预创建的 TestResult 行（execution_status=FAILED）

        与 _finalize_rounds 的正常收口对称：失败路径不提交评估，但结果行
        必须离开 running，否则报告/查询侧该行永远停留 running（INT-158）。
        rounds_data 为 None（异常路径拿不到已累积轮次数据）时仅收口状态，
        避免用空轮次覆盖已写入的 algorithm_result。
        """
        if not result_id:
            return
        try:
            if rounds_data is not None:
                algo_result = {
                    'test_type': 'e2e',
                    'algorithm_type': algorithm_type,
                    'total_rounds': total_rounds,
                    'rounds': rounds_data,
                    'aggregated': {},
                }
                self._aggregator.update_test_result(
                    result_id=result_id, algo_result=algo_result,
                    execution_status=ExecutionStatus.FAILED,
                    error_message=error_message, task_id=task_id,
                )
            else:
                self._task_data_repo.update_test_result_status(result_id, ExecutionStatus.FAILED)
        except Exception as close_err:
            self._log(level='ERROR', content=f"收口失败轮 TestResult 异常: {close_err}", task_id=task_id)

    def execute_e2e_case(self, task_id, tc_rel_id, device_id=None):
        """执行E2E测试用例

        device_id：当前路由行绑定的被测设备；只准备/驱动该设备。
        """
        self._log(
            level='DEBUG',
            content=f"E2E用例执行方法开始: task_id={task_id}, tc_rel_id={tc_rel_id}, device_id={device_id}",
            task_id=task_id
        )

        if not task_id or not tc_rel_id:
            error_msg = "任务ID和测试用例关联ID不能为空"
            self._log(level='ERROR', content=f"E2E 用例执行失败: {error_msg}", task_id=task_id)
            if tc_rel_id:
                self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status=ExecutionStatus.FAILED, status=TaskCaseStatus.FAILED, error_message=error_msg)
            return False

        data_result = self._validate_and_get_data(task_id, tc_rel_id)
        if not data_result['success']:
            error_msg = data_result.get('error', '获取基础数据失败')
            self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status=ExecutionStatus.FAILED, status=TaskCaseStatus.FAILED, error_message=error_msg)
            return False

        data = data_result['data']
        return self._execute_e2e_with_rounds(task_id, tc_rel_id, data, device_id=device_id)

    def _execute_e2e_with_rounds(self, task_id, tc_rel_id, data, device_id=None):
        """新格式执行：支持多轮（rounds）的 E2E 执行"""
        case_name = data['case_name']
        case_config = data['case_config']
        case_reference_params = data.get('case_reference_params', [])
        test_case_id = data['test_case_id']
        algorithm_type = data.get('algorithm_type', 'translation')

        # case_fields 已由 _validate_and_get_data → _get_case_fields 查询并填入 data
        case_fields = data.get('case_fields', {})
        case_field_values = {key: data.get(key) for key in case_fields.keys()}

        self.current_case_field_values = case_field_values
        self.current_test_case_id = test_case_id
        self._thread_ctx.current_test_case_id = test_case_id

        rounds = case_config.get('rounds', [])

        # INT-296：用例开始前清空 UI 抓取层降级标记（executor 为单例，防跨用例残留）
        self.reset_ui_capture_degraded()

        device_info_list = None
        result_id = None
        # INT-169: 评估提交失败留痕（每用例重置），收尾时统一收口
        self._eval_submit_failures = []
        try:
            self._log(
                level='INFO',
                content=f"开始执行E2E用例（rounds格式，共{len(rounds)}轮）: {case_name}",
                task_id=task_id, test_case_id=test_case_id
            )

            self._handle_control(task_id)
            self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status=ExecutionStatus.RUNNING)
            stop_event, pause_event = self._get_control_events(task_id)
            # 通过 ACL 仓储注册任务事件
            self._device_repo.register_task_events(
                task_id, stop_event.is_set() if stop_event else False,
                pause_event.is_set() if pause_event else True,
            )

            # ── 阶段一：循环前准备 ──
            device_info_list, result_id = self._prepare_rounds(
                task_id, tc_rel_id, data, case_config, algorithm_type,
                case_field_values, rounds, test_case_id, device_id=device_id
            )

            # 启动全局背景噪声（跨轮次持续播放，在轮次循环前启动）
            # 桥接启停打点到播放账本，供 collect_results 注入 global_noise_timestamps
            bg_ts = self._playback_repo.start_background_noise(case_config, task_id)
            if bg_ts:
                book = self._playback_timestamps.setdefault(task_id, {})
                book['global_noise_audio_id'] = bg_ts.get('audio_id')
                book['global_noise_start_ms'] = bg_ts.get('start_ms')

            # ── 阶段二：多轮循环 ──
            all_round_results, rounds_data, execution_success, last_adjusted_ref_params = \
                self._run_rounds_loop(
                    task_id, tc_rel_id, data, case_config, case_name,
                    algorithm_type, test_case_id, rounds,
                    device_info_list, result_id, case_reference_params
                )

            if not execution_success:
                error_msg = "执行失败，跳过评估" if not all_round_results else "执行过程中部分轮次失败"
                self._close_failed_test_result(result_id, algorithm_type, len(rounds),
                                               rounds_data, error_msg, task_id)
                self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status=ExecutionStatus.FAILED, status=TaskCaseStatus.FAILED, error_message=error_msg)
                return False

            if not all_round_results:
                error_msg = "所有轮次均未产生有效结果"
                self._close_failed_test_result(result_id, algorithm_type, len(rounds),
                                               rounds_data, error_msg, task_id)
                self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status=ExecutionStatus.FAILED, status=TaskCaseStatus.FAILED, error_message=error_msg)
                return False

            # ── 阶段三：循环后聚合 + 评估 ──
            success = self._finalize_rounds(
                task_id, tc_rel_id, data, case_config, case_name,
                algorithm_type, test_case_id, result_id,
                all_round_results, execution_success,
                case_reference_params, last_adjusted_ref_params,
                device_info_list
            )

            # INT-169: 评估提交失败以 evaluation_status 终态收口，不动执行口径
            self._finalize_eval_submit_failures(task_id, test_case_id, tc_rel_id)

            return success
        except TaskStopSignal:
            # 任务停止信号：执行状态 STOPPED、最终状态按 task_service 停止分支
            # 同款推导（derive_task_case_status(stopped, stopped) → failed，
            # TaskCaseStatus 无 STOPPED 成员，2e919c18 引用的枚举成员不存在，
            # 此处必抛 AttributeError 走异常路径——INT-308 审计#6 修复）
            self._log(level='INFO', content=f"用例 {case_name} 因任务停止而中断",
                      task_id=task_id, test_case_id=test_case_id)
            self._update_tc_rel_status(tc_rel_id, task_id=task_id,
                                       execution_status=ExecutionStatus.STOPPED,
                                       error_message='任务被手动停止')
            return False
        except Exception as e:
            import traceback
            error_msg = f"用例执行异常: {str(e)}"
            self._log(level='ERROR', content=f"用例 {case_name} 执行异常: {str(e)}\n{traceback.format_exc()}",
                      task_id=task_id, test_case_id=getattr(self, 'current_test_case_id', None))
            self._close_failed_test_result(result_id, algorithm_type, len(rounds),
                                           None, error_msg, task_id)
            self._update_tc_rel_status(tc_rel_id, task_id=task_id, execution_status=ExecutionStatus.FAILED, status=TaskCaseStatus.FAILED, error_message=error_msg)
            return False
        finally:
            # 停止全局背景噪声（与 start_background_noise 对称）
            try:
                bg_end_ts = self._playback_repo.stop_background_noise(task_id)
                # 回写结束打点（stop 返回含 audio_id/start_ms/end_ms 的完整记录）
                if bg_end_ts:
                    book = self._playback_timestamps.setdefault(task_id, {})
                    book['global_noise_audio_id'] = bg_end_ts.get('audio_id')
                    book['global_noise_start_ms'] = bg_end_ts.get('start_ms')
                    book['global_noise_end_ms'] = bg_end_ts.get('end_ms')
            except Exception as bg_err:
                self._log(
                    level='WARNING',
                    content=f"停止全局背景噪声异常（忽略）: {bg_err}",
                    task_id=task_id, test_case_id=test_case_id,
                )
            # ── 阶段四：设备驱动 teardown（与 initialize 对称）──
            if device_info_list:
                try:
                    teardown_ok = self._device_manager.teardown_devices(
                        device_info_list, task_id, test_case_id=test_case_id
                    )
                    if not teardown_ok:
                        self._log(
                            level='WARNING',
                            content="设备 teardown 部分失败（忽略）",
                            task_id=task_id, test_case_id=test_case_id
                        )
                except Exception as teardown_err:
                    self._log(
                        level='WARNING',
                        content=f"设备 teardown 异常（忽略）: {teardown_err}",
                        task_id=task_id, test_case_id=test_case_id
                    )
