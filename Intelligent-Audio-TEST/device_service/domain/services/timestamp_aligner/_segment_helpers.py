"""片段检测、校验、采样与重叠计算辅助方法"""

from shared.domain.ports.logging_port import log_not_emit
from .constants import MIN_REF_START_TIME


class SegmentHelperMixin:
    """片段级辅助方法：丢句检测、偏移量合理性校验、重叠计算、采样"""

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
