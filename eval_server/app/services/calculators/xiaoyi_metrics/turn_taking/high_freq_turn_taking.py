# -*- coding: utf-8 -*-
"""
high_freq_turn_taking.py
高频轮换场景下每轮回复时延计算

场景:
    音频中包含多轮对话（飞花令、成语接龙、快问快答等），
    user_wav 有多段用户讲话，ai_wav 有多段模型回复。
    测试每轮模型回复的时延。

方案:
    分别对 user_wav 和 ai_wav 调用 ASR，获取词级时间戳。
    两路 wav 共享同一时间轴（0 点为录音起点）。
    将每路 ASR chunks 合并为语音段（相邻间隙 < gap 合并）。
    逐轮匹配：对每个用户段，找到其结束后首个未被消费的 AI 段，
    该 AI 段即为该轮回复。
    回复时延 = AI段起点 - 用户段终点

    ASR 调用由 xiaoyi_metrics/__init__.py 统一完成，本模块只接收 chunks。
"""
import logging
from typing import Any, Dict, List, Optional

from ..shared.asr_utils import to_chunks, to_segments_with_text
from ..shared.constants import ASR_HIGH_FREQ_SEG_MERGE_GAP_S

logger = logging.getLogger(__name__)

# ─────────── 阈值 ───────────
SEG_MERGE_GAP_S = ASR_HIGH_FREQ_SEG_MERGE_GAP_S  # 合并相邻词为语音段的间隙阈值（秒）

# _to_segments / _to_chunks 由 shared.asr_utils 提供（消除重复实现）


# ─────────── 主逻辑 ───────────
def compute_high_freq_turn_taking(
    user_chunks: Any,
    ai_chunks: Any,
    seg_merge_gap_s: float = SEG_MERGE_GAP_S,
) -> Dict[str, Any]:
    """计算高频轮换场景下每轮回复时延

    逐轮匹配：对每个用户段 U_i，在 AI 段列表中找其结束后首个未被消费的段
    A_j（A_j.start >= U_i.end），即该轮回复。
    回复时延 = A_j.start - U_i.end

    Args:
        user_chunks: 用户通道 ASR chunks（list 或 {text, chunks}）
        ai_chunks:   AI 回复通道 ASR chunks（同上）。两路需在同一时间轴
        seg_merge_gap_s: 词合并为段的间隙阈值（秒），默认 0.7

    Returns:
        dict: {
            'n_rounds': int,                     用户段总数（=轮数）
            'per_round': list,                   每轮结果（见下）
            'avg_response_latency_s': float|None, 平均回复时延（秒）
            'min_response_latency_s': float|None, 最小回复时延（秒）
            'max_response_latency_s': float|None, 最大回复时延（秒）
            'avg_response_latency_ms': float|None, 平均回复时延（毫秒）
            'n_user_segments': int,              用户段总数
            'n_ai_segments': int,                AI段总数
            'n_matched_rounds': int,             成功匹配到AI回复的轮数
            'n_missed_rounds': int,              未匹配到AI回复的轮数
            'n_unmatched_ai_segments': int,      未被消费的AI段数（开场白/结束语等）
            'message': str,
        }

    per_round 每项:
        {
            'round_index': int,                 轮次（1-based）
            'user_segment': [start, end, text], 用户段
            'ai_segment': [start, end, text]|None, AI回复段
            'response_latency_s': float|None,   回复时延（秒）
            'response_latency_ms': float|None,  回复时延（毫秒）
            'inter_round_gap_s': float|None,    本轮AI结束→下轮用户开始的间隔（秒）
            'message': str,
        }
    """
    result: Dict[str, Any] = {
        'n_rounds': 0,
        'per_round': [],
        'avg_response_latency_s': None,
        'min_response_latency_s': None,
        'max_response_latency_s': None,
        'avg_response_latency_ms': None,
        'n_user_segments': 0,
        'n_ai_segments': 0,
        'n_matched_rounds': 0,
        'n_missed_rounds': 0,
        'n_unmatched_ai_segments': 0,
        'message': '',
    }

    user_chunks = to_chunks(user_chunks)
    ai_chunks = to_chunks(ai_chunks)

    u_segs = to_segments_with_text(user_chunks, seg_merge_gap_s=seg_merge_gap_s)
    m_segs = to_segments_with_text(ai_chunks, seg_merge_gap_s=seg_merge_gap_s)

    result['n_user_segments'] = len(u_segs)
    result['n_ai_segments'] = len(m_segs)

    if not u_segs:
        result['message'] = 'user_wav 无有效语音段，无法计算每轮回复时延'
        logger.warning(result['message'])
        return result

    if not m_segs:
        result['message'] = 'ai_wav 无有效语音段，无法计算每轮回复时延'
        logger.warning(result['message'])
        return result

    # ── 逐轮匹配：对每个用户段，找其结束后首个未被消费的 AI 段 ──
    consumed_ai: set = set()
    per_round: List[Dict[str, Any]] = []

    for i, (u_s, u_e, u_t) in enumerate(u_segs):
        round_result: Dict[str, Any] = {
            'round_index': i + 1,
            'user_segment': [round(u_s, 3), round(u_e, 3), u_t],
            'ai_segment': None,
            'response_latency_s': None,
            'response_latency_ms': None,
            'inter_round_gap_s': None,
            'message': '',
        }

        matched_j: Optional[int] = None
        for j, (m_s, m_e, m_t) in enumerate(m_segs):
            if j in consumed_ai:
                continue
            if m_s >= u_e:
                matched_j = j
                break

        if matched_j is not None:
            m_s, m_e, m_t = m_segs[matched_j]
            consumed_ai.add(matched_j)

            latency = m_s - u_e
            round_result['ai_segment'] = [round(m_s, 3), round(m_e, 3), m_t]
            round_result['response_latency_s'] = round(latency, 3)
            round_result['response_latency_ms'] = round(latency * 1000, 1)
            round_result['message'] = 'OK'
        else:
            round_result['message'] = '未找到该轮的 AI 回复段（可能 AI 未响应或回复段已在前序轮次消费）'

        # inter_round_gap：本轮 AI 结束 → 下轮用户开始（衡量对话紧凑度）
        if round_result['ai_segment'] is not None and i + 1 < len(u_segs):
            ai_end = round_result['ai_segment'][1]
            next_u_start = u_segs[i + 1][0]
            round_result['inter_round_gap_s'] = round(next_u_start - ai_end, 3)

        per_round.append(round_result)

    result['per_round'] = per_round
    result['n_rounds'] = len(per_round)
    result['n_matched_rounds'] = sum(1 for r in per_round if r['ai_segment'] is not None)
    result['n_missed_rounds'] = sum(1 for r in per_round if r['ai_segment'] is None)
    result['n_unmatched_ai_segments'] = len(m_segs) - len(consumed_ai)

    # ── 聚合统计 ──
    latencies = [r['response_latency_s'] for r in per_round
                 if r['response_latency_s'] is not None]
    if latencies:
        result['avg_response_latency_s'] = round(sum(latencies) / len(latencies), 3)
        result['min_response_latency_s'] = round(min(latencies), 3)
        result['max_response_latency_s'] = round(max(latencies), 3)
        result['avg_response_latency_ms'] = round(
            sum(latencies) / len(latencies) * 1000, 1)

    if result['n_missed_rounds'] > 0:
        result['message'] = (
            f'OK，{result["n_matched_rounds"]}/{result["n_rounds"]} 轮匹配到 AI 回复，'
            f'{result["n_missed_rounds"]} 轮未匹配'
        )
    else:
        result['message'] = 'OK'

    logger.info(
        f"[高频轮换] n_rounds={result['n_rounds']} "
        f"matched={result['n_matched_rounds']} missed={result['n_missed_rounds']} "
        f"unmatched_ai={result['n_unmatched_ai_segments']} "
        f"avg_latency={result['avg_response_latency_s']}s "
        f"min={result['min_response_latency_s']}s max={result['max_response_latency_s']}s"
    )
    return result


