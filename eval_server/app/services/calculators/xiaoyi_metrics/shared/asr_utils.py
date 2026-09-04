# -*- coding: utf-8 -*-
"""xiaoyi_metrics 共享 ASR 工具

抽取 interruption.py 和 non_interactive_latency.py 中完全重复的
chunk 归一化 / 段提取 / 标点过滤逻辑。
"""
import re
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    ASR_USER_SEG_MERGE_GAP_S,
    ASR_MODEL_SEG_MERGE_GAP_S,
    EPS_S,
    PAUSE_MIN_GAP,
    PAUSE_MAX_GAP,
)

logger = logging.getLogger(__name__)

# 含实际词字符（CJK / 字母 / 数字）才算是"说话"，纯标点/空白 chunk 的时间戳是 ASR 标点模型伪造的，需剔除
WORD_RE = re.compile(r'[\w一-鿿]')


def load_json(path: str) -> Any:
    """读取 JSON 文件（CLI 入口共用）"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def is_punct_or_empty(text: str) -> bool:
    """判断 chunk 文本是否为纯标点/空白（无实际词字符）"""
    return not WORD_RE.search(text or '')


def to_chunks(raw: Any) -> List[Dict[str, Any]]:
    """将 ASR 结果归一化为 chunks 列表

    接受三种输入:
      - list: 直接返回（逐元素取 dict）
      - dict 含 'chunks': 返回 chunks 字段
      - dict 含 'text' 但无 'chunks': 返回空列表

    纯标点/空白 chunk 的时间戳视为 ASR 标点模型伪造，予以剔除。
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        chunks = raw
    elif isinstance(raw, dict):
        chunks = raw.get('chunks', [])
    else:
        return []
    if not isinstance(chunks, list):
        return []
    return [c for c in chunks if isinstance(c, dict) and not is_punct_or_empty(c.get('text', ''))]


def valid_ts(ts: Any) -> Tuple[float, float]:
    """校验并解析时间戳为 (start, end) 浮点秒

    无效时返回 (0.0, 0.0)。
    """
    if not ts or not isinstance(ts, (list, tuple)) or len(ts) < 2:
        return 0.0, 0.0
    try:
        s, e = float(ts[0]), float(ts[1])
    except (TypeError, ValueError):
        return 0.0, 0.0
    if s < 0:
        s = 0.0
    if e < s:
        e = s + EPS_S
    return s, e


def to_segments(chunks: List[Dict[str, Any]],
                seg_merge_gap_s: float = ASR_MODEL_SEG_MERGE_GAP_S,
                ) -> List[List[float]]:
    """将 chunks 合并为语音段列表

    相邻 chunk 间隙 < seg_merge_gap_s 合并为一段。
    每段格式: [start_s, end_s]
    """
    if not chunks:
        return []
    segs: List[List[float]] = []
    cur_s, cur_e = valid_ts(chunks[0].get('timestamp'))
    for i in range(1, len(chunks)):
        s, e = valid_ts(chunks[i].get('timestamp'))
        if s - cur_e < seg_merge_gap_s:
            cur_e = max(cur_e, e)
        else:
            segs.append([cur_s, cur_e])
            cur_s, cur_e = s, e
    segs.append([cur_s, cur_e])
    return segs


def to_segments_with_text(chunks: List[Dict[str, Any]],
                          seg_merge_gap_s: float = ASR_MODEL_SEG_MERGE_GAP_S,
                          ) -> List[Tuple[float, float, str]]:
    """将 chunks 合并为语音段列表（含文本）

    相邻 chunk 间隙 < seg_merge_gap_s 合并为一段。
    每段格式: (start_s, end_s, text)
    """
    clean = to_chunks(chunks)
    intervals: List[Tuple[float, float, str]] = []
    for c in clean:
        s, e = valid_ts(c.get('timestamp'))
        if s == 0.0 and e == 0.0:
            continue
        intervals.append((s, e, str(c.get('text', ''))))

    if not intervals:
        return []

    intervals.sort(key=lambda x: x[0])
    merged: List[Tuple[float, float, str]] = [intervals[0]]
    for s, e, t in intervals[1:]:
        ps, pe, pt = merged[-1]
        if s - pe <= seg_merge_gap_s:
            merged[-1] = (ps, max(pe, e), pt + t)
        else:
            merged.append((s, e, t))
    return merged


def compute_pause_intervals(user_chunks: List[Dict[str, Any]],
                            min_gap: float = PAUSE_MIN_GAP,
                            max_gap: float = PAUSE_MAX_GAP,
                            ) -> List[Dict[str, Any]]:
    """从 user ASR 结果自动计算停顿区间

    相邻 chunk 间隔在 [min_gap, max_gap] 之间视为停顿。
    """
    if not user_chunks:
        return []
    pauses: List[Dict[str, Any]] = []
    for i in range(len(user_chunks) - 1):
        prev_end = valid_ts(user_chunks[i].get('timestamp'))[1]
        next_start = valid_ts(user_chunks[i + 1].get('timestamp'))[0]
        gap = next_start - prev_end
        if min_gap <= gap <= max_gap:
            pauses.append({'text': '[PAUSE]', 'timestamp': [prev_end, next_start]})
    return pauses
