# -*- coding: utf-8 -*-
"""interruptibility 包：打断指标与时序计算

统一入口 calculate_interruption_metrics 原位于 turn_taking/__init__.py，
现归位到 interruptibility 域，消除跨域依赖。
"""
import json
import logging

from .interruption import compute_interruption_metrics
from .interruption_llm import evaluate_interruption_llm

logger = logging.getLogger(__name__)


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'y', '是')
    return False


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


def _first_recovery_event(events):
    return next((event for event in events or []
                 if isinstance(event, dict)
                 and event.get('event_type') == 'interruption'
                 and event.get('model_recovery_text') is not None
                 and event.get('recovery_latency_s') is not None), None)

def _empty_interruption(message):
    """无双路音频或计算失败时返回的空打断结构（与 compute_interruption_metrics 输出键一致）"""
    return {
        'interruption_success_rate': 0.0,
        'interruption_failure_rate': None,
        'interruption_inquiry_rate': None,
        'first_recovery_coherence': None,
        'first_recovery_relevance': None,
        'first_recovery_adaptability': None,
        'first_recovery_overall': None,
        'first_recovery_latency_s': None,
        'stop_instruction_compliance_rate': None,
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
        'message': message,
        'timing_success_rate': None,
        'llm_success_rate': None,
        'interruption_real_rate': None,
        'is_actual_interruption': None,
        'interruption_rounds': [],
        'dangling_interruption_rounds': [],
        'behavior_respond': None,
        'behavior_recover': None,
        'behavior_uncertain': None,
        'behavior_unknown': None,
        'interaction_text': None,
        'evaluations': [],
        'behavior_judge': {'enabled': False, 'message': '未启用行为裁判'},
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
        'user_segments': [],
        'model_segments': [],
    }


