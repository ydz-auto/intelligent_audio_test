# -*- coding: utf-8 -*-
"""
tor.py
TOR（Take-Off Rate）计算：用户结束说话后模型是否正确开始回复

方案（与 takeover_latency 对齐，使用双路 ASR）：
    分别对 user_wav 和 ai_wav 调用 ASR 服务，获取字词级时间戳。
    两路 wav 共享同一时间轴（0 点为录音起点）。

    1. 取 user_wav 最后一词的结束时间 user_last_end
    2. 在 ai_wav 中找 user_last_end 之后的模型回复 chunks
    3. 判定：命中词时长 ≥ 1 秒 或 词数 > 3 → tor=1（模型正确回复）
       否则 → tor=0（模型未正确回复）

    注意：tor=1 表示模型正常回复，不是抢话。

输入: user_chunks + ai_chunks（由 xiaoyi_metrics/__init__.py 统一调 ASR 后传入）
"""
import logging

logger = logging.getLogger(__name__)

# ─────────── 阈值 ───────────
TURN_DURATION_THRESHOLD = 1   # 秒
TURN_NUM_WORDS_THRESHOLD = 3


def compute_tor(user_chunks, ai_chunks,
                duration_threshold=TURN_DURATION_THRESHOLD,
                num_words_threshold=TURN_NUM_WORDS_THRESHOLD):
    """计算用户结束说话后模型是否正确开始回复

    Args:
        user_chunks (list): user_wav ASR chunks，每项含 {"text", "timestamp": [start, end]}
        ai_chunks (list): ai_wav ASR chunks
        duration_threshold (float): 时长阈值，默认 1 秒
        num_words_threshold (int): 词数阈值，默认 3（严格大于）

    Returns:
        dict: {
            'tor': int,                  0 或 1（1=模型正确回复，0=未正确回复）
            'n_words': int,              命中词总数
            'duration': float,           命中词总跨度（max_end - min_start）
            'hit_words': list,           命中词列表
            'user_last_word_end_s': float,  user 最后一词结束时间（秒）
            'message': str,
        }
    """
    result = {
        'tor': 0,
        'n_words': 0,
        'duration': 0.0,
        'hit_words': [],
        'user_last_word_end_s': None,
        'message': '',
    }

    if not user_chunks:
        result['message'] = 'user_chunks 为空，无法计算 TOR'
        logger.warning(result['message'])
        return result

    if not ai_chunks:
        result['message'] = 'ai_chunks 为空，无法计算 TOR'
        logger.warning(result['message'])
        return result

    # 1. 取 user 最后一词结束时间
    user_last_chunk = user_chunks[-1]
    user_last_end_s = user_last_chunk['timestamp'][-1]
    if user_last_end_s is None:
        user_last_end_s = 0.0
    result['user_last_word_end_s'] = user_last_end_s

    logger.info(
        f"[TOR] user_chunks: {len(user_chunks)} chunks, "
        f"最后一词='{user_last_chunk.get('text', '')}', "
        f"end={user_last_end_s:.3f}s"
    )

    # 2. 过滤：只保留 user 最后一词结束之后的 AI chunks（跳过开场白等）
    hit_words = [
        {'text': c.get('text', ''), 'timestamp': c['timestamp']}
        for c in ai_chunks
        if c.get('timestamp') is not None
        and c['timestamp'][0] is not None
        and c['timestamp'][0] >= user_last_end_s
    ]

    # 3. 统一计算命中词的 duration 和 n_words
    n_words = len(hit_words)
    if n_words == 0:
        duration = 0.0
    else:
        starts = [w['timestamp'][0] for w in hit_words if w['timestamp'][0] is not None]
        ends = [w['timestamp'][1] for w in hit_words if w['timestamp'][1] is not None]
        duration = (max(ends) - min(starts)) if starts and ends else 0.0

    result['n_words'] = n_words
    result['duration'] = round(duration, 3)
    result['hit_words'] = hit_words

    logger.info(
        f"[TOR] ai_chunks: {len(ai_chunks)} total, "
        f"hit_words={n_words}, duration={duration:.3f}s"
    )

    # 4. 判定：时长 ≥ 1s 或 词数 > 3 → tor=1（模型正确回复）
    took_over = (duration >= duration_threshold) or (n_words > num_words_threshold)
    result['tor'] = 1 if took_over else 0
    result['message'] = 'OK'

    logger.info(
        f"[TOR] tor={result['tor']} "
        f"(n_words={n_words}, duration={duration:.3f}s, "
        f"user_last_end={user_last_end_s:.3f}s)"
    )

    return result
