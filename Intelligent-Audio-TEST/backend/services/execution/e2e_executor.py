import json
import time
import os
from backend.services.audio.playback_orchestrator import playback_orchestrator
from backend.utils.device_driver import device_driver_factory, register_task_events
from backend.utils.algorithm.field_mapper import get_field_mapper
from backend.services.execution.base_executor import BaseExecutor
from backend.services.execution.e2e_device_manager import E2EDeviceManager
from backend.services.execution.e2e_collector import E2ECollector
from backend.services.execution.e2e_aggregator import E2EAggregator

E2E_RESULT_COLLECTION_WAIT_TIME = float(os.environ.get('E2E_RESULT_COLLECTION_WAIT_TIME', '3.0'))


class E2EExecutor(BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self._playback_timestamps = {}
        # 委托组件
        self._device_manager = E2EDeviceManager(self)
        self._collector = E2ECollector(self)
        self._aggregator = E2EAggregator(self)

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
                self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
            return False

        data_result = self._validate_and_get_data(task_id, tc_rel_id)
        if not data_result['success']:
            error_msg = data_result.get('error', '获取基础数据失败')
            self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
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
        field_mapper = get_field_mapper()
        case_fields = field_mapper.get_case_fields(algorithm_type)
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
            self._update_tc_rel_status(tc_rel_id, execution_status='running')
            stop_event, pause_event = self._get_control_events(task_id)
            register_task_events(task_id, stop_event, pause_event)

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
                self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
                return False

            # ── 阶段三：循环后聚合 + 评估 ──
            success = self._finalize_rounds(
                task_id, tc_rel_id, data, case_config, case_name,
                algorithm_type, test_case_id, result_id,
                all_round_results, execution_success,
                case_reference_params, last_adjusted_ref_params
            )

            return success
        except Exception as e:
            import traceback
            error_msg = f"用例执行异常: {str(e)}"
            self._log(level='ERROR', content=f"用例 {case_name} 执行异常: {str(e)}\n{traceback.format_exc()}",
                      task_id=task_id, test_case_id=getattr(self, 'current_test_case_id', None))
            self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
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

    # ──────────────────────────────────────────────────
    #  阶段一：循环前准备
    # ──────────────────────────────────────────────────

    def _prepare_rounds(self, task_id, tc_rel_id, data, case_config, algorithm_type,
                        case_field_values, rounds, test_case_id):
        """设备准备 + 声纹注册 + 预创建 TestResult，返回 (device_info_list, result_id)"""
        # 设备准备
        device_result = self._device_manager.get_device_info(task_id, case_config)
        if not device_result['success']:
            error_msg = f"设备信息获取失败: {device_result.get('error')}"
            self._log(level='ERROR', content=error_msg, task_id=task_id, test_case_id=test_case_id)
            self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
            raise RuntimeError(error_msg)

        device_info_list = device_result['data']['device_info_list']
        self.current_extra_params = self._execute_extra_params(algorithm_type, case_field_values, include_format_strings=True)
        device_driver_factory.register_task_devices(task_id, device_info_list)

        for info in device_info_list:
            if info.get("driver"):
                info["driver"].set_task_id(task_id)
                info["driver"].set_test_case_id(test_case_id)
                info["driver"].set_device_id(info["device_id"])

        self._device_manager.initialize_devices(device_info_list, task_id, test_case_id=test_case_id, algorithm_type=algorithm_type)

        # 声纹注册
        self._register_voiceprint(task_id, tc_rel_id, rounds, test_case_id)

        # 预创建 TestResult
        first_device_id = device_info_list[0].get('device_id') if device_info_list else None
        result_id = self._save_result(
            task_id=task_id,
            test_case_id=test_case_id,
            result_data={'multi_round': True, 'total_rounds': len(rounds)},
            algo_result={'test_type': 'e2e', 'algorithm_type': algorithm_type, 'total_rounds': len(rounds), 'rounds': [], 'aggregated': {}},
            algorithm_type=algorithm_type,
            device_id=first_device_id,
            api_id=None,
            execution_status='running',
            response_time=0,
            error_message=None
        )
        self._log(
            level='DEBUG',
            content=f"预先创建多轮 TestResult: result_id={result_id}, total_rounds={len(rounds)}",
            task_id=task_id, test_case_id=test_case_id,
        )

        return device_info_list, result_id

    def _register_voiceprint(self, task_id, tc_rel_id, rounds, test_case_id):
        """从首轮 algorithmParams 提取声纹配置并执行注册"""
        from backend.utils.algorithm.case_parameter_extractor import _normalize_algorithm_params

        first_round_algo_params = {}
        if rounds and isinstance(rounds[0], dict):
            first_round_algo_params = _normalize_algorithm_params(rounds[0].get('algorithmParams', []))

        voiceprint_config = {
            'enabled': first_round_algo_params.get('voiceprintEnabled', False),
            'audio_id': first_round_algo_params.get('voiceprintAudioId'),
            'playback_device_id': first_round_algo_params.get('voiceprintPlaybackDeviceId'),
            'spl': first_round_algo_params.get('voiceprintSpl', 70.0),
            'wait_time': first_round_algo_params.get('voiceprintWaitTime', 5.0),
        }
        if voiceprint_config.get('enabled'):
            if not playback_orchestrator.play_voiceprint(voiceprint_config, task_id):
                self._log(level='ERROR', content='声纹注册失败，中止测试', task_id=task_id, test_case_id=test_case_id)
                self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message='声纹注册失败')
                raise RuntimeError('声纹注册失败')

    # ──────────────────────────────────────────────────
    #  阶段二：多轮循环
    # ──────────────────────────────────────────────────

    def _run_rounds_loop(self, task_id, tc_rel_id, data, case_config, case_name,
                         algorithm_type, test_case_id, rounds,
                         device_info_list, result_id, case_reference_params):
        """执行多轮循环，返回 (all_round_results, rounds_data, execution_success, last_adjusted_ref_params)"""
        all_round_results = []
        last_adjusted_ref_params = None
        execution_success = True
        rounds_data = []

        for round_idx, round_config in enumerate(rounds):
            if not isinstance(round_config, dict):
                continue

            round_number = round_config.get('roundNumber', round_idx + 1)
            self.execution_engine.update_case_round_progress(task_id, tc_rel_id, round_idx, len(rounds))
            self._log(level='INFO', content=f"执行第 {round_number} 轮", task_id=task_id, test_case_id=test_case_id)

            round_result = self._execute_single_round(
                task_id, tc_rel_id, data, case_config, case_name,
                algorithm_type, test_case_id, rounds,
                device_info_list, result_id, case_reference_params,
                round_idx, round_config, round_number, rounds_data
            )

            # 累积结果
            tagged_results = round_result.get('tagged_results', [])
            all_round_results.extend(tagged_results)
            if round_result.get('round_data'):
                rounds_data.append(round_result['round_data'])
            if not round_result.get('success', True):
                execution_success = False
            if round_result.get('adjusted_ref_params'):
                last_adjusted_ref_params = round_result['adjusted_ref_params']

        return all_round_results, rounds_data, execution_success, last_adjusted_ref_params

    def _execute_single_round(self, task_id, tc_rel_id, data, case_config, case_name,
                              algorithm_type, test_case_id, rounds,
                              device_info_list, result_id, case_reference_params,
                              round_idx, round_config, round_number, rounds_data):
        """执行单轮：环境设置 → 预处理 → 播放 → 后处理 → 采集 → 评估，返回轮次结果 dict"""
        from backend.utils.algorithm.case_parameter_extractor import _normalize_algorithm_params
        round_algo_params = _normalize_algorithm_params(round_config.get('algorithmParams', []))

        env_states = self._device_manager.setup_env_devices_for_round(round_algo_params, task_id)
        self._device_manager.pre_process_devices(
            device_info_list, task_id, test_case_id=test_case_id,
            extra_params={**self.current_extra_params, 'round_number': round_idx},
        )

        play_result = playback_orchestrator.play_round(
            round_config=round_config, task_id=task_id,
            case_config=case_config, test_case_id=test_case_id,
            round_number=round_number,
        )
        if not play_result:
            self._log(level='WARNING', content=f"第 {round_number} 轮音频播放失败，跳过",
                      task_id=task_id, test_case_id=test_case_id)
            self._device_manager.teardown_env_devices_for_round(env_states, task_id)
            return {
                'success': False,
                'tagged_results': [],
                'round_data': {'round': round_idx, 'input': {}, 'output': {}, 'latency': None, 'evaluation': {}},
                'adjusted_ref_params': None,
            }

        self._device_manager.post_process_devices(device_info_list, task_id, test_case_id=test_case_id)
        time.sleep(E2E_RESULT_COLLECTION_WAIT_TIME)

        # 采集结果
        collect_result = self._collector.collect_results(
            task_id, test_case_id, device_info_list,
            algorithm_type=algorithm_type,
            case_reference_params=case_reference_params
        )
        if isinstance(collect_result, tuple):
            round_results, adjusted_case_ref_params = collect_result
        else:
            round_results, adjusted_case_ref_params = collect_result, None

        tagged_results = round_results if isinstance(round_results, list) else [round_results]
        for r in tagged_results:
            r['round_number'] = round_idx

        # 字段映射：将 raw_results 映射为 target 字段（如 output_text、question_text 等）
        from backend.services.device.device_result_collector import get_device_result_collector
        tagged_results = get_device_result_collector().convert_results(tagged_results, algorithm_type)

        # 轮次内评估
        primary = tagged_results[0] if tagged_results else {}
        round_data = None
        round_success = True

        if primary:
            round_success = primary.get('success', primary.get('raw_results', {}).get('success', False))
            round_data = self._build_and_submit_round_data(
                task_id, tc_rel_id, data, case_config, case_name,
                algorithm_type, test_case_id, rounds,
                result_id, case_reference_params,
                round_idx, primary, tagged_results, rounds_data
            )

        # 收集播放时间戳
        self._collect_playback_timestamps(task_id, play_result, case_config)

        self._device_manager.teardown_env_devices_for_round(env_states, task_id)

        return {
            'success': round_success,
            'tagged_results': tagged_results,
            'round_data': round_data,
            'adjusted_ref_params': adjusted_case_ref_params,
        }

    def _build_and_submit_round_data(self, task_id, tc_rel_id, data, case_config, case_name,
                                     algorithm_type, test_case_id, rounds,
                                     result_id, case_reference_params,
                                     round_idx, primary, tagged_results, rounds_data):
        """构建本轮 round_data，增量更新 TestResult，提交单轮评估，返回 round_data

        Args:
            rounds_data: 已执行轮次的 round_data 列表（累积），用于构建含全部轮次的 algo_result
        """
        ref_fields = self._build_ref_fields(self.current_extra_params)

        self._aggregator.log_case_result(
            task_id, case_name, primary, ref_fields,
            algorithm_type=algorithm_type, test_case_id=test_case_id
        )

        case_rounds = case_config.get('rounds', [])
        round_cfg = case_rounds[round_idx] if round_idx < len(case_rounds) else {}
        audios = round_cfg.get('audios', [])
        first_audio = audios[0] if audios else {}
        audio_name = first_audio.get('audio_name') or first_audio.get('name', '')
        audio_path = first_audio.get('audio_path') or first_audio.get('path', '')

        # 用 source_param 从 primary 取值，用 target_param 作为 output 的 key
        mapped_output_fields = get_field_mapper().get_mapped_device_output_fields(algorithm_type)
        round_output = {}
        if isinstance(mapped_output_fields, list):
            for f in mapped_output_fields:
                target = f.get('code')
                src = f.get('source_param', target)
                val = primary.get(src)
                if val is not None:
                    round_output[target] = val
        else:
            for target, f in mapped_output_fields.items():
                src = f.get('source_param', target)
                val = primary.get(src)
                if val is not None:
                    round_output[target] = val

        latency = primary.get('response_time') or primary.get('latency')

        round_data = {
            'round': round_idx,
            'input': {'audio_name': audio_name, 'audio_path': audio_path, 'type': 'audio'},
            'output': round_output,
            'latency': latency,
            'evaluation': {},
        }

        # 构建含已执行轮次 + 本轮的 algo_result，使 _extract_round_eval_data(rounds[round_idx]) 能正确索引
        accumulated_rounds = list(rounds_data) + [round_data]
        current_algo_result = {
            'test_type': 'e2e',
            'algorithm_type': algorithm_type,
            'total_rounds': len(rounds),
            'rounds': accumulated_rounds,
            'aggregated': {},
        }
        self._aggregator.update_test_result(
            result_id=result_id, algo_result=current_algo_result,
            execution_status='running', task_id=task_id,
        )

        self._evaluate_result(
            task_id=task_id, result_id=result_id, test_case_id=test_case_id,
            algo_result=current_algo_result, case_config=case_config or {},
            case_reference_params=case_reference_params,
            algorithm_type=algorithm_type, test_type='e2e',
            case_algorithm_params=data.get('case_algorithm_params'),
            round_number=round_idx,
            reference_params_col=data.get('reference_params_col')
        )

        return round_data

    @staticmethod
    def _build_ref_fields(extra_params):
        """从 extra_params 提取 ref_fields"""
        def extract_value(val):
            if isinstance(val, dict) and 'value' in val:
                return val.get('value', '')
            return val

        ref_fields = {}
        for field_key, field_value in extra_params.items():
            if field_value:
                ref_fields[field_key] = extract_value(field_value)
        return ref_fields

    def _collect_playback_timestamps(self, task_id, play_result, case_config):
        """从 play_result 的 audio_timelines 收集播放时间戳"""
        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        overlap_rate = CaseParameterExtractor.get_overlap_rate(case_config) if case_config else 0
        overlap_time = CaseParameterExtractor.get_overlap_time(case_config) if case_config else 0

        audio_timelines = play_result.get('audio_timelines', []) if play_result else []
        for timeline in audio_timelines:
            if timeline.get('is_noise', False):
                continue
            audio_config = timeline.get('config', {})
            audio_obj = timeline.get('audio', {})
            audio_id = getattr(audio_obj, 'id', None)
            if not audio_id:
                continue

            if task_id not in self._playback_timestamps:
                self._playback_timestamps[task_id] = {
                    'record_start_time': time.time(),
                    'audio_play_times': [],
                    'theory_offsets': {},
                }
            self._playback_timestamps[task_id]['audio_play_times'].append({
                'audio_id': audio_id,
                'play_order': audio_config.get('play_order', 0),
                'actual_time': timeline.get('actual_play_time', time.time()),
                'actual_start_offset': timeline.get('start', 0),
                'is_overlap': bool(overlap_rate and overlap_rate > 0),
                'overlap_rate': overlap_rate,
                'overlap_time': overlap_time,
            })

    # ──────────────────────────────────────────────────
    #  阶段三：循环后聚合 + 评估
    # ──────────────────────────────────────────────────

    def _finalize_rounds(self, task_id, tc_rel_id, data, case_config, case_name,
                         algorithm_type, test_case_id, result_id,
                         all_round_results, execution_success,
                         case_reference_params, last_adjusted_ref_params):
        """构建最终 algo_result，提交整体评估，聚合维度分数，更新 TaskCase 状态"""
        # 构建最终 algo_result
        final_algo_result = self._aggregator.build_algorithm_result(task_id, all_round_results, case_config, algorithm_type)

        latency_values = []
        for r in all_round_results:
            lat = r.get('response_time') or r.get('latency')
            if lat is not None:
                try:
                    latency_values.append(float(lat))
                except (ValueError, TypeError):
                    pass
        avg_response_time = round(sum(latency_values) / len(latency_values), 4) if latency_values else 0

        self._aggregator.update_test_result(
            result_id=result_id, algo_result=final_algo_result,
            execution_status='completed' if execution_success else 'failed',
            response_time=avg_response_time,
            error_message=None if execution_success else "多轮测试存在失败轮次",
            task_id=task_id,
        )

        # 整体评估
        # 检查是否有评估维度（从 rounds[].evaluation.dimensions 读单轮维度，从 config.dimensions 读多轮维度）
        _has_dims = False
        if case_config:
            rounds = case_config.get('rounds', [])
            if rounds and isinstance(rounds, list):
                for round_item in rounds:
                    if isinstance(round_item, dict):
                        evaluation = round_item.get('evaluation', {})
                        if isinstance(evaluation, dict) and evaluation.get('dimensions'):
                            _has_dims = True
                            break
            if not _has_dims and case_config.get('dimensions'):
                _has_dims = True

        if execution_success and _has_dims:
            _dims_log = json.dumps(
                case_config.get('rounds', [{}])[0].get('evaluation', {}).get('dimensions', []),
                ensure_ascii=False
            )[:200] if case_config.get('rounds') else json.dumps(case_config.get('dimensions', []), ensure_ascii=False)[:200]
            self._log(
                level='INFO',
                content=f"提交整体评估: result_id={result_id}, dimensions={_dims_log}",
                task_id=task_id, test_case_id=test_case_id,
            )
            self._evaluate_result(
                task_id=task_id, result_id=result_id, test_case_id=test_case_id,
                algo_result=final_algo_result, case_config=case_config or {},
                case_reference_params=case_reference_params,
                algorithm_type=algorithm_type, test_type='e2e',
                case_algorithm_params=data.get('case_algorithm_params'),
                round_number=None,
                reference_params_col=data.get('reference_params_col')
            )

        # 聚合各轮评估分数到 algo_result
        self._aggregator.update_algorithm_result_evaluation(task_id, result_id)

        # 更新 TaskCase 状态
        success = self._aggregator.process_results(
            task_id, case_name, tc_rel_id, test_case_id, all_round_results, case_config,
            case_reference_params=case_reference_params,
            case_algorithm_params=data.get('case_algorithm_params'),
            algorithm_type=algorithm_type,
            adjusted_case_reference_params=last_adjusted_ref_params,
            precreated_result_id=result_id,
            precomputed_execution_success=execution_success
        )

        return success

    def _process_results_base(self, **kwargs):
        """委托到 BaseExecutor._process_results，供 E2EAggregator 调用"""
        return super()._process_results(**kwargs)



