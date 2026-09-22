# -*- coding: utf-8 -*-
"""interruptibility 包：打断指标与时序计算

统一入口 calculate_interruption_metrics 只做**本地时序**计算：
成功率/失败率、逐轮时延、首个恢复时延。
LLM 语义评分与行为裁判（含停止指令遵从率）全部由 interruption_judge 维度承担，
本包不再发起任何 LLM 调用。
"""
import json
import logging

from .interruption import compute_interruption_metrics

logger = logging.getLogger(__name__)


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'y', '是')
    return False


def _as_int(value):
    """payload 经 multipart 传输后标量会变字符串，这里统一成 int（失败返回 None）。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_index_list(value):
    """解析轮索引列表：兼容 list 与 JSON 字符串（multipart 表单传参）。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, list):
        return None
    return [idx for idx in (_as_int(v) for v in value) if idx is not None]


def _get_stop_intent(params, round_data=None):
    """读取显式停止意图；不把 is_interruption 当作停止指令。"""
    rd = round_data if isinstance(round_data, dict) else {}
    sources = [rd, params or {}]
    aliases = ('stop_intent', 'is_stop_instruction', 'stopInstruction', 'isStopInstruction')
    for source in sources:
        for key in aliases:
            if key in source and source[key] is not None:
                return _as_bool(source[key])
        for nested_key in ('algorithm_params', 'algorithmParams'):
            nested = source.get(nested_key)
            if isinstance(nested, dict):
                for key in aliases:
                    if key in nested:
                        return _as_bool(nested[key])
            elif isinstance(nested, list):
                for item in nested:
                    if not isinstance(item, dict):
                        continue
                    code = item.get('field_code') or item.get('fieldCode') or item.get('code')
                    if code in aliases:
                        return _as_bool(item.get('field_value', item.get('fieldValue', item.get('value'))))
    return False


def _target_interruption_event(events):
    """本轮的代表性打断事件：取**重叠时长最大**的 interruption 事件。

    一轮里可能有多个用户重叠（如 0.4s 的反馈词"你们"和真正设计的打断），
    真正的打断与模型语音重叠最久。并列时取开始更晚的那个。
    没有 interruption 事件时返回 None（只有 recovery_only / no_model_speech）。
    """
    best = None
    best_key = None
    for event in events or []:
        if not isinstance(event, dict) or event.get('event_type') != 'interruption':
            continue
        overlap = event.get('overlap_s')
        segment = event.get('user_segment') or [0, 0]
        key = (
            float(overlap) if isinstance(overlap, (int, float)) else -1.0,
            float(segment[0]) if isinstance(segment[0], (int, float)) else 0.0,
        )
        if best_key is None or key > best_key:
            best, best_key = event, key
    return best


def _derive_interruption_rounds(task_params):
    """有效实际打断轮 + dangling 末轮标记。

    优先用平台传来的用例级 interruption_rounds；缺失时按 rounds 里的
    is_actual_interruption 推导，再退一步按 is_interruption 的下一轮推导
    （驱动语义：标记轮不等待 AI 回复，实际打断发生在下一轮）。
    """
    params = task_params or {}
    rounds = params.get('rounds')
    actual = _as_index_list(params.get('interruption_rounds'))
    dangling = _as_index_list(params.get('dangling_interruption_rounds'))

    if actual is None and isinstance(rounds, list):
        actual = [
            i for i, rd in enumerate(rounds)
            if isinstance(rd, dict) and _as_bool(rd.get('is_actual_interruption'))
        ]
        if not actual:
            actual = [
                i + 1 for i, rd in enumerate(rounds)
                if isinstance(rd, dict) and _as_bool(rd.get('is_interruption')) and i + 1 < len(rounds)
            ]
    if dangling is None and isinstance(rounds, list):
        dangling = [
            i for i, rd in enumerate(rounds)
            if isinstance(rd, dict) and _as_bool(rd.get('is_interruption')) and i + 1 >= len(rounds)
        ]
    return (actual or []), (dangling or [])


def _current_round(task_params, interruption_rounds):
    """当前请求评估的轮索引；逐轮评估时由平台传 round_number。"""
    current = _as_int((task_params or {}).get('round_number'))
    if current is not None:
        return current
    rounds = (task_params or {}).get('rounds')
    if isinstance(rounds, list) and len(rounds) == 1:
        return interruption_rounds[-1] if interruption_rounds else 0
    return interruption_rounds[-1] if interruption_rounds else None


