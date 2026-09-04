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


def _empty_interruption(message):
    """无双路音频或计算失败时返回的空打断结构（与 compute_interruption_metrics 输出键一致）"""
    return {
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
        'message': message,
        'timing_success_rate': None,
        'llm_success_rate': None,
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

    result = compute_interruption_metrics(user_asr, model_asr, **kwargs)
    result['timing_success_rate'] = result.get('interruption_success_rate')
    logger.info(
        f"[interruption_metrics] success_rate={result['interruption_success_rate']} "
        f"stop_rate={result['stop_rate']} resume_rate={result['resume_rate']} "
        f"avg_stop={result['avg_stop_latency_s']}ms avg_recovery={result['avg_recovery_latency_s']}ms "
        f"message={result['message']}"
    )

    # ── 可选：大模型评估 ──
    _raw = task_params.get('enable_llm_eval', True)
    enable_llm = str(_raw).lower() in ('true', '1', 'yes')
    if enable_llm:
        try:
            llm_result = evaluate_interruption_llm(
                result.get('per_event') or [], task_params,
                user_segments=result.get('user_segments') or [],
                model_segments=result.get('model_segments') or [],
            )
            result['llm_eval'] = llm_result
            if llm_result.get('llm_success_rate') is not None:
                result['interruption_success_rate'] = llm_result['llm_success_rate']
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
            ):
                result[k] = llm_result.get(k)
            logger.info(
                f"[interruption_metrics] LLM 评估完成 model={llm_result.get('model')} "
                f"n_events_evaluated={llm_result.get('n_events_evaluated')} "
                f"interruption_real_rate={llm_result.get('interruption_real_rate')}"
            )
        except Exception as e:
            logger.warning(f"[interruption_metrics] LLM 评估失败，跳过: {e}")
            result['llm_eval'] = {'enabled': False, 'message': f'LLM 评估失败: {e}'}
    else:
        result['llm_eval'] = {'enabled': False, 'message': '未启用(enable_llm_eval=False)'}
        logger.info("[interruption_metrics] LLM 评估跳过：未启用(enable_llm_eval=False)")

    return result
