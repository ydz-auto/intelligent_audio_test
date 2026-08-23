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

            # ── 阶段 1.5：启动全局背景噪声（跨所有轮次持续播放） ──
            # 必须在 _prepare_rounds 之后（设备已初始化）、_run_rounds_loop 之前启动；
            # play_round 检测到全局背景噪声存在时会跳过轮次级背景噪声
            bg_started = playback_orchestrator.start_background_noise(case_config, task_id)
            if not bg_started:
                self._log(level='WARNING', content='全局背景噪声启动失败，继续执行轮次（轮次级背景噪声仍可生效）',
                          task_id=task_id, test_case_id=test_case_id)

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
                case_reference_params, last_adjusted_ref_params,
                device_info_list, rounds_data
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
            # ── 阶段 3.5：停止全局背景噪声 ──
            # 必须在设备 teardown 之前停止，避免设备流已关闭后仍持有 stop_event
            try:
                playback_orchestrator.stop_background_noise(task_id)
            except Exception as bg_stop_err:
                self._log(
                    level='WARNING',
                    content=f"停止全局背景噪声异常（忽略）: {bg_stop_err}",
                    task_id=task_id, test_case_id=getattr(self, 'current_test_case_id', None)
                )

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
        device_driver_factory.register_task_devices(task_id, device_info_list)

        # 首轮自定义参数一并透传给 initialize（pcm_app、record_mode 等驱动级参数）
        from backend.utils.algorithm.case_parameter_extractor import _normalize_algorithm_params
        first_round_params = _normalize_algorithm_params(data.get('case_algorithm_params') or {})

        for info in device_info_list:
            if info.get("driver"):
                info["driver"].set_task_id(task_id)
                info["driver"].set_test_case_id(test_case_id)
                info["driver"].set_device_id(info["device_id"])

        self._device_manager.initialize_devices(
            device_info_list, task_id, test_case_id=test_case_id,
            algorithm_type=algorithm_type, round_algo_params=first_round_params
        )

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

    def _register_voiceprint(self, task_id, tc_rel_id, round_algo_params, test_case_id):
        """从本轮 algorithm_params 提取声纹配置并执行注册

        voiceprint 是单个对象 { audio_id, spl, playback_device_id, voiceprint_wait_time }
        存在即表示启用，不存在则未配置。
        兼容旧格式（5个拆分字段）。
        """
        vp_obj = round_algo_params.get('voiceprint')
        if vp_obj and isinstance(vp_obj, dict):
            voiceprint_config = {
                'enabled': True,
                'audio_id': vp_obj.get('audio_id'),
                'playback_device_id': vp_obj.get('playback_device_id'),
                'spl': vp_obj.get('spl', 70.0),
                'wait_time': vp_obj.get('voiceprint_wait_time', 5.0),
            }
        else:
            # 兼容旧格式（5个拆分字段）
            voiceprint_config = {
                'enabled': round_algo_params.get('voiceprint_enabled', False),
                'audio_id': round_algo_params.get('voiceprint_audio_id'),
                'playback_device_id': round_algo_params.get('voiceprint_playback_device_id'),
                'spl': round_algo_params.get('voiceprint_spl', 70.0),
                'wait_time': round_algo_params.get('voiceprint_wait_time', 5.0),
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

            round_number = round_config.get('round_number', round_idx + 1)
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
        """执行单轮：环境设置 → 声纹注册 → 预处理 → 播放 → 后处理 → 采集 → 评估，返回轮次结果 dict"""
        from backend.utils.algorithm.case_parameter_extractor import _normalize_algorithm_params
        round_algo_params = _normalize_algorithm_params(round_config.get('algorithm_params', []))

        env_states = self._device_manager.setup_env_devices_for_round(round_algo_params, task_id)
        self._register_voiceprint(task_id, tc_rel_id, round_algo_params, test_case_id)
        self._device_manager.pre_process_devices(
            device_info_list, task_id, test_case_id=test_case_id,
            extra_params={'round_number': round_idx,
                          'total_rounds': len(rounds),
                          **round_algo_params},
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

        # 收集播放时间戳（含毫秒级起止时间），供 post_process / collect_results 传递给设备驱动
        self._collect_playback_timestamps(task_id, play_result, case_config)

        # 构建含播放时间戳的 extra_params，供设备驱动 post_process / get_results 使用
        playback_ts = self._playback_timestamps.get(task_id, {})
        round_start_ms = playback_ts.get('current_round_start_ms')
        round_end_ms = playback_ts.get('current_round_end_ms')
        post_extra_params = {'round_number': round_idx,
                             'total_rounds': len(rounds),
                             **round_algo_params}
        if round_start_ms is not None and round_end_ms is not None:
            post_extra_params['playback_start_time_ms'] = round_start_ms
            post_extra_params['playback_end_time_ms'] = round_end_ms
            detail = playback_ts.get('audio_play_times', [])
            if detail:
                post_extra_params['playback_timestamps_detail'] = [
                    {
                        'audio_id': p.get('audio_id'),
                        'play_order': p.get('play_order'),
                        'start_ms': p.get('playback_start_time_ms'),
                        'end_ms': p.get('playback_end_time_ms'),
                    }
                    for p in detail
                ]

        self._device_manager.post_process_devices(
            device_info_list, task_id, test_case_id=test_case_id,
            extra_params=post_extra_params,
        )

        # 采集结果
        collect_result = self._collector.collect_results(
            task_id, test_case_id, device_info_list,
            algorithm_type=algorithm_type,
            case_reference_params=case_reference_params,
            round_algo_params=round_algo_params,
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
                round_idx, primary, tagged_results, rounds_data,
                round_algo_params
            )

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
                                     round_idx, primary, tagged_results, rounds_data,
                                     round_algo_params=None):
        """构建本轮 round_data，增量更新 TestResult，提交单轮评估，返回 round_data

        Args:
            rounds_data: 已执行轮次的 round_data 列表（累积），用于构建含全部轮次的 algo_result
            round_algo_params: 本轮算法参数（已扁平化为 dict）
        """
        ref_fields = self._build_ref_fields(round_algo_params or {})

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

        # primary 中已包含映射后的 target 字段（由 convert_results 写入），直接用 target 取值
        # 同时保留维度专属 key（target__dim_N），供评估阶段按维度取值
        mapped_output_fields = get_field_mapper().get_mapped_device_output_fields(algorithm_type)
        round_output = {}
        if isinstance(mapped_output_fields, list):
            for f in mapped_output_fields:
                target = f.get('code')
                dim_id = f.get('dimension_id')
                if dim_id is not None:
                    dim_key = f'{target}__dim_{dim_id}'
                    dim_val = primary.get(dim_key)
                    if dim_val is not None:
                        round_output[dim_key] = dim_val
                val = primary.get(target)
                if val is not None:
                    if target not in round_output or not round_output[target]:
                        round_output[target] = val
        else:
            for target, f in mapped_output_fields.items():
                dim_id = f.get('dimension_id') if isinstance(f, dict) else None
                if dim_id is not None:
                    dim_key = f'{target}__dim_{dim_id}'
                    dim_val = primary.get(dim_key)
                    if dim_val is not None:
                        round_output[dim_key] = dim_val
                val = primary.get(target)
                if val is not None:
                    if target not in round_output or not round_output[target]:
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
        # DEBUG: 记录单轮写入后的 record_file 状态
        self._log(
            level='DEBUG',
            content=f"[_build_and_submit_round_data] round_idx={round_idx}, round_output_keys={list(round_output.keys())}, record_file={round_output.get('record_file', '<MISSING>')}",
            task_id=task_id, test_case_id=test_case_id,
        )

        # 检查本轮 evaluation.enabled 开关，enabled 为 False 时跳过单轮评估
        _round_eval_enabled = True
        if case_config:
            _case_rounds = case_config.get('rounds', [])
            if _case_rounds and round_idx < len(_case_rounds):
                _round_eval = _case_rounds[round_idx].get('evaluation', {})
                if isinstance(_round_eval, dict) and _round_eval.get('enabled', True) is False:
                    _round_eval_enabled = False

        if _round_eval_enabled:
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
        round_start_ms = None
        round_end_ms = None
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
            start_ms = timeline.get('playback_start_time_ms')
            end_ms = timeline.get('playback_end_time_ms')
            if start_ms is not None and (round_start_ms is None or start_ms < round_start_ms):
                round_start_ms = start_ms
            if end_ms is not None and (round_end_ms is None or end_ms > round_end_ms):
                round_end_ms = end_ms
            self._playback_timestamps[task_id]['audio_play_times'].append({
                'audio_id': audio_id,
                'play_order': audio_config.get('play_order', 0),
                'actual_time': timeline.get('actual_play_time', time.time()),
                'actual_end_time': timeline.get('actual_end_time'),
                'playback_start_time_ms': start_ms,
                'playback_end_time_ms': end_ms,
                'actual_start_offset': timeline.get('start', 0),
                'is_overlap': bool(overlap_rate and overlap_rate > 0),
                'overlap_rate': overlap_rate,
                'overlap_time': overlap_time,
            })
        # 记录本轮播放起止时间戳（毫秒），供 collect_results 传递给设备驱动
        if round_start_ms is not None and round_end_ms is not None:
            self._playback_timestamps[task_id]['current_round_start_ms'] = round_start_ms
            self._playback_timestamps[task_id]['current_round_end_ms'] = round_end_ms

    # ──────────────────────────────────────────────────
    #  阶段三：循环后聚合 + 评估
    # ──────────────────────────────────────────────────

    def _finalize_rounds(self, task_id, tc_rel_id, data, case_config, case_name,
                         algorithm_type, test_case_id, result_id,
                         all_round_results, execution_success,
                         case_reference_params, last_adjusted_ref_params,
                         device_info_list=None, rounds_data=None):
        """构建最终 algo_result，提交整体评估，聚合维度分数，更新 TaskCase 状态

        若设备驱动覆写了 get_final_results()，则优先使用其返回的最终结果替代逐轮聚合。
        返回值会走与 get_results 相同的 collect_raw_results 包装 + convert_results 字段映射。
        """
        # 设备驱动的最终结果获取步骤（可选）
        if device_info_list:
            for info in device_info_list:
                driver = info.get('driver')
                if driver is None:
                    continue
                device_sn = info.get('device_sn') or info.get('device_id', '')
                try:
                    final_results = driver.get_final_results(
                        device_sn, task_id=task_id, test_case_id=test_case_id,
                        rounds_data=rounds_data or [],
                        all_round_results=all_round_results,
                        case_config=case_config or {},
                    )
                except Exception as e:
                    self._log(
                        level='WARNING',
                        content=f"get_final_results 异常(回退到逐轮聚合): {e}",
                        task_id=task_id, test_case_id=test_case_id,
                    )
                    final_results = False
                if final_results is not False:
                    self._log(
                        level='INFO',
                        content=f"使用驱动 get_final_results 返回的最终结果: device_sn={device_sn}, "
                                f"results_count={len(final_results) if isinstance(final_results, list) else 1}",
                        task_id=task_id, test_case_id=test_case_id,
                    )
                    # 走与单轮采集相同的包装链路：raw_results → 包装 → convert_results
                    from backend.services.device.device_result_collector import get_device_result_collector
                    import copy as _copy
                    base = {
                        'device_id': info.get('device_id'),
                        'device_name': info.get('device_name'),
                        'device_sn': device_sn,
                    }
                    raw_list = final_results if isinstance(final_results, list) else [final_results]
                    wrapped = []
                    for item in raw_list:
                        w = base.copy()
                        w['raw_results'] = _copy.deepcopy(item)
                        w['result_type'] = item.get('result_type', 'default') if isinstance(item, dict) else 'default'
                        wrapped.append(w)
                    all_round_results = get_device_result_collector().convert_results(wrapped, algorithm_type)
                    break

        # 构建最终 algo_result
        final_algo_result = self._aggregator.build_algorithm_result(task_id, all_round_results, case_config, algorithm_type)

        # 持久化 raw_results 到文件，供重新评估时重新映射字段
        from backend.utils.common.result_data_store import write_result_data_file
        import copy
        result_data_to_save = {
            'multi_round': True,
            'total_rounds': len(all_round_results),
            'raw_results_list': copy.deepcopy(all_round_results),
        }
        # 调整后的参考参数也一并存储
        if last_adjusted_ref_params:
            result_data_to_save['adjusted_reference_params'] = last_adjusted_ref_params
        device_sn = all_round_results[0].get('device_sn', '') if all_round_results else ''
        result_data_path = write_result_data_file(task_id, test_case_id, device_sn, result_data_to_save)

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
            result_data_path=result_data_path or None,
        )
        # DEBUG: 确认 finalize 写入的 record_file 和 result_data_path
        _final_out = final_algo_result.get('rounds', [{}])[0].get('output', {})
        self._log(
            level='DEBUG',
            content=f"[_finalize_rounds] result_id={result_id}, result_data_path={result_data_path!r}, output_keys={list(_final_out.keys())}, record_file={_final_out.get('record_file', '<MISSING>')!r}",
            task_id=task_id, test_case_id=test_case_id,
        )

        # 整体评估
        # 检查是否有评估维度（从 rounds[].evaluation.dimensions 读单轮维度，从 config.dimensions 读多轮维度）
        # 同时检查 evaluation.enabled 开关：enabled 为 False 时不提交评估
        _has_dims = False
        if case_config:
            rounds = case_config.get('rounds', [])
            if rounds and isinstance(rounds, list):
                for round_item in rounds:
                    if isinstance(round_item, dict):
                        evaluation = round_item.get('evaluation', {})
                        if isinstance(evaluation, dict):
                            if evaluation.get('enabled', True) is False:
                                continue
                            if evaluation.get('dimensions'):
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

        # 聚合各轮评估分数到 algo_result（仅当有评估维度时才执行）
        if _has_dims:
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



