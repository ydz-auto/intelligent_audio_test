# -*- coding: utf-8 -*-
"""
xiaoyi_metrics 包
小艺评估指标统一入口：调一次 ASR，三个维度共享结果

维度:
    - tor (接话率)          : TOR.compute_tor_during_pauses
    - false_takeover (误接管率) : false_takeover.compute_false_takeover
    - takeover_latency (接管时延) : takeover_latency.compute_takeover_latency_from_raw
"""
import logging
from datetime import datetime, timezone, timedelta

from .tor import compute_tor_during_pauses
from .false_takeover import compute_false_takeover
from .takeover_latency import compute_takeover_latency_from_raw
from .input_asr import compute_input_asr_match

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))


def _ms_to_utc(ms):
    """毫秒 Unix 时间戳 → 东八区时间字符串"""
    if ms is None:
        return 'N/A'
    return datetime.fromtimestamp(ms / 1000, tz=_CST).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def _format_takeover_latency(r):
    """格式化 takeover_latency 结果用于日志打印：时间戳加 UTC，时延/补偿用秒"""
    return (
        f"{{takeover_latency_ms={r.get('takeover_latency_ms')}({(r.get('takeover_latency_ms') or 0) / 1000:.3f}s) "
        f"first_frame_ms={r.get('first_frame_ms')}({_ms_to_utc(r.get('first_frame_ms'))}) "
        f"first_word_begin_ms={r.get('first_word_begin_ms')} "
        f"model_first_word_ms={r.get('model_first_word_ms')}({_ms_to_utc(r.get('model_first_word_ms'))}) "
        f"end_ms={r.get('end_ms')}({_ms_to_utc(r.get('end_ms'))}) "
        f"offset_ms={r.get('offset_ms')}({(r.get('offset_ms') or 0) / 1000:.3f}s) "
        f"audio_end_with_offset_ms={r.get('audio_end_with_offset_ms')}({_ms_to_utc(r.get('audio_end_with_offset_ms'))}) "
        f"message={r.get('message')}}}"
    )

def _format_input_asr(r):
    """格式化 input_asr 结果用于日志打印"""
    return (
        f"{{match={r.get('match')} "
        f"similarity={r.get('similarity')} "
        f"query_original={r.get('query_original')!r} "
        f"question_original={r.get('question_original')!r} "
        f"query_normalized={r.get('query_normalized')!r} "
        f"question_normalized={r.get('question_normalized')!r} "
        f"threshold={r.get('threshold')} "
        f"message={r.get('message')}}}"
    )

def calculate_xiaoyi_metrics(task_params):
    """
    统一入口：调一次 ASR，三个维度共享结果

    Args:
        task_params (dict): 包含以下字段
            - record_file (str): wav 录音文件路径
            - pause (list): 停顿区间数据
            - first_frame_ms (int|None): 录屏首帧时刻
            - start_ms (int|None): 音频开始播放时刻
            - input (list): 主服务下发的 input 词级时间戳
            - offset_ms (int): 时延补偿，默认 40
            - query (str): 参考参数 JSON 中的 query 文本（与 pause 同源）
            - question (str): get_results() 返回的设备识别用户提问文本

    Returns:
        dict: {
            'tor': {...},              接话率结果
            'false_takeover': {...},   误接管率结果
            'takeover_latency': {...}, 接管时延结果
            'input_asr': {...},        输入识别准确率结果
        }
    """
    import json as _json
    from app.utils.asr_adapator import call_modelscope_asr, parse_result

    logger.info(f"[xiaoyi_metrics] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    wav_path = task_params.get('record_file') or task_params.get('record_path') or task_params.get('wav_path')
    if not wav_path:
        raise ValueError("xiaoyi_metrics: 缺少 record_file")

    # 1. 调一次 ASR，三个维度共享（不写文件，通过返回值传递）
    raw = call_modelscope_asr(wav_path)
    asr_hyp = parse_result(raw)
    chunks = asr_hyp.get("chunks", [])
    logger.info(f"ASR 完成，chunks={len(chunks)}，开始计算三个维度")

    # 2. pause 数据
    pause_intervals = task_params.get('pause', [])
    if isinstance(pause_intervals, str):
        pause_intervals = _json.loads(pause_intervals)

    # 3. 三个维度共享 asr_hyp
    results = {}

    # tor
    results['tor'] = compute_tor_during_pauses(chunks, pause_intervals)
    logger.info(f"[tor] {results['tor']}")

    # false_takeover
    results['false_takeover'] = compute_false_takeover(chunks, pause_intervals)
    logger.info(f"[false_takeover] {results['false_takeover']}")

    # takeover_latency: start_ms / input_lastword 可能在 rounds[0] 中
    rounds = task_params.get('rounds', [])
    round0 = rounds[0] if rounds else {}
    input_words = (
        task_params.get('input')
        or task_params.get('input_lastword')
        or round0.get('input')
        or round0.get('input_lastword')
        or []
    )
    start_ms = task_params.get('start_ms') or round0.get('start_ms')
    offset_ms = task_params.get('offset_ms') or round0.get('offset_ms') or 40

    results['takeover_latency'] = compute_takeover_latency_from_raw(
        first_frame_ms=task_params.get('first_frame_ms'),
        asr_hyp=asr_hyp,
        start_ms=start_ms,
        input_words=input_words,
        offset_ms=offset_ms,
    )
    logger.info(f"[takeover_latency] {_format_takeover_latency(results['takeover_latency'])}")

    # input_asr: 对比参考 query 与设备识别 question
    results['input_asr'] = compute_input_asr_match(
        task_params=task_params,
    )
    logger.info(f"[input_asr] {_format_input_asr(results['input_asr'])}")

    return results
