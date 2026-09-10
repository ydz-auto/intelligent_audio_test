# -*- coding: utf-8 -*-
"""interruptibility 策略类

打断指标计算：用户打断正在说话的小艺时，衡量小艺"停得下、恢复得来"。

单轮 vs 多轮区分：
  - round_number 有值（0/1/2...）→ 单轮评估，取 rounds[round_number]
  - round_number 不存在 → 多轮整体评估，取最后一轮

取参方式：
  单轮 → 取当前轮 user_wav/ai_wav（或已对齐的 user_asr/model_asr）
  多轮 → 取最后一轮双路音频/ASR（打断场景通常在最后一轮）

委托计算给 interruptibility.calculate_interruption_metrics 统一入口，
该入口内部完成 wav→ASR、时序指标(compute_interruption_metrics)、
可选 LLM 评估(evaluate_interruption_llm)。
"""
import logging
from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class InterruptionMetricsCalculator(BaseCalculator):
    """打断指标：用户打断模型时，衡量"停得下、恢复得来"

    单轮：取当前轮双路音频
    多轮：取最后一轮双路音频算 1 次

    单轮/多轮公共方法（_is_multi_round / _get_target_round_index /
    _get_round_safe / _get_audio_from_round）由 BaseCalculator 统一提供。
    """
    task_type = 'interruption_metrics'

    # ─── Calculator 实现 ───

    def validate(self, task_params):
        rounds = task_params.get('rounds') or []
        actual_rounds = task_params.get('interruption_rounds')
        if actual_rounds is None and isinstance(rounds, list):
            actual_rounds = [
                i for i, rd in enumerate(rounds)
                if isinstance(rd, dict) and rd.get('is_actual_interruption')
            ]
        if actual_rounds:
            for idx in actual_rounds:
                rd = self._get_round_safe(task_params, idx)
                if self._round_has_input(task_params, rd):
                    return True, None
            return False, f"Missing required field for {self.task_type}: actual interruption round audio/ASR"

        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        if self._round_has_input(task_params, rd):
            return True, None
        return False, f"Missing required field for {self.task_type}: user_wav/ai_wav or user_asr/model_asr"

    @staticmethod
    def _round_has_input(task_params, round_data):
        params = task_params or {}
        rd = round_data or {}
        return bool(
            (rd.get('user_wav') or params.get('user_wav') or rd.get('user_asr') or params.get('user_asr') or rd.get('user_chunks') or params.get('user_chunks'))
            and
            (rd.get('ai_wav') or params.get('ai_wav') or rd.get('model_asr') or params.get('model_asr') or rd.get('model_chunks') or params.get('model_chunks'))
        )

    def prepare_params(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        rd = self._get_round_safe(task_params, idx)
        user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or rd.get('user_asr')
        model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or rd.get('model_asr')
        rounds = task_params.get('rounds') or []
        actual_rounds = task_params.get('interruption_rounds')
        if actual_rounds is None and isinstance(rounds, list):
            actual_rounds = [
                i for i, item in enumerate(rounds)
                if isinstance(item, dict) and item.get('is_actual_interruption')
            ]
        is_actual_interruption = None
        if actual_rounds is not None:
            is_actual_interruption = (True if not rounds and actual_rounds
                                      else idx in actual_rounds)
        return {
            'mode': 'single',
            'user_wav': user_wav,
            'ai_wav': ai_wav,
            'user_asr': user_asr,
            'model_asr': model_asr,
            'is_actual_interruption': is_actual_interruption,
            'interruption_rounds': actual_rounds,
            'task_params': task_params,
        }

    def run(self, task_params):
        """独立调用入口：结果包装为 {'interruption': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'interruption': result}

    @staticmethod
    def _average(results, key):
        values = [r.get(key) for r in results]
        values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return round(sum(values) / len(values), 3) if values else None

    def _calculate_round(self, params, round_index, shared_asr=None):
        from app.services.calculators.xiaoyi_metrics.interruptibility import calculate_interruption_metrics

        source = params.get('task_params') or {}
        rounds = source.get('rounds') or []
        rd = rounds[round_index] if round_index < len(rounds) and isinstance(rounds[round_index], dict) else {}
        task_params = dict(source)
        task_params['round_number'] = round_index
        task_params['user_wav'] = rd.get('user_wav') or ''
        task_params['ai_wav'] = rd.get('ai_wav') or rd.get('model_wav') or ''
        task_params['user_asr'] = (
            rd.get('user_asr')
            or rd.get('user_chunks')
            or source.get('user_asr')
            or source.get('user_chunks')
        )
        task_params['model_asr'] = (
            rd.get('model_asr')
            or rd.get('model_chunks')
            or source.get('model_asr')
            or source.get('model_chunks')
        )
        task_params['is_actual_interruption'] = True
        task_params['interruption_rounds'] = [round_index]
        task_params['stop_intent'] = source.get('stop_intent', False)
        if isinstance(source.get('stop_intent'), list) and round_index < len(source['stop_intent']):
            task_params['stop_intent'] = source['stop_intent'][round_index]
        task_params['stop_intent'] = rd.get('stop_intent', rd.get('is_stop_instruction', task_params['stop_intent']))

        child_params = {
            'user_wav': task_params.get('user_wav'),
            'ai_wav': task_params.get('ai_wav'),
            'task_params': task_params,
        }
        if shared_asr and shared_asr.get('user_wav') == task_params.get('user_wav') \
                and shared_asr.get('ai_wav') == task_params.get('ai_wav'):
            child_params['_shared_asr'] = shared_asr

        # Reuse the existing single-round path; only matching-source shared ASR is reused.
        single = self.prepare_params(task_params)
        single.update(child_params)
        single['is_actual_interruption'] = True
        return self.calculate_single(single)

    def calculate_single(self, params):
        from app.services.calculators.xiaoyi_metrics.interruptibility import calculate_interruption_metrics

        task_params = dict(params.get('task_params') or {})
        shared = params.get('_shared_asr') or {}
        if shared.get('user_chunks') and shared.get('user_wav') == params.get('user_wav') \
                and not task_params.get('user_asr'):
            task_params['user_asr'] = shared['user_chunks']
        if shared.get('ai_chunks') and shared.get('ai_wav') == params.get('ai_wav') \
                and not task_params.get('model_asr'):
            task_params['model_asr'] = shared['ai_chunks']
        if params.get('is_actual_interruption') is not None:
            task_params['is_actual_interruption'] = params['is_actual_interruption']
        return calculate_interruption_metrics(task_params)

    def calculate(self, params):
        actual_rounds = params.get('interruption_rounds')
        source = params.get('task_params') or {}
        rounds = source.get('rounds') or []
        # Overall multi-round evaluation: calculate each valid actual round, then AND the binary results.
        if actual_rounds and rounds and isinstance(rounds, list) and params.get('mode') == 'single' \
                and source.get('round_number') is None:
            shared = params.get('_shared_asr') or {}
            round_results = [self._calculate_round(params, idx, shared) for idx in actual_rounds]
            if not round_results:
                return {'interruption_success_rate': 0, 'timing_success_rate': 0,
                        'interruption_rounds': list(actual_rounds), 'round_results': [],
                        'message': '无有效实际打断轮'}

            result = dict(round_results[-1])
            result['interruption_rounds'] = list(actual_rounds)
            result['round_results'] = [dict(r, round_number=idx)
                                       for idx, r in zip(actual_rounds, round_results)]
            result['per_event'] = [event for r in round_results for event in r.get('per_event', [])]
            for key in ('n_events', 'n_user_segments', 'n_recovery_only', 'n_no_model_speech'):
                result[key] = sum((r.get(key) or 0) for r in round_results)
            for key in ('avg_stop_latency_s', 'avg_recovery_latency_s',
                        'avg_overlap_s', 'avg_silence_gap_s'):
                result[key] = self._average(round_results, key)
            result['interruption_success_rate'] = int(all(
                r.get('interruption_success_rate') == 1 for r in round_results
            ))
            result['interruption_failure_rate'] = round(sum(
                (r.get('interruption_failure_rate') or 0) for r in round_results
            ) / len(round_results), 3)
            result['interruption_inquiry_rate'] = self._average(
                round_results, 'interruption_inquiry_rate'
            )
            for key in ('first_recovery_coherence', 'first_recovery_relevance',
                        'first_recovery_adaptability', 'first_recovery_overall',
                        'first_recovery_latency_s', 'stop_instruction_compliance_rate'):
                result[key] = self._average(round_results, key)
            result['timing_success_rate'] = result['interruption_success_rate']
            result['stop_rate'] = int(all(r.get('stop_rate') == 1 for r in round_results))
            result['resume_rate'] = int(all(r.get('resume_rate') == 1 for r in round_results))
            result['message'] = 'OK' if result['interruption_success_rate'] else '至少一个实际打断轮失败'
            for key in ('llm_recovery_avg_coherence', 'llm_recovery_avg_relevance',
                        'llm_recovery_avg_adaptability', 'interruption_real_rate'):
                result[key] = self._average(round_results, key)
            result['llm_recovery_per_round'] = [
                item for r in round_results for item in r.get('llm_recovery_per_round', [])
            ]
            return result

        return self.calculate_single(params)
