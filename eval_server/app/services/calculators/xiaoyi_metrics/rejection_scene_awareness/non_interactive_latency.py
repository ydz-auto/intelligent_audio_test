# -*- coding: utf-8 -*-
"""
non_interactive_latency.py
用户非交互意图语音期间，模型响应时延计算

场景:
    用户问完后，模型开始第一次回复。在回复期间用户又说了话（user_asr 的第 2 段），
    需要计算两个时延:
        1. stop_latency_s     : 用户开始讲话 → 模型停止回复
        2. recovery_latency_s  : 用户讲完 → 模型开始回复

输入: 两路 wav 音频路径（内部自动调 ASR 服务）
    - user_wav : 用户语音 wav 路径
    - ai_wav   : 模型语音 wav 路径

时间单位: 秒（timestamp=[start, end]）
"""
import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _get_asr(wav_path: str) -> Dict[str, Any]:
    """调用远程 ASR 服务获取词级时间戳，返回 {text, chunks} 结构"""
    if not wav_path or not os.path.isfile(wav_path):
        raise FileNotFoundError(f"wav 文件不存在: {wav_path}")
    from app.utils.asr_adapator import call_modelscope_asr, parse_result
    raw = call_modelscope_asr(wav_path)
    return parse_result(raw)

# ─────────── 阈值 ───────────
SEG_MERGE_GAP_S = 0.7  # 合并相邻词为语音段的间隙阈值（秒），0.7s 适配句内最大停顿 ~0.5s

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


def _to_segments(chunks: List[Dict[str, Any]], gap: float = SEG_MERGE_GAP_S
                 ) -> List[Tuple[float, float, str]]:
    """把词级 chunks 合并成语音段 [(start, end, text), ...]

    按时间排序、相邻间隙 < gap 合并。返回纯语音段（不含段间静默），单位秒。
    """
    intervals: List[Tuple[float, float, str]] = []
    for c in chunks:
        if not isinstance(c, dict):
            continue
        if _is_punct_or_empty(c.get('text')):
            continue
        iv = _valid_ts(c.get('timestamp'))
        if iv is None:
            continue
        intervals.append((iv[0], iv[1], str(c.get('text', ''))))

    if not intervals:
        return []

    intervals.sort(key=lambda x: x[0])
    merged: List[Tuple[float, float, str]] = [intervals[0]]
    for s, e, t in intervals[1:]:
        ps, pe, pt = merged[-1]
        if s - pe <= gap:
            merged[-1] = (ps, max(pe, e), pt + t)
        else:
            merged.append((s, e, t))
    return merged


# ─────────── 主逻辑 ───────────
def _compute_from_asr(user_asr: Any, model_asr: Any,
                      seg_merge_gap_s: float = SEG_MERGE_GAP_S,
                      target_segment_index: int = 1) -> Dict[str, Any]:
    """从已就绪的 ASR 结果计算时延（内部函数，不调 ASR 服务）

    Args:
        user_asr: 用户语音 ASR 结果（chunks 列表 或 {text, chunks}）
        model_asr: 模型语音 ASR 结果（同上）。两路需在同一时间轴
        seg_merge_gap_s: 词合并为段的间隙阈值（秒），默认 0.7
        target_segment_index: 目标用户段索引（0-based，默认 1=第 2 段）

    Returns:
        dict: {
            'stop_latency_s': float|None,       用户开始讲话→模型停止回复
            'recovery_latency_s': float|None,    用户讲完→模型开始回复
            'user_segment': [start, end, text],
            'model_active_segment': [start, end, text]|None,
            'model_recovery_segment': [start, end, text]|None,
            'silence_gap_s': float|None,  模型第一次回复结束→再次回复的静默
            'overlap_s': float|None,     用户与模型同时说话的时长
            'n_user_segments': int,
            'n_model_segments': int,
            'message': str,
        }
    """
    result: Dict[str, Any] = {
        'stop_latency_s': None,
        'recovery_latency_s': None,
        'user_segment': None,
        'model_active_segment': None,
        'model_recovery_segment': None,
        'silence_gap_s': None,
        'overlap_s': None,
        'n_user_segments': 0,
        'n_model_segments': 0,
        'message': '',
    }

    user_chunks = _to_chunks(user_asr)
    model_chunks = _to_chunks(model_asr)

    u_segs = _to_segments(user_chunks, gap=seg_merge_gap_s)
    m_segs = _to_segments(model_chunks, gap=seg_merge_gap_s)

    result['n_user_segments'] = len(u_segs)
    result['n_model_segments'] = len(m_segs)

    if not u_segs:
        result['message'] = 'user_asr 无有效时间戳，无法提取用户段'
        logger.warning(result['message'])
        return result

    if target_segment_index >= len(u_segs):
        result['message'] = (
            f'用户只有 {len(u_segs)} 段语音，无法取第 {target_segment_index + 1} 段作为目标'
        )
        logger.warning(result['message'])
        return result

    # 目标用户段
    u_s, u_e, u_t = u_segs[target_segment_index]
    result['user_segment'] = [round(u_s, 3), round(u_e, 3), u_t]

    # ── 1. 定位被插话的模型回复段 ──
    # 用目标段的前一段（提问段）结束时间，找模型在该时间之后、且与用户目标段有重叠或紧邻的回复段
    prev_idx = target_segment_index - 1
    if prev_idx < 0:
        result['message'] = '目标段为第 1 段，无前一段提问可定位模型回复'
        logger.warning(result['message'])
        return result

    u_prev_end = u_segs[prev_idx][1]  # 前一段提问的结束时间

    # 找在用户提问后开始的模型段中，在用户目标段开始时正在说话（或刚说完）的段
    m_active: Optional[Tuple[float, float, str]] = None
    for ms, me, mt in m_segs:
        if ms >= u_prev_end:  # 在用户提问之后开始的模型段
            # 优先找与用户目标段有时间重叠的模型段
            if me > u_s:  # 模型在用户开始讲话时还没说完
                m_active = (ms, me, mt)
                break
            # 记录最后一个在用户开始之前结束的段（作为候选）
            if m_active is None:
                m_active = (ms, me, mt)

    if m_active is not None:
        m_s, m_e, m_t = m_active
        result['model_active_segment'] = [round(m_s, 3), round(m_e, 3), m_t]

        # 用户开始讲话 → 模型停止回复（模型在用户说话时还在继续，持续了多久才停）
        # 如果模型在用户开始前就已结束，说明没有被打断，stop_latency=0
        result['stop_latency_s'] = round(max(0.0, m_e - u_s), 3)

        # 重叠时长
        ov_s = max(0.0, min(m_e, u_e) - max(m_s, u_s))
        result['overlap_s'] = round(ov_s, 3)

        # ── 2. 找模型再次回复的段（第一次回复结束之后的新段）──
        m_next: Optional[Tuple[float, float, str]] = None
        for ms, me, mt in m_segs:
            if ms >= m_e and ms > u_e:
                m_next = (ms, me, mt)
                break

        if m_next is not None:
            result['model_recovery_segment'] = [round(m_next[0], 3), round(m_next[1], 3), m_next[2]]
            result['recovery_latency_s'] = round(m_next[0] - u_e, 3)
            result['silence_gap_s'] = round(m_next[0] - m_e, 3)
        else:
            logger.warning('用户讲完后模型未再次回复，无法计算恢复时延')

        result['message'] = 'OK'
    else:
        # 用户提问后模型未回复，两个时延都返回 None
        result['message'] = '用户提问后模型未回复，stop_latency 和 recovery 均为 None'
        logger.warning(
            f'用户第 {prev_idx + 1} 段提问结束({u_prev_end:.3f}s)后模型未回复，'
            '两个时延均为 None'
        )

    logger.info(
        f"[非交互意图时延] user_seg={result['user_segment']} "
        f"stop_latency={result['stop_latency_s']}s recovery={result['recovery_latency_s']}s "
        f"silence={result['silence_gap_s']}s overlap={result['overlap_s']}s "
        f"msg={result['message']}"
    )
    return result


