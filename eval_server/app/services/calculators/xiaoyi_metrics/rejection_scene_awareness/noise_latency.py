# -*- coding: utf-8 -*-
"""
noise_latency.py
噪声打断时延计算(逻辑与 non_interactive_latency.py 对称,
把"用户在模型回复期间说话"的非交互意图替换为"噪声播放")

场景:
    模型正在回复期间，播放环境噪声 [start_ms, end_ms](世界时间)。
    衡量模型"停得下、恢复得来":
        1. stop_latency      : 噪声开始 → 模型当前回复结束(被打断后还拖了多久才停)
        2. recovery_latency  : 噪声结束 → 模型再次回复(恢复时延)

输入:
    ai_wav          模型语音 wav 路径（内部自动调 ASR 服务）
    start_ms        噪声播放开始时间(世界毫秒)
    end_ms          噪声结束播放时间(世界毫秒)
    pcm_first_ms    模型 PCM 文件创建时间(世界毫秒，绝对基准，用于噪声↔模型时间轴对齐)
    seg_merge_gap_s 词合并为段的间隙阈值(秒)，默认 0.7

时间对齐:
    噪声是绝对世界毫秒，模型 ASR 是相对音频秒。
    用 pcm_first_ms 把噪声换算到模型音频的相对秒:
        n_s = (start_ms - pcm_first_ms) / 1000
        n_e = (end_ms   - pcm_first_ms) / 1000
    随后与 non_interactive_latency 同流程(同秒级时间轴)。

用法:
    python noise_latency.py --ai_wav ai.wav --start_ms 5000 --end_ms 8000 \\
        --pcm_first_ms 2000 [--merge_gap 0.7] [-o out.json]

    from noise_latency import compute_noise_latency
    res = compute_noise_latency(ai_wav, start_ms, end_ms, pcm_first_ms)
"""
import logging
from typing import Any, Dict

from ..shared.constants import MS_PER_S

try:
    from .non_interactive_latency import (
        SEG_MERGE_GAP_S, _compute_from_asr, _get_asr,
    )
except ImportError:  # 直接作为脚本运行
    from non_interactive_latency import (
        SEG_MERGE_GAP_S, _compute_from_asr, _get_asr,
    )

logger = logging.getLogger(__name__)


def compute_noise_latency(ai_wav: str, start_ms: float, end_ms: float,
                          pcm_first_ms: float,
                          seg_merge_gap_s: float = SEG_MERGE_GAP_S,
                          model_asr: Any = None) -> Dict[str, Any]:
    """计算噪声打断模型的时延(与 non_interactive 对称)

    把噪声 [start_ms, end_ms] 用 pcm_first_ms 换算到模型音频相对秒，
    作为"打断事件段"喂给 non_interactive_latency 的同套逻辑，再补充绝对毫秒输出。

    优先使用已就绪的 model_asr（共享 ASR 池注入），缺失时内部调 ASR 服务。

    Args:
        ai_wav: 模型语音 wav 路径（内部自动调 ASR 服务）
        start_ms: 噪声播放开始时间(绝对毫秒)
        end_ms: 噪声结束播放时间(绝对毫秒)
        pcm_first_ms: 模型 PCM 文件创建时间(绝对毫秒)
        seg_merge_gap_s: 词合并为段的间隙阈值(秒)，默认 0.7
        model_asr: 已就绪的模型 ASR 结果（chunks 列表 或 {text, chunks}），可选

    Returns dict(non_interactive 原字段 + 绝对毫秒):
        stop_latency_s / stop_latency_ms          噪声开始→模型当前回复结束(秒/毫秒)
        recovery_latency_s / recovery_latency_ms  噪声结束→模型再次回复(秒/毫秒)
        noise_segment                         [n_s, n_e, 'noise'](相对秒)
        noise_start_ms / noise_end_ms          噪声绝对起止(回传)
        pcm_first_ms                           PCM 创建时刻(回传)
        model_active_segment                   噪声期间正在说的模型段(相对秒)
        model_active_segment_abs               同上(绝对毫秒)
        model_recovery_segment                 恢复回复段(相对秒)
        model_recovery_segment_abs             同上(绝对毫秒)
        model_recovery_abs_ms                  恢复回复绝对世界时刻(ms)
        silence_gap_s                          模型当前回复结束→恢复回复的静默(秒)
        overlap_s                              噪声与模型当前回复重叠(秒)
        n_model_segments                       模型回复段数
        has_model_reply                        模型是否产生有效回复
        message                                状态说明
    """
    # 噪声绝对毫秒 → 模型音频相对秒
    n_s = (start_ms - pcm_first_ms) / MS_PER_S
    n_e = (end_ms - pcm_first_ms) / MS_PER_S
    # 包装成 ASR chunk，复用 non_interactive 的段提取(0.7s 合并、剔除标点)
    # 添加伪提问段 [0, 0.001] 使 non_interactive 的 prev_idx 逻辑可用：
    #   non_interactive 需要 target_segment_index >= 1 来定位"前一段提问"，
    #   噪声只有 1 段(index=0)会触发 prev_idx=-1 提前返回。
    #   伪段 [0, 0.001] 距噪声 >0.7s 确保拆为独立段(要求 n_s > 0.701s)。
    noise_asr = {"chunks": [
        {"text": "q", "timestamp": [0.0, 0.001]},
        {"text": "noise", "timestamp": [n_s, n_e]},
    ]}

    # 优先用共享池注入的模型 ASR，缺失时内部调 ASR 服务
    if model_asr is None:
        model_asr = _get_asr(ai_wav)

    r = _compute_from_asr(
        noise_asr, model_asr,
        seg_merge_gap_s=seg_merge_gap_s,
        target_segment_index=1,  # 噪声是第 2 段(index=1)
    )

    # 在 non_interactive 结果上补充绝对毫秒
    result: Dict[str, Any] = dict(r)
    result['noise_start_ms'] = start_ms
    result['noise_end_ms'] = end_ms
    result['pcm_first_ms'] = pcm_first_ms
    result['has_model_reply'] = r.get('n_model_segments', 0) > 0

    # stop_latency 毫秒
    if r.get('stop_latency_s') is not None:
        result['stop_latency_ms'] = round(r['stop_latency_s'] * MS_PER_S, 1)

    # 模型当前回复段(绝对毫秒)
    if r.get('model_active_segment'):
        ms, me, mt = r['model_active_segment']
        result['model_active_segment_abs'] = [
            round(pcm_first_ms + ms * MS_PER_S, 1),
            round(pcm_first_ms + me * MS_PER_S, 1), mt]

    # 恢复回复段(绝对毫秒)+ 恢复时延毫秒 + 恢复绝对时刻
    if r.get('model_recovery_segment'):
        rs, re_, rt = r['model_recovery_segment']
        rec_abs = pcm_first_ms + rs * MS_PER_S
        result['model_recovery_segment_abs'] = [
            round(rec_abs, 1), round(pcm_first_ms + re_ * MS_PER_S, 1), rt]
        result['model_recovery_abs_ms'] = round(rec_abs, 1)
        if r.get('recovery_latency_s') is not None:
            result['recovery_latency_ms'] = round(r['recovery_latency_s'] * MS_PER_S, 1)

    logger.info(
        f"[噪声打断时延] noise=[{start_ms},{end_ms}]ms pcm_first={pcm_first_ms} "
        f"stop_latency={result.get('stop_latency_ms')}ms "
        f"recovery={result.get('recovery_latency_ms')}ms "
        f"msg={result.get('message')}"
    )
    return result


