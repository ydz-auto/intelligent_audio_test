# -*- coding: utf-8 -*-
"""
xiaoyi_takeover_latency.py
计算"小艺接管时延" = ai_wav 首字开始时间 - user_wav 最后一字结束时间

方案：
    分别对 user_wav 和 ai_wav 调用 ASR 服务，获取字词级时间戳，
    takeover_latency_ms = ai_wav 首字开始时间 - user_wav 最后一字结束时间

    两路 wav 来自设备端 cap_client 采集的 PCM 转换：
      - user_wav: cap_client_process_out.wav（用户说话通道）
      - ai_wav:   cap_client_ec_out.wav（AI 回复通道）
    两路音频同时开始录制，共享同一时间轴（0 点为录音起点），
    因此直接用各路 ASR 时间戳相减即可得到接管时延。

    ASR 调用由 xiaoyi_metrics/__init__.py 统一完成，本模块只接收 chunks。
"""
import logging

logger = logging.getLogger(__name__)


def compute_takeover_latency_from_raw(first_frame_ms, asr_hyp, start_ms, input_words,
                                      offset_ms=40, **kwargs):
    """兼容旧调用入口，委托到 compute_takeover_latency_from_chunks

    当调用方提供 user_chunks/ai_chunks 时走新逻辑；
    否则回退到旧逻辑（基于 first_frame_ms + asr_hyp）。
    """
    user_chunks = kwargs.get('user_chunks')
    ai_chunks = kwargs.get('ai_chunks')

    if user_chunks and ai_chunks:
        return compute_takeover_latency_from_chunks(user_chunks, ai_chunks)

    # 回退：旧逻辑（first_frame_ms + asr_hyp 首词偏移）
    return _compute_takeover_latency_legacy(
        first_frame_ms, asr_hyp, start_ms, input_words, offset_ms
    )


def compute_takeover_latency_from_chunks(user_chunks, ai_chunks):
    """计算小艺接管时延（双路 ASR 时间戳直接相减）

    公式: takeover_latency_ms = ai_first_word_start_ms - user_last_word_end_ms

    Args:
        user_chunks (list): user_wav ASR chunks，每项含 {"text", "timestamp": [start, end]}
        ai_chunks (list): ai_wav ASR chunks

    Returns:
        dict: {
            'takeover_latency_ms': float|None,   接管时延（毫秒，正值=AI在用户说完后才开始，负值=AI抢话）
            'user_last_word_end_ms': float,       user_wav 最后一字结束时间（毫秒）
            'ai_first_word_start_ms': float,      ai_wav 首字开始时间（毫秒）
            'message': str,
        }
    """
    result = {
        'takeover_latency_ms': None,
        'user_last_word_end_ms': None,
        'ai_first_word_start_ms': None,
        'message': '',
    }

    if not user_chunks:
        result['message'] = 'user_chunks 为空，无法计算接管时延'
        logger.warning(result['message'])
        return result

    if not ai_chunks:
        result['message'] = 'ai_chunks 为空，无法计算接管时延'
        logger.warning(result['message'])
        return result

    # 1. 取 user 最后一字结束时间
    #    如果 user_wav 包含 AI 回复之后的用户后续话语（全双工录音），
    #    需要找到 AI 首词开始之前的 user 最后一词作为"用户结束说话"的时间点
    user_last_chunk = user_chunks[-1]
    user_last_end_s = user_last_chunk['timestamp'][-1]
    if user_last_end_s is None:
        user_last_end_s = 0.0

    # 检查 AI 首词开始时间
    ai_valid_starts = [
        c['timestamp'][0] for c in ai_chunks
        if c.get('timestamp') and c['timestamp'][0] is not None
    ]
    ai_first_start = min(ai_valid_starts) if ai_valid_starts else None

    # 如果用户最后一词在 AI 首词之后，说明 user_wav 包含了 AI 回复之后的后续话语，
    # 回退到 AI 首词之前的 user 最后一词（即用户提问的结束时间）
    if ai_first_start is not None and user_last_end_s > ai_first_start:
        logger.info(
            f"[接管时延] 用户最后一词(end={user_last_end_s:.3f}s)在 AI 首词(start={ai_first_start:.3f}s)之后，"
            f"说明 user_wav 包含 AI 回复后的后续话语，回退查找 AI 首词之前的用户最后一词"
        )
        for uc in reversed(user_chunks):
            ts = uc.get('timestamp')
            if ts and ts[1] is not None and ts[1] <= ai_first_start:
                user_last_end_s = ts[1]
                user_last_chunk = uc
                break
        else:
            user_last_end_s = 0.0
        logger.info(
            f"[接管时延] 修正后 user_last_end={user_last_end_s:.3f}s "
            f"(最后一词='{user_last_chunk.get('text', '')}')"
        )

    user_last_word_end_ms = user_last_end_s * 1000.0
    result['user_last_word_end_ms'] = user_last_word_end_ms

    logger.info(
        f"[接管时延] user_chunks: {len(user_chunks)} chunks, "
        f"最后一字='{user_last_chunk.get('text', '')}', "
        f"end={user_last_end_s:.3f}s ({user_last_word_end_ms:.1f}ms)"
    )

    # 2. 开场白过滤：找到 user 最后一字结束之后的首个 AI chunk
    ai_response_chunks = [
        c for c in ai_chunks
        if c.get('timestamp') and c['timestamp'][0] is not None
        and c['timestamp'][0] >= user_last_end_s
    ]

    if not ai_response_chunks:
        result['message'] = (
            f'ai_chunks 中未找到用户说完后的 AI 回复 chunk '
            f'(user_last_end={user_last_end_s:.3f}s, ai_chunks={len(ai_chunks)})'
        )
        logger.error(result['message'])
        for i, c in enumerate(ai_chunks):
            ts = c.get('timestamp', [None, None])
            logger.info(f"  ai_chunk[{i}]: text='{c.get('text','')}' ts={ts}")
        return result

    ai_first_chunk = ai_response_chunks[0]
    ai_first_start_s = ai_first_chunk['timestamp'][0]
    if ai_first_start_s is None:
        ai_first_start_s = 0.0
    ai_first_word_start_ms = ai_first_start_s * 1000.0
    result['ai_first_word_start_ms'] = ai_first_word_start_ms

    skipped_count = len(ai_chunks) - len(ai_response_chunks)
    result['ai_skipped_opening_chunks'] = skipped_count
    result['ai_total_chunks'] = len(ai_chunks)

    logger.info(
        f"[接管时延] ai_chunks: total={len(ai_chunks)}, "
        f"skipped_opening={skipped_count}, "
        f"response_chunks={len(ai_response_chunks)}, "
        f"首字='{ai_first_chunk.get('text', '')}', "
        f"start={ai_first_start_s:.3f}s ({ai_first_word_start_ms:.1f}ms)"
    )

    # 3. 接管时延 = AI 真正回复首字开始 - user 最后一字结束
    takeover_latency_ms = ai_first_word_start_ms - user_last_word_end_ms
    result['takeover_latency_ms'] = takeover_latency_ms
    result['message'] = 'OK'

    logger.info(
        f"[接管时延] takeover_latency_ms={takeover_latency_ms:.1f}ms "
        f"(ai_first_start={ai_first_word_start_ms:.1f}ms - "
        f"user_last_end={user_last_word_end_ms:.1f}ms, "
        f"skipped_opening={skipped_count})"
    )

    return result


