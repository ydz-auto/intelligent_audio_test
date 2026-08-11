"""时间戳对齐策略

兼容性入口：将原 timestamp_aligner.py 拆分为以下子模块：
- constants: 对齐常量
- _segment_helpers: 片段检测、校验、采样、重叠计算
- _content_alignment: 文本内容对齐（DP）
- _offset_strategies: 偏移量计算策略
- _timestamp_helpers: 设备/参考时间戳提取
- _strategies: 对齐策略编排
- aligner: TimestampAligner 主类
"""

from .aligner import TimestampAligner
from .constants import (
    MAX_ALIGNMENT_OFFSET,
    MIN_OVERLAP_THRESHOLD,
    MAX_CANDIDATE_PAIRS,
    MIN_GAP_MATCH_TOLERANCE,
    GAP_PATTERN_MIN_SEGMENTS,
    MIN_REF_START_TIME,
    MIN_TEXT_SIMILARITY,
    MIN_CONTENT_MATCH_PAIRS,
    CONTENT_ALIGNMENT_SKIP_PENALTY,
    CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD,
    CONTENT_OUTLIER_OFFSET_THRESHOLD,
)

__all__ = [
    'TimestampAligner',
    'MAX_ALIGNMENT_OFFSET',
    'MIN_OVERLAP_THRESHOLD',
    'MAX_CANDIDATE_PAIRS',
    'MIN_GAP_MATCH_TOLERANCE',
    'GAP_PATTERN_MIN_SEGMENTS',
    'MIN_REF_START_TIME',
    'MIN_TEXT_SIMILARITY',
    'MIN_CONTENT_MATCH_PAIRS',
    'CONTENT_ALIGNMENT_SKIP_PENALTY',
    'CONTENT_ALIGNMENT_CONFIDENCE_THRESHOLD',
    'CONTENT_OUTLIER_OFFSET_THRESHOLD',
]
