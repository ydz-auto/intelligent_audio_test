# -*- coding: utf-8 -*-
"""
interruption.py
打断指标计算：用户打断正在说话的小艺时，衡量小艺"停得下、恢复得来"

输入: 两路 ASR 词级时间戳（用户提问流 + 模型恢复流），二者等长、同一时间轴
     - user_asr  : 用户打断语音的 ASR chunks（即"打断事件"来源）
     - model_asr : 模型语音的 ASR chunks（含被打断时正在说的尾巴 + 停顿 + 恢复）
                   若只含恢复段，停止时延无法判定，自动退化成只算恢复时延

三个指标（对每个用户打断段 u=[u_s, u_e]）:
    1. 打断检查时延 (stop_latency)      : 用户开始打断 → 模型当前语音段结束（停下）
                                          参考 Full-Duplex-Bench v1.5 get_timing.py latency_stop_list
    2. 打断恢复时延 (recovery_latency)  : 用户说完 → 模型重新开口（恢复段起点）
                                          参考 Full-Duplex-Bench v1.5 get_timing.py latency_resp_list
    3. 打断成功率    (success)           : 在容差内停下 且 之后恢复（event_type='interruption' 才计入分母）
                                          参考 v1.0 eval_user_interruption.py 的 TOR↑

时间单位: ASR 时间戳/语音段为秒（timestamp=[start, end] 为秒）；
     时长指标（stop_latency/recovery_latency/overlap/silence_gap 及其均值）输出为毫秒(ms)，
     字段名保留 _s 历史后缀以便兼容既有维度 field_path，但值为毫秒。
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    ASR_USER_SEG_MERGE_GAP_S,
    ASR_MODEL_SEG_MERGE_GAP_S,
    YIELD_GRACE_S,
    EPS_S,
)
from app.services.calculators.xiaoyi_metrics.shared.asr_utils import (
    is_punct_or_empty,
    to_chunks,
    valid_ts,
)

logger = logging.getLogger(__name__)

# ─────────── 阈值 ───────────
# 用户侧/模型侧用不同阈值合并字词为语音段：用户 1.5s（句内停顿宽松），
# 模型 0.7s（更敏感，以识别打断后短停顿 + 恢复，避免把"停下又恢复"并成一段而漏判）
USER_SEG_MERGE_GAP_S = ASR_USER_SEG_MERGE_GAP_S
MODEL_SEG_MERGE_GAP_S = ASR_MODEL_SEG_MERGE_GAP_S

# _is_punct_or_empty / _to_chunks / _valid_ts 由 shared.asr_utils 提供（消除重复实现）


# ─────────── ASR 结果归一化 ───────────


def _to_segments(chunks: List[Dict[str, Any]], gap: float = USER_SEG_MERGE_GAP_S) -> List[Dict[str, Any]]:
    """把词级 chunks 合并成语音段，返回 [{start, end, text, words}, ...]

    - 按时间排序、相邻间隙 < gap 的词合并为同一段
    - text 为该段内词文本拼接（保留 ASR 原序），words 为该段内原始 word chunks
      （{text, timestamp}，供 LLM 拿到字词级 ASR 结果做语义复核/打分）
    - 跳过纯标点/空白 chunk：其时间戳是 ASR 标点模型伪造的，不代表真实语音

    返回纯语音段（不含段间静默），单位秒。
    """
    words: List[Dict[str, Any]] = []
    for c in chunks:
        if not isinstance(c, dict):
            continue
        # 跳过纯标点/空白 chunk：其时间戳是 ASR 标点模型伪造的，不代表真实语音
        if is_punct_or_empty(c.get('text')):
            continue
        iv = valid_ts(c.get('timestamp'))
        if iv == (0.0, 0.0):  # 无效时间戳（valid_ts 的哨兵返回值）
            continue
        words.append({'text': str(c.get('text', '')), 'timestamp': [iv[0], iv[1]]})

    if not words:
        return []

    # 按起点排序，保留 word 原始字段
    words.sort(key=lambda w: w['timestamp'][0])
    merged: List[Dict[str, Any]] = [{
        'start': words[0]['timestamp'][0],
        'end': words[0]['timestamp'][1],
        'text': words[0]['text'],
        'words': [words[0]],
    }]
    for w in words[1:]:
        s, e = w['timestamp']
        cur = merged[-1]
        if s - cur['end'] <= gap:
            # 与上一段合并（取更宽的端点、拼接文本与词）
            cur['end'] = max(cur['end'], e)
            cur['text'] += w['text']
            cur['words'].append(w)
        else:
            merged.append({'start': s, 'end': e, 'text': w['text'], 'words': [w]})
    return merged


def _overlap(a, b) -> Optional[Tuple[float, float]]:
    """两区间交集，边界相等不算（与 false_takeover._intervals_overlap 一致）

    a/b 可为 (start, end) 元组或 {'start':..,'end':..} 段字典。
    """
    a_s = a[0] if isinstance(a, (list, tuple)) else a['start']
    a_e = a[1] if isinstance(a, (list, tuple)) else a['end']
    b_s = b[0] if isinstance(b, (list, tuple)) else b['start']
    b_e = b[1] if isinstance(b, (list, tuple)) else b['end']
    s = max(a_s, b_s)
    e = min(a_e, b_e)
    if e - s <= EPS_S:
        return None
    return s, e


# ─────────── 单事件指标 ───────────
def _evaluate_one_event(u: Dict[str, Any],
                        m_segs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对单个用户打断段 u={start,end,text,words} 计算指标

    Args:
        u: 用户打断语音段 dict（start/end 秒、text、words 字词级 chunks）
        m_segs: 模型语音段列表（同 dict 结构，已按 start 排序）

    Returns:
        dict: 单事件结果。除时序指标外，富集 user/model 的字词级 ASR 文本与 words，
              供 LLM 做语义复核与回复打分（is_real_interruption / coherence 等）。
    """
    u_s, u_e = u['start'], u['end']

    # 模型在用户开始打断时正在说的段 m_active（m_s <= u_s < m_e）
    m_active: Optional[Dict[str, Any]] = None
    for m in m_segs:
        if m['start'] <= u_s < m['end']:
            m_active = m
            break
        if m['start'] > u_s:
            break  # 已过 u_s，后面更靠后

    # 用户说完之后第一段模型语音（用于恢复时延，无论 m_active 是否存在）
    m_next_after_user: Optional[Dict[str, Any]] = None
    for m in m_segs:
        if m['start'] > u_e:
            m_next_after_user = m
            break

    result: Dict[str, Any] = {
        'user_segment': [round(u_s, 3), round(u_e, 3)],
        'user_text': u.get('text', ''),
        'user_words': u.get('words', []),
        'model_interrupted_text': '',
        'model_interrupted_words': [],
        'model_recovery_text': '',
        'model_recovery_words': [],
        'event_type': '',
        'stop_latency_s': None,
        'recovery_latency_s': None,
        'silence_gap_s': None,
        'overlap_s': None,
        'stopped': None,
        'resumed': None,
        'success': None,
    }

    # ── 情形 A：模型当时在说话（完整打断事件）──
    if m_active is not None:
        ov = _overlap(m_active, u)
        # 时长指标以毫秒(ms)输出：内部时间戳/段为秒，差值 ×1000 转毫秒
        result['overlap_s'] = round((ov[1] - ov[0]) * 1000, 1) if ov else 0.0
        # 被打断时模型正在说的尾巴（字词级 ASR）
        result['model_interrupted_text'] = m_active.get('text', '')
        result['model_interrupted_words'] = m_active.get('words', [])

        stop_latency = m_active['end'] - u_s

        # 下一段模型语音（恢复）：m_next 存在说明模型当前段结束后停了下来，之后又恢复
        m_next: Optional[Dict[str, Any]] = None
        for m in m_segs:
            if m['start'] > m_active['end']:
                m_next = m
                break
        resumed = m_next is not None

        # 模型是否停下：有后续恢复段 = 停下了（可能有时延，正是要测量的）
        # 无后续段 = 模型说完就没再恢复 = 完全无视打断，一直说完才结束
        stopped = resumed
        result['stopped'] = stopped
        result['resumed'] = resumed
        result['stop_latency_s'] = round(stop_latency * 1000, 1) if stopped else None
        if m_next is not None:
            result['recovery_latency_s'] = round((m_next['start'] - u_e) * 1000, 1)
            result['silence_gap_s'] = round((m_next['start'] - m_active['end']) * 1000, 1)
            result['model_recovery_text'] = m_next.get('text', '')
            result['model_recovery_words'] = m_next.get('words', [])

        result['event_type'] = 'interruption'
        result['success'] = bool(stopped and resumed)
        return result

    # ── 情形 B：模型当时不在说话（model_asr 可能只含恢复段，或模型提前停了）──
    if m_next_after_user is not None:
        result['recovery_latency_s'] = round((m_next_after_user['start'] - u_e) * 1000, 1)
        result['silence_gap_s'] = None  # 无 m_active 尾巴，静默段无法定义
        result['resumed'] = True
        result['stopped'] = None  # 未知（缺被打断时的模型尾巴）
        result['event_type'] = 'recovery_only'
        result['success'] = None  # 无法判定，不计入成功率分母
        result['model_recovery_text'] = m_next_after_user.get('text', '')
        result['model_recovery_words'] = m_next_after_user.get('words', [])
        return result

    # ── 情形 C：模型全程没说话 ──
    result['event_type'] = 'no_model_speech'
    result['resumed'] = False
    result['success'] = None
    return result