def _compute_takeover_latency_legacy(first_frame_ms, asr_hyp, start_ms, input_words,
                                      offset_ms=40):
    """旧版接管时延计算（基于 first_frame_ms + 录屏 ASR），保留兼容

    公式: takeover_latency_ms = model_first_word_ms - (start_ms + t2_ms + offset_ms)
           model_first_word_ms = first_frame_ms + first_word_begin_ms
    """
    DEFAULT_FIRST_FRAME_OFFSET_MS = 100

    result = {
        'takeover_latency_ms': None,
        'first_frame_ms': first_frame_ms,
        'first_word_begin_ms': 0,
        'model_first_word_ms': None,
        'start_ms': start_ms,
        'offset_ms': offset_ms,
        'message': '',
    }

    if first_frame_ms is None:
        result['message'] = 'first_frame_ms 为 None, 无法计算'
        return result
    if start_ms is None:
        result['message'] = 'start_ms 为 None, 无法计算'
        return result

    chunks = (asr_hyp or {}).get('chunks', [])
    if not chunks:
        result['message'] = 'ASR chunks 为空'
        return result

    first_word_begin_s = chunks[0]['timestamp'][0]
    if first_word_begin_s is None:
        first_word_begin_s = 0.0
    first_word_begin_ms = int(first_word_begin_s * 1000)
    result['first_word_begin_ms'] = first_word_begin_ms

    first_frame_corrected_ms = first_frame_ms - DEFAULT_FIRST_FRAME_OFFSET_MS
    model_first_word_ms = first_frame_corrected_ms + first_word_begin_ms
    result['model_first_word_ms'] = model_first_word_ms

    if input_words:
        try:
            last_end_s = input_words[-1].get('timestamp', [0.0, 0.0])[-1]
            if last_end_s is None:
                last_end_s = 0.0
            t2_ms = int(last_end_s * 1000)
        except (IndexError, TypeError, KeyError):
            t2_ms = 0
    else:
        t2_ms = 0
    result['t2_ms'] = t2_ms

    audio_start_with_offset_ms = start_ms + t2_ms + offset_ms
    result['audio_start_with_offset_ms'] = audio_start_with_offset_ms

    takeover_latency_ms = model_first_word_ms - audio_start_with_offset_ms
    result['takeover_latency_ms'] = takeover_latency_ms
    result['message'] = 'OK (legacy mode)'

    logger.info(
        f"[接管时延-legacy] first_frame_ms={first_frame_ms} "
        f"first_word_begin_ms={first_word_begin_ms} "
        f"model_first_word_ms={model_first_word_ms} "
        f"start_ms={start_ms} t2_ms={t2_ms} offset_ms={offset_ms} "
        f"audio_start_with_offset_ms={audio_start_with_offset_ms} "
        f"takeover_latency_ms={takeover_latency_ms}ms"
    )
    return result