if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='计算噪声打断模型的时延(与 non_interactive 对称)'
    )
    parser.add_argument('--ai_wav', required=True,
                        help='模型端 wav 路径')
    parser.add_argument('--start_ms', type=float, required=True,
                        help='噪声播放开始时间(绝对毫秒)')
    parser.add_argument('--end_ms', type=float, required=True,
                        help='噪声结束播放时间(绝对毫秒)')
    parser.add_argument('--pcm_first_ms', type=float, required=True,
                        help='模型 PCM 文件创建时间(绝对毫秒)')
    parser.add_argument('--merge_gap', type=float, default=SEG_MERGE_GAP_S,
                        help=f'词合并为段的间隙阈值(秒)，默认 {SEG_MERGE_GAP_S}')
    parser.add_argument('-o', '--output', default=None,
                        help='结果写入的 JSON 路径(可选，不传则只打印)')
    args = parser.parse_args()

    r = compute_noise_latency(
        args.ai_wav, args.start_ms, args.end_ms, args.pcm_first_ms,
        seg_merge_gap_s=args.merge_gap)

    print('=' * 56)
    print(f"噪声:        {r['noise_start_ms']:.0f} -> {r['noise_end_ms']:.0f} ms"
          f"  (持续 {r['noise_end_ms'] - r['noise_start_ms']:.0f} ms)")
    print(f"PCM 创建时刻: {r['pcm_first_ms']:.0f} ms")
    # 噪声相对秒
    ns = (r['noise_start_ms'] - r['pcm_first_ms']) / MS_PER_S
    ne = (r['noise_end_ms'] - r['pcm_first_ms']) / MS_PER_S
    print(f"噪声(模型轴): {ns:.3f}s -> {ne:.3f}s")
    print(f"模型回复段数: {r['n_model_segments']}")

    if r.get('model_active_segment'):
        ms, me, mt = r['model_active_segment']
        ams, ame, _ = r['model_active_segment_abs']
        print(f"── 噪声期间模型在说 ──")
        print(f"  模型当前回复: [{ms:.1f}-{me:.1f}]s = [{ams:.0f}-{ame:.0f}]ms  {mt[:30]}")
        print(f"  重叠:       {r.get('overlap_s')}s")
        if r.get('stop_latency_s') is not None:
            print(f"  噪声开始→回复结束(拖尾): {r['stop_latency_s']}s = {r.get('stop_latency_ms')}ms")

    if r.get('model_recovery_segment'):
        rs, re_, rt = r['model_recovery_segment']
        ars, are_, _ = r['model_recovery_segment_abs']
        print(f"── 模型恢复回复 ──")
        print(f"  恢复段:     [{rs:.1f}-{re_:.1f}]s = [{ars:.0f}-{are_:.0f}]ms  {rt[:30]}")
        print(f"  噪声结束→恢复: {r['recovery_latency_s']}s = {r.get('recovery_latency_ms')}ms")
        if r.get('silence_gap_s') is not None:
            print(f"  静默:       {r['silence_gap_s']}s")
    else:
        print("(模型未恢复回复)")

    print(f"message: {r.get('message')}")
    print('=' * 56)
    print(json.dumps(r, ensure_ascii=False, indent=2))

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"已写入: {args.output}")
