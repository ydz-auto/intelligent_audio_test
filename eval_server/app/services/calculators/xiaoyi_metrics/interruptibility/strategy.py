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
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        if not user_wav:
            return False, f"Missing required field for {self.task_type}: user_wav"
        if not ai_wav:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        rd = self._get_round_safe(task_params, idx)
        user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or rd.get('user_asr')
        model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or rd.get('model_asr')
        return {
            'mode': 'single',
            'user_wav': user_wav,
            'ai_wav': ai_wav,
            'user_asr': user_asr,
            'model_asr': model_asr,
            'task_params': task_params,
        }

    def run(self, task_params):
        """独立调用入口：结果包装为 {'interruption': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'interruption': result}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.interruptibility import calculate_interruption_metrics

        task_params = dict(params.get('task_params') or {})
        # ── 共享 ASR 优先：主编排器按目标轮统一算好的 chunks 直接注入，
        #    避免重复调用 ASR，且与同请求其他子维度基于同一份词级时间戳 ──
        shared = params.get('_shared_asr') or {}
        if shared.get('user_chunks') and shared.get('user_wav') == params.get('user_wav') \
                and not task_params.get('user_asr'):
            task_params['user_asr'] = shared['user_chunks']
        if shared.get('ai_chunks') and shared.get('ai_wav') == params.get('ai_wav') \
                and not task_params.get('model_asr'):
            task_params['model_asr'] = shared['ai_chunks']
        return calculate_interruption_metrics(task_params)
