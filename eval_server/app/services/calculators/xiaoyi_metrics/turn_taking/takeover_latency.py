# -*- coding: utf-8 -*-
"""
xiaoyi_takeover_latency.py
计算"小艺接管时延" = model_first_word_start_ms - client_out_end_ms

方案（与 false_takeover.py 一致）：
    通过 played_audios（干净音源）与 user_wav（client_out）做 FFT 互相关对齐，
    获取 client_out 的起止时间戳，再用模型回复首字时间戳减去 client_out 结束时间戳。

    时延 = model_first_word_start_ms - client_out_end_ms

    当 played_audios / user_wav 缺失时，回退到旧逻辑（ASR 时间戳直接相减）。
"""
import logging

from ..shared.constants import TAKEOVER_OFFSET_MS, TAKEOVER_FIRST_FRAME_OFFSET_MS

logger = logging.getLogger(__name__)


def compute_takeover_latency_from_raw(first_frame_ms, asr_hyp, start_ms, input_words,
                                      offset_ms=TAKEOVER_OFFSET_MS, **kwargs):
    """兼容旧调用入口，委托到 compute_takeover_latency_from_chunks

    当调用方提供 played_audios + user_wav 时走 client_out 时延新逻辑；
    当调用方提供 user_chunks/ai_chunks 时走 ASR 旧逻辑；
    否则回退到 legacy 逻辑（基于 first_frame_ms + asr_hyp）。
    """
    played_audios = kwargs.get('played_audios')
    user_wav = kwargs.get('user_wav')
    user_chunks = kwargs.get('user_chunks')
    ai_chunks = kwargs.get('ai_chunks')

    # 优先：played_audios + user_wav → client_out 互相关对齐
    if played_audios and user_wav:
        return compute_takeover_latency_from_chunks(
            user_chunks, ai_chunks, played_audios=played_audios, user_wav=user_wav,
        )

    # 回退：ASR 时间戳直接相减
    if user_chunks and ai_chunks:
        return compute_takeover_latency_from_chunks(user_chunks, ai_chunks)

    # 回退：旧逻辑（first_frame_ms + asr_hyp 首词偏移）
    return _compute_takeover_latency_legacy(
        first_frame_ms, asr_hyp, start_ms, input_words, offset_ms
    )


def compute_takeover_latency_from_chunks(user_chunks, ai_chunks,
                                          played_audios=None, user_wav=None):
    """计算小艺接管时延

    优先模式（played_audios + user_wav）：
        通过 FFT 互相关对齐获取 client_out 起止时间戳，
        时延 = model_first_word_start_ms - client_out_end_ms

    回退模式（无 played_audios/user_wav）：
        ASR 时间戳直接相减，
        时延 = ai_first_word_start_ms - user_last_word_end_ms

    Args:
        user_chunks (list): user_wav ASR chunks
        ai_chunks (list): ai_wav ASR chunks
        played_audios (str|None): 干净音源路径（互相关对齐用）
        user_wav (str|None): 用户通道音频路径（=client_out，对齐目标）

    Returns:
        dict: client_out 时延字段（新模式）或旧模式字段
    """
    # ── 优先：played_audios + user_wav → client_out 互相关对齐 ──
    # FFT 互相关用于验证对齐质量(NCC)，时延计算改用 ASR 最后一字结束时间
    if played_audios and user_wav:
        from .false_takeover import compute_client_out_latency
        lat_res = compute_client_out_latency(played_audios, user_wav, ai_chunks)

        # FFT 互相关结果（RMS 区间，仅作参考）
        fft_client_out_end_ms = lat_res.get('client_out_end_ms')
        ncc = lat_res.get('ncc')

        # 用 ASR 最后一字结束时间作为用户说话结束点（更精确）
        user_last_end_ms = None
        if user_chunks:
            valid_user_ends = [
                c['timestamp'][1] for c in user_chunks
                if c.get('timestamp') and c['timestamp'][1] is not None
            ]
            if valid_user_ends:
                user_last_end_ms = max(valid_user_ends) * 1000.0

        ai_first_start_ms = lat_res.get('model_first_word_start_ms')

        if user_last_end_ms is not None and ai_first_start_ms is not None:
            takeover_latency_ms = ai_first_start_ms - user_last_end_ms
            msg = 'OK'
        else:
            takeover_latency_ms = None
            msg = lat_res.get('message', '时延计算失败')

        result = {
            'client_out_start_ms': lat_res.get('client_out_start_ms'),
            'client_out_end_ms': fft_client_out_end_ms,
            'model_first_word_start_ms': ai_first_start_ms,
            'ncc': ncc,
            'message': msg,
        }
        # 兼容旧字段名
        result['takeover_latency_ms'] = takeover_latency_ms
        result['user_last_word_end_ms'] = user_last_end_ms
        result['ai_first_word_start_ms'] = ai_first_start_ms
        logger.info(
            f"[接管时延] latency={takeover_latency_ms}ms "
            f"(user_last_end={user_last_end_ms}ms, ai_first_start={ai_first_start_ms}ms) "
            f"ncc={ncc} fft_ref_end={fft_client_out_end_ms}ms"
        )
        return result

    # ── 回退：ASR 时间戳直接相减 ──
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
                                      offset_ms=TAKEOVER_OFFSET_MS):
    """旧版接管时延计算（基于 first_frame_ms + 录屏 ASR），保留兼容

    公式: takeover_latency_ms = model_first_word_ms - (start_ms + t2_ms + offset_ms)
           model_first_word_ms = first_frame_ms + first_word_begin_ms
    """

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

    first_frame_corrected_ms = first_frame_ms - TAKEOVER_FIRST_FRAME_OFFSET_MS
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
