# -*- coding: utf-8 -*-
"""
tor.py
TOR（Take-Off Rate）计算：判断模型是否在打断后"接话"

参考: Full-Duplex-Bench/v1_v1.5/evaluation/eval_pause_handling.py

输入: ASR chunks + pause 区间（由 xiaoyi_metrics/__init__.py 统一调 ASR 后传入）
"""
import logging

logger = logging.getLogger(__name__)

# ─────────── 阈值 ───────────
TURN_DURATION_THRESHOLD = 1  # 秒
TURN_NUM_WORDS_THRESHOLD = 3


def compute_tor(chunks):
    """根据 chunks 时间戳计算 TOR（0=没接话，1=接话）"""
    if len(chunks) == 0:
        return 0
    last_end = chunks[-1]["timestamp"][-1]
    first_start = chunks[0]["timestamp"][0]
    if last_end is None:
        last_end = chunks[-1]["timestamp"][0]
    duration = last_end - first_start
    if duration < TURN_DURATION_THRESHOLD:
        if len(chunks) <= TURN_NUM_WORDS_THRESHOLD:
            return 0
        else:
            return 1
    else:
        return 1


# ─────────── 基于 pause 区间的 TOR ───────────
def _intervals_overlap(a, b):
    """判断两个 [start, end] 区间是否相交（边界相等不算）"""
    return a[0] < b[1] and b[0] < a[1]


def compute_tor_during_pauses(chunks, pause_intervals):
    """计算每个 pause 区间内模型是否错误接管（开口）

    Args:
        chunks (list): ASR chunks，每项含 {"text", "timestamp": [start, end]}
        pause_intervals (list): pause 区间列表，每项 {"text", "timestamp": [start, end]}

    Returns:
        dict: {
            'per_pause': [0|1, ...],   每个 pause 区间的接管标记
            'takeover_count': int,     错误接管的 pause 数
            'total_pauses': int,       pause 区间总数
            'tor': float,              错误接管率 = takeover_count / total_pauses
        }
    """
    total = len(pause_intervals)
    if total == 0:
        return {'per_pause': [], 'takeover_count': 0, 'total_pauses': 0, 'tor': 0.0}

    per_pause = []
    takeover_count = 0
    for p in pause_intervals:
        p_iv = p.get('timestamp', [0, 0])
        if p_iv[0] is None or p_iv[1] is None:
            per_pause.append(0)
            continue
        # 检查是否有 chunk 与该 pause 区间重叠
        takeover = 0
        for c in chunks:
            c_iv = c.get('timestamp', [0, 0])
            if c_iv[0] is None or c_iv[1] is None:
                continue
            if _intervals_overlap(c_iv, p_iv):
                takeover = 1
                break
        per_pause.append(takeover)
        if takeover:
            takeover_count += 1

    tor = takeover_count / total if total > 0 else 0.0
    return {
        'per_pause': per_pause,
        'takeover_count': takeover_count,
        'total_pauses': total,
        'tor': tor,
    }