def compute_non_interactive_latency(user_wav: str, ai_wav: str,
                                    seg_merge_gap_s: float = SEG_MERGE_GAP_S,
                                    target_segment_index: int = 1) -> Dict[str, Any]:
    """计算用户在模型回复期间说话的时延（内部自动调 ASR 服务）

    Args:
        user_wav: 用户语音 wav 路径
        ai_wav: 模型语音 wav 路径
        seg_merge_gap_s: 词合并为段的间隙阈值（秒），默认 0.7
        target_segment_index: 目标用户段索引（0-based，默认 1=第 2 段）
    """
    user_asr = _get_asr(user_wav)
    model_asr = _get_asr(ai_wav)
    return _compute_from_asr(user_asr, model_asr,
                             seg_merge_gap_s=seg_merge_gap_s,
                             target_segment_index=target_segment_index)


if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='计算用户在模型回复期间说话的时延'
    )
    parser.add_argument('--user_wav', required=True,
                        help='用户 wav 路径')
    parser.add_argument('--ai_wav', required=True,
                        help='模型 wav 路径')
    parser.add_argument('--merge_gap', type=float, default=SEG_MERGE_GAP_S,
                        help=f'词合并为段的间隙阈值(秒)，默认 {SEG_MERGE_GAP_S}')
    parser.add_argument('--target_index', type=int, default=1,
                        help='目标用户段索引（0-based，默认 1=第 2 段）')
    args = parser.parse_args()

    # 计算（内部自动调 ASR）
    r = compute_non_interactive_latency(
        args.user_wav, args.ai_wav,
        seg_merge_gap_s=args.merge_gap,
        target_segment_index=args.target_index,
    )
    print(f'\n── 计算结果 ──')
    print(json.dumps(r, ensure_ascii=False, indent=2))

    # 时间线
    if r.get('message') == 'OK':
        print('\n── 关键时间线 ──')
        us, ue, ut = r['user_segment']
        print(f'  用户讲话:   [{us:.1f}-{ue:.1f}] {ut[:30]}')
        if r['model_active_segment']:
            ms, me, mt = r['model_active_segment']
            print(f'  模型回复:   [{ms:.1f}-{me:.1f}] {mt[:30]}')
            print(f'  重叠:       {r["overlap_s"]}s')
            if r['stop_latency_s'] is not None:
                print(f'  开始讲话→模型停止: {r["stop_latency_s"]}s')
        if r['model_recovery_segment']:
            rs, re_, rt = r['model_recovery_segment']
            print(f'  模型再回复: [{rs:.1f}-{re_:.1f}] {rt[:30]}')
            print(f'  讲完→再回复: {r["recovery_latency_s"]}s')
            if r['silence_gap_s'] is not None:
                print(f'  静默:       {r["silence_gap_s"]}s')