if __name__ == '__main__':
    import argparse
    import json
    from ..shared.asr_utils import load_json

    parser = argparse.ArgumentParser(
        description='计算高频轮换场景下每轮回复时延（飞花令/成语接龙/快问快答等）'
    )
    parser.add_argument('--user_asr', required=True,
                        help='用户通道 ASR JSON 路径（{text, chunks} 或 chunks 列表）')
    parser.add_argument('--ai_asr', required=True,
                        help='AI 回复通道 ASR JSON 路径（{text, chunks} 或 chunks 列表）')
    parser.add_argument('--merge_gap', type=float, default=SEG_MERGE_GAP_S,
                        help=f'词合并为段的间隙阈值(秒)，默认 {SEG_MERGE_GAP_S}')
    args = parser.parse_args()

    user_data = load_json(args.user_asr)
    ai_data = load_json(args.ai_asr)

    # 先展示所有段
    u_segs = to_segments_with_text(to_chunks(user_data), seg_merge_gap_s=args.merge_gap)
    m_segs = to_segments_with_text(to_chunks(ai_data), seg_merge_gap_s=args.merge_gap)

    print('── 用户每段讲话 ──')
    for i, (s, e, t) in enumerate(u_segs):
        print(f'  U{i+1}: [{s:.2f}-{e:.2f}] ({e-s:.1f}s)  {t[:50]}')

    print('\n── AI 每段回复 ──')
    for i, (s, e, t) in enumerate(m_segs):
        print(f'  A{i+1}: [{s:.2f}-{e:.2f}] ({e-s:.1f}s)  {t[:50]}')

    # 计算
    r = compute_high_freq_turn_taking(
        user_data, ai_data,
        seg_merge_gap_s=args.merge_gap,
    )
    print('\n── 每轮结果 ──')
    for rd in r['per_round']:
        us = rd['user_segment']
        print(f'  轮{rd["round_index"]}: 用户[{us[0]:.2f}-{us[1]:.2f}] '
              f'→ ', end='')
        if rd['ai_segment']:
            ai = rd['ai_segment']
            print(f'AI[{ai[0]:.2f}-{ai[1]:.2f}] '
                  f'时延={rd["response_latency_ms"]:.0f}ms', end='')
            if rd.get('inter_round_gap_s') is not None:
                print(f'  间隔={rd["inter_round_gap_s"]:.2f}s')
            else:
                print()
        else:
            print('未匹配')

    print(f'\n── 汇总 ──')
    print(f'  总轮数: {r["n_rounds"]}')
    print(f'  匹配: {r["n_matched_rounds"]} / 未匹配: {r["n_missed_rounds"]}')
    print(f'  未消费AI段: {r["n_unmatched_ai_segments"]}')
    if r['avg_response_latency_s'] is not None:
        print(f'  平均时延: {r["avg_response_latency_ms"]:.0f}ms')
        print(f'  最小: {r["min_response_latency_s"]*1000:.0f}ms  '
              f'最大: {r["max_response_latency_s"]*1000:.0f}ms')
    print(f'  {r["message"]}')
