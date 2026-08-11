"""E2E 结果采集：原始结果收集、时间戳偏移计算

偏移计算委托给 domain/services/E2ECalculationService，
gRPC 采集委托给 infrastructure/acl/DeviceResultAclRepositoryImpl。
"""
from e2e_test_service.domain.services import E2ECalculationService
from e2e_test_service.infrastructure.acl import DeviceResultAclRepositoryImpl


class E2ECollector:
    """E2E 结果采集器"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    def collect_results(self, task_id, test_case_id, device_info_list, **kwargs):
        """采集设备原始结果，计算播放偏移，返回 all_results（可能含 adjusted_reference_params）"""
        # 通过 gRPC DeviceResultService.CollectResult 采集设备原始结果
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        extra_params = self._executor._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)

        playback_timestamps = self._executor._playback_timestamps.get(task_id)
        if playback_timestamps:
            audio_offsets = E2ECalculationService.calculate_actual_offset(playback_timestamps)
            case_ref_params = kwargs.get('case_reference_params')
            self._log(
                level='DEBUG',
                content=f"[_collect_results] audio_offsets count={len(audio_offsets) if audio_offsets else 0}, "
                        f"case_reference_params={'found' if case_ref_params else 'None'}",
                task_id=task_id
            )
            if audio_offsets:
                offset_values = [v['offset'] for v in audio_offsets.values()]
                if offset_values:
                    actual_offset = offset_values[0]
                    self._log(
                        level='INFO',
                        content=f"计算实际时间戳偏移: {actual_offset:.3f}s (共{len(audio_offsets)}个播放)",
                        task_id=task_id
                    )
                    extra_params['playback_time_offsets'] = audio_offsets
                    extra_params['reference_params'] = case_ref_params
                    # 传递毫秒级播放起止时间戳给设备驱动，供其自行统计时延
                    round_start_ms = playback_timestamps.get('current_round_start_ms')
                    round_end_ms = playback_timestamps.get('current_round_end_ms')
                    if round_start_ms is not None and round_end_ms is not None:
                        extra_params['playback_start_time_ms'] = round_start_ms
                        extra_params['playback_end_time_ms'] = round_end_ms
                        # 本轮每个音频的起止时间戳明细
                        playback_ts_list = playback_timestamps.get('audio_play_times', [])
                        if playback_ts_list:
                            extra_params['playback_timestamps_detail'] = [
                                {
                                    'audio_id': p.get('audio_id'),
                                    'play_order': p.get('play_order'),
                                    'start_ms': p.get('playback_start_time_ms'),
                                    'end_ms': p.get('playback_end_time_ms'),
                                }
                                for p in playback_ts_list
                            ]

        def log_callback(level, content, task_id, device_id):
            self._log(level=level, content=content, task_id=task_id, device_id=device_id)

        all_results = DeviceResultAclRepositoryImpl().collect_results(
            task_id, test_case_id, device_info_list, extra_params,
            **kwargs
        )

        adjusted_ref_params = None
        if all_results and isinstance(all_results, list):
            for res in all_results:
                if res.adjusted_reference_params is not None:
                    result_type = res.result_type or 'e2e'
                    if adjusted_ref_params is None:
                        adjusted_ref_params = {}
                    adjusted_ref_params[result_type] = res.adjusted_reference_params

        if adjusted_ref_params:
            self._log(
                level='DEBUG',
                content=f"[_collect_results] found adjusted_reference_params: {list(adjusted_ref_params.keys())}",
                task_id=task_id
            )

        self._log(
            level='DEBUG',
            content=f"[e2e_collector] before return: all_results id={id(all_results)}, "
                    f"raw_keys[0]={list((all_results[0].raw_results or {}).keys())[:10] if all_results else 'empty'}",
            task_id=task_id
        )

        result_to_return = all_results
        if adjusted_ref_params:
            result_to_return = (all_results, adjusted_ref_params)

        _first = result_to_return[0] if result_to_return else None
        _first_device = _first[0] if isinstance(_first, list) else _first
        self._log(
            level='DEBUG',
            content=f"[e2e_collector] returning: result_to_return id={id(result_to_return)}, "
                    f"raw_keys[0]={list((_first_device.raw_results or {}).keys())[:10] if _first_device else 'empty'}",
            task_id=task_id
        )

        return result_to_return
