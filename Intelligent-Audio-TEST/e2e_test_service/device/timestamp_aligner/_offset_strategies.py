"""偏移量计算策略：最大重叠、间隙模式匹配、候选偏移量生成"""

from shared.utils.log_handler import log_not_emit
from .constants import (
    MAX_ALIGNMENT_OFFSET,
    GAP_PATTERN_MIN_SEGMENTS,
)


class OffsetStrategyMixin:
    """偏移量计算策略方法：候选偏移量生成、最大重叠对齐、间隙模式匹配"""

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
