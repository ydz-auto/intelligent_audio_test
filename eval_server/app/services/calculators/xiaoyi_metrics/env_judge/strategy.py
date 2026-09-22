# -*- coding: utf-8 -*-
"""env_judge 策略类

环境理解裁判：通过 task_type 输入参数区分无语义/有语义场景
  - task_type=0 → non_semantic（无语义：环境声为噪声，判断声音类型识别）
  - task_type=1 → semantic（有语义：环境声含语义内容，判断内容理解）

  - 主音频：ai_wav（模型回复，被判定对象）
  - 用户侧：user_wav（用户通道音频，含环境声+用户询问）
  - 环境声：play_audio（原始干净音源，FFT互相关定位）
  - 正确答案：correctAnswer（参考内容文本）
  - LLM 配置：model / max_tokens / temperature
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
    """环境理解裁判公共基类

    单轮/多轮公共方法（_get_target_round_index / _get_round_safe /
    _iter_rounds / _aggregate_results）由 BaseCalculator 统一提供。
    """

    @staticmethod
    def _extract_llm_config(task_params, rd):
        """提取 LLM 配置参数

        model / max_tokens / temperature 缺省时回退到 config.LLM_JUDGE。
        """
        llm_config = get_llm_config()
        return {
            'model': task_params.get('model') or rd.get('model') or '',
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)),
        }


class EnvJudgeCalculator(_BaseEnvJudgeCalculator):
    """环境理解裁判：判断模型对环境音内容的理解是否正确 + 计算用户询问到模型回复的时延

    通过 task_type 输入参数区分无语义/有语义：
      task_type=0 → non_semantic（无语义：环境声为噪声，判断声音类型识别）
      task_type=1 → semantic（有语义：环境声含语义内容，判断内容理解）
    输入：user_wav, ai_wav, play_audio, correctAnswer, task_type
    输出：understand_correct (True/False), response_latency_ms, score, reason
    """
    task_type = 'env_judge'
    supports_per_round = True

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        has_ai = task_params.get('ai_wav') or rd.get('ai_wav')
        has_user = task_params.get('user_wav') or rd.get('user_wav')
        has_play = task_params.get('play_audio') or rd.get('play_audio')
        has_answer = task_params.get('correctAnswer') or rd.get('correctAnswer')
        if not has_ai:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        if not has_user:
            return False, f"Missing required field for {self.task_type}: user_wav"
        if not has_play:
            return False, f"Missing required field for {self.task_type}: play_audio"
        if not has_answer:
            return False, f"Missing required field for {self.task_type}: correctAnswer"
        return True, None

    def prepare_params(self, task_params):
        """提取环境理解裁判所需参数"""
        rounds = task_params.get('rounds') or []
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        llm_config = self._extract_llm_config(task_params, rd)

        return {
            'mode': 'single',
            'rounds': rounds,
            'ai_wav': task_params.get('ai_wav') or rd.get('ai_wav') or '',
            'user_wav': task_params.get('user_wav') or rd.get('user_wav') or '',
            'play_audio': task_params.get('play_audio') or rd.get('play_audio') or '',
            'correctAnswer': task_params.get('correctAnswer') or rd.get('correctAnswer') or '',
            'task_type': task_params.get('task_type', rd.get('task_type', 0)),
            **llm_config,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.env_judge import evaluate_env_judge

        return evaluate_env_judge(
            user_wav=params['user_wav'],
            ai_wav=params['ai_wav'],
            play_audio=params['play_audio'],
            correctAnswer=params['correctAnswer'],
            task_type=params.get('task_type', 0),
            model=params.get('model', ''),
            max_tokens=params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS),
            temperature=params.get('temperature', LLM_DEFAULT_TEMPERATURE),
        )


class RejectionJudgeCalculator(_BaseEnvJudgeCalculator):
    """拒识裁判：评估模型在拒识场景（非意图交互内容出现时）下的行为表现

    裁判 LLM 直接听取 ai_wav + user_wav 音频，判断模型行为类别（五选一），
    再由代码根据 timing + behavior 计算 rate 评级。

    输入：ai_wav, user_wav, is_single_round, timing, model, max_tokens, temperature
    输出：evaluations, behavior_*(5个0/1字段), rate, rate_*(3个0/1字段),
          rate_*_count(3组分组统计字典)
    """
    task_type = 'reject_judge'
    supports_per_round = True

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        has_ai = task_params.get('ai_wav') or rd.get('ai_wav')
        if not has_ai:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        """提取拒识裁判所需参数"""
        rounds = task_params.get('rounds') or []
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        llm_config = self._extract_llm_config(task_params, rd)

        is_single_round = rd.get('is_single_round', task_params.get('is_single_round', False))
        if isinstance(is_single_round, str):
            is_single_round = is_single_round.strip().lower() in ('true', '1', 'yes')

        timing = rd.get('timing', task_params.get('timing', '静默'))

        return {
            'mode': 'single',
            'rounds': rounds,
            'ai_wav': task_params.get('ai_wav') or rd.get('ai_wav') or '',
            'user_wav': task_params.get('user_wav') or rd.get('user_wav') or '',
            'is_single_round': is_single_round,
            'timing': timing,
            **llm_config,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.rejection_judge import evaluate_rejection_judge

        return evaluate_rejection_judge(
            ai_wav=params['ai_wav'],
            user_wav=params.get('user_wav', ''),
            is_single_round=params.get('is_single_round', False),
            timing=params.get('timing', '静默'),
            model=params.get('model', ''),
            max_tokens=params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS),
            temperature=params.get('temperature', LLM_DEFAULT_TEMPERATURE),
        )
