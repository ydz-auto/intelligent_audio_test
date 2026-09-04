# -*- coding: utf-8 -*-
"""env_judge 策略类

从原 env_judge 拆分为两个独立子维度：
  - rejection_judge   拒识场景评估
  - interruption_judge 打断场景评估

单轮 vs 多轮区分：
  - round_number 有值（0/1/2...）→ 单轮评估，取 rounds[round_number]
  - round_number 不存在 → 多轮整体评估

取参方式：
  单轮 → 取当前轮 ai_wav/user_wav/时间参数，rounds 整体保留
  多轮 → 所有字段取最后一轮，单次评估；rounds 整体保留作上下文

  - 主音频：ai_wav（模型回复，被判定对象）
  - 用户侧：user_wav（用户通道音频，生成 ASR 时间线）
  - 时间线：env_events / start_ms / end_ms / pcm_first_ms
  - LLM 配置：model / max_tokens / temperature / scene
"""
import logging
from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.llm_client import get_llm_config
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class _BaseEnvJudgeCalculator(BaseCalculator):
    """拒识/打断裁判公共基类

    单轮/多轮公共方法（_is_multi_round / _get_target_round_index /
    _get_round_safe / _iter_rounds / _aggregate_results）由
    BaseCalculator 统一提供。
    """

    # ─── Calculator 实现 ───

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        if not (task_params.get('ai_wav') or rd.get('ai_wav')):
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        """单轮/多轮统一取最后一轮字段；rounds 整体保留作上下文"""
        rounds = task_params.get('rounds') or []
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        item = self._extract_round_fields(task_params, rd)
        llm_config = self._extract_llm_config(task_params, rd)
        return {
            'mode': 'single',
            'rounds': rounds,  # 整体保留作上下文
            **item,
            **llm_config,
        }

    @staticmethod
    def _extract_round_fields(task_params, rd):
        """从顶层或指定轮取音频和时间参数"""
        return {
            'ai_wav': task_params.get('ai_wav') or rd.get('ai_wav') or '',
            'user_wav': task_params.get('user_wav') or rd.get('user_wav') or '',
            'env_events': task_params.get('env_events') or rd.get('env_events'),
            'start_ms': task_params.get('start_ms') or rd.get('start_ms'),
            'end_ms': task_params.get('end_ms') or rd.get('end_ms'),
            'pcm_first_ms': task_params.get('pcm_first_ms') or rd.get('pcm_first_ms'),
        }

    @staticmethod
    def _extract_llm_config(task_params, rd):
        """提取 LLM 配置参数

        scene 为新参数名，兼容旧 env_type 字段回退。
        model / max_tokens / temperature 缺省时回退到 config.LLM_JUDGE。
        """
        llm_config = get_llm_config()

        scene = task_params.get('scene') or rd.get('scene') or ''
        if not scene:
            scene = task_params.get('env_type') or rd.get('env_type') or ''
        return {
            'scene': scene,
            'model': task_params.get('model') or rd.get('model') or '',
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)),
        }


class RejectionJudgeCalculator(_BaseEnvJudgeCalculator):
    """拒识场景裁判：发送模型回复音频+环境时间线给多模态 LLM 判断"""
    task_type = 'rejection_judge'

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.rejection_judge import evaluate_rejection_judge

        return evaluate_rejection_judge(
            ai_wav=params['ai_wav'],
            user_wav=params['user_wav'],
            model=params.get('model', ''),
            max_tokens=params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS),
            temperature=params.get('temperature', LLM_DEFAULT_TEMPERATURE),
        )


class InterruptionJudgeCalculator(_BaseEnvJudgeCalculator):
    """打断场景裁判：发送模型回复音频+环境时间线给多模态 LLM 判断"""
    task_type = 'interruption_judge'

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.interruption_judge import evaluate_interruption_judge

        return evaluate_interruption_judge(
            ai_wav=params['ai_wav'],
            user_wav=params['user_wav'],
            model=params.get('model', ''),
            max_tokens=params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS),
            temperature=params.get('temperature', LLM_DEFAULT_TEMPERATURE),
        )