def calculate_interruption_metrics(task_params):
    """打断指标统一入口（纯本地时序，不调用 LLM）

    支持两种入参形式（优先 wav，向后兼容已对齐 chunks）：
      A. 传两路 wav 路径（user_wav / ai_wav）：内部调远程 asr_server 转成 ASR chunks 再算
      B. 直接传两路已对齐 ASR 结果（user_asr / model_asr）：不内部调 ASR

    Returns:
        dict: 本地时序结果，含
            interruption_success_rate / interruption_failure_rate / timing_success_rate
            avg_stop_latency_s / avg_recovery_latency_s（跨轮平均，供维度取值）
            round_latencies（逐轮时延明细，额外字段）
            first_recovery_latency_s（仅最后一个有效实际打断轮有值）
    """
    from app.utils.asr_adapter import call_modelscope_asr_word, parse_result
    from .interruption import USER_SEG_MERGE_GAP_S, MODEL_SEG_MERGE_GAP_S

    logger.info(f"[interruption_metrics] 收到 task_params: {json.dumps(task_params, ensure_ascii=False, default=str)}")

    _rounds = task_params.get('rounds') or []
    _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}

    user_wav = task_params.get('user_wav') or _r0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or task_params.get('model_wav') or _r0.get('ai_wav') or _r0.get('model_wav')
    case_wav = task_params.get('case_wav') or _r0.get('case_wav')
    # 干净打断音源：真实数据在 played_audios（case_config 映射 audios→played_audios），
    # case_wav 是历史死链（无驱动产出），仅保留兼容
    played_audios = task_params.get('played_audios') or _r0.get('played_audios') or case_wav
    user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or task_params.get('input_asr') or _r0.get('user_asr') or _r0.get('user_chunks')
    model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or task_params.get('recovery_asr') or _r0.get('model_asr') or _r0.get('model_chunks')

    def _wav_to_asr(wav_path, label):
        if not wav_path:
            return None
        try:
            raw = call_modelscope_asr_word(wav_path)
            asr_result = parse_result(raw)
            if not asr_result.get('chunks'):
                logger.warning(f"[interruption_metrics] {label} ASR chunks 为空: {wav_path}")
            logger.info(f"[interruption_metrics] {label} ASR 完成 chunks={len(asr_result.get('chunks', []))} wav={wav_path}")
            return asr_result
        except Exception as e:
            raise ValueError(f"interruption_metrics: {label} ASR 调用失败 ({wav_path}): {e}") from e

    if user_asr is None and user_wav:
        user_asr = _wav_to_asr(user_wav, 'user_wav')
    if model_asr is None and ai_wav:
        model_asr = _wav_to_asr(ai_wav, 'ai_wav')

    if user_asr is None:
        raise ValueError("interruption_metrics: 缺少 user_wav 或 user_asr（用户提问/打断 wav 或 ASR）")
    if model_asr is None:
        raise ValueError("interruption_metrics: 缺少 ai_wav 或 model_asr（模型恢复 wav 或 ASR）")

    # ── FFT 互相关精修打断时延：case_wav(干净打断音源) + user_wav(录言)对齐，
    #    拿到用户打断的准确起止(秒)，传入 compute_interruption_metrics 覆盖
    #    ASR 段边界，使 stop/recovery 时延基于准确时刻 ──
    client_out_start_s = client_out_end_s = client_out_ncc = None
    if played_audios and user_wav:
        try:
            from app.services.calculators.xiaoyi_metrics.shared.asr_utils import to_chunks
            from ..turn_taking.false_takeover import compute_client_out_latency
            lat = compute_client_out_latency(played_audios, user_wav, to_chunks(model_asr))
            if lat.get('client_out_start_ms') is not None:
                client_out_start_s = lat['client_out_start_ms'] / 1000.0
                client_out_end_s = lat['client_out_end_ms'] / 1000.0
                client_out_ncc = lat.get('ncc')
                logger.info(f"[interruption_metrics] FFT 对齐 start={client_out_start_s:.3f}s "
                            f"end={client_out_end_s:.3f}s ncc={client_out_ncc}")
            else:
                logger.warning(f"[interruption_metrics] FFT 对齐未取到起止: {lat.get('message')}")
        except Exception as exc:
            logger.warning(f"[interruption_metrics] FFT 对齐失败，回退 ASR 时戳: {exc}")

    if task_params.get('stop_tolerance_s') is not None:
        logger.info("[interruption_metrics] stop_tolerance_s 已废弃，忽略")

    user_gap_raw = task_params.get('user_seg_merge_gap_s') or _r0.get('user_seg_merge_gap_s')
    model_gap_raw = task_params.get('model_seg_merge_gap_s') or _r0.get('model_seg_merge_gap_s')

    def _parse_gap(raw, default, label):
        if raw is None:
            return default
        try:
            v = float(raw)
            if v < 0.1:
                logger.info(f"[interruption_metrics] {label}={v} < 0.1，强制提升到 0.1")
                v = 0.1
            return v
        except (TypeError, ValueError):
            logger.warning(f"[interruption_metrics] {label} 非数值({raw!r})，用默认 {default}")
            return default

    interruption_rounds, dangling_rounds = _derive_interruption_rounds(task_params)

    kwargs = {
        'user_seg_merge_gap_s': _parse_gap(user_gap_raw, USER_SEG_MERGE_GAP_S, 'user_seg_merge_gap_s'),
        'model_seg_merge_gap_s': _parse_gap(model_gap_raw, MODEL_SEG_MERGE_GAP_S, 'model_seg_merge_gap_s'),
        'stop_intent': _get_stop_intent(task_params, _r0),
        'client_out_start_s': client_out_start_s,
        'client_out_end_s': client_out_end_s,
    }
    if task_params.get('is_actual_interruption') is not None:
        kwargs['actual_interruption'] = _as_bool(task_params.get('is_actual_interruption'))
    elif interruption_rounds:
        kwargs['actual_interruption'] = True

    result = compute_interruption_metrics(user_asr, model_asr, **kwargs)

    # FFT 对齐结果(秒转毫秒)挂到结果，供报告展示与对齐可信度(ncc)诊断
    if client_out_start_s is not None:
        result['client_out_start_ms'] = round(client_out_start_s * 1000, 1)
        result['client_out_end_ms'] = round(client_out_end_s * 1000, 1)
        result['client_out_ncc'] = client_out_ncc

    is_actual = task_params.get('is_actual_interruption')
    result['is_actual_interruption'] = _as_bool(is_actual) if is_actual is not None else bool(interruption_rounds)
    result['interruption_rounds'] = interruption_rounds
    result['dangling_interruption_rounds'] = dangling_rounds
    result['stop_intent'] = kwargs['stop_intent']
    if dangling_rounds and not interruption_rounds:
        result['message'] = f"无有效实际打断轮；末轮 is_interruption 标记未闭合: {dangling_rounds}"
    result['timing_success_rate'] = result.get('interruption_success_rate')
    # 失败率与成功率二值互补（多轮里任一轮失败即整例失败）；无任何可判定轮时留空
    has_judgeable = bool(interruption_rounds) or bool(result.get('n_events'))
    if (result.get('interruption_success_rate') in (0, 1)
            and kwargs.get('actual_interruption') is not None
            and has_judgeable):
        result['interruption_failure_rate'] = float(1 - result['interruption_success_rate'])

    # 本轮代表性打断事件 = 重叠时长最大的那个（短插话/反馈词不当作本轮打断）
    current_round = _current_round(task_params, interruption_rounds)
    is_last_actual = (not interruption_rounds) or current_round == interruption_rounds[-1]
    target = _target_interruption_event(result.get('per_event'))
    result['target_stop_latency_s'] = target.get('stop_latency_s') if target else None
    result['target_recovery_latency_s'] = target.get('recovery_latency_s') if target else None
    # 恢复首轮内容时延：只有最后一个有效实际打断轮的回复是完整的，其余轮返回 None
    result['first_recovery_latency_s'] = (
        result['target_recovery_latency_s'] if is_last_actual else None
    )
    result['round_latencies'] = [{
        'round': current_round,
        'stop_latency_s': result.get('avg_stop_latency_s'),
        'recovery_latency_s': result.get('avg_recovery_latency_s'),
        'target_stop_latency_s': result['target_stop_latency_s'],
        'target_recovery_latency_s': result['target_recovery_latency_s'],
        'first_recovery_latency_s': result['first_recovery_latency_s'],
    }]

    # ── v2 spec 字段：本轮时序锚定 + 用例类型推导 + 派生层（round_metrics）──
    #    行为判定来自 LLM（round_behaviors，由统一计算器进程内合流）；
    #    缺省时派生层走降级路径：数量/评分 None、时延 list 记 -1
    from .round_metrics import _RESUME_ALIASES, derive_case_type, derive_round_metrics, extract_round_timing

    if (isinstance(_rounds, list) and current_round is not None
            and 0 <= current_round < len(_rounds) and isinstance(_rounds[current_round], dict)):
        _cur_rd = _rounds[current_round]
    else:
        _cur_rd = _r0  # 平台逐轮评估时 rounds 已切片，rounds[0] 即本轮
    timing = extract_round_timing(result, _cur_rd, current_round)
    _si = task_params.get('stop_intent')
    case_info = derive_case_type(
        _rounds if isinstance(_rounds, list) else [],
        interruption_rounds, dangling_rounds,
        stop_intent=_si if isinstance(_si, list) else result['stop_intent'],
    )
    spec = derive_round_metrics([timing], result.get('round_behaviors'), case_info)
    # 恢复首轮内容时延：仅恢复轮本身产出（=该轮回复时延）；其余轮（含普通用例
    # 末轮）→ None 显示 -，与恢复内容评分口径一致
    if any(_as_bool(_cur_rd.get(k)) for k in _RESUME_ALIASES):
        spec['resume_first_reply_latency_ms'] = timing.get('reply_latency_ms')
    else:
        spec['resume_first_reply_latency_ms'] = None
    result.update(spec)
    result['round_timing'] = [timing]

    logger.info(
        f"[interruption_metrics] success_rate={result['interruption_success_rate']} "
        f"failure_rate={result['interruption_failure_rate']} "
        f"stop_rate={result['stop_rate']} resume_rate={result['resume_rate']} "
        f"avg_stop={result['avg_stop_latency_s']}ms avg_recovery={result['avg_recovery_latency_s']}ms "
        f"target_stop={result['target_stop_latency_s']}ms target_recovery={result['target_recovery_latency_s']}ms "
        f"first_recovery={result['first_recovery_latency_s']}ms round={current_round} "
        f"interruption_rounds={interruption_rounds} message={result['message']}"
    )
    return result