def calculate_interruption_metrics(task_params):
    """打断指标统一入口：用户流 + 模型恢复流 ASR 词级时间戳，直接算三项指标

    支持两种入参形式（优先 wav，向后兼容已对齐 chunks）：
      A. 传两路 wav 路径（user_wav / ai_wav）：内部调远程 asr_server 转成 ASR chunks 再算
      B. 直接传两路已对齐 ASR 结果（user_asr / model_asr）：不内部调 ASR

    Args:
        task_params (dict): 包含以下字段
            - user_wav  (str|None): 用户打断语音 wav 路径（走 A 时必填）
            - ai_wav    (str|None): 模型恢复语音 wav 路径（别名 model_wav）
            - user_asr  (list|dict|None): 用户 ASR（走 B 时必填）
            - model_asr (list|dict|None): 模型 ASR（走 B 时必填）
            - seg_merge_gap_s  (float, 可选): 词合并为段的间隙阈值(秒)

    Returns:
        dict: 打断指标结果
    """
    from app.utils.asr_adapter import call_modelscope_asr_word, parse_result
    from .interruption import USER_SEG_MERGE_GAP_S, MODEL_SEG_MERGE_GAP_S

    logger.info(f"[interruption_metrics] 收到 task_params: {json.dumps(task_params, ensure_ascii=False, default=str)}")

    _rounds = task_params.get('rounds') or []
    _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}

    user_wav = task_params.get('user_wav') or _r0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or task_params.get('model_wav') or _r0.get('ai_wav') or _r0.get('model_wav')
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

    stop_tol = task_params.get('stop_tolerance_s')
    user_gap_raw = task_params.get('user_seg_merge_gap_s') or _r0.get('user_seg_merge_gap_s')
    model_gap_raw = task_params.get('model_seg_merge_gap_s') or _r0.get('model_seg_merge_gap_s')

    kwargs = {}
    if stop_tol is not None:
        logger.info("[interruption_metrics] stop_tolerance_s 已废弃，忽略")

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

    kwargs['user_seg_merge_gap_s'] = _parse_gap(user_gap_raw, USER_SEG_MERGE_GAP_S, 'user_seg_merge_gap_s')
    kwargs['model_seg_merge_gap_s'] = _parse_gap(model_gap_raw, MODEL_SEG_MERGE_GAP_S, 'model_seg_merge_gap_s')
    if 'is_actual_interruption' in task_params:
        kwargs['actual_interruption'] = task_params.get('is_actual_interruption')

    kwargs['stop_intent'] = _get_stop_intent(task_params, _r0)

    result = compute_interruption_metrics(user_asr, model_asr, **kwargs)
    result['is_actual_interruption'] = task_params.get('is_actual_interruption')
    result['interruption_rounds'] = task_params.get('interruption_rounds') or []
    result['dangling_interruption_rounds'] = task_params.get('dangling_interruption_rounds') or []
    if result['dangling_interruption_rounds'] and not result['interruption_rounds']:
        result['message'] = f"无有效实际打断轮；末轮 is_interruption 标记未闭合: {result['dangling_interruption_rounds']}"
    result['timing_success_rate'] = result.get('interruption_success_rate')
    result['interruption_failure_rate'] = (
        1.0 - result['interruption_success_rate']
        if result.get('interruption_success_rate') in (0, 1)
        and result.get('n_events', 0)
        else result.get('interruption_failure_rate')
    )
    first = _first_recovery_event(result.get('per_event'))
    if first:
        result['first_recovery_latency_s'] = first.get('recovery_latency_s')
    if result.get('stop_intent'):
        stop_events = [e for e in result.get('per_event', []) if e.get('stop_intent')]
        judged = [e.get('stop_complied') for e in stop_events if e.get('stop_complied') is not None]
        result['stop_instruction_compliance_rate'] = (
            round(sum(judged) / len(judged), 3) if judged else None
        )
    logger.info(
        f"[interruption_metrics] success_rate={result['interruption_success_rate']} "
        f"stop_rate={result['stop_rate']} resume_rate={result['resume_rate']} "
        f"avg_stop={result['avg_stop_latency_s']}ms avg_recovery={result['avg_recovery_latency_s']}ms "
        f"message={result['message']}"
    )

    # ── 可选：大模型评估 ──
    _raw = task_params.get('enable_llm_eval', False)
    enable_llm = str(_raw).lower() in ('true', '1', 'yes')
    sub_tasks = task_params.get('sub_tasks')
    legacy_full = sub_tasks is None
    sub_tasks = set(sub_tasks or [])
    need_text_llm = legacy_full or bool(sub_tasks.intersection({
        'interruption_coherence', 'interruption_relevance', 'interruption_adaptability',
        'interruption_first_recovery_content', 'interruption_recovery_first_turn_content',
    }))
    need_behavior_judge = legacy_full or bool(sub_tasks.intersection({
        'interruption_behavior_respond', 'interruption_behavior_recover',
        'interruption_behavior_uncertain', 'interruption_behavior_unknown',
        'interruption_inquiry_rate',
    }))

    if enable_llm and need_text_llm:
        try:
            llm_result = evaluate_interruption_llm(
                result.get('per_event') or [], task_params,
                user_segments=result.get('user_segments') or [],
                model_segments=result.get('model_segments') or [],
            )
            result['llm_eval'] = llm_result
            if llm_result.get('llm_success_rate') is not None:
                # LLM 成功率仅作辅助诊断；主成功率由本地时序/实际轮次决定。
                result['llm_success_rate'] = llm_result['llm_success_rate']
            for k in (
                'llm_recovery_avg_coherence', 'llm_recovery_avg_relevance',
                'llm_recovery_avg_adaptability',
                'llm_recovery_coherence_reason', 'llm_recovery_relevance_reason',
                'llm_recovery_adaptability_reason',
                'llm_return_avg_coherence', 'llm_return_avg_relevance',
                'llm_return_avg_adaptability',
                'llm_recovery_per_round', 'llm_return_scores_per_round',
                'interruption_real_rate',
                'first_recovery_coherence', 'first_recovery_relevance',
                'first_recovery_adaptability', 'first_recovery_overall',
            ):
                result[k] = llm_result.get(k)
            first_llm = _first_recovery_event(result.get('per_event'))
            if first_llm and result.get('llm_recovery_per_round'):
                first_score = result['llm_recovery_per_round'][0]
                for src, dst in (
                    ('coherence', 'first_recovery_coherence'),
                    ('relevance', 'first_recovery_relevance'),
                    ('adaptability', 'first_recovery_adaptability'),
                    ('overall', 'first_recovery_overall'),
                ):
                    result[dst] = first_score.get(src)

            logger.info(
                f"[interruption_metrics] n_events_evaluated={llm_result.get('n_events_evaluated')} "
                f"interruption_real_rate={llm_result.get('interruption_real_rate')}"
            )
        except Exception as e:
            logger.warning(f"[interruption_metrics] LLM 评估失败，跳过: {e}")
            result['llm_eval'] = {'enabled': False, 'message': f'LLM 评估失败: {e}'}
    else:
        result['llm_eval'] = {'enabled': False, 'message': (
            '未选文本 LLM 子维度' if not need_text_llm
            else '未启用(enable_llm_eval=False)'
        )}
        logger.info("[interruption_metrics] 文本 LLM 评估跳过")

    if enable_llm and need_behavior_judge:
        try:
            from app.services.calculators.xiaoyi_metrics.env_judge.interruption_judge import evaluate_interruption_judge
            judge_result = evaluate_interruption_judge(
                ai_wav=ai_wav,
                user_wav=user_wav,
                model=task_params.get('model', ''),
                max_tokens=task_params.get('max_tokens'),
                temperature=task_params.get('temperature'),
            )
            result['behavior_judge'] = judge_result
            for key in ('behavior_respond', 'behavior_recover', 'behavior_uncertain', 'behavior_unknown', 'interaction_text', 'evaluations'):
                result[key] = judge_result.get(key)
            valid_evaluations = judge_result.get('evaluations') or []
            if judge_result.get('enabled') and valid_evaluations:
                result['interruption_inquiry_rate'] = int(
                    valid_evaluations[0].get('behavior') == '不确定询问'
                )
        except Exception as e:
            result['behavior_judge'] = {'enabled': False, 'message': f'行为裁判失败: {e}'}
            logger.warning(f"[interruption_metrics] 行为裁判失败，跳过: {e}")
    else:
        result['behavior_judge'] = {'enabled': False, 'message': (
            '未启用(enable_llm_eval=False)' if not enable_llm
            else '未选行为裁判子维度'
        )}

    return result
