import threading
import copy
import json
import difflib
import statistics
from backend.algorithm.field_mapper import get_field_mapper
from backend.utils.log_handler import log_not_emit

MAX_ALIGNMENT_OFFSET = 30.0
MIN_OVERLAP_THRESHOLD = 0.5
MAX_CANDIDATE_PAIRS = 100
MIN_GAP_MATCH_TOLERANCE = 0.5    # 间隙匹配容差(秒)
GAP_PATTERN_MIN_SEGMENTS = 3     # gap_pattern 策略所需最少片段数
MIN_REF_START_TIME = -0.5       # 调整后参考首个片段允许的最小起始时间(秒)
MIN_TEXT_SIMILARITY = 0.3                        # SequenceMatcher 最小匹配相似度
MIN_CONTENT_MATCH_PAIRS = 2                       # 内容对齐所需最少匹配对数
CONTENT_ALIGNMENT_SKIP_PENALTY = -0.1             # DP 跳段惩罚
CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD = 0.5      # 内容对齐最低置信度阈值
CONTENT_OUTLIER_OFFSET_THRESHOLD = 2.0            # 偏移量离群值过滤阈值(秒)


class DeviceResultCollector:
    """设备结果采集器基类"""

    def __init__(self):
        self.field_mapper = get_field_mapper()

    def collect_raw_results(self, task_id, test_case_id, device_info_list, extra_params, log_callback=None, **kwargs):
        """采集原始结果

        Args:
            task_id: 任务ID
            test_case_id: 测试用例ID
            device_info_list: 设备信息列表
            extra_params: 额外参数
            log_callback: 日志回调函数 fn(level, content, task_id, device_id)
            **kwargs: 额外参数，包含 case_reference_params 等

        Returns:
            list: 原始结果列表
        """
        playback_time_offsets = extra_params.get('playback_time_offsets', {})
        reference_params = extra_params.get('reference_params')
        algorithm_type = extra_params.get('algorithm_type') or kwargs.get('algorithm_type')

        log_not_emit('DEBUG', 'device_collector',
                     f'[collect_raw_results] playback_time_offsets={bool(playback_time_offsets)}, reference_params={bool(reference_params)}',
                     category='engine')

        all_results = []

        for idx, info in enumerate(device_info_list):
            res = {
                'device_id': info["device_id"],
                'device_name': info["device_name"],
                'device_sn': info["device_sn"]
            }
            try:
                if info["driver"]:
                    merged_params = {**extra_params, **kwargs}
                    raw_results = info["driver"].get_results(
                        info["device_sn"],
                        task_id=task_id,
                        test_case_id=test_case_id,
                        **merged_params
                    )

                    if isinstance(raw_results, list):
                        log_not_emit('DEBUG', 'device_collector', f'raw_results is list, length={len(raw_results)}',
                                     category='engine')
                        import copy
                        for result_idx, result_item in enumerate(raw_results):
                            log_not_emit('DEBUG', 'device_collector',
                                         f'result_item[{result_idx}] id: {id(result_item)}, keys: {list(result_item.keys())[:10]}',
                                         category='engine')
                            log_not_emit('DEBUG', 'device_collector',
                                         f'result_item[{result_idx}] str[:200]: {str(result_item)[:200]}',
                                         category='engine')
                            item_res = res.copy()
                            copied_item = copy.deepcopy(result_item)
                            log_not_emit('DEBUG', 'device_collector',
                                         f'copied_item[{result_idx}] id: {id(copied_item)}, keys: {list(copied_item.keys())[:10]}',
                                         category='engine')
                            item_res['raw_results'] = copied_item
                            log_not_emit('DEBUG', 'device_collector',
                                         f'item_res[{result_idx}][raw_results] id: {id(item_res["raw_results"])}, keys: {list(item_res["raw_results"].keys())[:10]}',
                                         category='engine')
                            item_res['result_type'] = result_item.get('result_type', 'default')
                            log_not_emit('DEBUG', 'device_collector',
                                         f'before append item_res[{result_idx}] id: {id(item_res)}, raw_results id: {id(item_res["raw_results"])}',
                                         category='engine')

                            alignment_result = self._calculate_effective_offset_for_single_result(
                                result_item, reference_params, playback_time_offsets, algorithm_type
                            )
                            item_res['adjusted_reference_params'] = alignment_result.get('adjusted_params')
                            item_res['alignment_info'] = alignment_result.get('alignment_info')

                            all_results.append(item_res)
                            log_not_emit('DEBUG', 'device_collector',
                                         f'after append all_results[{result_idx}] raw_results id: {id(all_results[-1]["raw_results"])}, keys: {list(all_results[-1]["raw_results"].keys())[:5]}',
                                         category='engine')
                        continue

                    res['raw_results'] = raw_results or {}
                    res['result_type'] = 'default'

                    alignment_result = self._calculate_effective_offset_for_single_result(
                        raw_results, reference_params, playback_time_offsets, algorithm_type
                    )
                    res['adjusted_reference_params'] = alignment_result.get('adjusted_params')
                    res['alignment_info'] = alignment_result.get('alignment_info')

            except Exception as e:
                if log_callback:
                    log_callback('ERROR', f"采集结果失败: {str(e)}", task_id, info["device_id"])
            all_results.append(res)

        log_not_emit('DEBUG', 'device_collector',
                     f'FINAL before return: all_results id={id(all_results)}, count={len(all_results)}',
                     category='engine')

        import copy
        return copy.deepcopy(all_results)

    def _calculate_effective_offset_for_single_result(self, raw_results, reference_params, playback_time_offsets, algorithm_type=None):
        """为单个设备结果计算 effective_offset 并调整参考参数

        每个设备分别计算 offset，因为不同设备可能有不同的 VAD 处理

        采用混合对齐策略：
        0. 优先使用文本内容对齐（DP 序列匹配）
        1. 最大重叠对齐（处理丢句/多句场景）
        2. 如果 max_overlap 未通过，尝试间隙模式匹配验证
        3. 回退到首个时间戳对齐（含丢句安全检查）
        4. 最终兜底使用 playback_time_offsets

        Args:
            raw_results: 单个设备的原始结果
            reference_params: 参考参数列表
            playback_time_offsets: 系统测量的播放时间偏移
            algorithm_type: 算法类型（可选，用于动态查找设备输出字段名）

        Returns:
            dict: {
                'adjusted_params': 调整后的参考参数列表,
                'alignment_info': {
                    'method': 'content_alignment' | 'max_overlap' | 'gap_pattern' | 'first_timestamp' | 'fallback' | 'none',
                    'offset': float,
                    'max_overlap': float (仅max_overlap方法),
                    'device_segment_count': int,
                    'ref_segment_count': int,
                    'device_first_ts': float,
                    'ref_first_ts': float,
                    'missing_segment_detected': bool,
                    'missing_segment_detail': str,
                    'gap_pattern_offset': float|None,
                    'gap_pattern_match_score': float|None,
                    'first_timestamp_reliability': str,
                    'content_alignment_score': float|None,
                    'content_matched_pairs': int,
                    'content_skipped_device': int,
                    'content_skipped_ref': int
                }
            }
        """
        alignment_info = {
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

        if not reference_params:
            log_not_emit('WARNING', 'device_collector',
                         '[_calculate_effective_offset_for_single_result] reference_params is empty', category='engine')
            return {'adjusted_params': None, 'alignment_info': alignment_info}

        device_segments = self._extract_segments_from_result(raw_results, algorithm_type)
        ref_segments = self._extract_segments_from_reference(reference_params)

        alignment_info['device_segment_count'] = len(device_segments)
        alignment_info['ref_segment_count'] = len(ref_segments)

        # ========== 丢句预检测 ==========
        missing_info = self._detect_missing_segments(device_segments, ref_segments)
        alignment_info['missing_segment_detected'] = missing_info['detected']
        alignment_info['missing_segment_detail'] = missing_info['description']

        # ========== 策略0: content_alignment (文本内容对齐) ==========
        content_offset, content_confidence, content_details = self._align_by_content(
            device_segments, ref_segments
        )

        alignment_info['content_alignment_score'] = content_confidence
        alignment_info['content_matched_pairs'] = len(content_details.get('matched_pairs', []))
        alignment_info['content_skipped_device'] = content_details.get('skipped_device', 0)
        alignment_info['content_skipped_ref'] = content_details.get('skipped_ref', 0)

        if (content_offset is not None
                and content_confidence >= CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD):
            if not self._validate_offset_reasonable(content_offset, ref_segments):
                log_not_emit('WARNING', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] content_alignment 偏移量 {content_offset:.3f}s 不合理, 跳过',
                             category='engine')
            else:
                log_not_emit('INFO', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] ===== CONTENT ALIGNMENT =====',
                             category='engine')
                log_not_emit('INFO', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] 偏移量: {content_offset:.3f}s, '
                             f'置信度: {content_confidence:.3f}, 匹配对数: {len(content_details["matched_pairs"])}',
                             category='engine')

                alignment_info['method'] = 'content_alignment'
                alignment_info['offset'] = content_offset

                if abs(content_offset) < 0.001:
                    alignment_info['method'] = 'content_alignment_no_adjustment'
                    return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

                adjusted = self._apply_single_offset(reference_params, content_offset)
                return {'adjusted_params': adjusted, 'alignment_info': alignment_info}
        else:
            if content_offset is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] 内容对齐置信度不足: '
                             f'offset={content_offset}, confidence={content_confidence:.3f}',
                             category='engine')

        # ========== 策略1: max_overlap ==========
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

            log_not_emit('INFO', 'device_collector',
                         f'[_calculate_effective_offset_for_single_result] ===== MAX OVERLAP ALIGNMENT =====',
                         category='engine')
            log_not_emit('INFO', 'device_collector',
                         f'[_calculate_effective_offset_for_single_result] 设备片段数: {len(device_segments)}, 参考片段数: {len(ref_segments)}',
                         category='engine')
            log_not_emit('INFO', 'device_collector',
                         f'[_calculate_effective_offset_for_single_result] 最优偏移量: {best_offset:.3f}s, 最大重叠时间: {max_overlap:.3f}s',
                         category='engine')

            if max_overlap >= MIN_OVERLAP_THRESHOLD:
                # 校验偏移量合理性：防止参考时间戳变为负数
                if not self._validate_offset_reasonable(best_offset, ref_segments):
                    log_not_emit('WARNING', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] max_overlap 偏移量 {best_offset:.3f}s 不合理(会导致参考负数时间戳), 跳过',
                                 category='engine')
                else:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] 使用最大重叠对齐结果', category='engine')
                    log_not_emit('INFO', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] =================================',
                                 category='engine')

                    if abs(best_offset) < 0.001:
                        alignment_info['method'] = 'max_overlap_no_adjustment'
                        return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

                    adjusted = self._apply_single_offset(reference_params, best_offset)
                    return {'adjusted_params': adjusted, 'alignment_info': alignment_info}
            else:
                log_not_emit('INFO', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] 重叠时间 {max_overlap:.3f}s < 阈值 {MIN_OVERLAP_THRESHOLD}s',
                             category='engine')

        # ========== 策略2: gap_pattern 验证 ==========
        use_gap_pattern = (
                device_segments and
                ref_segments and
                len(device_segments) >= GAP_PATTERN_MIN_SEGMENTS and
                len(ref_segments) >= GAP_PATTERN_MIN_SEGMENTS
        )

        if use_gap_pattern:
            gap_offset, gap_score = self._validate_offset_by_gap_pattern(
                device_segments, ref_segments
            )
            alignment_info['gap_pattern_offset'] = gap_offset
            alignment_info['gap_pattern_match_score'] = gap_score

            if gap_offset is not None and gap_score > 0.5:
                # 校验偏移量合理性
                if not self._validate_offset_reasonable(gap_offset, ref_segments):
                    log_not_emit('WARNING', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] gap_pattern 偏移量 {gap_offset:.3f}s 不合理, 跳过',
                                 category='engine')
                else:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] ===== GAP PATTERN ALIGNMENT =====',
                                 category='engine')
                    log_not_emit('INFO', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] 间隙模式偏移量: {gap_offset:.3f}s, 匹配得分: {gap_score:.3f}',
                                 category='engine')

                    alignment_info['method'] = 'gap_pattern'
                    alignment_info['offset'] = gap_offset

                    if abs(gap_offset) < 0.001:
                        alignment_info['method'] = 'gap_pattern_no_adjustment'
                        return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

                    adjusted = self._apply_single_offset(reference_params, gap_offset)
                    return {'adjusted_params': adjusted, 'alignment_info': alignment_info}
            else:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] 间隙模式验证未通过: offset={gap_offset}, score={gap_score}',
                             category='engine')

        # ========== 策略3: first_timestamp + 丢句感知 ==========
        device_first_ts = self._get_device_first_timestamp_from_result(raw_results, algorithm_type)
        alignment_info['device_first_ts'] = device_first_ts

        if device_first_ts is None:
            log_not_emit('WARNING', 'device_collector',
                         '[_calculate_effective_offset_for_single_result] Cannot get device first timestamp, fallback to playback_time_offsets',
                         category='engine')
            alignment_info['method'] = 'fallback'
            fallback_result = self._apply_fallback_offset(reference_params, playback_time_offsets)
            return {'adjusted_params': fallback_result, 'alignment_info': alignment_info}

        ref_first_ts = self._get_reference_first_timestamp(reference_params)
        alignment_info['ref_first_ts'] = ref_first_ts

        if ref_first_ts is None:
            log_not_emit('WARNING', 'device_collector',
                         '[_calculate_effective_offset_for_single_result] Cannot get reference first timestamp',
                         category='engine')
            return {'adjusted_params': None, 'alignment_info': alignment_info}

        # 保存 max_overlap 结果供丢句场景使用（在覆盖 alignment_info 之前）
        prev_max_overlap_value = alignment_info.get('max_overlap')
        prev_max_overlap_offset = alignment_info.get('offset') if alignment_info.get('method') == 'max_overlap' else None

        effective_offset = device_first_ts - ref_first_ts
        alignment_info['method'] = 'first_timestamp'
        alignment_info['offset'] = effective_offset

        # first_timestamp 可靠性评估
        if missing_info['detected'] and missing_info['confidence'] in ('high', 'medium'):
            alignment_info['first_timestamp_reliability'] = 'low'
        elif missing_info['detected']:
            alignment_info['first_timestamp_reliability'] = 'medium'
        else:
            alignment_info['first_timestamp_reliability'] = 'high'

        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_for_single_result] ===== FIRST TIMESTAMP ALIGNMENT =====',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_for_single_result] 参考首个时间戳 (ref_first_ts): {ref_first_ts:.3f}s',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_for_single_result] 设备首个时间戳 (device_first_ts): {device_first_ts:.3f}s',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_for_single_result] 有效偏移量 (effective_offset): {effective_offset:.3f}s',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_for_single_result] 可靠性: {alignment_info["first_timestamp_reliability"]}',
                     category='engine')
        log_not_emit('INFO', 'device_collector',
                     f'[_calculate_effective_offset_for_single_result] ======================================',
                     category='engine')

        # 丢句场景: first_timestamp 不可信，优先使用之前已算出的 max_overlap 结果
        if missing_info['detected']:
            # 虽然 max_overlap 未通过 MIN_OVERLAP_THRESHOLD，但在丢句场景下它比 first_timestamp 更可靠
            if prev_max_overlap_value is not None and prev_max_overlap_value > 0 and prev_max_overlap_offset is not None:
                log_not_emit('WARNING', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] 检测到丢句, first_timestamp 不可信, '
                             f'回退使用 max_overlap 结果: offset={prev_max_overlap_offset:.3f}s, overlap={prev_max_overlap_value:.3f}s',
                             category='engine')
                alignment_info['method'] = 'max_overlap_fallback'
                alignment_info['offset'] = prev_max_overlap_offset

                if not self._validate_offset_reasonable(prev_max_overlap_offset, ref_segments):
                    log_not_emit('WARNING', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] max_overlap fallback 偏移量 {prev_max_overlap_offset:.3f}s 也不合理',
                                 category='engine')
                else:
                    if abs(prev_max_overlap_offset) < 0.001:
                        return {'adjusted_params': reference_params, 'alignment_info': alignment_info}
                    adjusted = self._apply_single_offset(reference_params, prev_max_overlap_offset)
                    return {'adjusted_params': adjusted, 'alignment_info': alignment_info}

            # 无可用 max_overlap 结果，对 first_timestamp 做重叠验证
            if device_segments and ref_segments:
                adjusted_ref_for_check = [
                    {'start': seg['start'] + effective_offset, 'end': seg['end'] + effective_offset}
                    for seg in ref_segments
                ]
                check_overlap = self._compute_total_overlap(device_segments, adjusted_ref_for_check)
                total_device_dur = sum(s['end'] - s['start'] for s in device_segments)
                overlap_ratio = check_overlap / total_device_dur if total_device_dur > 0 else 0

                log_not_emit('INFO', 'device_collector',
                             f'[_calculate_effective_offset_for_single_result] 丢句场景 first_timestamp 验证: '
                             f'offset={effective_offset:.3f}s, 重叠={check_overlap:.3f}s, 重叠率={overlap_ratio:.2f}',
                             category='engine')

                if overlap_ratio < 0.5:
                    log_not_emit('WARNING', 'device_collector',
                                 f'[_calculate_effective_offset_for_single_result] first_timestamp 验证失败(重叠率={overlap_ratio:.2f} < 0.5), '
                                 f'检测到丢句, 该偏移量不可信, 尝试使用 playback_time_offsets',
                                 category='engine')
                    alignment_info['method'] = 'fallback'
                    fallback_result = self._apply_fallback_offset(reference_params, playback_time_offsets)
                    if fallback_result:
                        return {'adjusted_params': fallback_result, 'alignment_info': alignment_info}

        # first_timestamp 偏移量合理性校验
        if not self._validate_offset_reasonable(effective_offset, ref_segments):
            log_not_emit('WARNING', 'device_collector',
                         f'[_calculate_effective_offset_for_single_result] first_timestamp 偏移量 {effective_offset:.3f}s 不合理'
                         f'(会导致参考负数时间戳), 尝试使用 playback_time_offsets',
                         category='engine')
            alignment_info['method'] = 'fallback'
            fallback_result = self._apply_fallback_offset(reference_params, playback_time_offsets)
            if fallback_result:
                return {'adjusted_params': fallback_result, 'alignment_info': alignment_info}

        if abs(effective_offset) < 0.001:
            log_not_emit('INFO', 'device_collector',
                         '[_calculate_effective_offset_for_single_result] effective_offset ~= 0, no adjustment needed',
                         category='engine')
            alignment_info['method'] = 'first_timestamp_no_adjustment'
            return {'adjusted_params': reference_params, 'alignment_info': alignment_info}

        adjusted = self._apply_single_offset(reference_params, effective_offset)
        log_not_emit('INFO', 'device_collector', f'[_calculate_effective_offset_for_single_result] Adjustment applied',
                     category='engine')
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
            return self._apply_fallback_offset(reference_params, playback_time_offsets)

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

        adjusted = self._apply_single_offset(reference_params, effective_offset)
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

            stm_content, rttm_content = self._get_stm_rttm_content_from_result(raw_results, algorithm_type)

            log_not_emit('DEBUG', 'device_collector',
                         f'[_get_device_first_timestamp] result[{idx}]: rttm_len={len(rttm_content) if rttm_content else 0}, stm_len={len(stm_content) if stm_content else 0}',
                         category='engine')

            # 优先使用 STM（包含文本内容）
            if stm_content:
                ts = self._extract_first_timestamp_from_text(stm_content, 'stm')
                if ts is not None:
                    log_not_emit('INFO', 'device_collector',
                                 f'[_get_device_first_timestamp] result[{idx}]: Found device timestamp from STM: {ts:.3f}s',
                                 category='engine')
                    return ts

            # 回退到 RTTM
            if rttm_content:
                ts = self._extract_first_timestamp_from_text(rttm_content, 'rttm')
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

        stm_content, rttm_content = self._get_stm_rttm_content_from_result(extracted_result, algorithm_type)

        # 优先使用 STM（包含文本内容）
        if stm_content:
            ts = self._extract_first_timestamp_from_text(stm_content, 'stm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp_from_result] from stm: {ts:.3f}', category='engine')
                return ts

        # 回退到 RTTM
        if rttm_content:
            ts = self._extract_first_timestamp_from_text(rttm_content, 'rttm')
            if ts is not None:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_device_first_timestamp_from_result] from rttm: {ts:.3f}', category='engine')
                return ts

        log_not_emit('WARNING', 'device_collector',
                     '[_get_device_first_timestamp_from_result] No valid timestamp found in extracted_result',
                     category='engine')
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
                elif format_type == 'stm' and len(parts) >= 4 and parts[0] != 'SPEAKER' and not line.startswith('SPK-'):
                    return float(parts[3])
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

    def _get_stm_rttm_content_from_result(self, result_dict, algorithm_type=None):
        """从结果字典中提取 STM/RTTM 内容

        优先使用数据库配置（algorithm_device_params 的 param_type）动态查找字段名，
        失败时按后缀（*_stm_content / *_rttm_content）扫描兜底。

        Args:
            result_dict: 设备结果字典
            algorithm_type: 算法类型（可选，用于从数据库配置动态查找字段名）

        Returns:
            tuple: (stm_content, rttm_content)
        """
        if not result_dict:
            return '', ''

        stm_content = ''
        rttm_content = ''

        # 策略1: 通过数据库配置动态查找字段名
        if algorithm_type and self.field_mapper:
            try:
                stm_codes = self.field_mapper.get_device_output_field_codes_by_type(algorithm_type, 'stm')
                rttm_codes = self.field_mapper.get_device_output_field_codes_by_type(algorithm_type, 'rttm')
                for code in stm_codes:
                    if result_dict.get(code):
                        stm_content = result_dict[code]
                        break
                for code in rttm_codes:
                    if result_dict.get(code):
                        rttm_content = result_dict[code]
                        break
            except Exception as e:
                log_not_emit('DEBUG', 'device_collector',
                             f'[_get_stm_rttm_content] FieldMapper lookup failed: {e}', category='engine')

        # 策略2: 后缀扫描兜底（匹配 *_stm_content / *_rttm_content）
        if not stm_content or not rttm_content:
            for key, value in result_dict.items():
                if not value:
                    continue
                if key.endswith('_stm_content') and not stm_content:
                    stm_content = value
                elif key.endswith('_rttm_content') and not rttm_content:
                    rttm_content = value

        return stm_content, rttm_content

    def _extract_segments_from_result(self, raw_results, algorithm_type=None):
        """从设备结果中提取片段列表

        Args:
            raw_results: 设备驱动提取的结果
            algorithm_type: 算法类型（可选，用于动态查找字段名）

        Returns:
            list: 片段列表
        """
        if not raw_results:
            return []

        stm_content, rttm_content = self._get_stm_rttm_content_from_result(raw_results, algorithm_type)

        # 优先使用 STM（包含文本内容，支持内容对齐）
        if stm_content:
            segments = self._extract_segments_from_text(stm_content, 'stm')
            if segments:
                return segments

        # 回退到 RTTM（无文本内容）
        if rttm_content:
            segments = self._extract_segments_from_text(rttm_content, 'rttm')
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

        # 如果任一侧全部无文本，跳过内容对齐
        if not any(d_texts) or not any(r_texts):
            return None, 0.0, empty_details

        N = len(device_segments)
        M = len(ref_segments)

        # 构建 N×M 相似度矩阵
        sim = [[0.0] * M for _ in range(N)]
        for i in range(N):
            if not d_texts[i]:
                continue
            for j in range(M):
                if not r_texts[j]:
                    continue
                sim[i][j] = self._compute_text_similarity(d_texts[i], r_texts[j])

        # DP 对齐表
        dp = [[0.0] * (M + 1) for _ in range(N + 1)]
        traceback = [[''] * (M + 1) for _ in range(N + 1)]

        for i in range(1, N + 1):
            for j in range(1, M + 1):
                # match: 只有相似度达阈值才允许配对
                match_score = float('-inf')
                if sim[i - 1][j - 1] >= MIN_TEXT_SIMILARITY:
                    # 时间惩罚：防止时间差距过大的荒谬配对
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

        # 回溯恢复对齐路径
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
        # 处理剩余的 i 或 j
        while i > 0:
            skipped_device += 1
            i -= 1
        while j > 0:
            skipped_ref += 1
            j -= 1

        matched_pairs.reverse()

        if len(matched_pairs) < MIN_CONTENT_MATCH_PAIRS:
            details = {'matched_pairs': matched_pairs, 'skipped_device': skipped_device, 'skipped_ref': skipped_ref}
            return None, 0.0, details

        # 计算偏移量：中位数 + 离群值过滤
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

        # 置信度 = 平均相似度 × 设备覆盖率 × 偏移量一致性
        # - 设备覆盖率：设备侧片段是否都被正确匹配了（主要指标）
        # - 偏移量一致性：匹配对算出的 offset 是否紧密一致（排除误匹配）
        # - 不使用参考覆盖率，避免设备严重丢句时置信度被不合理压低
        avg_similarity = statistics.mean([p[2] for p in filtered_pairs])
        unique_device_matched = len(set(p[0] for p in filtered_pairs))
        device_coverage = unique_device_matched / N

        # 偏移量一致性：stdev 越小说明匹配对之间的偏移量越一致
        if len(filtered_pairs) >= 3:
            offsets = [p[3] for p in filtered_pairs]
            offset_stdev = statistics.stdev(offsets)
            offset_consistency = max(0.0, 1.0 - offset_stdev / CONTENT_OUTLIER_OFFSET_THRESHOLD)
        else:
            # 只有 2 对时无法计算 stdev，用差值做简化估计
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

            for test_type in ['api', 'e2e']:
                value = param.get(test_type)
                if not value or not isinstance(value, dict):
                    log_not_emit('DEBUG', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: no valid value, skip',
                                 category='engine')
                    continue

                segments = value.get('segments') or value.get('json', [])
                if segments and isinstance(segments, list) and len(segments) > 0:
                    first_seg = segments[0]
                    if isinstance(first_seg, dict) and 'start' in first_seg:
                        ts = float(first_seg['start'])
                        log_not_emit('INFO', 'device_collector',
                                     f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: Found reference timestamp from segments[0]: {ts:.3f}s',
                                     category='engine')
                        return ts
                    else:
                        log_not_emit('DEBUG', 'device_collector',
                                     f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: first_seg has no start, seg_keys={list(first_seg.keys()) if isinstance(first_seg, dict) else type(first_seg)}',
                                     category='engine')

                text = value.get('text', '')
                format_type = value.get('format', '')
                if text and format_type in ['rttm', 'stm']:
                    ts = self._extract_first_timestamp_from_text(text, format_type)
                    if ts is not None:
                        log_not_emit('INFO', 'device_collector',
                                     f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: Found reference timestamp from text ({format_type}): {ts:.3f}s',
                                     category='engine')
                        return ts
                else:
                    log_not_emit('DEBUG', 'device_collector',
                                 f'[_get_reference_first_timestamp] param[{param_idx}] {test_type}: text={len(text) if text else 0}, format={format_type}',
                                 category='engine')

        log_not_emit('WARNING', 'device_collector',
                     '[_get_reference_first_timestamp] No valid timestamp found in reference params', category='engine')
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

        log_not_emit('DEBUG', 'device_collector', f'[_apply_fallback_offset] Using playback_time_offsets: {offset_val}',
                     category='engine')

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
            log_not_emit('DEBUG', 'device_collector',
                         '[_apply_time_offset_to_reference_params] reference_params is empty, returning as-is',
                         category='engine')
            return reference_params

        log_not_emit('DEBUG', 'device_collector',
                     f'[_apply_time_offset_to_reference_params] reference_params count={len(reference_params)}, offset type={type(offset).__name__}',
                     category='engine')

        offset_dict = {}
        if isinstance(offset, dict):
            log_not_emit('DEBUG', 'device_collector',
                         f'[_apply_time_offset_to_reference_params] offset dict keys={list(offset.keys())}',
                         category='engine')
            for k, v in offset.items():
                if isinstance(v, dict) and 'offset' in v:
                    play_order = v.get('play_order')
                    if play_order is not None:
                        offset_dict[play_order] = v['offset']
                        log_not_emit('DEBUG', 'device_collector',
                                     f'[_apply_time_offset_to_reference_params] Added offset_dict[{play_order}] = {v["offset"]}',
                                     category='engine')
                elif isinstance(v, (int, float)):
                    if isinstance(k, str) and '_' in k:
                        offset_dict[int(k.split('_')[-1])] = v if isinstance(v, int) else float(v)
                        log_not_emit('DEBUG', 'device_collector',
                                     f'[_apply_time_offset_to_reference_params] Added offset_dict from str key[{k.split("_")[-1]}] = {v}',
                                     category='engine')
                    elif isinstance(k, int):
                        offset_dict[k] = v if isinstance(v, int) else float(v)

        log_not_emit('DEBUG', 'device_collector',
                     f'[_apply_time_offset_to_reference_params] Final offset_dict={offset_dict}', category='engine')

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
            log_not_emit('WARNING', 'device_collector', '[_apply_single_offset] reference_params is empty',
                         category='engine')
            return None

        if not isinstance(reference_params, list):
            log_not_emit('WARNING', 'device_collector',
                         f'[_apply_single_offset] reference_params is not a list, type={type(reference_params)}',
                         category='engine')
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

            log_not_emit('DEBUG', 'device_collector',
                         f'[_apply_single_offset] SUCCESS: adjusted {len(adjusted_params)} params', category='engine')
            return adjusted_params

        except Exception as e:
            import traceback
            log_not_emit('ERROR', 'device_collector',
                         f'[_apply_single_offset] FAILED: {str(e)}, traceback: {traceback.format_exc()}',
                         category='engine')
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
            print(
                f"DEBUG convert_results ENTRY: raw_results keys = {list(all_results[0].get('raw_results', {}).keys())}")

        # 深拷贝，防止外部修改
        import copy
        all_results = copy.deepcopy(all_results)

        print(f"DEBUG convert_results AFTER DEEPCOPY: all_results id={id(all_results)}")
        if all_results and len(all_results) > 0:
            print(
                f"DEBUG convert_results AFTER DEEPCOPY: raw_results keys = {list(all_results[0].get('raw_results', {}).keys())}")

        for res in all_results:
            raw_results = res.get('raw_results', {})
            result_type = res.get('result_type', 'default')
            log_not_emit('DEBUG', 'device_collector',
                         f'convert_results: result_type={result_type}, all_results id={id(all_results)}, res id={id(res)}, raw_results id={id(raw_results)}, raw_keys={list(raw_results.keys())[:5]}',
                         category='engine')

            # 添加更多调试信息
            from backend.algorithm.field_mapper import get_field_mapper
            fm = get_field_mapper()
            mapped_fields = fm.get_mapped_device_output_fields(algorithm_type)
            if isinstance(mapped_fields, list):
                log_not_emit('DEBUG', 'device_collector', f'mapped_fields: {[f.get("code") for f in mapped_fields]}',
                             category='engine')
            else:
                log_not_emit('DEBUG', 'device_collector', f'mapped_fields keys: {list(mapped_fields.keys())}',
                             category='engine')

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
