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

from .tor import compute_tor_during_pauses
from .false_takeover import compute_false_takeover
from .takeover_latency import compute_takeover_latency_from_raw

logger = logging.getLogger(__name__)


def calculate_xiaoyi_metrics(task_params):
    """
    统一入口：调一次 ASR，三个维度共享结果

    Args:
        task_params (dict): 包含以下字段
            - record_path (str): wav 录音文件路径
            - pause (list): 停顿区间数据
            - first_frame_ms (int|None): 录屏首帧时刻
            - end_ms (int|None): 音频结束时刻
            - offset_ms (int): 时延补偿，默认 40

    Returns:
        dict: {
            'tor': {...},              接话率结果
            'false_takeover': {...},   误接管率结果
            'takeover_latency': {...}, 接管时延结果
        }
    """
    import json as _json
    from ..utils.asr_adapator import call_modelscope_asr, parse_result

    wav_path = task_params.get('record_path') or task_params.get('wav_path')
    if not wav_path:
        raise ValueError("xiaoyi_metrics: 缺少 record_path 或 wav_path")

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

    # takeover_latency
    results['takeover_latency'] = compute_takeover_latency_from_raw(
        first_frame_ms=task_params.get('first_frame_ms'),
        asr_hyp=asr_hyp,
        end_ms=task_params.get('end_ms'),
        offset_ms=task_params.get('offset_ms', 40),
    )
    logger.info(f"[takeover_latency] {results['takeover_latency']}")

    return results
