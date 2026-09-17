# -*- coding: utf-8 -*-
"""turn_eval 策略类：逐轮三分类主维度

从 turn_taking 拆出的独立主维度，专注：
  1. 轮次切分 + 逐轮三分类（误解管 / 接管 / 未接管）
  2. 仅对"接管"轮计算接管时延
  3. 仅对"接管"轮评分回复质量

ASR 共享：优先复用上层编排器（XiaoyiMetricsCalculator）注入的 _shared_asr，
独立调用时自行调 ASR + 音频对齐。
"""
import logging

from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.asr_utils import compute_pause_intervals
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class TurnEvalCalculator(BaseCalculator):
    """逐轮三分类主维度：轮次切分 → 三分类 → 接管时延 → 回复质量

    与 TurnTakingCalculator 的区别：
    - TurnTakingCalculator：旧流程，tor/false_takeover/takeover_latency 各算各的
    - TurnEvalCalculator：新流程，先切轮次 → 逐轮统一判定三分类 → 按分类结果补充时延/质量

    输出结构：
        {
            'turn_classification': {
                'summary': '正常接管N，未接管M，误解管K',
                'normal_takeover_count': N,
                'no_takeover_count': M,
                'false_takeover_count': K,
                'total_turns': T,
                'turns': [...],   # 逐轮详情
            },
            # 兼容旧字段（取最后一轮结果）
            'tor': {...},
            'false_takeover': {...},
            'takeover_latency': {...},
            'reply_quality': {...},
            'interaction_text': '...',
        }
    """
    task_type = 'turn_eval'

    def validate(self, task_params):
        user_wav, ai_wav = self._get_audio_from_round(
            task_params, self._get_target_round_index(task_params)
        )
        if not (user_wav or ai_wav):
            return False, (
                f"Missing required field for {self.task_type}: "
                f"user_wav / ai_wav，至少需要一个"
            )
        return True, None

    def prepare_params(self, task_params):
        """直接透传 task_params"""
        return task_params

    def calculate(self, params):
        """新流程：轮次切分 → 逐轮三分类 → 接管时延 → 回复质量 → 汇总输出

        三个核心模块：
        1. turn_evaluation.py — 轮次切分 + 误解管判断 + 接管/未接管判断
        2. takeover_latency.py — 接管时延（仅"接管"时计算，误解管/未接管为 null）
        3. reply_quality.py — 回复质量评分（仅"接管"时评分，误解管/未接管为 null）
        """
        from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingBase
        from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
            evaluate_all_turns, TurnClassification,
        )
        from app.services.calculators.xiaoyi_metrics.turn_taking.takeover_latency import (
            compute_takeover_latency_from_chunks,
        )
        from app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality import (
            evaluate_reply_quality_per_turn,
        )
        from app.services.calculators.xiaoyi_metrics.shared.llm_client import build_interaction_text

        results = {}

        # ── ASR 共享：优先使用上层编排器（XiaoyiMetricsCalculator）注入的结果 ──
        shared_asr = params.get('_shared_asr')
        if not shared_asr:
            idx = self._get_target_round_index(params)
            user_wav, ai_wav = self._get_audio_from_round(params, idx)
            rd = self._get_round_safe(params, idx)
            played_audios = params.get('played_audios') or rd.get('played_audios')

            # 音频对齐：played_audios（干净音源）→ user_wav（劣化）生成干净版音频
            effective_user_wav = user_wav
            if played_audios and user_wav:
                from app.services.calculators.xiaoyi_metrics.shared.audio_alignment import (
                    generate_aligned_clean_audio,
                )
                try:
                    align_result = generate_aligned_clean_audio(user_wav, played_audios)
                    if align_result.get('aligned_wav'):
                        effective_user_wav = align_result['aligned_wav']
                        logger.info(
                            f"[turn_eval] 音频对齐成功: "
                            f"平均NCC={align_result.get('ncc', 0):.4f}"
                        )
                    else:
                        logger.warning(f"[turn_eval] 音频对齐失败: {align_result.get('message')}")
                except Exception as e:
                    logger.warning(f"[turn_eval] 音频对齐异常: {e}，回退原始 user_wav")

            shared_asr = {}
            if effective_user_wav:
                shared_asr['user_wav'] = effective_user_wav
                shared_asr['user_chunks'] = TurnTakingBase._get_asr_chunks(effective_user_wav)
            if ai_wav:
                shared_asr['ai_wav'] = ai_wav
                shared_asr['ai_chunks'] = TurnTakingBase._get_asr_chunks(ai_wav)
                shared_asr['ai_word_chunks'] = TurnTakingBase._get_asr_chunks(ai_wav, filter_punct=False)
            if played_audios:
                shared_asr['played_audios'] = played_audios
            if shared_asr.get('user_chunks'):
                shared_asr['pause_intervals'] = TurnTakingBase._compute_pause_intervals(shared_asr['user_chunks'])
            else:
                shared_asr['pause_intervals'] = []

        logger.info(
            f"[turn_eval] 共享 ASR 完成: "
            f"user_chunks={len(shared_asr.get('user_chunks') or [])}, "
            f"ai_chunks={len(shared_asr.get('ai_chunks') or [])}, "
            f"ai_word_chunks={len(shared_asr.get('ai_word_chunks') or [])}, "
            f"pause={len(shared_asr.get('pause_intervals') or [])}"
        )

        user_chunks = shared_asr.get('user_chunks') or []
        ai_chunks = shared_asr.get('ai_chunks') or []
        ai_word_chunks = shared_asr.get('ai_word_chunks') or ai_chunks

        # ════════════════════════════════════════════
        # 模块1+2+3：轮次切分 → 逐轮三分类 → 接管时延 → 回复质量
        # ════════════════════════════════════════════
        task_params = params.get('task_params') or params
        turns, classifications = evaluate_all_turns(user_chunks, ai_chunks, task_params)

        turn_results = []
        normal_count = 0
        no_takeover_count = 0
        false_takeover_count = 0

        for turn, cls in zip(turns, classifications):
            turn_detail = {
                'turn_index': turn.turn_index,
                'classification': cls.classification,
                'false_takeover': cls.false_takeover,
                'tor': cls.tor,
                'takeover_judge': cls.takeover_judge,
                'takeover_latency': None,    # 仅"接管"时填
                'reply_quality': None,       # 仅"接管"时填
                'user_start_s': round(turn.user_start_s, 3),
                'user_end_s': round(turn.user_end_s, 3),
                'ai_start_s': round(turn.ai_start_s, 3) if turn.ai_start_s is not None else None,
                'ai_end_s': round(turn.ai_end_s, 3) if turn.ai_end_s is not None else None,
                'has_ai_reply': turn.has_ai_reply(),
            }

            if cls.classification == TurnClassification.TAKEOVER:
                # ── 接管时延（仅"接管"时计算）──
                latency_result = compute_takeover_latency_from_chunks(
                    turn.user_chunks, turn.ai_chunks or [],
                    played_audios=shared_asr.get('played_audios'),
                    user_wav=shared_asr.get('user_wav'),
                )
                turn_detail['takeover_latency'] = latency_result

                # ── 回复质量评分（仅"接管"时评分）──
                quality_result = evaluate_reply_quality_per_turn(
                    user_chunks=turn.user_chunks,
                    ai_chunks=turn.ai_chunks,
                    classification=cls.classification,
                    task_params=task_params,
                )
                turn_detail['reply_quality'] = quality_result
                normal_count += 1

            elif cls.classification == TurnClassification.NO_TAKEOVER:
                no_takeover_count += 1

            elif cls.classification == TurnClassification.MISUNDERSTAND:
                false_takeover_count += 1

            turn_results.append(turn_detail)

        # 汇总输出
        results['turn_classification'] = {
            'summary': f'正常接管{normal_count}，未接管{no_takeover_count}，误解管{false_takeover_count}',
            'normal_takeover_count': normal_count,
            'no_takeover_count': no_takeover_count,
            'false_takeover_count': false_takeover_count,
            'total_turns': len(turns),
            'turns': turn_results,
        }

        # 兼容旧字段：tor / false_takeover / takeover_latency / reply_quality 取最后一轮的结果
        if turn_results:
            last = turn_results[-1]
            # tor 兼容
            if last.get('tor'):
                results['tor'] = last['tor']
            else:
                results['tor'] = {'tor': 0, 'n_words': 0, 'duration': 0.0, 'message': '无 AI 回复'}
            # false_takeover 兼容
            results['false_takeover'] = {
                'tor': last['false_takeover']['false_takeover'],
                'reason': last['false_takeover']['reason'],
            }
            # takeover_latency 兼容
            if last.get('takeover_latency'):
                results['takeover_latency'] = last['takeover_latency']
            else:
                results['takeover_latency'] = {
                    'takeover_latency_ms': None,
                    'message': f"分类为{last['classification']}，不计算接管时延",
                }
            # reply_quality 兼容
            if last.get('reply_quality'):
                results['reply_quality'] = last['reply_quality']
            else:
                results['reply_quality'] = {
                    'score': None,
                    'message': f"分类为{last['classification']}，不进行回复质量评分",
                }

        logger.info(
            f"[turn_eval] 三分类汇总: 正常接管{normal_count}，"
            f"未接管{no_takeover_count}，误解管{false_takeover_count}，"
            f"共{len(turns)}轮"
        )

        # 完整交互文字（query/answer + [m:ss; m:ss] 时间戳）
        results['interaction_text'] = build_interaction_text(
            shared_asr.get('user_chunks'),
            ai_word_chunks,
        )

        return results
