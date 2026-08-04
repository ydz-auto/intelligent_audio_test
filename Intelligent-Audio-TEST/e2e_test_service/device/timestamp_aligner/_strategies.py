"""对齐策略编排：策略0-3的依次尝试"""

from shared.utils.log_handler import log_not_emit
from .constants import (
    GAP_PATTERN_MIN_SEGMENTS,
    MIN_OVERLAP_THRESHOLD,
    CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD,
)


class StrategyMixin:
    """对齐策略方法：内容对齐、最大重叠、间隙模式、首个时间戳"""

    def _init_alignment_info(self):
        """初始化 alignment_info 字典"""
        return {
            'method': 'none',
            'offset': 0.0,
            'device_segment_count': 0,
            'ref_segment_count': 0,
            'device_first_ts': None,
            'ref_first_ts': None,
            'missing_segment_detected': False,
            'missing_segment_detail': '',
            'gap_pattern_offset': None,
            'gap_pattern_match_score': None,
            'first_timestamp_reliability': 'high',
            'content_alignment_score': None,
            'content_matched_pairs': 0,
            'content_skipped_device': 0,
            'content_skipped_ref': 0
        }

    def _try_content_alignment(self, device_segments, ref_segments, reference_params, alignment_info):
        """策略0: 文本内容对齐"""
        content_offset, content_confidence, content_details = self._align_by_content(
            device_segments, ref_segments
        )

        alignment_info['content_alignment_score'] = content_confidence
        alignment_info['content_matched_pairs'] = len(content_details.get('matched_pairs', []))
        alignment_info['content_skipped_device'] = content_details.get('skipped_device', 0)
        alignment_info['content_skipped_ref'] = content_details.get('skipped_ref', 0)

        if content_offset is None or content_confidence < CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD:
            if content_offset is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[calculate_effective_offset_for_single_result] 内容对齐置信度不足: '
                             f'offset={content_offset}, confidence={content_confidence:.3f}',
                             category='engine')
            return None

        if not self._validate_offset_reasonable(content_offset, ref_segments):
            log_not_emit('WARNING', 'device_collector',
                         f'[calculate_effective_offset_for_single_result] content_alignment 偏移量 {content_offset:.3f}s 不合理, 跳过',
                         category='engine')
            return None

        log_not_emit('INFO', 'device_collector', '===== CONTENT ALIGNMENT =====', category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'偏移量: {content_offset:.3f}s, 置信度: {content_confidence:.3f}, 匹配对数: {len(content_details["matched_pairs"])}',
                     category='engine')

        alignment_info['method'] = 'content_alignment'
        alignment_info['offset'] = content_offset

        if abs(content_offset) < 0.001:
            alignment_info['method'] = 'content_alignment_no_adjustment'
            return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

        adjusted = self._rttm_utils._apply_single_offset(reference_params, content_offset)
        return {'adjusted_params': adjusted, 'alignment_info': alignment_info}

    def _try_max_overlap(self, device_segments, ref_segments, reference_params, alignment_info):
        """策略1: 最大重叠对齐"""
        use_max_overlap = (
            device_segments and ref_segments and
            len(device_segments) >= 2 and len(ref_segments) >= 2
        )
        if not use_max_overlap:
            return None

        best_offset, max_overlap = self._calculate_offset_by_max_overlap(device_segments, ref_segments)

        alignment_info['method'] = 'max_overlap'
        alignment_info['offset'] = best_offset
        alignment_info['max_overlap'] = max_overlap

        log_not_emit('INFO', 'device_collector', '===== MAX OVERLAP ALIGNMENT =====', category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'设备片段数: {len(device_segments)}, 参考片段数: {len(ref_segments)}', category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'最优偏移量: {best_offset:.3f}s, 最大重叠时间: {max_overlap:.3f}s', category='engine')

        if max_overlap < MIN_OVERLAP_THRESHOLD:
            log_not_emit('INFO', 'device_collector',
                         f'重叠时间 {max_overlap:.3f}s < 阈值 {MIN_OVERLAP_THRESHOLD}s', category='engine')
            return None

        if not self._validate_offset_reasonable(best_offset, ref_segments):
            log_not_emit('WARNING', 'device_collector',
                         f'max_overlap 偏移量 {best_offset:.3f}s 不合理, 跳过', category='engine')
            return None

        log_not_emit('INFO', 'device_collector', '使用最大重叠对齐结果', category='engine')

        if abs(best_offset) < 0.001:
            alignment_info['method'] = 'max_overlap_no_adjustment'
            return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

        adjusted = self._rttm_utils._apply_single_offset(reference_params, best_offset)
        return {'adjusted_params': adjusted, 'alignment_info': alignment_info}

    def _try_gap_pattern(self, device_segments, ref_segments, reference_params, alignment_info):
        """策略2: 间隙模式匹配验证"""
        use_gap_pattern = (
            device_segments and ref_segments and
            len(device_segments) >= GAP_PATTERN_MIN_SEGMENTS and
            len(ref_segments) >= GAP_PATTERN_MIN_SEGMENTS
        )
        if not use_gap_pattern:
            return None

        gap_offset, gap_score = self._validate_offset_by_gap_pattern(device_segments, ref_segments)
        alignment_info['gap_pattern_offset'] = gap_offset
        alignment_info['gap_pattern_match_score'] = gap_score

        if gap_offset is None or gap_score <= 0.5:
            log_not_emit('DEBUG', 'device_collector',
                         f'间隙模式验证未通过: offset={gap_offset}, score={gap_score}', category='engine')
            return None

        if not self._validate_offset_reasonable(gap_offset, ref_segments):
            log_not_emit('WARNING', 'device_collector',
                         f'gap_pattern 偏移量 {gap_offset:.3f}s 不合理, 跳过', category='engine')
            return None

        log_not_emit('INFO', 'device_collector', '===== GAP PATTERN ALIGNMENT =====', category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'间隙模式偏移量: {gap_offset:.3f}s, 匹配得分: {gap_score:.3f}', category='engine')

        alignment_info['method'] = 'gap_pattern'
        alignment_info['offset'] = gap_offset

        if abs(gap_offset) < 0.001:
            alignment_info['method'] = 'gap_pattern_no_adjustment'
            return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

        adjusted = self._rttm_utils._apply_single_offset(reference_params, gap_offset)
        return {'adjusted_params': adjusted, 'alignment_info': alignment_info}

    def _try_first_timestamp(self, raw_results, reference_params, playback_time_offsets,
                             device_segments, ref_segments, alignment_info, missing_info, algorithm_type=None):
        """策略3: 首个时间戳对齐（含丢句安全检查）"""
        device_first_ts = self._get_device_first_timestamp_from_result(raw_results, algorithm_type=algorithm_type)
        alignment_info['device_first_ts'] = device_first_ts

        if device_first_ts is None:
            log_not_emit('WARNING', 'device_collector',
                         'Cannot get device first timestamp, fallback to playback_time_offsets', category='engine')
            alignment_info['method'] = 'fallback'
            return {'adjusted_params': self._rttm_utils._apply_fallback_offset(reference_params, playback_time_offsets),
                    'alignment_info': alignment_info}

        ref_first_ts = self._get_reference_first_timestamp(reference_params)
        alignment_info['ref_first_ts'] = ref_first_ts

        if ref_first_ts is None:
            log_not_emit('WARNING', 'device_collector', 'Cannot get reference first timestamp', category='engine')
            return {'adjusted_params': None, 'alignment_info': alignment_info}

        prev_max_overlap_value = alignment_info.get('max_overlap')
        prev_max_overlap_offset = alignment_info.get('offset') if alignment_info.get('method') == 'max_overlap' else None

        effective_offset = device_first_ts - ref_first_ts
        alignment_info['method'] = 'first_timestamp'
        alignment_info['offset'] = effective_offset

        # 可靠性评估
        if missing_info['detected'] and missing_info['confidence'] in ('high', 'medium'):
            alignment_info['first_timestamp_reliability'] = 'low'
        elif missing_info['detected']:
            alignment_info['first_timestamp_reliability'] = 'medium'

        log_not_emit('INFO', 'device_collector', '===== FIRST TIMESTAMP ALIGNMENT =====', category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'ref_first_ts: {ref_first_ts:.3f}s, device_first_ts: {device_first_ts:.3f}s, '
                     f'effective_offset: {effective_offset:.3f}s, 可靠性: {alignment_info["first_timestamp_reliability"]}',
                     category='engine')

        # 丢句场景处理
        result = self._handle_missing_segments(
            missing_info, prev_max_overlap_value, prev_max_overlap_offset,
            effective_offset, device_segments, ref_segments,
            reference_params, playback_time_offsets, alignment_info
        )
        if result is not None:
            return result

        # 偏移量合理性校验
        if not self._validate_offset_reasonable(effective_offset, ref_segments):
            log_not_emit('WARNING', 'device_collector',
                         f'first_timestamp 偏移量 {effective_offset:.3f}s 不合理, 尝试 playback_time_offsets',
                         category='engine')
            alignment_info['method'] = 'fallback'
            fallback = self._rttm_utils._apply_fallback_offset(reference_params, playback_time_offsets)
            if fallback:
                return {'adjusted_params': fallback, 'alignment_info': alignment_info}

        if abs(effective_offset) < 0.001:
            alignment_info['method'] = 'first_timestamp_no_adjustment'
            return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

        adjusted = self._rttm_utils._apply_single_offset(reference_params, effective_offset)
        log_not_emit('INFO', 'device_collector', 'Adjustment applied', category='engine')
        return {'adjusted_params': adjusted, 'alignment_info': alignment_info}

    def _handle_missing_segments(self, missing_info, prev_overlap_val, prev_overlap_offset,
                                  effective_offset, device_segments, ref_segments,
                                  reference_params, playback_time_offsets, alignment_info):
        """丢句场景: first_timestamp 不可信时的处理"""
        if not missing_info['detected']:
            return None

        # 优先回退到 max_overlap 结果
        if prev_overlap_val is not None and prev_overlap_val > 0 and prev_overlap_offset is not None:
            log_not_emit('WARNING', 'device_collector',
                         f'检测到丢句, first_timestamp 不可信, 回退 max_overlap: '
                         f'offset={prev_overlap_offset:.3f}s, overlap={prev_overlap_val:.3f}s',
                         category='engine')
            alignment_info['method'] = 'max_overlap_fallback'
            alignment_info['offset'] = prev_overlap_offset

            if self._validate_offset_reasonable(prev_overlap_offset, ref_segments):
                if abs(prev_overlap_offset) < 0.001:
                    return {'adjusted_params': reference_params, 'alignment_info': alignment_info}
                adjusted = self._rttm_utils._apply_single_offset(reference_params, prev_overlap_offset)
                return {'adjusted_params': adjusted, 'alignment_info': alignment_info}

        # 对 first_timestamp 做重叠验证
        if device_segments and ref_segments:
            adjusted_ref = [
                {'start': s['start'] + effective_offset, 'end': s['end'] + effective_offset}
                for s in ref_segments
            ]
            check_overlap = self._compute_total_overlap(device_segments, adjusted_ref)
            total_dur = sum(s['end'] - s['start'] for s in device_segments)
            overlap_ratio = check_overlap / total_dur if total_dur > 0 else 0

            log_not_emit('INFO', 'device_collector',
                         f'丢句验证: offset={effective_offset:.3f}s, 重叠率={overlap_ratio:.2f}',
                         category='engine')

            if overlap_ratio < 0.5:
                log_not_emit('WARNING', 'device_collector',
                             f'first_timestamp 验证失败(重叠率={overlap_ratio:.2f} < 0.5), 使用 playback_time_offsets',
                             category='engine')
                alignment_info['method'] = 'fallback'
                fallback = self._rttm_utils._apply_fallback_offset(reference_params, playback_time_offsets)
                if fallback:
                    return {'adjusted_params': fallback, 'alignment_info': alignment_info}

        return None
