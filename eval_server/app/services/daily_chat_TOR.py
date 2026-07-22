# -*- coding: utf-8 -*-
"""
daily_chat_TOR.py
TOR（Take-Off Rate）计算：判断模型是否在打断后"接话"

参考: Full-Duplex-Bench/v1_v1.5/evaluation/eval_pause_handling.py

依赖: app.utils.PAUSE_JSON.generate_pause_json 生成 ASR JSON（{wav同名}.json）
      注意：引用的是 {wav同名}.json（ASR 词级时间戳），不是 {wav同名}.pause.json
"""
import logging

logger = logging.getLogger(__name__)

# ─────────── TOR 计算 ───────────
# TOR = Take-Off Rate：判断模型是否在打断后"接话"
TURN_DURATION_THRESHOLD = 1  # 秒
TURN_NUM_WORDS_THRESHOLD = 3


def compute_tor(chunks):
    """根据 chunks 时间戳计算 TOR（0=没接话，1=接话）"""
    if len(chunks) == 0:
        return 0
    last_end = chunks[-1]["timestamp"][-1]
    first_start = chunks[0]["timestamp"][0]
    # 处理 None（无 end_time 的 chunk，用 first chunk 的 start 兜底）
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


def compute_tor_from_json(asr_json_path):
    """从 ASR JSON 文件读取 chunks 并计算 TOR

    Args:
        asr_json_path (str): app.utils.PAUSE_JSON.generate_pause_json 生成的 ASR JSON 路径
                             （引用的是 {wav同名}.json，不是 {wav同名}.pause.json）

    Returns:
        int: 0 或 1（读取失败返回 0）
    """
    import json
    try:
        with open(asr_json_path, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        logger.error(f"读取 ASR JSON 失败: {asr_json_path} {e}")
        return 0
    tor = compute_tor(result.get("chunks", []))
    logger.info(f"TOR: {tor}")
    return tor


# ─────────── 基于 pause 区间的 TOR ───────────
def _intervals_overlap(a, b):
    """判断两个 [start, end] 区间是否相交（边界相等不算）"""
    return a[0] < b[1] and b[0] < a[1]


def compute_tor_during_pauses(chunks, pause_intervals):
    """计算每个 pause 区间内模型是否错误接管（开口）

    判定规则：若模型的某个词的 [start, end] 与 pause 区间 [p_start, p_end] 相交，
    则该 pause 区间记为错误接管（1），否则为正确等待（0）。

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
        p_iv = p.get('timestamp') or [p['start'], p['end']]
        # 判断模型是否在 pause 区间内开口：任一词与区间相交即算
        took_over = any(
            _intervals_overlap(c['timestamp'], p_iv)
            for c in chunks
            if c.get('timestamp') is not None
        )
        per_pause.append(1 if took_over else 0)
        if took_over:
            takeover_count += 1

    return {
        'per_pause': per_pause,
        'takeover_count': takeover_count,
        'total_pauses': total,
        'tor': takeover_count / total,
    }


def compute_tor_during_pauses_from_files(asr_json_path, pause_json_path):
    """从 {name}.json 和 {name}.pause.json 两个文件计算 pause 期间的 TOR

    Args:
        asr_json_path (str): PAUSE_JSON 生成的 ASR JSON 路径（{wav同名}.json）
        pause_json_path (str): PAUSE_JSON 生成的 pause 区间 JSON 路径（{wav同名}.pause.json）

    Returns:
        dict: 同 compute_tor_during_pauses（读取失败时 tor=0.0）
    """
    import json
    try:
        with open(asr_json_path, "r", encoding="utf-8") as f:
            asr_result = json.load(f)
        with open(pause_json_path, "r", encoding="utf-8") as f:
            pause_intervals = json.load(f)
    except Exception as e:
        logger.error(f"读取 ASR/pause JSON 失败: {asr_json_path} / {pause_json_path} {e}")
        return {'per_pause': [], 'takeover_count': 0, 'total_pauses': 0, 'tor': 0.0}

    chunks = asr_result.get("chunks", [])
    res = compute_tor_during_pauses(chunks, pause_intervals)
    logger.info(
        f"[pause-TOR] per_pause={res['per_pause']} "
        f"takeover={res['takeover_count']}/{res['total_pauses']} "
        f"tor={res['tor']:.3f}"
    )
    return res
