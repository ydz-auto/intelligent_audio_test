import threading
import copy
import json
from backend.algorithm.field_mapper import get_field_mapper
from backend.utils.log_handler import log_not_emit

MAX_ALIGNMENT_OFFSET = 30.0
MIN_OVERLAP_THRESHOLD = 0.5
MAX_CANDIDATE_PAIRS = 100

class DeviceResultCollector:
    """设备结果采集器基类"""

    def __init__(self):
        self.field_mapper = get_field_mapper()

    def collect_raw_results(self, task_id, device_info_list, extra_params, log_callback=None, **kwargs):
        """采集原始结果

        Args:
            task_id: 任务ID
            device_info_list: 设备信息列表
            extra_params: 额外参数
            log_callback: 日志回调函数 fn(level, content, task_id, device_id)
            **kwargs: 额外参数，包含 case_name, case_id, task_id, task_name 等

        Returns:
            list: 原始结果列表
        """
        playback_time_offsets = extra_params.get('playback_time_offsets', {})
        reference_params = extra_params.get('reference_params')

        log_not_emit('DEBUG', 'device_collector', f'[collect_raw_results] playback_time_offsets={bool(playback_time_offsets)}, reference_params={bool(reference_params)}', category='engine')

        all_results = []

        for idx, info in enumerate(device_info_list):
            res = {
                'device_id': info["device_id"],
                'device_name': info["device_name"],
            }
            try:
                if info["driver"]:
                    merged_params = {**extra_params, 'task_id': task_id, **kwargs}
                    raw_results = info["driver"].get_results(
                        info.get("device_connect_id") or info["device_id"],
                        **merged_params
                    )

                    if isinstance(raw_results, list):
                        log_not_emit('DEBUG', 'device_collector', f'raw_results is list, length={len(raw_results)}', category='engine')
                        import copy
                        for result_idx, result_item in enumerate(raw_results):
                            log_not_emit('DEBUG', 'device_collector', f'result_item[{result_idx}] id: {id(result_item)}, keys: {list(result_item.keys())[:10]}', category='engine')
                            log_not_emit('DEBUG', 'device_collector', f'result_item[{result_idx}] str[:200]: {str(result_item)[:200]}', category='engine')
                            item_res = res.copy()
                            copied_item = copy.deepcopy(result_item)
                            log_not_emit('DEBUG', 'device_collector', f'copied_item[{result_idx}] id: {id(copied_item)}, keys: {list(copied_item.keys())[:10]}', category='engine')
                            item_res['raw_results'] = copied_item
                            log_not_emit('DEBUG', 'device_collector', f'item_res[{result_idx}][raw_results] id: {id(item_res["raw_results"])}, keys: {list(item_res["raw_results"].keys())[:10]}', category='engine')
                            item_res['result_type'] = result_item.get('result_type', 'default')
                            log_not_emit('DEBUG', 'device_collector', f'before append item_res[{result_idx}] id: {id(item_res)}, raw_results id: {id(item_res["raw_results"])}', category='engine')

                            alignment_result = self._calculate_effective_offset_for_single_result(
                                result_item, reference_params, playback_time_offsets
                            )
                            item_res['adjusted_reference_params'] = alignment_result.get('adjusted_params')
                            item_res['alignment_info'] = alignment_result.get('alignment_info')

                            all_results.append(item_res)
                            log_not_emit('DEBUG', 'device_collector', f'after append all_results[{result_idx}] raw_results id: {id(all_results[-1]["raw_results"])}, keys: {list(all_results[-1]["raw_results"].keys())[:5]}', category='engine')
                        continue

                    res['raw_results'] = raw_results or {}
                    res['result_type'] = 'default'

                    alignment_result = self._calculate_effective_offset_for_single_result(
                        raw_results, reference_params, playback_time_offsets
                    )
                    res['adjusted_reference_params'] = alignment_result.get('adjusted_params')
                    res['alignment_info'] = alignment_result.get('alignment_info')

            except Exception as e:
                if log_callback:
                    log_callback('ERROR', f"采集结果失败: {str(e)}", task_id, info["device_id"])
            all_results.append(res)

        log_not_emit('DEBUG', 'device_collector', f'FINAL before return: all_results id={id(all_results)}, count={len(all_results)}', category='engine')

        import copy
        return copy.deepcopy(all_results)

    def _calculate_effective_offset_for_single_result(self, raw_results, reference_params, playback_time_offsets):
        """为单个设备结果计算 effective_offset 并调整参考参数

        每个设备分别计算 offset，因为不同设备可能有不同的 VAD 处理

        采用混合对齐策略：
        1. 优先使用最大重叠对齐（处理丢句/多句场景）
        2. 如果片段不足或重叠太低，回退到首个时间戳对齐

        Args:
            raw_results: 单个设备的原始结果
            reference_params: 参考参数列表
            playback_time_offsets: 系统测量的播放时间偏移

        Returns:
            dict: {
                'adjusted_params': 调整后的参考参数列表,
                'alignment_info': {
                    'method': 'max_overlap' | 'first_timestamp' | 'fallback' | 'none',
                    'offset': float,
                    'max_overlap': float (仅max_overlap方法),
                    'device_segment_count': int,
                    'ref_segment_count': int,
                    'device_first_ts': float,
                    'ref_first_ts': float
                }
            }
        """
        alignment_info = {
            'method': 'none',
            'offset': 0.0,
            'device_segment_count': 0,
            'ref_segment_count': 0,
            'device_first_ts': None,
            'ref_first_ts': None
        }

        if not reference_params:
            log_not_emit('WARNING', 'device_collector', '[_calculate_effective_offset_for_single_result] reference_params is empty', category='engine')
            return {'adjusted_params': None, 'alignment_info': alignment_info}

        device_segments = self._extract_segments_from_result(raw_results)
        ref_segments = self._extract_segments_from_reference(reference_params)

        alignment_info['device_segment_count'] = len(device_segments)
        alignment_info['ref_segment_count'] = len(ref_segments)

        use_max_overlap = (
            device_segments and 
            ref_segments and 
            len(device_segments) >= 2 and 
            len(ref_segments) >= 2
        )

        if use_max_overlap:
            best_offset, max_overlap = self._calculate_offset_by_max_overlap(
                device_segments, ref_segments
            )

            alignment_info['method'] = 'max_overlap'
            alignment_info['offset'] = best_offset
            alignment_info['max_overlap'] = max_overlap

            log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] ===== MAX OVERLAP ALIGNMENT =====', category='engine')
            log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] 设备片段数: {len(device_segments)}, 参考片段数: {len(ref_segments)}', category='engine')
            log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] 最优偏移量: {best_offset:.3f}s, 最大重叠时间: {max_overlap:.3f}s', category='engine')

            if max_overlap >= MIN_OVERLAP_THRESHOLD:
                log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] 使用最大重叠对齐结果', category='engine')
                log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] =================================', category='engine')

                if abs(best_offset) < 0.001:
                    alignment_info['method'] = 'max_overlap_no_adjustment'
                    return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

                adjusted = self._apply_single_offset(reference_params, best_offset)
                return {'adjusted_params': adjusted, 'alignment_info': alignment_info}
            else:
                log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] 重叠时间 {max_overlap:.3f}s < 阈值 {MIN_OVERLAP_THRESHOLD}s, 回退到首个时间戳对齐', category='engine')

        device_first_ts = self._get_device_first_timestamp_from_result(raw_results)
        alignment_info['device_first_ts'] = device_first_ts

        if device_first_ts is None:
            log_not_emit('WARNING', 'device_collector', '[_calculate_effective_offset_for_single_result] Cannot get device first timestamp, fallback to playback_time_offsets', category='engine')
            alignment_info['method'] = 'fallback'
            fallback_result = self._apply_fallback_offset(reference_params, playback_time_offsets)
            return {'adjusted_params': fallback_result, 'alignment_info': alignment_info}

        ref_first_ts = self._get_reference_first_timestamp(reference_params)
        alignment_info['ref_first_ts'] = ref_first_ts

        if ref_first_ts is None:
            log_not_emit('WARNING', 'device_collector', '[_calculate_effective_offset_for_single_result] Cannot get reference first timestamp', category='engine')
            return {'adjusted_params': None, 'alignment_info': alignment_info}

        effective_offset = device_first_ts - ref_first_ts
        alignment_info['method'] = 'first_timestamp'
        alignment_info['offset'] = effective_offset

        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] ===== FIRST TIMESTAMP ALIGNMENT =====', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] 参考首个时间戳 (ref_first_ts): {ref_first_ts:.3f}s', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] 设备首个时间戳 (device_first_ts): {device_first_ts:.3f}s', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] 有效偏移量 (effective_offset): {effective_offset:.3f}s', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] ======================================', category='engine')

        if abs(effective_offset) < 0.001:
            log_not_emit('INFO', 'device_collector', '[_calculate_effective_offset_for_single_result] effective_offset ~= 0, no adjustment needed', category='engine')
            alignment_info['method'] = 'first_timestamp_no_adjustment'
            return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

        adjusted = self._apply_single_offset(reference_params, effective_offset)
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] Adjustment applied', category='engine')
        return {'adjusted_params': adjusted, 'alignment_info': alignment_info}

    def _calculate_effective_offset_and_adjust(self, all_results, reference_params, playback_time_offsets):
        """根据设备实际返回的首个时间戳计算 effective_offset 并调整参考参数

        核心逻辑：
        1. 从设备 raw_results 中提取 rttm/stm 首个时间戳（设备时间戳可能因 VAD 去除静音而变小）
        2. 从参考参数中提取参考首个时间戳
        3. 计算 effective_offset = 设备首个时间戳 - 参考首个时间戳
        4. 用 effective_offset 调整参考参数

        Args:
            all_results: 设备结果列表
            reference_params: 参考参数列表
            playback_time_offsets: 系统测量的播放时间偏移

        Returns:
            调整后的参考参数列表
        """
        if not reference_params:
            log_not_emit('WARNING', 'device_collector', '[_calculate_effective_offset_and_adjust] reference_params is empty', category='engine')
            return None

        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_and_adjust] START: reference_params count={len(reference_params)}, all_results count={len(all_results)}', category='engine')

        device_first_timestamp = self._get_device_first_timestamp(all_results)
        if device_first_timestamp is None:
            log_not_emit('WARNING', 'device_collector', '[_calculate_effective_offset_and_adjust] Cannot get device first timestamp, fallback to playback_time_offsets', category='engine')
            return self._apply_fallback_offset(reference_params, playback_time_offsets)

        ref_first_timestamp = self._get_reference_first_timestamp(reference_params)
        if ref_first_timestamp is None:
            log_not_emit('WARNING', 'device_collector', '[_calculate_effective_offset_and_adjust] Cannot get reference first timestamp', category='engine')
            return None

        effective_offset = device_first_timestamp - ref_first_timestamp

        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_and_adjust] ===== OFFSET CALCULATION =====', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_and_adjust] 参考首个时间戳 (ref_first_ts): {ref_first_timestamp:.3f}s', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_and_adjust] 设备首个时间戳 (device_first_ts): {device_first_timestamp:.3f}s', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_and_adjust] 有效偏移量 (effective_offset): {effective_offset:.3f}s', category='engine')
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_and_adjust] ==============================', category='engine')

        if abs(effective_offset) < 0.001:
            log_not_emit('INFO', 'device_collector', '[_calculate_effective_offset_and_adjust] effective_offset ~= 0, no adjustment needed', category='engine')
            return reference_params

        adjusted = self._apply_single_offset(reference_params, effective_offset)
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_and_adjust] Adjustment applied, returning adjusted params', category='engine')
        return adjusted

    def _get_device_first_timestamp(self, all_results):
        """从设备结果中提取首个时间戳

        优先从 recording_rttm_content 获取，其次 recording_stm_content

        Args:
            all_results: 设备结果列表

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        log_not_emit('DEBUG', 'device_collector', f'[_get_device_first_timestamp] START: all_results count={len(all_results)}', category='engine')

        for idx, res in enumerate(all_results):
            raw_results = res.get('raw_results', {})
            if not raw_results:
                log_not_emit('DEBUG', 'device_collector', f'[_get_device_first_timestamp] result[{idx}]: raw_results is empty', category='engine')
                continue

            rttm_content = raw_results.get('recording_rttm_content', '')
            stm_content = raw_results.get('recording_stm_content', '')

            log_not_emit('DEBUG', 'device_collector', f'[_get_device_first_timestamp] result[{idx}]: rttm_len={len(rttm_content) if rttm_content else 0}, stm_len={len(stm_content) if stm_content else 0}', category='engine')

            if rttm_content:
                ts = self._extract_first_timestamp_from_text(rttm_content, 'rttm')
                if ts is not None:
                    log_not_emit('INFO', 'device_collector', f'[_get_device_first_timestamp] result[{idx}]: Found device timestamp from RTTM: {ts:.3f}s', category='engine')
                    return ts

            if stm_content:
                ts = self._extract_first_timestamp_from_text(stm_content, 'stm')
                if ts is not None:
                    log_not_emit('INFO', 'device_collector', f'[_get_device_first_timestamp] result[{idx}]: Found device timestamp from STM: {ts:.3f}s', category='engine')
                    return ts

        log_not_emit('WARNING', 'device_collector', '[_get_device_first_timestamp] No valid timestamp found in device results', category='engine')
        return None

    def _get_device_first_timestamp_from_result(self, extracted_result):
        """从单个设备提取结果中提取首个时间戳

        Args:
            extracted_result: 设备驱动提取的单个结果

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        if not extracted_result:
            return None

        rttm_content = extracted_result.get('recording_rttm_content', '')
        stm_content = extracted_result.get('recording_stm_content', '')

        if rttm_content:
            ts = self._extract_first_timestamp_from_text(rttm_content, 'rttm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector', f'[_get_device_first_timestamp_from_result] from rttm: {ts:.3f}', category='engine')
                return ts

        if stm_content:
            ts = self._extract_first_timestamp_from_text(stm_content, 'stm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector', f'[_get_device_first_timestamp_from_result] from stm: {ts:.3f}', category='engine')
                return ts

        log_not_emit('WARNING', 'device_collector', '[_get_device_first_timestamp_from_result] No valid timestamp found in extracted_result', category='engine')
        return None

    def _extract_first_timestamp_from_text(self, text_content, format_type):
        """从 RTTM/STM 文本中提取首个时间戳

        Args:
            text_content: RTTM 或 STM 格式的文本
            format_type: 'rttm' 或 'stm'

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        if not text_content:
            return None

        lines = text_content.split('\n')
        for line in lines:
            parts = line.split()
            if not parts:
                continue

            try:
                if format_type == 'rttm' and parts[0] == 'SPEAKER' and len(parts) >= 4:
                    return float(parts[3])
                elif format_type == 'stm' and len(parts) >= 3 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                    return float(parts[2])
            except (ValueError, IndexError):
                continue

        return None

    def _extract_segments_from_text(self, text_content, format_type):
        """从 RTTM/STM 文本中提取所有片段列表

        Args:
            text_content: RTTM 或 STM 格式的文本
            format_type: 'rttm' 或 'stm'

        Returns:
            list: 片段列表，每个元素为 {'start': float, 'end': float, 'text': str, 'speaker': str}
        """
        if not text_content:
            return []

        segments = []
        lines = text_content.split('\n')

        for line in lines:
            parts = line.split()
            if not parts:
                continue

            try:
                if format_type == 'rttm' and parts[0] == 'SPEAKER' and len(parts) >= 8:
                    start = float(parts[3])
                    duration = float(parts[4])
                    end = start + duration
                    speaker = parts[7]
                    segments.append({
                        'start': start,
                        'end': end,
                        'speaker': speaker,
                        'text': ''
                    })
                elif format_type == 'stm' and len(parts) >= 6 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                    start = float(parts[3])
                    end = float(parts[4])
                    speaker = parts[2]
                    text = ' '.join(parts[5:])
                    segments.append({
                        'start': start,
                        'end': end,
                        'speaker': speaker,
                        'text': text
                    })
            except (ValueError, IndexError):
                continue

        segments.sort(key=lambda x: x['start'])
        return segments

    def _extract_segments_from_result(self, raw_results):
        """从设备结果中提取片段列表

        Args:
            raw_results: 设备驱动提取的结果

        Returns:
            list: 片段列表
        """
        if not raw_results:
            return []

        rttm_content = raw_results.get('recording_rttm_content', '')
        stm_content = raw_results.get('recording_stm_content', '')

        if rttm_content:
            segments = self._extract_segments_from_text(rttm_content, 'rttm')
            if segments:
                return segments

        if stm_content:
            segments = self._extract_segments_from_text(stm_content, 'stm')
            if segments:
                return segments

        return []

    def _extract_segments_from_reference(self, reference_params):
        """从参考参数中提取片段列表

        Args:
            reference_params: 参考参数列表

        Returns:
            list: 片段列表
        """
        if not reference_params:
            return []

        for param in reference_params:
            if not isinstance(param, dict):
                continue

            param_type = param.get('type', '')
            if param_type not in ['rttm', 'stm']:
                continue

            for test_type in ['api', 'e2e']:
                value = param.get(test_type)
                if not value or not isinstance(value, dict):
                    continue

                segments = value.get('segments') or value.get('json', [])
                if segments and isinstance(segments, list):
                    valid_segments = []
                    for seg in segments:
                        if isinstance(seg, dict) and 'start' in seg and 'end' in seg:
                            valid_segments.append({
                                'start': float(seg['start']),
                                'end': float(seg['end']),
                                'speaker': seg.get('speaker', ''),
                                'text': seg.get('text', '')
                            })
                    if valid_segments:
                        valid_segments.sort(key=lambda x: x['start'])
                        return valid_segments

                text = value.get('text', '')
                if text and param_type in ['rttm', 'stm']:
                    segments = self._extract_segments_from_text(text, param_type)
                    if segments:
                        return segments

        return []

    def _compute_total_overlap(self, segs_a, segs_b):
        """计算两组片段的总重叠时间

        Args:
            segs_a: 片段列表A
            segs_b: 片段列表B

        Returns:
            float: 总重叠时间（秒）
        """
        total = 0.0
        for a in segs_a:
            for b in segs_b:
                overlap_start = max(a['start'], b['start'])
                overlap_end = min(a['end'], b['end'])
                if overlap_end > overlap_start:
                    total += overlap_end - overlap_start
        return total

    def _compute_text_similarity(self, text_a, text_b):
        """计算两个文本的相似度（简单词重叠率）

        Args:
            text_a: 文本A
            text_b: 文本B

        Returns:
            float: 相似度 (0.0-1.0)
        """
        if not text_a or not text_b:
            return 0.0

        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        return len(intersection) / len(union) if union else 0.0

    def _find_candidate_pairs_by_text(self, device_segments, ref_segments, min_similarity=0.3):
        """基于文本相似度找到候选匹配对

        Args:
            device_segments: 设备片段列表
            ref_segments: 参考片段列表
            min_similarity: 最小相似度阈值

        Returns:
            list: [(device_idx, ref_idx, similarity), ...]
        """
        candidates = []

        for i, d_seg in enumerate(device_segments):
            d_text = d_seg.get('text', '')
            if not d_text:
                continue

            for j, r_seg in enumerate(ref_segments):
                r_text = r_seg.get('text', '')
                if not r_text:
                    continue

                similarity = self._compute_text_similarity(d_text, r_text)
                if similarity >= min_similarity:
                    candidates.append((i, j, similarity))

        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[:MAX_CANDIDATE_PAIRS]

    def _sample_segments_by_duration(self, segments, max_count=20):
        """按时长优先采样片段

        优先选择时长较长的片段（更稳定可靠）
        同时保证时间分布均匀

        Args:
            segments: 片段列表
            max_count: 最大采样数量

        Returns:
            list: 采样后的片段索引列表
        """
        if not segments:
            return []

        if len(segments) <= max_count:
            return list(range(len(segments)))

        indexed = [(i, seg['end'] - seg['start']) for i, seg in enumerate(segments)]
        indexed.sort(key=lambda x: x[1], reverse=True)

        top_by_duration = [idx for idx, _ in indexed[:max_count * 2]]

        top_by_duration.sort()

        step = max(1, len(top_by_duration) // max_count)
        sampled = top_by_duration[::step][:max_count]

        return sampled

    def _sample_segments_by_time_distribution(self, segments, max_count=20):
        """按时间分布均匀采样片段

        将时间轴分成多个区间，每个区间采样若干片段

        Args:
            segments: 片段列表
            max_count: 最大采样数量

        Returns:
            list: 采样后的片段索引列表
        """
        if not segments:
            return []

        if len(segments) <= max_count:
            return list(range(len(segments)))

        total_duration = segments[-1]['end'] - segments[0]['start']
        if total_duration <= 0:
            return list(range(min(max_count, len(segments))))

        num_bins = min(max_count, 10)
        bin_size = total_duration / num_bins

        bins = [[] for _ in range(num_bins)]
        for i, seg in enumerate(segments):
            bin_idx = min(int((seg['start'] - segments[0]['start']) / bin_size), num_bins - 1)
            bins[bin_idx].append((i, seg['end'] - seg['start']))

        sampled = []
        per_bin = max(1, max_count // num_bins)
        for bin_segs in bins:
            bin_segs.sort(key=lambda x: x[1], reverse=True)
            for idx, _ in bin_segs[:per_bin]:
                sampled.append(idx)

        return sampled[:max_count]

    def _generate_candidate_offsets(self, device_segments, ref_segments, max_offset=MAX_ALIGNMENT_OFFSET):
        """生成候选偏移量集合

        综合使用多种策略：
        1. 文本相似度匹配（如果有文本）
        2. 时长优先采样
        3. 时间分布均匀采样

        Args:
            device_segments: 设备片段列表
            ref_segments: 参考片段列表
            max_offset: 最大偏移量限制

        Returns:
            set: 候选偏移量集合
        """
        candidate_offsets = set()

        text_candidates = self._find_candidate_pairs_by_text(device_segments, ref_segments)
        if text_candidates:
            for d_idx, r_idx, _ in text_candidates:
                offset = device_segments[d_idx]['start'] - ref_segments[r_idx]['start']
                if abs(offset) <= max_offset:
                    candidate_offsets.add(round(offset, 3))

        device_sample_duration = self._sample_segments_by_duration(device_segments, 15)
        ref_sample_duration = self._sample_segments_by_duration(ref_segments, 15)

        for d_idx in device_sample_duration:
            for r_idx in ref_sample_duration:
                offset = device_segments[d_idx]['start'] - ref_segments[r_idx]['start']
                if abs(offset) <= max_offset:
                    candidate_offsets.add(round(offset, 3))

        device_sample_time = self._sample_segments_by_time_distribution(device_segments, 15)
        ref_sample_time = self._sample_segments_by_time_distribution(ref_segments, 15)

        for d_idx in device_sample_time:
            for r_idx in ref_sample_time:
                offset = device_segments[d_idx]['start'] - ref_segments[r_idx]['start']
                if abs(offset) <= max_offset:
                    candidate_offsets.add(round(offset, 3))

        return candidate_offsets

    def _calculate_offset_by_max_overlap(self, device_segments, ref_segments, max_offset=MAX_ALIGNMENT_OFFSET):
        """基于最大重叠时间计算最优偏移量

        Args:
            device_segments: 设备片段列表
            ref_segments: 参考片段列表
            max_offset: 最大偏移量限制（秒）

        Returns:
            tuple: (best_offset, max_overlap)
        """
        if not device_segments or not ref_segments:
            return 0.0, 0.0

        candidate_offsets = self._generate_candidate_offsets(
            device_segments, ref_segments, max_offset
        )

        if not candidate_offsets:
            candidate_offsets.add(0.0)

        best_offset = 0.0
        max_overlap = 0.0

        for offset in candidate_offsets:
            adjusted_ref = []
            for seg in ref_segments:
                adjusted_ref.append({
                    'start': seg['start'] + offset,
                    'end': seg['end'] + offset,
                    'speaker': seg.get('speaker', ''),
                    'text': seg.get('text', '')
                })

            overlap = self._compute_total_overlap(device_segments, adjusted_ref)
            if overlap > max_overlap:
                max_overlap = overlap
                best_offset = offset

        return best_offset, max_overlap

    def _get_reference_first_timestamp(self, reference_params):
        """从参考参数中提取首个时间戳

        Args:
            reference_params: 参考参数列表

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        log_not_emit('DEBUG', 'device_collector', f'[_get_reference_first_timestamp] START: reference_params count={len(reference_params)}', category='engine')

        for param_idx, param in enumerate(reference_params):
            if not isinstance(param, dict):
                log_not_emit('DEBUG', 'device_collector', f'[_get_reference_first_timestamp] param[{param_idx}]: not a dict, skip', category='engine')
                continue

            log_not_emit('DEBUG', 'device_collector', f'[_get_reference_first_timestamp] param[{param_idx}]: keys={list(param.keys())}', category='engine')

            for test_type in ['api', 'e2e']:
                value = param.get(test_type)
                if not value or not isinstance(value, dict):
                    log_not_emit('DEBUG', 'device_collector', f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: no valid value, skip', category='engine')
                    continue

                segments = value.get('segments') or value.get('json', [])
                if segments and isinstance(segments, list) and len(segments) > 0:
                    first_seg = segments[0]
                    if isinstance(first_seg, dict) and 'start' in first_seg:
                        ts = float(first_seg['start'])
                        log_not_emit('INFO', 'device_collector', f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: Found reference timestamp from segments[0]: {ts:.3f}s', category='engine')
                        return ts
                    else:
                        log_not_emit('DEBUG', 'device_collector', f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: first_seg has no start, seg_keys={list(first_seg.keys()) if isinstance(first_seg, dict) else type(first_seg)}', category='engine')

                text = value.get('text', '')
                format_type = value.get('format', '')
                if text and format_type in ['rttm', 'stm']:
                    ts = self._extract_first_timestamp_from_text(text, format_type)
                    if ts is not None:
                        log_not_emit('INFO', 'device_collector', f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: Found reference timestamp from text ({format_type}): {ts:.3f}s', category='engine')
                        return ts
                else:
                    log_not_emit('DEBUG', 'device_collector', f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: text={len(text) if text else 0}, format={format_type}', category='engine')

        log_not_emit('WARNING', 'device_collector', '[_get_reference_first_timestamp] No valid timestamp found in reference params', category='engine')
        return None

    def _apply_fallback_offset(self, reference_params, playback_time_offsets):
        """当无法从设备结果提取时间戳时，回退使用 playback_time_offsets

        Args:
            reference_params: 参考参数列表
            playback_time_offsets: 系统测量的播放时间偏移

        Returns:
            调整后的参考参数列表
        """
        if not playback_time_offsets:
            return None

        if isinstance(playback_time_offsets, dict):
            first_offset = list(playback_time_offsets.values())[0] if playback_time_offsets else 0
            offset_val = first_offset.get('offset', 0) if isinstance(first_offset, dict) else first_offset
        else:
            offset_val = playback_time_offsets

        log_not_emit('DEBUG', 'device_collector', f'[_apply_fallback_offset] Using playback_time_offsets: {offset_val}', category='engine')

        if offset_val != 0 and reference_params:
            return self._apply_single_offset(reference_params, offset_val)

        return None
    
    def _apply_time_offset_to_reference_params(self, reference_params, offset):
        """根据实际播放时间偏移调整参考参数字段中的时间戳
        
        Args:
            reference_params: 参考参数列表
            offset: 时间偏移量（秒）或 {audio_id_playorder: {offset: xxx, play_order: xx}} 字典
            
        Returns:
            调整后的参考参数列表
        """
        if not reference_params:
            log_not_emit('DEBUG', 'device_collector', '[_apply_time_offset_to_reference_params] reference_params is empty, returning as-is', category='engine')
            return reference_params
        
        log_not_emit('DEBUG', 'device_collector', f'[_apply_time_offset_to_reference_params] reference_params count={len(reference_params)}, offset type={type(offset).__name__}', category='engine')
        
        offset_dict = {}
        if isinstance(offset, dict):
            log_not_emit('DEBUG', 'device_collector', f'[_apply_time_offset_to_reference_params] offset dict keys={list(offset.keys())}', category='engine')
            for k, v in offset.items():
                if isinstance(v, dict) and 'offset' in v:
                    play_order = v.get('play_order')
                    if play_order is not None:
                        offset_dict[play_order] = v['offset']
                        log_not_emit('DEBUG', 'device_collector', f'[_apply_time_offset_to_reference_params] Added offset_dict[{play_order}] = {v["offset"]}', category='engine')
                elif isinstance(v, (int, float)):
                    if isinstance(k, str) and '_' in k:
                        offset_dict[int(k.split('_')[-1])] = v if isinstance(v, int) else float(v)
                        log_not_emit('DEBUG', 'device_collector', f'[_apply_time_offset_to_reference_params] Added offset_dict from str key[{k.split("_")[-1]}] = {v}', category='engine')
                    elif isinstance(k, int):
                        offset_dict[k] = v if isinstance(v, int) else float(v)
        
        log_not_emit('DEBUG', 'device_collector', f'[_apply_time_offset_to_reference_params] Final offset_dict={offset_dict}', category='engine')
        
        if not offset_dict:
            first_val = list(offset.values())[0] if offset else 0
            if isinstance(first_val, dict):
                first_val = first_val.get('offset', 0)
            if first_val == 0:
                return reference_params
            return self._apply_single_offset(reference_params, first_val)
        
        if all(v == 0 for v in offset_dict.values()):
            return reference_params
        
        adjusted_params = []
        for param in reference_params:
            if not isinstance(param, dict):
                adjusted_params.append(param)
                continue
            
            new_param = param.copy()
            
            for test_type in ['api', 'e2e']:
                value = param.get(test_type)
                if not value:
                    continue
                
                if isinstance(value, dict):
                    adjusted_value = value.copy()
                    
                    if 'segments' in value:
                        adjusted_segments = []
                        for seg in value['segments']:
                            new_seg = seg.copy()
                            seg_play_order = new_seg.get('play_order')
                            if seg_play_order is not None and seg_play_order in offset_dict:
                                seg_offset = offset_dict[seg_play_order]
                            else:
                                seg_offset = list(offset_dict.values())[0] if offset_dict else 0
                            
                            if 'start' in new_seg:
                                new_seg['start'] = new_seg['start'] + seg_offset
                            if 'end' in new_seg:
                                new_seg['end'] = new_seg['end'] + seg_offset
                            adjusted_segments.append(new_seg)
                        adjusted_value['segments'] = adjusted_segments
                        adjusted_value['json'] = adjusted_segments
                    
                    if 'text' in value and value.get('format') in ['rttm', 'stm']:
                        adjusted_value['text'] = self._adjust_rttm_stm_text_by_play_order(value['text'], offset_dict)
                    
                    new_param[test_type] = adjusted_value
                else:
                    new_param[test_type] = value
            
            adjusted_params.append(new_param)
        
        return adjusted_params
    
    def _apply_single_offset(self, reference_params, offset):
        """应用单一偏移量（兼容旧逻辑）"""
        log_not_emit('DEBUG', 'device_collector', f'[_apply_single_offset] START: offset={offset}', category='engine')
        
        if not reference_params:
            log_not_emit('WARNING', 'device_collector', '[_apply_single_offset] reference_params is empty', category='engine')
            return None
            
        if not isinstance(reference_params, list):
            log_not_emit('WARNING', 'device_collector', f'[_apply_single_offset] reference_params is not a list, type={type(reference_params)}', category='engine')
            return None
            
        try:
            adjusted_params = []
            for param_idx, param in enumerate(reference_params):
                if not isinstance(param, dict):
                    adjusted_params.append(param)
                    continue
                
                new_param = param.copy()
                
                for test_type in ['api', 'e2e']:
                    value = param.get(test_type)
                    if not value:
                        continue
                    
                    if isinstance(value, dict):
                        adjusted_value = value.copy()
                        
                        if 'json' in value and value['json']:
                            adjusted_segments = []
                            json_data = value['json']
                            if isinstance(json_data, str):
                                try:
                                    json_data = json.loads(json_data)
                                except:
                                    json_data = None
                            if json_data and isinstance(json_data, list):
                                for seg in json_data:
                                    if isinstance(seg, dict):
                                        new_seg = seg.copy()
                                        if 'start' in new_seg:
                                            new_seg['start'] = new_seg['start'] + offset
                                        if 'end' in new_seg:
                                            new_seg['end'] = new_seg['end'] + offset
                                        adjusted_segments.append(new_seg)
                                    else:
                                        adjusted_segments.append(seg)
                            if adjusted_segments:
                                adjusted_value['json'] = adjusted_segments
                        
                        if 'segments' in value and value['segments']:
                            adjusted_segments = []
                            for seg in value['segments']:
                                if isinstance(seg, dict):
                                    new_seg = seg.copy()
                                    if 'start' in new_seg:
                                        new_seg['start'] = new_seg['start'] + offset
                                    if 'end' in new_seg:
                                        new_seg['end'] = new_seg['end'] + offset
                                    adjusted_segments.append(new_seg)
                                else:
                                    adjusted_segments.append(seg)
                            adjusted_value['segments'] = adjusted_segments
                        
                        if 'text' in value and value.get('format') in ['rttm', 'stm']:
                            adjusted_value['text'] = self._adjust_rttm_stm_text(value['text'], offset)
                        
                        new_param[test_type] = adjusted_value
                    else:
                        new_param[test_type] = value
                
                adjusted_params.append(new_param)
            
            log_not_emit('DEBUG', 'device_collector', f'[_apply_single_offset] SUCCESS: adjusted {len(adjusted_params)} params', category='engine')
            return adjusted_params
            
        except Exception as e:
            import traceback
            log_not_emit('ERROR', 'device_collector', f'[_apply_single_offset] FAILED: {str(e)}, traceback: {traceback.format_exc()}', category='engine')
            return None
    
    def _adjust_rttm_stm_text(self, text_content, offset):
        """调整 RTTM/STM 文本中的时间戳
        
        Args:
            text_content: RTTM 或 STM 格式的文本
            offset: 时间偏移量（秒）
            
        Returns:
            调整后的文本
        """
        if not text_content or offset == 0:
            return text_content
        
        lines = text_content.split('\n')
        adjusted_lines = []
        
        for line in lines:
            parts = line.split()
            if not parts:
                adjusted_lines.append(line)
                continue
            
            format_type = None
            if parts[0] == 'SPEAKER':
                format_type = 'rttm'
            elif len(parts) >= 4 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                format_type = 'stm'
            
            if format_type == 'rttm' and len(parts) >= 5:
                try:
                    start_time = float(parts[3])
                    new_start_time = start_time + offset
                    parts[3] = f"{new_start_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            elif format_type == 'stm' and len(parts) >= 4:
                try:
                    start_time = float(parts[2])
                    end_time = float(parts[3])
                    new_start_time = start_time + offset
                    new_end_time = end_time + offset
                    parts[2] = f"{new_start_time:.2f}"
                    parts[3] = f"{new_end_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            else:
                adjusted_lines.append(line)
        
        return '\n'.join(adjusted_lines)
    
    def _adjust_rttm_stm_text_by_play_order(self, text_content, offset_dict):
        """根据 play_order 分别调整 RTTM/STM 文本中的时间戳
        
        Args:
            text_content: RTTM 或 STM 格式的文本
            offset_dict: {play_order: offset} 字典
            
        Returns:
            调整后的文本
        """
        if not text_content or not offset_dict:
            return text_content
        
        if all(v == 0 for v in offset_dict.values()):
            return text_content
        
        default_offset = list(offset_dict.values())[0] if offset_dict else 0
        
        sorted_play_orders = sorted(offset_dict.keys())
        
        lines = text_content.split('\n')
        adjusted_lines = []
        
        current_play_order_idx = 0
        play_order_ranges = []
        current_start = 0
        for i, po in enumerate(sorted_play_orders):
            if i + 1 < len(sorted_play_orders):
                next_po = sorted_play_orders[i + 1]
                play_order_ranges.append((po, current_start, next_po))
                current_start = next_po
            else:
                play_order_ranges.append((po, current_start, None))
        
        def get_offset_for_time(start_time):
            for po, range_start, range_end in play_order_ranges:
                if range_end is None or start_time < range_end:
                    return offset_dict.get(po, default_offset)
            return default_offset
        
        for line in lines:
            parts = line.split()
            if not parts:
                adjusted_lines.append(line)
                continue
            
            format_type = None
            if parts[0] == 'SPEAKER':
                format_type = 'rttm'
            elif len(parts) >= 4 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                format_type = 'stm'
            
            if format_type == 'rttm' and len(parts) >= 5:
                try:
                    start_time = float(parts[3])
                    seg_offset = get_offset_for_time(start_time)
                    new_start_time = start_time + seg_offset
                    parts[3] = f"{new_start_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            elif format_type == 'stm' and len(parts) >= 4:
                try:
                    start_time = float(parts[2])
                    seg_offset = get_offset_for_time(start_time)
                    end_time = float(parts[3])
                    new_start_time = start_time + seg_offset
                    new_end_time = end_time + seg_offset
                    parts[2] = f"{new_start_time:.2f}"
                    parts[3] = f"{new_end_time:.2f}"
                    adjusted_lines.append(' '.join(parts))
                except (ValueError, IndexError):
                    adjusted_lines.append(line)
            else:
                adjusted_lines.append(line)
        
        return '\n'.join(adjusted_lines)
    
    def convert_results(self, all_results, algorithm_type):
        """转换原始结果为映射后的格式
        
        Args:
            all_results: 原始结果列表
            algorithm_type: 算法类型
            
        Returns:
            list: 转换后的结果列表（包含 success 字段）
        """
        
        # 调试：打印原始传入的数据
        print(f"DEBUG convert_results ENTRY: all_results id={id(all_results)}")
        if all_results and len(all_results) > 0:
            print(f"DEBUG convert_results ENTRY: raw_results keys = {list(all_results[0].get('raw_results', {}).keys())}")
        
        # 深拷贝，防止外部修改
        import copy
        all_results = copy.deepcopy(all_results)
        
        print(f"DEBUG convert_results AFTER DEEPCOPY: all_results id={id(all_results)}")
        if all_results and len(all_results) > 0:
            print(f"DEBUG convert_results AFTER DEEPCOPY: raw_results keys = {list(all_results[0].get('raw_results', {}).keys())}")
        
        for res in all_results:
            raw_results = res.get('raw_results', {})
            result_type = res.get('result_type', 'default')
            log_not_emit('DEBUG', 'device_collector', f'convert_results: result_type={result_type}, all_results id={id(all_results)}, res id={id(res)}, raw_results id={id(raw_results)}, raw_keys={list(raw_results.keys())[:5]}', category='engine')
            
            # 添加更多调试信息
            from backend.algorithm.field_mapper import get_field_mapper
            fm = get_field_mapper()
            mapped_fields = fm.get_mapped_device_output_fields(algorithm_type)
            if isinstance(mapped_fields, list):
                log_not_emit('DEBUG', 'device_collector', f'mapped_fields: {[f.get("code") for f in mapped_fields]}', category='engine')
            else:
                log_not_emit('DEBUG', 'device_collector', f'mapped_fields keys: {list(mapped_fields.keys())}', category='engine')
            
            mapped_results = self.field_mapper.convert_device_output(algorithm_type, raw_results)
            
            res.update(mapped_results)
            
            has_values = any(mapped_results.values())
            res['success'] = has_values
        
        return all_results
    
    def build_case_result_log(self, algorithm_type, res, ref_fields=None, **kwargs):
        """构建用例结果日志内容
        
        Args:
            algorithm_type: 算法类型（如 translation, fix 等）
            res: 单个结果字典，包含设备执行结果
            ref_fields: 参考字段字典（如参考文本、参考RTTM等）
            **kwargs: 额外字段
            
        Returns:
            str: 日志内容
        """
        # 确保 ref_fields 不为 None
        if ref_fields is None:
            ref_fields = {}
        
        # 获取算法映射后的设备输出字段键列表
        mapped_output_keys = self.field_mapper.get_mapped_device_output_field_keys(algorithm_type)
        
        # 初始化日志内容，先记录设备名称和执行状态
        log_content = f"设备 {res.get('device_name', 'Unknown')} 执行结果:\n" + \
                      f"  采集状态: {'成功' if res.get('success', False) else '失败'}\n"
        
        for key in mapped_output_keys:
            # 获取结果值，可能是字符串、字典、列表等任意类型
            value = res.get(key)
            if value:
                # 先转换为字符串再截断，避免对字典/列表直接切片导致 KeyError: slice(None, 100, None)
                # 原始代码 res.get(key, '')[:100] 当 value 是字典时会报错
                value = str(value)[:100]
            else:
                value = ''
            log_content += f"  {key}: {value}...\n"
        
        # 处理参考字段（如参考文本、参考RTTM等）
        if ref_fields:
            for field_key, field_value in ref_fields.items():
                if field_value:
                    display_value = str(field_value)[:100]
                    log_content += f"  {field_key}: {display_value}...\n"
        
        # 处理额外配置的查询字段
        extra_fields = self.field_mapper._get_algorithm_extra_config(algorithm_type).get('query_fields', {}).keys()
        for field in extra_fields:
            field_value = kwargs.get(field)
            if field_value:
                log_content += f"  {field}: {field_value}\n"
        
        return log_content


def get_device_result_collector():
    """获取设备结果采集器实例"""
    return DeviceResultCollector()
