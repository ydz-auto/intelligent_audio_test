import time

from e2e_test_service.domain.services import E2ECalculationService
from e2e_test_service.infrastructure.acl import (
    PlaybackAclRepositoryImpl,
    DeviceResultAclRepositoryImpl,
)
from shared.utils.dto_utils import dto_to_dict


class RoundsLoopMixin:
    """阶段二：多轮循环 —— 环境设置 → 预处理 → 播放 → 后处理 → 采集 → 评估"""

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
        """执行单轮：环境设置 → 预处理 → 播放 → 后处理 → 采集 → 评估，返回轮次结果 dict"""
        from shared.clients.grpc_clients import algo_normalize_algorithm_params
        round_algo_params = algo_normalize_algorithm_params(round_config.get('algorithm_params', []))

        env_states = self._device_manager.setup_env_devices_for_round(round_algo_params, task_id)
        self._device_manager.pre_process_devices(
            device_info_list, task_id, test_case_id=test_case_id,
            extra_params={**self.current_extra_params, 'round_number': round_idx},
        )

        play_result = PlaybackAclRepositoryImpl().play_round(
            round_config=round_config, task_id=task_id,
            case_config=case_config, test_case_id=test_case_id,
            round_number=round_number,
            audio_local_paths=self._audio_local_paths,
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
        self._log(level='DEBUG', content=f"[play_round] has audio_timelines={play_result.audio_timelines is not None if play_result else False}", task_id=task_id, test_case_id=test_case_id)
        self._collect_playback_timestamps(task_id, play_result, case_config)

        # 构建含播放时间戳的 extra_params，供设备驱动 post_process / get_results 使用
        playback_ts = self._playback_timestamps.get(task_id, {})
        round_start_ms = playback_ts.get('current_round_start_ms')
        round_end_ms = playback_ts.get('current_round_end_ms')
        post_extra_params = {**self.current_extra_params, 'round_number': round_idx}
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
            case_reference_params=case_reference_params
        )
        if isinstance(collect_result, tuple):
            round_results, adjusted_case_ref_params = collect_result
        else:
            round_results, adjusted_case_ref_params = collect_result, None

        tagged_results = round_results if isinstance(round_results, list) else [round_results]
        for r in tagged_results:
            r.round_number = round_idx

        # 字段映射：将 raw_results 映射为 target 字段（如 output_text、question_text 等）
        # 通过 ACL 仓储转换结果字段
        tagged_results = DeviceResultAclRepositoryImpl().convert_results(tagged_results, algorithm_type)
        # 转换 DTO 为 dict 供下游处理
        tagged_results = [dto_to_dict(r) for r in tagged_results]

        # 轮次内评估
        primary = tagged_results[0] if tagged_results else {}
        round_data = None
        round_success = True

        if primary:
            round_success = primary.get('success')
            if round_success is None:
                raw_results = primary.get('raw_results', {})
                round_success = raw_results.get('success', False)
            round_data = self._build_and_submit_round_data(
                task_id, tc_rel_id, data, case_config, case_name,
                algorithm_type, test_case_id, rounds,
                result_id, case_reference_params,
                round_idx, primary, tagged_results, rounds_data
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
                                     round_idx, primary, tagged_results, rounds_data):
        """构建本轮 round_data，增量更新 TestResult，提交单轮评估，返回 round_data

        Args:
            rounds_data: 已执行轮次的 round_data 列表（累积），用于构建含全部轮次的 algo_result
        """
        ref_fields = E2ECalculationService.build_ref_fields(self.current_extra_params)

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

        round_data = E2ECalculationService.build_round_data(
            primary, round_idx, case_config, algorithm_type,
            audio_name, audio_path,
        )

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

    def _collect_playback_timestamps(self, task_id, play_result, case_config):
        """从 play_result 的 audio_timelines 收集播放时间戳"""
        from shared.clients.grpc_clients import algo_normalize_algorithm_params
        algo_params = algo_normalize_algorithm_params(case_config.get('algorithm_params', {})) if case_config else {}
        try:
            overlap_rate = max(0.0, min(1.0, float(algo_params.get('overlap_rate', 0)))) if algo_params else 0
        except (ValueError, TypeError):
            overlap_rate = 0
        try:
            overlap_time = max(0.0, float(algo_params.get('overlap_time', 0))) if algo_params else 0
        except (ValueError, TypeError):
            overlap_time = 0

        audio_timelines = (play_result.audio_timelines or []) if play_result else []
        self._log(level='DEBUG', content=f"[collect_ts] audio_timelines count={len(audio_timelines)}, first_keys={list(audio_timelines[0].keys()) if audio_timelines else 'empty'}", task_id=task_id)
        round_start_ms = None
        round_end_ms = None
        for timeline in audio_timelines:
            if timeline.get('is_noise', False):
                continue
            audio_config = timeline.get('config', {})
            audio_obj = timeline.get('audio', {})
            # gRPC JSON 序列化后 audio 变成字符串，优先从 config 取 audio_id
            audio_id = audio_config.get('audio_id') or getattr(audio_obj, 'id', None)
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
