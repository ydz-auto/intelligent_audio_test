"""时间戳对齐策略"""

import json
import difflib
import statistics
from shared.utils.field_mapper import get_field_mapper
from shared.utils.log_handler import log_not_emit
from .rttm_stm_utils import RttmStmUtils

# 对齐常量
MAX_ALIGNMENT_OFFSET = 30.0
MIN_OVERLAP_THRESHOLD = 0.5
MAX_CANDIDATE_PAIRS = 100
MIN_GAP_MATCH_TOLERANCE = 0.5
GAP_PATTERN_MIN_SEGMENTS = 3
MIN_REF_START_TIME = -0.5
MIN_TEXT_SIMILARITY = 0.3
MIN_CONTENT_MATCH_PAIRS = 2
CONTENT_ALIGNMENT_SKIP_PENALTY = -0.1
CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD = 0.5
CONTENT_OUTLIER_OFFSET_THRESHOLD = 2.0


class TimestampAligner:
    """时间戳对齐器"""

    def __init__(self):
        self.field_mapper = get_field_mapper()
        self._rttm_utils = RttmStmUtils()

    def _needs_alignment(self, algorithm_type, reference_params):
        """判断是否需要进行时间对齐

        根据算法配置判断：
        1. reference_params 中是否有 rttm/stm 类型的参考参数
        2. 设备输出字段中是否有 rttm/stm 类型

        两者都满足时才需要对齐，否则对齐无意义（如纯文本 ASR、翻译等）。

        Args:
            algorithm_type: 算法类型
            reference_params: 参考参数列表

        Returns:
            bool: True 表示需要对齐，False 表示不需要
        """
        if not reference_params:
            return False

        has_time_series_ref = False
        for param in reference_params:
            if isinstance(param, dict):
                param_type = param.get('type', '')
                if param_type in ('rttm', 'stm'):
                    has_time_series_ref = True
                    break

        if not has_time_series_ref:
            log_not_emit('DEBUG', 'device_collector',
                         f'[_needs_alignment] No rttm/stm in reference_params, alignment not needed',
                         category='engine')
            return False

        if algorithm_type and self.field_mapper:
            try:
                stm_codes = self.field_mapper.get_device_output_field_codes_by_type(algorithm_type, 'stm')
                rttm_codes = self.field_mapper.get_device_output_field_codes_by_type(algorithm_type, 'rttm')
                has_time_series_output = bool(stm_codes or rttm_codes)
                if not has_time_series_output:
                    log_not_emit('DEBUG', 'device_collector',
                                 f'[_needs_alignment] No rttm/stm device output fields for {algorithm_type}, alignment not needed',
                                 category='engine')
                    return False
            except Exception as e:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_needs_alignment] FieldMapper lookup failed: {e}, defaulting to True',
                             category='engine')
                return True

        return True

    def calculate_effective_offset_for_single_result(self, raw_results, reference_params, playback_time_offsets, algorithm_type=None):
        """为单个设备结果计算 effective_offset 并调整参考参数

        采用混合对齐策略（按优先级）：
        0. 文本内容对齐 → 1. 最大重叠 → 2. 间隙模式 → 3. 首个时间戳 → 4. 兜底
        """
        alignment_info = self._init_alignment_info()

        if not reference_params:
            log_not_emit('WARNING', 'device_collector',
                         '[calculate_effective_offset_for_single_result] reference_params is empty', category='engine')
            return {'adjusted_params': reference_params or [], 'alignment_info': alignment_info}

        if not self._needs_alignment(algorithm_type, reference_params):
            alignment_info['method'] = 'skipped'
            return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

        device_segments = self._rttm_utils._extract_segments_from_result(raw_results, algorithm_type)
        ref_segments = self._rttm_utils._extract_segments_from_reference(reference_params)

        alignment_info['device_segment_count'] = len(device_segments)
        alignment_info['ref_segment_count'] = len(ref_segments)

        missing_info = self._detect_missing_segments(device_segments, ref_segments)
        alignment_info['missing_segment_detected'] = missing_info['detected']
        alignment_info['missing_segment_detail'] = missing_info['description']

        # 策略0-2: 依次尝试
        for strategy_fn in (self._try_content_alignment, self._try_max_overlap, self._try_gap_pattern):
            result = strategy_fn(device_segments, ref_segments, reference_params, alignment_info)
            if result is not None:
                return result

        # 策略3: first_timestamp + 丢句感知
        return self._try_first_timestamp(
            raw_results, reference_params, playback_time_offsets,
            device_segments, ref_segments, alignment_info, missing_info, algorithm_type
        )

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
            log_not_emit('WARNING', 'device_collector',
                         '[_calculate_effective_offset_and_adjust] reference_params is empty', category='engine')
            return None

        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_and_adjust] START: reference_params count={len(reference_params)}, all_results count={len(all_results)}',
                     category='engine')

        device_first_timestamp = self._get_device_first_timestamp(all_results)
        if device_first_timestamp is None:
            log_not_emit('WARNING', 'device_collector',
                         '[_calculate_effective_offset_and_adjust] Cannot get device first timestamp, fallback to playback_time_offsets',
                         category='engine')
            return self._rttm_utils._apply_fallback_offset(reference_params, playback_time_offsets)

        ref_first_timestamp = self._get_reference_first_timestamp(reference_params)
        if ref_first_timestamp is None:
            log_not_emit('WARNING', 'device_collector',
                         '[_calculate_effective_offset_and_adjust] Cannot get reference first timestamp',
                         category='engine')
            return None

        effective_offset = device_first_timestamp - ref_first_timestamp

        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_and_adjust] ===== OFFSET CALCULATION =====', category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_and_adjust] 参考首个时间戳 (ref_first_ts): {ref_first_timestamp:.3f}s',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_and_adjust] 设备首个时间戳 (device_first_ts): {device_first_timestamp:.3f}s',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_and_adjust] 有效偏移量 (effective_offset): {effective_offset:.3f}s',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_and_adjust] ==============================', category='engine')

        if abs(effective_offset) < 0.001:
            log_not_emit('INFO', 'device_collector',
                         '[_calculate_effective_offset_and_adjust] effective_offset ~= 0, no adjustment needed',
                         category='engine')
            return reference_params

        adjusted = self._rttm_utils._apply_single_offset(reference_params, effective_offset)
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_and_adjust] Adjustment applied, returning adjusted params',
                     category='engine')
        return adjusted

    def _get_device_first_timestamp(self, all_results, algorithm_type=None):
        """从设备结果中提取首个时间戳

        优先从 STM 获取（包含文本），其次 RTTM。
        优先使用数据库配置动态查找字段名，失败时后缀扫描兜底。

        Args:
            all_results: 设备结果列表
            algorithm_type: 算法类型（可选，用于动态查找字段名）

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        log_not_emit('DEBUG', 'device_collector',
                     f'[_get_device_first_timestamp] START: all_results count={len(all_results)}', category='engine')

        for idx, res in enumerate(all_results):
            raw_results = res.get('raw_results', {})
            if not raw_results:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp] result[{idx}]: raw_results is empty', category='engine')
                continue

            stm_content, rttm_content = self._rttm_utils._get_stm_rttm_content_from_result(raw_results, algorithm_type)

            log_not_emit('DEBUG', 'device_collector',
                         f'[_get_device_first_timestamp] result[{idx}]: rttm_len={len(rttm_content) if rttm_content else 0}, stm_len={len(stm_content) if stm_content else 0}',
                         category='engine')

            # 优先使用 STM（包含文本内容）
            if stm_content:
                ts = self._rttm_utils._extract_first_timestamp_from_text(stm_content, 'stm')
                if ts is not None:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_device_first_timestamp] result[{idx}]: Found device timestamp from STM: {ts:.3f}s',
                                 category='engine')
                    return ts

            # 回退到 RTTM
            if rttm_content:
                ts = self._rttm_utils._extract_first_timestamp_from_text(rttm_content, 'rttm')
                if ts is not None:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_device_first_timestamp] result[{idx}]: Found device timestamp from RTTM: {ts:.3f}s',
                                 category='engine')
                    return ts

        log_not_emit('WARNING', 'device_collector',
                     '[_get_device_first_timestamp] No valid timestamp found in device results', category='engine')
        return None

    def _get_device_first_timestamp_from_result(self, extracted_result, algorithm_type=None):
        """从单个设备提取结果中提取首个时间戳

        优先使用数据库配置动态查找字段名，失败时后缀扫描兜底。

        Args:
            extracted_result: 设备驱动提取的单个结果
            algorithm_type: 算法类型（可选，用于动态查找字段名）

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        if not extracted_result:
            return None

        stm_content, rttm_content = self._rttm_utils._get_stm_rttm_content_from_result(extracted_result, algorithm_type)

        # 优先使用 STM（包含文本内容）
        if stm_content:
            ts = self._rttm_utils._extract_first_timestamp_from_text(stm_content, 'stm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp_from_result] from stm: {ts:.3f}', category='engine')
                return ts

        # 回退到 RTTM
        if rttm_content:
            ts = self._rttm_utils._extract_first_timestamp_from_text(rttm_content, 'rttm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp_from_result] from rttm: {ts:.3f}', category='engine')
                return ts

        log_not_emit('WARNING', 'device_collector',
                     '[_get_device_first_timestamp_from_result] No valid timestamp found in extracted_result',
                     category='engine')
        return None

    def _detect_missing_segments(self, device_segments, ref_segments):
        """检测是否存在丢句

        通过比较设备片段数与参考片段数、以及总时长比率来判断

        Args:
            device_segments: 设备片段列表
            ref_segments: 参考片段列表

        Returns:
            dict: {
                'detected': bool,
                'confidence': str ('high'/'medium'/'low'/'none'),
                'count_diff': int,
                'device_count': int,
                'ref_count': int,
                'duration_ratio': float,
                'description': str
            }
        """
        result = {
            'detected': False,
            'confidence': 'none',
            'count_diff': 0,
            'device_count': len(device_segments),
            'ref_count': len(ref_segments),
            'duration_ratio': 1.0,
            'description': ''
        }

        if not device_segments or not ref_segments:
            result['description'] = '片段列表为空，无法检测丢句'
            return result

        count_diff = len(ref_segments) - len(device_segments)
        result['count_diff'] = count_diff

        device_total_dur = sum(seg['end'] - seg['start'] for seg in device_segments)
        ref_total_dur = sum(seg['end'] - seg['start'] for seg in ref_segments)

        duration_ratio = device_total_dur / ref_total_dur if ref_total_dur > 0 else 1.0
        result['duration_ratio'] = round(duration_ratio, 3)

        if count_diff <= 0:
            result['description'] = f'设备片段数({len(device_segments)}) >= 参考片段数({len(ref_segments)})，未检测到丢句'
            return result

        # count_diff > 0: 设备片段比参考少
        if duration_ratio < 0.75 and count_diff >= 2:
            result['detected'] = True
            result['confidence'] = 'high'
        elif duration_ratio < 0.9 and count_diff >= 1:
            result['detected'] = True
            result['confidence'] = 'medium'
        else:
            result['detected'] = True
            result['confidence'] = 'low'

        result['description'] = (
            f'设备片段数({len(device_segments)}) < 参考片段数({len(ref_segments)}), '
            f'差异: {count_diff}, 时长比: {duration_ratio:.2f}, 置信度: {result["confidence"]}'
        )

        log_not_emit('WARNING', 'device_collector',
                     f'[_detect_missing_segments] {result["description"]}', category='engine')

        return result

    def _validate_offset_reasonable(self, offset, ref_segments):
        """校验偏移量是否合理：应用后参考首个片段不应出现显著负数时间戳

        Args:
            offset: 待校验的偏移量
            ref_segments: 参考片段列表

        Returns:
            bool: True 表示偏移量合理，False 表示不合理
        """
        if not ref_segments:
            return True

        first_ref_start = min(seg['start'] for seg in ref_segments)
        adjusted_first_start = first_ref_start + offset

        if adjusted_first_start < MIN_REF_START_TIME:
            log_not_emit('WARNING', 'device_collector',
                         f'[_validate_offset_reasonable] 偏移量 {offset:.3f}s 不合理: '
                         f'参考首个片段 start={first_ref_start:.3f}s, '
                         f'调整后={adjusted_first_start:.3f}s < {MIN_REF_START_TIME}s',
                         category='engine')
            return False

        return True

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
        """计算两个文本的相似度（SequenceMatcher 字符级序列匹配）

        Args:
            text_a: 文本A
            text_b: 文本B

        Returns:
            float: 相似度 (0.0-1.0)
        """
        if not text_a or not text_b:
            return 0.0

        text_a = text_a.strip().lower()
        text_b = text_b.strip().lower()

        if len(text_a) < 3 or len(text_b) < 3:
            return 0.0

        return difflib.SequenceMatcher(None, text_a, text_b).ratio()

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

    def _align_by_content(self, device_segments, ref_segments):
        """基于文本内容的动态规划对齐

        使用 SequenceMatcher 构建 N×M 相似度矩阵，通过 DP 找到最优的
        设备-参考片段配对路径，从匹配对的时间差中计算鲁棒的偏移量。

        Args:
            device_segments: 设备片段列表 (each has 'start', 'end', 'text')
            ref_segments: 参考片段列表 (each has 'start', 'end', 'text')

        Returns:
            tuple: (offset, confidence, details_dict)
                - offset: float or None (None if alignment failed)
                - confidence: float (0.0-1.0)
                - details_dict: {
                    'matched_pairs': [(dev_idx, ref_idx, similarity, offset)],
                    'skipped_device': int,
                    'skipped_ref': int,
                  }
        """
        empty_details = {'matched_pairs': [], 'skipped_device': 0, 'skipped_ref': 0}

        if not device_segments or not ref_segments:
            return None, 0.0, empty_details

        # 提取文本
        d_texts = [seg.get('text', '').strip() for seg in device_segments]
        r_texts = [seg.get('text', '').strip() for seg in ref_segments]

        if not any(d_texts) or not any(r_texts):
            return None, 0.0, empty_details

        N = len(device_segments)
        M = len(ref_segments)

        # DP 对齐
        sim, dp, traceback = self._build_dp_alignment(d_texts, r_texts, device_segments, ref_segments, N, M)

        # 回溯
        matched_pairs, skipped_device, skipped_ref = self._backtrace_dp(
            traceback, sim, device_segments, ref_segments, N, M
        )

        if len(matched_pairs) < MIN_CONTENT_MATCH_PAIRS:
            details = {'matched_pairs': matched_pairs, 'skipped_device': skipped_device, 'skipped_ref': skipped_ref}
            return None, 0.0, details

        # 计算偏移量和置信度
        return self._compute_offset_and_confidence(matched_pairs, skipped_device, skipped_ref, N)

    def _build_dp_alignment(self, d_texts, r_texts, device_segments, ref_segments, N, M):
        """构建 DP 对齐表"""
        sim = [[0.0] * M for _ in range(N)]
        for i in range(N):
            if not d_texts[i]:
                continue
            for j in range(M):
                if not r_texts[j]:
                    continue
                sim[i][j] = self._compute_text_similarity(d_texts[i], r_texts[j])

        dp = [[0.0] * (M + 1) for _ in range(N + 1)]
        traceback = [[''] * (M + 1) for _ in range(N + 1)]

        for i in range(1, N + 1):
            for j in range(1, M + 1):
                match_score = float('-inf')
                if sim[i - 1][j - 1] >= MIN_TEXT_SIMILARITY:
                    time_penalty = max(
                        -0.01 * abs(device_segments[i - 1]['start'] - ref_segments[j - 1]['start']),
                        -0.5
                    )
                    match_score = dp[i - 1][j - 1] + sim[i - 1][j - 1] + time_penalty

                skip_ref_score = dp[i][j - 1] + CONTENT_ALIGNMENT_SKIP_PENALTY
                skip_dev_score = dp[i - 1][j] + CONTENT_ALIGNMENT_SKIP_PENALTY

                best = max(match_score, skip_ref_score, skip_dev_score)
                dp[i][j] = best

                if best == match_score:
                    traceback[i][j] = 'match'
                elif best == skip_ref_score:
                    traceback[i][j] = 'skip_ref'
                else:
                    traceback[i][j] = 'skip_device'

        return sim, dp, traceback

    def _backtrace_dp(self, traceback, sim, device_segments, ref_segments, N, M):
        """回溯 DP 表恢复对齐路径"""
        matched_pairs = []
        skipped_device = 0
        skipped_ref = 0
        i, j = N, M
        while i > 0 and j > 0:
            action = traceback[i][j]
            if action == 'match':
                dev_idx = i - 1
                ref_idx = j - 1
                pair_offset = device_segments[dev_idx]['start'] - ref_segments[ref_idx]['start']
                matched_pairs.append((dev_idx, ref_idx, sim[dev_idx][ref_idx], pair_offset))
                i -= 1
                j -= 1
            elif action == 'skip_ref':
                skipped_ref += 1
                j -= 1
            elif action == 'skip_device':
                skipped_device += 1
                i -= 1
            else:
                break
        while i > 0:
            skipped_device += 1
            i -= 1
        while j > 0:
            skipped_ref += 1
            j -= 1
        matched_pairs.reverse()
        return matched_pairs, skipped_device, skipped_ref

    def _compute_offset_and_confidence(self, matched_pairs, skipped_device, skipped_ref, N):
        """从匹配对计算偏移量和置信度"""
        offsets = [p[3] for p in matched_pairs]
        median_offset = statistics.median(offsets)

        filtered_pairs = [
            p for p in matched_pairs
            if abs(p[3] - median_offset) <= CONTENT_OUTLIER_OFFSET_THRESHOLD
        ]

        if len(filtered_pairs) < MIN_CONTENT_MATCH_PAIRS:
            details = {'matched_pairs': matched_pairs, 'skipped_device': skipped_device, 'skipped_ref': skipped_ref}
            return None, 0.0, details

        final_offset = statistics.median([p[3] for p in filtered_pairs])

        avg_similarity = statistics.mean([p[2] for p in filtered_pairs])
        unique_device_matched = len(set(p[0] for p in filtered_pairs))
        device_coverage = unique_device_matched / N

        if len(filtered_pairs) >= 3:
            offset_stdev = statistics.stdev([p[3] for p in filtered_pairs])
            offset_consistency = max(0.0, 1.0 - offset_stdev / CONTENT_OUTLIER_OFFSET_THRESHOLD)
        else:
            offsets = [p[3] for p in filtered_pairs]
            offset_consistency = max(0.0, 1.0 - abs(offsets[0] - offsets[1]) / CONTENT_OUTLIER_OFFSET_THRESHOLD)

        confidence = avg_similarity * device_coverage * offset_consistency

        details = {
            'matched_pairs': filtered_pairs,
            'skipped_device': skipped_device,
            'skipped_ref': skipped_ref,
        }
        return final_offset, confidence, details

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
            if overlap > max_overlap or (overlap == max_overlap and abs(offset) < abs(best_offset)):
                max_overlap = overlap
                best_offset = offset

        return best_offset, max_overlap

    def _validate_offset_by_gap_pattern(self, device_segments, ref_segments, max_offset=MAX_ALIGNMENT_OFFSET):
        """基于间隙模式滑动窗口匹配验证/计算偏移量

        利用相邻片段之间的时间间隙作为指纹，通过滑动窗口匹配找到正确的对应位置。
        即使首句丢失，后续句子之间的间隙模式不变，仍能正确匹配。

        Args:
            device_segments: 设备片段列表
            ref_segments: 参考片段列表
            max_offset: 最大偏移量限制（秒）

        Returns:
            tuple: (best_offset, match_score) -- 无法确定时返回 (None, 0.0)
        """
        if not device_segments or not ref_segments:
            return None, 0.0

        if len(device_segments) < GAP_PATTERN_MIN_SEGMENTS or len(ref_segments) < GAP_PATTERN_MIN_SEGMENTS:
            return None, 0.0

        # 计算间隙序列
        ref_gaps = [ref_segments[i + 1]['start'] - ref_segments[i]['end'] for i in range(len(ref_segments) - 1)]
        device_gaps = [device_segments[i + 1]['start'] - device_segments[i]['end'] for i in range(len(device_segments) - 1)]

        if len(device_gaps) < 2 or len(ref_gaps) < 2:
            return None, 0.0

        # 设备间隙比参考间隙多，不适合滑动窗口
        if len(device_gaps) > len(ref_gaps):
            return None, 0.0

        # 滑动窗口匹配
        best_score = -1.0
        second_best_score = -1.0
        best_k = 0

        max_k = len(ref_gaps) - len(device_gaps)
        for k in range(max_k + 1):
            ref_window = ref_gaps[k:k + len(device_gaps)]
            score = sum(1.0 / (1.0 + abs(dg - rw)) for dg, rw in zip(device_gaps, ref_window))

            if score > best_score:
                second_best_score = best_score
                best_score = score
                best_k = k
            elif score > second_best_score:
                second_best_score = score

        # 归一化得分
        normalized_score = best_score / len(device_gaps) if len(device_gaps) > 0 else 0.0

        # 唯一性检查：最高分与次高分差距 < 10% 则有歧义
        if best_score > 0 and second_best_score > 0:
            if (best_score - second_best_score) / best_score < 0.10:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_validate_offset_by_gap_pattern] 匹配有歧义: best={best_score:.3f}, second={second_best_score:.3f}',
                             category='engine')
                return None, 0.0

        # 计算偏移量
        offset = device_segments[0]['start'] - ref_segments[best_k]['start']

        if abs(offset) > max_offset:
            log_not_emit('DEBUG', 'device_collector',
                         f'[_validate_offset_by_gap_pattern] 偏移量 {offset:.3f}s 超出范围 {max_offset}s',
                         category='engine')
            return None, 0.0

        log_not_emit('INFO', 'device_collector',
                     f'[_validate_offset_by_gap_pattern] 匹配成功: offset={offset:.3f}s, score={normalized_score:.3f}, best_k={best_k}',
                     category='engine')

        return offset, normalized_score

    def _get_reference_first_timestamp(self, reference_params):
        """从参考参数中提取首个时间戳

        Args:
            reference_params: 参考参数列表

        Returns:
            float: 首个时间戳，如果无法提取则返回 None
        """
        log_not_emit('DEBUG', 'device_collector',
                     f'[_get_reference_first_timestamp] START: reference_params count={len(reference_params)}',
                     category='engine')

        for param_idx, param in enumerate(reference_params):
            if not isinstance(param, dict):
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_reference_first_timestamp] param[{param_idx}]: not a dict, skip',
                             category='engine')
                continue

            log_not_emit('DEBUG', 'device_collector',
                         f'[_get_reference_first_timestamp] param[{param_idx}]: keys={list(param.keys())}',
                         category='engine')

            value = param.get('value')
            if not value or not isinstance(value, dict):
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_reference_first_timestamp] param[{param_idx}]: no valid value, skip',
                             category='engine')
                continue

            segments = value.get('segments') or value.get('json', [])
            if segments and isinstance(segments, list) and len(segments) > 0:
                first_seg = segments[0]
                if isinstance(first_seg, dict) and 'start' in first_seg:
                    ts = float(first_seg['start'])
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}]: Found reference timestamp from segments[0]: {ts:.3f}s',
                                 category='engine')
                    return ts
                else:
                    log_not_emit('DEBUG', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}]: first_seg has no start, seg_keys={list(first_seg.keys()) if isinstance(first_seg, dict) else type(first_seg)}',
                                 category='engine')

            text = value.get('text', '')
            format_type = value.get('format', '')
            if text and format_type in ['rttm', 'stm']:
                ts = self._rttm_utils._extract_first_timestamp_from_text(text, format_type)
                if ts is not None:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}]: Found reference timestamp from text ({format_type}): {ts:.3f}s',
                                 category='engine')
                    return ts
            else:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_reference_first_timestamp] param[{param_idx}]: text={len(text) if text else 0}, format={format_type}',
                             category='engine')

        log_not_emit('WARNING', 'device_collector',
                     '[_get_reference_first_timestamp] No valid timestamp found in reference params', category='engine')
        return None

