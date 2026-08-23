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
  多轮 → 逐轮取音频和时间参数，逐轮算后聚合；rounds 整体保留作上下文

  - 主音频：ai_wav（模型回复，被判定对象）
  - 用户侧：user_wav（用户通道音频，生成 ASR 时间线）
  - 时间线：env_events / start_ms / end_ms / pcm_first_ms
  - LLM 配置：model / max_tokens / temperature / scene
"""
import logging
from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class _BaseEnvJudgeCalculator(BaseCalculator):
    """拒识/打断裁判公共基类"""

    # ─── 单轮/多轮公共方法 ───

    @staticmethod
    def _is_multi_round(task_params):
        return task_params.get('round_number') is None

    @staticmethod
    def _get_target_round_index(task_params):
        rn = task_params.get('round_number')
        if rn is not None:
            return rn
        return -1

    @staticmethod
    def _get_round_safe(task_params, index):
        rounds = (task_params or {}).get('rounds')
        if not (rounds and isinstance(rounds, list)):
            return {}
        idx = index if index >= 0 else len(rounds) + index
        if 0 <= idx < len(rounds) and isinstance(rounds[idx], dict):
            return rounds[idx]
        return {}

    @staticmethod
    def _iter_rounds(task_params):
        rounds = (task_params or {}).get('rounds')
        if not (rounds and isinstance(rounds, list)):
            return
        rn = task_params.get('round_number')
        if rn is not None:
            if 0 <= rn < len(rounds) and isinstance(rounds[rn], dict):
                yield rn, rounds[rn]
        else:
            for i, rd in enumerate(rounds):
                if isinstance(rd, dict):
                    yield i, rd

    @staticmethod
    def _aggregate_results(per_round_results):
        if not per_round_results:
            return {}
        if len(per_round_results) == 1:
            return dict(per_round_results[0])
        result = dict(per_round_results[-1])
        first = per_round_results[0]
        for k, v in first.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals = [r.get(k) for r in per_round_results if r.get(k) is not None]
                if vals:
                    result[k] = round(sum(vals) / len(vals), 3)
        result['n_rounds'] = len(per_round_results)
        result['per_round'] = per_round_results
        return result

    # ─── Calculator 实现 ───

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        if not (task_params.get('ai_wav') or rd.get('ai_wav')):
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        """单轮取当前轮，多轮所有字段取最后一轮；rounds 整体保留作上下文"""
        rounds = task_params.get('rounds') or []

        if self._is_multi_round(task_params):
            # 多轮：所有字段取最后一轮
            rd_last = self._get_round_safe(task_params, -1)
            item = self._extract_round_fields(task_params, rd_last)
            llm_config = self._extract_llm_config(task_params, rd_last)
            return {
                'mode': 'single',
                'rounds': rounds,  # 整体保留作上下文
                **item,
                **llm_config,
            }
        else:
            # 单轮
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
        """
        scene = task_params.get('scene') or rd.get('scene') or ''
        if not scene:
            scene = task_params.get('env_type') or rd.get('env_type') or ''
        return {
            'scene': scene,
            'model': task_params.get('model') or rd.get('model') or '',
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or 4096),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or 0.1),
        }


class RejectionJudgeCalculator(_BaseEnvJudgeCalculator):
    """拒识场景裁判：发送模型回复音频+环境时间线给多模态 LLM 判断"""
    task_type = 'rejection_judge'

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.rejection_judge import evaluate_rejection_judge

        return evaluate_rejection_judge(
            ai_wav=params['ai_wav'],
            user_wav=params['user_wav'],
            env_events=params['env_events'],
            start_ms=params['start_ms'],
            end_ms=params['end_ms'],
            pcm_first_ms=params['pcm_first_ms'],
            rounds=params.get('rounds', []),
            scene=params['scene'],
            model=params['model'],
            max_tokens=params['max_tokens'],
            temperature=params['temperature'],
        )


class InterruptionJudgeCalculator(_BaseEnvJudgeCalculator):
    """打断场景裁判：发送模型回复音频+环境时间线给多模态 LLM 判断"""
    task_type = 'interruption_judge'

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.interruption_judge import evaluate_interruption_judge

        return evaluate_interruption_judge(
            ai_wav=params['ai_wav'],
            user_wav=params['user_wav'],
            env_events=params['env_events'],
            start_ms=params['start_ms'],
            end_ms=params['end_ms'],
            pcm_first_ms=params['pcm_first_ms'],
            rounds=params.get('rounds', []),
            scene=params['scene'],
            model=params['model'],
            max_tokens=params['max_tokens'],
            temperature=params['temperature'],
        )