# ─────────── 主入口 ───────────
def compute_interruption_metrics(user_asr: Any, model_asr: Any,
                                  user_seg_merge_gap_s: float = USER_SEG_MERGE_GAP_S,
                                  model_seg_merge_gap_s: float = MODEL_SEG_MERGE_GAP_S) -> Dict[str, Any]:
    """计算打断指标（时延类用数据算；成功率由调用方叠加 LLM 语义判定覆盖）

    用户侧/模型侧用不同阈值合并字词为语音段（user 1.5s / model 0.7s），
    避免共用一个阈值导致模型"短停顿+恢复"被并成一段而漏判。

    Args:
        user_asr: 用户提问/打断语音的 ASR 结果（chunks 列表 或 {text, chunks}）
        model_asr: 模型恢复语音的 ASR 结果（同上）。两路需在同一时间轴、等长
        user_seg_merge_gap_s: 用户侧词合并为段的间隙阈值(秒)，默认 1.5
        model_seg_merge_gap_s: 模型侧词合并为段的间隙阈值(秒)，默认 0.7

    Returns:
        dict: {
            'interruption_success_rate': float, 打断成功率（本地时序启发式：让出且恢复 / 有效打断事件；
                                              若 LLM 启用，由 calculate_interruption_metrics 用 LLM 语义判定覆盖）
            'stop_rate': float,                 让出率（没说穿，时序启发式）
            'resume_rate': float,              恢复率（时序启发式）
            'avg_stop_latency_s': float|None,   平均打断检查时延（毫秒；字段名保留 _s 历史后缀，值为 ms）
            'avg_recovery_latency_s': float|None, 平均打断恢复时延（毫秒）
            'avg_overlap_s': float|None,        平均双方同时说话时长（毫秒，越短越好）
            'avg_silence_gap_s': float|None,    平均静默时长（毫秒）
            'n_events': int,                   有效打断事件数（interruption）
            'n_user_segments': int,            用户语音段总数
            'n_recovery_only': int,            退化事件数（只算到恢复时延）
            'n_no_model_speech': int,           模型全程未说话的用户段数
            'per_event': list,                 每个用户段的结果
            'message': str,
        }
    """
    user_chunks = to_chunks(user_asr)
    model_chunks = to_chunks(model_asr)

    result: Dict[str, Any] = {
        'interruption_success_rate': 0.0,
        'stop_rate': 0.0,
        'resume_rate': 0.0,
        'avg_stop_latency_s': None,
        'avg_recovery_latency_s': None,
        'avg_overlap_s': None,
        'avg_silence_gap_s': None,
        'n_events': 0,
        'n_user_segments': 0,
        'n_recovery_only': 0,
        'n_no_model_speech': 0,
        'per_event': [],
        'message': '',
        # ── 大模型评估（可选）：由 calculate_interruption_metrics 在
        # enable_llm_eval=True 且配置 API key 时填充，未启用时保持这些默认值 ──
        # 行为分类裁判（五类行为）已移除，改由 interruption_judge 维度承担
        # 注：interruption_success_rate 是本地时序启发式(让出且恢复)；LLM 启用时由
        #    calculate_interruption_metrics 用 LLM 语义判定覆盖，本地值存到 timing_success_rate
        'timing_success_rate': None,   # 本地时序启发式成功率(备份)，LLM 启用前与 interruption_success_rate 同值
        'llm_success_rate': None,     # LLM 语义判定的成功率(成功事件/已评估事件)
        'llm_eval': {'enabled': False, 'message': '未启用 LLM 评估'},
        'llm_recovery_avg_coherence': None,
        'llm_recovery_avg_relevance': None,
        'llm_recovery_avg_adaptability': None,
        'llm_recovery_coherence_reason': None,
        'llm_recovery_relevance_reason': None,
        'llm_recovery_adaptability_reason': None,
        'llm_return_avg_coherence': None,
        'llm_return_avg_relevance': None,
        'llm_return_avg_adaptability': None,
        'llm_recovery_per_round': [],
        'llm_return_scores_per_round': [],
        # ── 两路完整语音段时间线（过滤开场白后，含字词级 words），
        # 供 LLM 评估时看到模型/用户全局上下文，而非仅 per_event 里的两段切片 ──
        'user_segments': [],
        'model_segments': [],
    }

    if not user_chunks:
        result['message'] = 'user_asr 为空，无用户打断段'
        logger.warning(result['message'])
        return result

    u_segs = _to_segments(user_chunks, gap=user_seg_merge_gap_s)
    m_segs = _to_segments(model_chunks, gap=model_seg_merge_gap_s)

    result['n_user_segments'] = len(u_segs)
    if not u_segs:
        result['message'] = 'user_asr 无有效时间戳，无法提取打断段'
        logger.warning(result['message'])
        return result

    # 过滤模型开场白：用户第一句之前的模型语音段是问候语，不作为打断判定依据
    if u_segs and m_segs:
        first_u_start = u_segs[0]['start']
        m_segs = [m for m in m_segs if m['start'] >= first_u_start]

    if not m_segs:
        # 模型全程没说话：所有用户段都是 no_model_speech
        result['n_no_model_speech'] = len(u_segs)
        result['per_event'] = [_evaluate_one_event(u, []) for u in u_segs]
        result['user_segments'] = u_segs   # 模型侧为空，保持默认 []
        result['message'] = 'model_asr 为空，模型全程未说话，无法计算打断指标'
        logger.warning(result['message'])
        return result

    per_event = [_evaluate_one_event(u, m_segs) for u in u_segs]
    result['per_event'] = per_event
    # 导出两路完整时间线（u_segs/m_segs 已在上方过滤开场白，含字词级 words），
    # 供 LLM 评估看到全局上下文，与本地判定使用同一份段数据
    result['user_segments'] = u_segs
    result['model_segments'] = m_segs

    # ── 聚合 ──
    interruption_events = [e for e in per_event if e['event_type'] == 'interruption']
    recovery_only_events = [e for e in per_event if e['event_type'] == 'recovery_only']
    no_model_events = [e for e in per_event if e['event_type'] == 'no_model_speech']

    result['n_events'] = len(interruption_events)
    result['n_recovery_only'] = len(recovery_only_events)
    result['n_no_model_speech'] = len(no_model_events)

    n = len(interruption_events)
    if n > 0:
        result['interruption_success_rate'] = round(
            sum(1 for e in interruption_events if e['success']) / n, 3)
        result['stop_rate'] = round(
            sum(1 for e in interruption_events if e['stopped']) / n, 3)
        result['resume_rate'] = round(
            sum(1 for e in interruption_events if e['resumed']) / n, 3)

    # 时延均值：stop_latency/recovery_latency/overlap 仅统计 interruption 事件
    stop_lats = [e['stop_latency_s'] for e in interruption_events if e['stop_latency_s'] is not None]
    recov_lats = [e['recovery_latency_s'] for e in interruption_events if e['recovery_latency_s'] is not None]
    overlaps = [e['overlap_s'] for e in interruption_events if e['overlap_s'] is not None]
    silences = [e['silence_gap_s'] for e in per_event if e['silence_gap_s'] is not None]

    result['avg_stop_latency_s'] = BaseCalculator._avg(stop_lats)
    result['avg_recovery_latency_s'] = BaseCalculator._avg(recov_lats)
    result['avg_overlap_s'] = BaseCalculator._avg(overlaps)
    result['avg_silence_gap_s'] = BaseCalculator._avg(silences)

    if n == 0 and result['n_recovery_only'] > 0:
        result['message'] = (
            'model_asr 似乎只含恢复段（用户打断时模型未在说话），'
            '停止时延/成功率无法判定，仅给出恢复时延'
        )
        logger.warning(result['message'])
    else:
        result['message'] = 'OK'

    logger.info(
        f"[打断指标] n_user_segments={result['n_user_segments']} "
        f"n_events={n} n_recovery_only={result['n_recovery_only']} "
        f"success_rate={result['interruption_success_rate']} "
        f"stop_rate={result['stop_rate']} resume_rate={result['resume_rate']} "
        f"avg_stop={result['avg_stop_latency_s']}ms avg_recovery={result['avg_recovery_latency_s']}ms"
    )
    return result


