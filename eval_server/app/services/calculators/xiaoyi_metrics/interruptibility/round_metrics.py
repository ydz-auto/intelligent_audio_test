# -*- coding: utf-8 -*-
"""打断指标 v2 派生层：用例类型推导 + 逐轮时序锚定 + spec 指标派生（纯函数，无 IO/LLM）

对应《打断指标重构规划》(04-工作安排/打断指标重构.md) §3.1/§3.2/§3.4：
  - derive_case_type       : 7 类用例类型由轮次标记推导（is_actual_interruption + stop_intent + is_return_to_topic）
  - extract_round_timing   : 单轮时序锚定（FFT 窗口 → 驱动轮窗口 → 最大重叠启发式），出响应/回复时延(ms)
  - derive_round_metrics   : 时序 × 行为(LLM，可缺省) → spec 全部字段（数量/时延 list(-1)/avg/min/max/评分/停止遵从）

口径（规划 §0 默认口径）：
  - 询问轮时延照记不 -1；失败(恢复/无关/静默)与 unknown 轮 list 记 -1、不入数量
  - avg/min/max 排除 -1，全 -1 → None
  - 行为不可用(round_behaviors=None，LLM 降级) → 数量/评分 None、list 全 -1
  - 恢复轮不入数量分母；停止指令遵循仅停止类用例计算，否则 None
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 五分类行为量表（spec：回复/恢复/无关/静默/询问；判定全部来自 LLM，本模块只做确定性映射）
BEHAVIOR_REPLY = '回复'
BEHAVIOR_RECOVER = '恢复'
BEHAVIOR_IRRELEVANT = '无关'
BEHAVIOR_SILENCE = '静默'
BEHAVIOR_ASK = '询问'
BEHAVIOR_LABELS_V2 = (BEHAVIOR_REPLY, BEHAVIOR_RECOVER, BEHAVIOR_IRRELEVANT,
                      BEHAVIOR_SILENCE, BEHAVIOR_ASK)
# 成败映射（spec：回复行为=成功，恢复/无关/静默=失败，询问=询问）
_FAIL_BEHAVIORS = (BEHAVIOR_RECOVER, BEHAVIOR_IRRELEVANT, BEHAVIOR_SILENCE)

CASE_TYPE_LABELS = {
    'single': '一次打断',
    'single_stop': '一次打断-停止指令',
    'multi': '多次打断',
    'stop_resume_single': '停止指令后恢复前文-一次打断一次恢复',
    'stop_resume_multi': '停止指令后恢复前文-多次打断一次恢复',
    'topic_resume_single': '其他话题后恢复前文-一次插入',
    'topic_resume_multi': '其他话题后恢复前文-多次插入',
}
STOP_CASE_TYPES = ('single_stop', 'stop_resume_single', 'stop_resume_multi')

_RESUME_ALIASES = ('is_return_to_topic', 'isReturnToTopic', 'return_to_topic')


def _as_bool(value):
    from . import _as_bool as pkg_as_bool
    return pkg_as_bool(value)


def _as_float(value) -> Optional[float]:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _round_data(rounds, idx) -> Dict[str, Any]:
    if isinstance(rounds, list) and 0 <= idx < len(rounds) and isinstance(rounds[idx], dict):
        return rounds[idx]
    return {}


# ─────────── §3.1 用例类型推导 ───────────

def derive_case_type(rounds, actual_rounds, dangling_rounds,
                     stop_intent: Any = None) -> Dict[str, Any]:
    """7 类用例类型推导（零平台配置，全部来自轮次标记）。

    Args:
        rounds: 轮次列表（取 is_return_to_topic / stop_intent 标记；逐轮评估切片时可能不全）
        actual_rounds: 有效实际打断轮索引
        dangling_rounds: 末轮 dangling 标记（不计入 n）
        stop_intent: 用例级停止标记兜底（bool 或按轮 list；rounds 缺失轮内标记时用）

    Returns:
        {case_type, case_type_label, is_stop_type, n_actual,
         effective_actual_rounds, resume_rounds}；无有效实际轮时 case_type=None
    """
    from . import _get_stop_intent

    rounds = rounds if isinstance(rounds, list) else []
    resume_rounds = [
        i for i, rd in enumerate(rounds)
        if isinstance(rd, dict) and any(_as_bool(rd.get(k)) for k in _RESUME_ALIASES)
    ]
    skip = set(dangling_rounds or []) | set(resume_rounds)
    effective = [i for i in (actual_rounds or []) if i not in skip]
    n = len(effective)

    stop = False
    for i in effective:
        rd = _round_data(rounds, i)
        if rd and _get_stop_intent({}, rd):
            stop = True
            break
    if not stop and stop_intent is not None:
        if isinstance(stop_intent, list):
            stop = any(_as_bool(stop_intent[i]) for i in effective
                       if 0 <= i < len(stop_intent))
        else:
            stop = _as_bool(stop_intent) and bool(effective)

    if n == 0 and not stop:
        return {'case_type': None, 'case_type_label': None, 'is_stop_type': False,
                'n_actual': 0, 'effective_actual_rounds': effective,
                'resume_rounds': resume_rounds}

    has_resume = bool(resume_rounds)
    if has_resume:
        if stop:
            case_type = 'stop_resume_single' if n <= 1 else 'stop_resume_multi'
        else:
            case_type = 'topic_resume_single' if n <= 1 else 'topic_resume_multi'
    elif stop:
        case_type = 'single_stop'
    else:
        case_type = 'single' if n <= 1 else 'multi'

    return {
        'case_type': case_type,
        'case_type_label': CASE_TYPE_LABELS[case_type],
        'is_stop_type': case_type in STOP_CASE_TYPES,
        'n_actual': n,
        'effective_actual_rounds': effective,
        'resume_rounds': resume_rounds,
    }


# ─────────── §3.2 逐轮时序锚定 ───────────

def round_latency_from_window(u_s: float, u_e: float,
                              model_segments: List[Dict[str, Any]],
                              u_next: Optional[float] = None) -> Tuple[Optional[float], Optional[float]]:
    """用户窗口 [u_s,u_e](秒) → (响应时延, 回复时延)，单位 ms。

    响应时延 = u_s 时刻活跃模型段尾 m_e − u_s（无活跃段 → None）
    回复时延 = u_e 后仍在输出（end > u_e）的首个模型段起点 mn_s − u_e（无 → None；
    barge-in 抢答时为负，与旧 per_event 的 recovery_latency_s 口径一致）
    与旧 _evaluate_one_event 不同：不做 stopped/resumed 门控（spec 口径，行为判定归 LLM）。

    u_next: 下一轮用户窗口起点（全局时间线切片用）。本轮静默时 m_next 会取到
    下一轮的模型回应段 → 误判成有回应；限定 start < u_next 挡住跨轮串扰。
    """
    m_active = next((m for m in model_segments if m['start'] <= u_s < m['end']), None)
    # barge-in：模型可能在用户话未说完（u_e 前）已开始回应，故按 end > u_e 取段（reply_ms 可为负），
    # 排除 m_active 本身（被打断段不算回应）
    m_next = next((m for m in model_segments
                   if m['end'] > u_e and m is not m_active
                   and (u_next is None or m['start'] < u_next)), None)
    response_ms = round((m_active['end'] - u_s) * 1000, 1) if m_active else None
    reply_ms = round((m_next['start'] - u_e) * 1000, 1) if m_next else None
    return response_ms, reply_ms


def _driver_window_overlap(rd: Dict[str, Any],
                           user_segments: List[Dict[str, Any]]) -> Optional[Tuple[float, float]]:
    """驱动轮窗口 start_ms/end_ms ∩ 用户段，取最大重叠段边界（共用录音 case 模式的次级锚定）。"""
    s = _as_float(rd.get('start_ms'))
    e = _as_float(rd.get('end_ms'))
    if s is None or e is None or e <= s or not user_segments:
        return None
    win = (s / 1000.0, e / 1000.0)
    best, best_ov = None, 0.0
    for seg in user_segments:
        ov_s, ov_e = max(seg['start'], win[0]), min(seg['end'], win[1])
        if ov_e - ov_s > best_ov:
            best, best_ov = seg, ov_e - ov_s
    return (best['start'], best['end']) if best else None


def locate_fft_window(played_audios, user_wav) -> Optional[Tuple[float, float, float]]:
    """played_audios(干净音源) FFT 对齐到 user_wav → (u_s, u_e, ncc) 秒；失败 None。

    供恢复轮等无法走 compute_interruption_metrics 精修路径的轮次独立锚定；
    打断轮的 FFT 窗口已在结果 client_out_*_ms 里，不重复调用。
    """
    if not played_audios or not user_wav:
        return None
    try:
        from ..turn_taking.false_takeover import _locate_client_out, _resolve_played_audio_path
        path = _resolve_played_audio_path(played_audios)
        if not path:
            return None
        s, e, ncc = _locate_client_out(path, user_wav)
        if s is None or e is None:
            return None
        # 假锁定防护：目标语音不在录音里时 FFT 仍会返回一个"最佳"窗口（如平台
        # 误传第 0 轮录音时，打断轮模板锁到第 0 轮话语上），NCC 显著低于真锁定
        # (≈0.999)。阈值与 shared/audio_alignment.MIN_NCC_THRESHOLD 保持一致。
        if ncc is not None and ncc < 0.3:
            logger.warning(f"[round_metrics] FFT NCC={ncc:.4f} 低于 0.3，判为假锁定: {path}")
            return None
        return (s, e, ncc)
    except Exception as exc:
        logger.warning(f"[round_metrics] FFT 窗口定位失败，回退: {exc}")
        return None


def extract_round_timing(round_result: Dict[str, Any], rd: Optional[Dict[str, Any]] = None,
                         round_idx: Optional[int] = None,
                         role: str = 'interruption') -> Dict[str, Any]:
    """从单轮 compute 结果提取本轮时序锚定条目。

    锚定优先级：FFT 精修窗口(client_out_*_ms) → 驱动轮窗口∩用户段 → 最大重叠目标事件
    → (恢复轮)首个用户段。全部失败 → 时延 None（派生层记 -1）。
    """
    from . import _target_interruption_event

    rd = rd if isinstance(rd, dict) else {}
    round_result = round_result or {}
    user_segs = round_result.get('user_segments') or []
    model_segs = round_result.get('model_segments') or []

    u_s = u_e = None
    method = 'none'
    co_s, co_e = round_result.get('client_out_start_ms'), round_result.get('client_out_end_ms')
    if co_s is not None and co_e is not None:
        u_s, u_e, method = co_s / 1000.0, co_e / 1000.0, 'fft'
    else:
        win = _driver_window_overlap(rd, user_segs)
        if win:
            u_s, u_e, method = win[0], win[1], 'driver_window'
        else:
            target = _target_interruption_event(round_result.get('per_event'))
            if target and target.get('user_segment'):
                u_s, u_e = target['user_segment']
                method = 'overlap_heuristic'
            elif role == 'resume' and user_segs:
                # 恢复轮无"打断事件"，取首个用户段（轮录音以恢复话术开始）
                u_s, u_e = user_segs[0]['start'], user_segs[0]['end']
                method = 'first_user_segment'

    if u_s is not None:
        response_ms, reply_ms = round_latency_from_window(u_s, u_e, model_segs)
    else:
        response_ms = reply_ms = None

    return {
        'round': round_idx,
        'role': role,
        'u_s': round(u_s, 3) if u_s is not None else None,
        'u_e': round(u_e, 3) if u_e is not None else None,
        'anchor_method': method,
        'response_latency_ms': response_ms,
        'reply_latency_ms': reply_ms,
        'stop_intent': bool(round_result.get('stop_intent') or rd.get('stop_intent')),
    }


# ─────────── §3.3 LLM 裁判输入构建（纯函数） ───────────

def chunks_from_segments(segments) -> List[Dict[str, Any]]:
    """语音段(含 words) → 词级 chunks，供 build_interaction_text 复用同一份 ASR。"""
    return [{'text': w.get('text', ''), 'timestamp': w.get('timestamp')}
            for s in (segments or []) if isinstance(s, dict)
            for w in (s.get('words') or [])
            if isinstance(w, dict) and w.get('timestamp')]


def build_round_block(t: Dict[str, Any], round_result: Optional[Dict[str, Any]] = None,
                      rd: Optional[Dict[str, Any]] = None,
                      u_next: Optional[float] = None) -> Dict[str, Any]:
    """逐轮 LLM 裁判标注块：轮号/角色(打断|停止|恢复)/定位窗口/脚本台词/三段文本。

    三段文本按锚定窗口从段取（与计时同源）：用户窗口内语音、u_s 时刻模型活跃段、
    u_e 后首个模型段。u_next 同 round_latency_from_window（全局时间线跨轮边界）。
    """
    round_result = round_result or {}
    rd = rd if isinstance(rd, dict) else {}
    u_segs = round_result.get('user_segments') or []
    m_segs = round_result.get('model_segments') or []
    u_s, u_e = t.get('u_s'), t.get('u_e')
    user_text = ''.join(
        s.get('text', '') for s in u_segs
        if u_s is not None and u_e is not None and s['end'] > u_s and s['start'] < u_e
    )
    m_active = next((m for m in m_segs
                     if u_s is not None and m['start'] <= u_s < m['end']), None)
    # 与 round_latency_from_window 同口径：barge-in 段（end > u_e）也算回应，排除被打断段本身
    m_next = next((m for m in m_segs
                   if u_e is not None and m['end'] > u_e and m is not m_active
                   and (u_next is None or m['start'] < u_next)), None)
    role = '恢复' if t.get('role') == 'resume' else ('停止' if t.get('stop_intent') else '打断')
    return {
        'round': t.get('round'),
        'role': role,
        'window': [u_s, u_e],
        'query': rd.get('query') or None,
        'user_text': user_text,
        'model_interrupted_text': (m_active or {}).get('text', ''),
        'model_recovery_text': (m_next or {}).get('text', ''),
    }


# ─────────── §3.4 spec 指标派生 ───────────

def _agg(values: List[float]) -> Dict[str, Optional[float]]:
    """排除 -1 后 avg/min/max；无有效值 → None（不给 0）。"""
    valid = [v for v in values if isinstance(v, (int, float)) and v != -1]
    if not valid:
        return {'avg': None, 'min': None, 'max': None}
    return {'avg': round(sum(valid) / len(valid), 1),
            'min': round(min(valid), 1), 'max': round(max(valid), 1)}


def derive_round_metrics(round_timing: Optional[List[Dict[str, Any]]],
                         round_behaviors: Optional[List[Dict[str, Any]]],
                         case_info: Optional[Dict[str, Any]] = None,
                         resume_timing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """时序 × 行为 → spec 全部字段（纯函数；round_behaviors=None 即 LLM 降级路径）。

    Args:
        round_timing: extract_round_timing 条目列表（含 role='resume' 时自动排除出数量）
        round_behaviors: 与打断轮对齐的 LLM 行为列表
            [{'round', 'behavior', 'behavior_reason', 'score_overall', 'stop_complied'}]；
            None = 行为不可用（数量/评分 None、时延 list 全 -1）
        case_info: derive_case_type 输出
        resume_timing: 恢复轮锚定条目（缺省时回退末个实际打断轮的回复时延＝spec"最后一轮模型的回复时延"）

    Returns:
        dict: case_type/label、8 个数量、2 个时延 list(-1)、avg/min/max×2、
              resume_first_reply_latency_ms、reply_content_score、resume_content_score、
              stop_compliance_rate、round_details
    """
    case_info = case_info or {}
    rt_all = [t for t in (round_timing or []) if isinstance(t, dict)]
    rt = [t for t in rt_all if t.get('role') != 'resume']
    bmap = {b.get('round'): b for b in (round_behaviors or []) if isinstance(b, dict)}

    counts = {label: 0 for label in BEHAVIOR_LABELS_V2} if round_behaviors is not None else None
    resp_list: List[float] = []
    reply_list: List[float] = []
    details: List[Dict[str, Any]] = []
    scores: List[float] = []

    for t in rt:
        b = bmap.get(t['round']) if round_behaviors is not None else None
        # 停止指令轮口径（2026-09-22）：直接静默=遵从停止 → 按「回复」成功计。
        # "好的"等确认语后静默由 prompt 指引 LLM 直接判回复；此处兜底重映射静默，
        # 无回应内容可评 → score_overall 置 None 不入内容均分。
        if b and b.get('behavior') == BEHAVIOR_SILENCE and t.get('stop_intent'):
            b = dict(b, behavior=BEHAVIOR_REPLY, stop_complied=True, score_overall=None)
            bmap[t['round']] = b  # 停止遵从率统计取重映射后的值
        behavior = (b or {}).get('behavior')
        known = behavior in BEHAVIOR_LABELS_V2
        if known and counts is not None:
            counts[behavior] += 1
        # list 口径：失败(恢复/无关/静默)与 unknown 轮记 -1；回复/询问轮照记（时延缺失也 -1）
        timed_ok = known and behavior not in _FAIL_BEHAVIORS
        resp = t.get('response_latency_ms')
        reply = t.get('reply_latency_ms')
        resp_list.append(resp if (timed_ok and resp is not None) else -1)
        reply_list.append(reply if (timed_ok and reply is not None) else -1)
        score_overall = (b or {}).get('score_overall')
        if isinstance(score_overall, (int, float)) and not isinstance(score_overall, bool):
            scores.append(float(score_overall))
        details.append({
            'round': t.get('round'),
            'role': t.get('role', 'interruption'),
            'anchor_method': t.get('anchor_method'),
            'response_latency_ms': resp,
            'reply_latency_ms': reply,
            'stop_intent': bool(t.get('stop_intent')),
            'behavior': behavior if known else None,
            'behavior_reason': (b or {}).get('behavior_reason'),
            'score_overall': score_overall,
            'stop_complied': (b or {}).get('stop_complied'),
        })

    resp_agg, reply_agg = _agg(resp_list), _agg(reply_list)

    # 恢复首轮内容时延：恢复轮回复时延；无恢复轮锚定 → 末个实际打断轮回复时延（spec 括号口径）
    resume_ms = (resume_timing or {}).get('reply_latency_ms')
    if resume_ms is None and rt:
        resume_ms = rt[-1].get('reply_latency_ms')
    if resume_timing:
        details.append(dict({k: resume_timing.get(k) for k in
                             ('round', 'role', 'anchor_method', 'response_latency_ms',
                              'reply_latency_ms', 'stop_intent')},
                            behavior=None, behavior_reason=None,
                            score_overall=None, stop_complied=None))

    # 停止指令遵循：仅停止类用例、且停止轮有 LLM 判定
    stop_compliance_rate = None
    if case_info.get('is_stop_type'):
        stop_rounds = [t.get('round') for t in rt if t.get('stop_intent')]
        judged = [(bmap.get(r) or {}).get('stop_complied') for r in stop_rounds] \
            if round_behaviors is not None else []
        judged = [v for v in judged if v is not None]
        if judged:
            stop_compliance_rate = round(sum(1 for v in judged if v) / len(judged), 3)

    if counts is not None:
        success_count = counts[BEHAVIOR_REPLY]
        failure_count = sum(counts[b] for b in _FAIL_BEHAVIORS)
        inquiry_count = counts[BEHAVIOR_ASK]
    else:
        success_count = failure_count = inquiry_count = None

    return {
        'case_type': case_info.get('case_type'),
        'case_type_label': case_info.get('case_type_label'),
        # 数量类（成功≡回复行为数、询问≡询问行为数，spec 对称性两名并存同值）
        'success_count': success_count,
        'reply_behavior_count': success_count,
        'failure_count': failure_count,
        'recover_behavior_count': counts[BEHAVIOR_RECOVER] if counts else None,
        'irrelevant_behavior_count': counts[BEHAVIOR_IRRELEVANT] if counts else None,
        'silence_behavior_count': counts[BEHAVIOR_SILENCE] if counts else None,
        'inquiry_count': inquiry_count,
        'ask_behavior_count': inquiry_count,
        # 时延 list（ms，失败/unknown 记 -1）
        'round_response_latencies': resp_list,
        'round_reply_latencies': reply_list,
        'response_latency_avg_ms': resp_agg['avg'],
        'response_latency_min_ms': resp_agg['min'],
        'response_latency_max_ms': resp_agg['max'],
        'reply_latency_avg_ms': reply_agg['avg'],
        'reply_latency_min_ms': reply_agg['min'],
        'reply_latency_max_ms': reply_agg['max'],
        'resume_first_reply_latency_ms': resume_ms,
        # 评分类
        'reply_content_score': round(sum(scores) / len(scores), 2) if scores else None,
        'resume_content_score': (resume_timing or {}).get('score_overall'),
        'stop_compliance_rate': stop_compliance_rate,
        'round_details': details,
    }


# ─────────── per_round 逐轮投影（整体评估返回逐轮结果方案 §4.2） ───────────

def build_per_round(n_rounds: int, round_details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """round_details → per_round[]（纯函数，零额外 LLM/ASR 调用）。

    每轮元素 {'round_number': i, 'interruption': {轮级字段}}，字段名与整体 spec 同名，
    平台按维度 field_path（interruption.*）直接提取并覆盖逐轮 TRD。
    只投影轮级有意义字段：成功/失败/询问 0/1、两个时延、评分、停止遵从、恢复首轮回覆时延；
    用例级字段（case_type/行为计数/聚合值）不投影 → 平台解析为 None 自动跳过。
    无时序数据的轮（发起交互轮/悬挂轮）返回 {'round_number', 'message'} 跳过项。
    """
    by_round = {d.get('round'): d for d in (round_details or []) if isinstance(d, dict)}
    per_round = []
    for i in range(n_rounds):
        d = by_round.get(i)
        if not d:
            per_round.append({'round_number': i, 'message': '跳过: 非计时轮(无打断时序)'})
            continue
        item: Dict[str, Any] = {}
        behavior = d.get('behavior')
        if behavior in BEHAVIOR_LABELS_V2:
            item['success_count'] = int(behavior == BEHAVIOR_REPLY)
            item['failure_count'] = int(behavior in _FAIL_BEHAVIORS)
            item['inquiry_count'] = int(behavior == BEHAVIOR_ASK)
        if d.get('role') == 'resume':
            # 恢复轮：回复时延即「恢复首轮内容时延」维度的轮级值
            if d.get('reply_latency_ms') is not None:
                item['resume_first_reply_latency_ms'] = d['reply_latency_ms']
        else:
            # 与 list 口径一致：失败(恢复/无关/静默)与 unknown 轮不投时延
            timed_ok = behavior in BEHAVIOR_LABELS_V2 and behavior not in _FAIL_BEHAVIORS
            if timed_ok and d.get('response_latency_ms') is not None:
                item['response_latency_avg_ms'] = d['response_latency_ms']
            if timed_ok and d.get('reply_latency_ms') is not None:
                item['reply_latency_avg_ms'] = d['reply_latency_ms']
        if d.get('score_overall') is not None:
            item['reply_content_score'] = d['score_overall']
        if d.get('stop_complied') is not None:
            item['stop_compliance_rate'] = float(d['stop_complied'])
        per_round.append({'round_number': i, 'interruption': item} if item
                         else {'round_number': i, 'message': '跳过: 该轮无可投影指标'})
    return per_round
