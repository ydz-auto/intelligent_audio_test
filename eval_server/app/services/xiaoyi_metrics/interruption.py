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

时间单位: 秒（与项目 chunks 约定一致，timestamp=[start, end] 为秒）
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────── 阈值 ───────────
SEG_MERGE_GAP_S = 0.3          # 合并相邻词为语音段的间隙阈值（秒），参考 v1.5 USER_MERGE_GAP
# 让出宽限：模型语音段结尾比用户打断结尾晚 YIELD_GRACE_S 以内，仍视为"让出"（模型把当前词说完的自然过延）；
# 超过则视为"说穿"（模型无视打断继续说）。0.05 太严会把词尾过延误判成说穿。
YIELD_GRACE_S = 0.5
EPS_S = 1e-6

# 含实际词字符（CJK / 字母 / 数字）才算是"说话"，纯标点/空白 chunk 的时间戳是 ASR 标点模型伪造的，需剔除
_WORD_RE = re.compile(r'[\w一-鿿]')


def _is_punct_or_empty(text: Any) -> bool:
    """chunk 文本是否纯标点/空白（无实际词字符）"""
    if not text:
        return True
    return not _WORD_RE.search(str(text))


# ─────────── ASR 结果归一化 ───────────
def _to_chunks(val: Any) -> List[Dict[str, Any]]:
    """把 user_asr / model_asr 归一成 chunks 列表

    接受:
        - [{"text":..., "timestamp":[s,e]}, ...]
        - {"text":..., "chunks":[...]}
        - 直接 chunks 列表
    """
    if val is None:
        return []
    if isinstance(val, dict):
        chunks = val.get('chunks')
        if isinstance(chunks, list):
            return chunks
        return []
    if isinstance(val, list):
        return val
    return []


def _valid_ts(ts: Any) -> Optional[Tuple[float, float]]:
    """取 chunk 的 timestamp=[start,end]，非法返回 None"""
    if not isinstance(ts, (list, tuple)) or len(ts) < 2:
        return None
    s, e = ts[0], ts[1]
    if s is None or e is None:
        return None
    try:
        s_f, e_f = float(s), float(e)
    except (TypeError, ValueError):
        return None
    if e_f < s_f:
        return None
    return s_f, e_f


def _to_segments(chunks: List[Dict[str, Any]], gap: float = SEG_MERGE_GAP_S) -> List[Tuple[float, float]]:
    """把词级 chunks 合并成语音段 [(start,end), ...]，按时间排序、相邻间隙<gap 合并

    返回纯语音段（不含段间静默），单位秒。
    """
    intervals: List[Tuple[float, float]] = []
    for c in chunks:
        if not isinstance(c, dict):
            continue
        # 跳过纯标点/空白 chunk：其时间戳是 ASR 标点模型伪造的，不代表真实语音
        if _is_punct_or_empty(c.get('text')):
            continue
        iv = _valid_ts(c.get('timestamp'))
        if iv is None:
            continue
        intervals.append(iv)

    if not intervals:
        return []

    intervals.sort(key=lambda x: x[0])
    merged: List[Tuple[float, float]] = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = merged[-1]
        if s - pe <= gap:
            # 与上一段合并（取更宽的端点）
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def _overlap(a: Tuple[float, float], b: Tuple[float, float]) -> Optional[Tuple[float, float]]:
    """两区间交集，边界相等不算（与 false_takeover._intervals_overlap 一致）"""
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    if e - s <= EPS_S:
        return None
    return s, e