if __name__ == '__main__':
    import argparse
    import json
    from app.services.calculators.xiaoyi_metrics.shared.asr_utils import load_json

    parser = argparse.ArgumentParser(description='计算打断三项指标（用户流 + 模型恢复流 ASR）')
    parser.add_argument('--user_asr', required=True,
                        help='用户提问 ASR JSON 路径（{text, chunks} 或 chunks 列表）')
    parser.add_argument('--model_asr', required=True,
                        help='模型恢复 ASR JSON 路径（{text, chunks} 或 chunks 列表）')
    parser.add_argument('--user_merge_gap', type=float, default=USER_SEG_MERGE_GAP_S,
                        help=f'用户侧词合并为段的间隙阈值(秒)，默认 {USER_SEG_MERGE_GAP_S}')
    parser.add_argument('--model_merge_gap', type=float, default=MODEL_SEG_MERGE_GAP_S,
                        help=f'模型侧词合并为段的间隙阈值(秒)，默认 {MODEL_SEG_MERGE_GAP_S}')
    args = parser.parse_args()

    r = compute_interruption_metrics(
        load_json(args.user_asr), load_json(args.model_asr),
        user_seg_merge_gap_s=args.user_merge_gap,
        model_seg_merge_gap_s=args.model_merge_gap,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2))
