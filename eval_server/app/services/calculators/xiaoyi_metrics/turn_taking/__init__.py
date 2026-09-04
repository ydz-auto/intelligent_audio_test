# -*- coding: utf-8 -*-
"""
turn_taking 包：话轮接管与打断指标

ASR 词级时间戳获取的唯一出口：_get_asr_chunks
被 strategy.py / shared/llm_client.py / env_judge 等复用，
内部封装远程 asr_adapter 调用 + 标点过滤。
"""
import os
import logging

from .tor import compute_tor
from .false_takeover import compute_false_takeover, compute_false_takeover_llm
from .takeover_latency import compute_takeover_latency_from_raw
from .input_asr import compute_input_asr_match
from .high_freq_turn_taking import compute_high_freq_turn_taking
from .high_freq_llm_judge import evaluate_high_freq_llm
from ..shared.asr_utils import is_punct_or_empty

logger = logging.getLogger(__name__)


def _get_asr_chunks(wav_path, filter_punct=True):
    """调用远程 ASR 服务获取词级时间戳（Paraformer，user_wav / ai_wav 共用）

    Args:
        wav_path: 本地 wav 文件路径
        filter_punct: 是否过滤纯标点/空白 chunk（其时间戳是 ASR 标点模型伪造的，
            不代表真实语音）。默认 True；需要完整词序的指标（如 false_takeover
            词级时间戳裁剪）传 False。

    Returns:
        list: chunks 列表 [{text, timestamp:[start_s, end_s]}, ...]
        None: ASR 失败或 chunks 为空
    """
    if not wav_path or not os.path.isfile(wav_path):
        logger.error(f"wav 文件不存在: {wav_path}")
        return None

    from app.utils.asr_adapter import call_modelscope_asr_word, parse_result

    try:
        raw = call_modelscope_asr_word(wav_path)
        asr_result = parse_result(raw)
        chunks = asr_result.get('chunks', [])
        if filter_punct:
            chunks = [
                c for c in chunks
                if isinstance(c, dict) and not is_punct_or_empty(c.get('text', ''))
            ]
        if not chunks:
            logger.warning(f"ASR(词级) chunks 为空: {wav_path}")
            return None
        return chunks
    except Exception as e:
        logger.error(f"ASR(词级) 调用失败 {wav_path}: {e}")
        return None
