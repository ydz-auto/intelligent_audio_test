"""时间戳对齐器主类

通过组合多个 Mixin 实现完整的时间戳对齐能力：
- SegmentHelperMixin: 片段检测、校验、采样、重叠计算
- ContentAlignmentMixin: 文本内容对齐（DP）
- OffsetStrategyMixin: 偏移量计算策略（最大重叠、间隙模式）
- TimestampHelperMixin: 设备/参考时间戳提取
- StrategyMixin: 对齐策略编排（策略0-3）
"""

from shared.algorithm.field_mapper import get_field_mapper
from shared.utils.log_handler import log_not_emit
from ..rttm_stm_utils import RttmStmUtils
from ._content_alignment import ContentAlignmentMixin
from ._offset_strategies import OffsetStrategyMixin
from ._segment_helpers import SegmentHelperMixin
from ._strategies import StrategyMixin
from ._timestamp_helpers import TimestampHelperMixin


class TimestampAligner(
    SegmentHelperMixin,
    ContentAlignmentMixin,
    OffsetStrategyMixin,
    TimestampHelperMixin,
    StrategyMixin,
):
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