# ─────────── 单事件指标 ───────────
def _evaluate_one_event(u: Tuple[float, float],
                        m_segs: List[Tuple[float, float]]) -> Dict[str, Any]:
    """对单个用户打断段 u=[u_s, u_e] 计算指标

    Args:
        u: 用户打断语音段 (start, end)，秒
        m_segs: 模型语音段列表（已排序），秒

    Returns:
        dict: 单事件结果
    """
    u_s, u_e = u

    # 模型在用户开始打断时正在说的段 m_active（m_s <= u_s < m_e）
    m_active: Optional[Tuple[float, float]] = None
    for ms, me in m_segs:
        if ms <= u_s < me:
            m_active = (ms, me)
            break
        if ms > u_s:
            break  # 已过 u_s，后面更靠后

    # 用户说完之后第一段模型语音（用于恢复时延，无论 m_active 是否存在）
    m_next_after_user: Optional[Tuple[float, float]] = None
    for ms, me in m_segs:
        if ms > u_e:
            m_next_after_user = (ms, me)
            break

    result: Dict[str, Any] = {
        'user_segment': [round(u_s, 3), round(u_e, 3)],
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
        m_s, m_e = m_active
        ov = _overlap(m_active, u)
        result['overlap_s'] = round((ov[1] - ov[0]), 3) if ov else 0.0

        stop_latency = m_e - u_s
        # 模型是否"说穿"：语音段结尾比用户打断结尾晚 YIELD_GRACE_S 以上 → 无视打断继续说
        talked_through = m_e > u_e + YIELD_GRACE_S
        # stopped = 模型让出（没说穿）；与 stop_latency 解耦，后者作为连续量单独报
        stopped = not talked_through
        result['stopped'] = stopped
        # 仅当模型真在打断期间停下时，stop_latency 才有意义；
        # 说穿（没让出）时模型根本没"停止"，记 None，避免把"段尾=轮次结束"误当停止时延
        result['stop_latency_s'] = round(stop_latency, 3) if stopped else None

        # 下一段模型语音（恢复）
        m_next: Optional[Tuple[float, float]] = None
        for ms, me in m_segs:
            if ms > m_e:
                m_next = (ms, me)
                break
        resumed = m_next is not None
        result['resumed'] = resumed
        if m_next is not None:
            result['recovery_latency_s'] = round(m_next[0] - u_e, 3)
            result['silence_gap_s'] = round(m_next[0] - m_e, 3)

        result['event_type'] = 'interruption'
        result['success'] = bool(stopped and resumed)
        return result

    # ── 情形 B：模型当时不在说话（model_asr 可能只含恢复段，或模型提前停了）──
    if m_next_after_user is not None:
        result['recovery_latency_s'] = round(m_next_after_user[0] - u_e, 3)
        result['silence_gap_s'] = None  # 无 m_active 尾巴，静默段无法定义
        result['resumed'] = True
        result['stopped'] = None  # 未知（缺被打断时的模型尾巴）
        result['event_type'] = 'recovery_only'
        result['success'] = None  # 无法判定，不计入成功率分母
        return result

    # ── 情形 C：模型全程没说话 ──
    result['event_type'] = 'no_model_speech'
    result['resumed'] = False
    result['success'] = None
    return result


# ─────────── 主入口 ───────────
def compute_interruption_metrics(user_asr: Any, model_asr: Any,
                                  seg_merge_gap_s: float = SEG_MERGE_GAP_S) -> Dict[str, Any]:
    """计算打断三项指标

    Args:
        user_asr: 用户提问/打断语音的 ASR 结果（chunks 列表 或 {text, chunks}）
        model_asr: 模型恢复语音的 ASR 结果（同上）。两路需在同一时间轴、等长
        seg_merge_gap_s: 词合并为段的间隙阈值（秒），默认 0.3

    Returns:
        dict: {
            'interruption_success_rate': float, 打断成功率（让出且恢复 / 有效打断事件）
            'stop_rate': float,                 让出率（没说穿）
            'resume_rate': float,              恢复率
            'avg_stop_latency_s': float|None,   平均打断检查时延（秒）
            'avg_recovery_latency_s': float|None, 平均打断恢复时延（秒）
            'avg_overlap_s': float|None,        平均双方同时说话时长（秒，越短越好）
            'avg_silence_gap_s': float|None,    平均静默时长（秒）
            'n_events': int,                   有效打断事件数（interruption）
            'n_user_segments': int,            用户语音段总数
            'n_recovery_only': int,            退化事件数（只算到恢复时延）
            'n_no_model_speech': int,           模型全程未说话的用户段数
            'per_event': list,                 每个用户段的结果
            'message': str,
        }
    """
    user_chunks = _to_chunks(user_asr)
    model_chunks = _to_chunks(model_asr)

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
    }

    if not user_chunks:
        result['message'] = 'user_asr 为空，无用户打断段'
        logger.warning(result['message'])
        return result

    u_segs = _to_segments(user_chunks, gap=seg_merge_gap_s)
    m_segs = _to_segments(model_chunks, gap=seg_merge_gap_s)

    result['n_user_segments'] = len(u_segs)
    if not u_segs:
        result['message'] = 'user_asr 无有效时间戳，无法提取打断段'
        logger.warning(result['message'])
        return result

    if not m_segs:
        # 模型全程没说话：所有用户段都是 no_model_speech
        result['n_no_model_speech'] = len(u_segs)
        result['per_event'] = [_evaluate_one_event(u, []) for u in u_segs]
        result['message'] = 'model_asr 为空，模型全程未说话，无法计算打断指标'
        logger.warning(result['message'])
        return result

    per_event = [_evaluate_one_event(u, m_segs) for u in u_segs]
    result['per_event'] = per_event

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

    # 时延均值：interruption + recovery_only 都能贡献 recovery_latency；stop_latency 仅 interruption
    stop_lats = [e['stop_latency_s'] for e in interruption_events if e['stop_latency_s'] is not None]
    recov_lats = [e['recovery_latency_s'] for e in per_event if e['recovery_latency_s'] is not None]
    overlaps = [e['overlap_s'] for e in interruption_events if e['overlap_s'] is not None]
    silences = [e['silence_gap_s'] for e in per_event if e['silence_gap_s'] is not None]

    def _avg(lst):
        return round(sum(lst) / len(lst), 3) if lst else None

    result['avg_stop_latency_s'] = _avg(stop_lats)
    result['avg_recovery_latency_s'] = _avg(recov_lats)
    result['avg_overlap_s'] = _avg(overlaps)
    result['avg_silence_gap_s'] = _avg(silences)

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
        f"avg_stop={result['avg_stop_latency_s']}s avg_recovery={result['avg_recovery_latency_s']}s"
    )
    return result


if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(description='计算打断三项指标（用户流 + 模型恢复流 ASR）')
    parser.add_argument('--user_asr', required=True,
                        help='用户提问 ASR JSON 路径（{text, chunks} 或 chunks 列表）')
    parser.add_argument('--model_asr', required=True,
                        help='模型恢复 ASR JSON 路径（{text, chunks} 或 chunks 列表）')
    parser.add_argument('--merge_gap', type=float, default=SEG_MERGE_GAP_S,
                        help=f'词合并为段的间隙阈值(秒)，默认 {SEG_MERGE_GAP_S}')
    args = parser.parse_args()

    def _load(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)

    r = compute_interruption_metrics(
        _load(args.user_asr), _load(args.model_asr),
        seg_merge_gap_s=args.merge_gap,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2))
