# -*- coding: utf-8 -*-
"""env_judge 策略类

环境理解裁判：通过 env_type 输入参数区分无语义/有语义场景
  - env_type=false/0 → non_semantic（无语义：环境声为噪声，判断声音类型识别）
  - env_type=true/1  → semantic（有语义：环境声含语义内容，判断内容理解）

  - 主音频：ai_wav（模型回复，被判定对象）
  - 用户侧：user_wav（用户通道音频，含环境声+用户询问）
  - 环境声：played_audios（本轮被播放音频，FFT互相关定位）
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

# 0/1 字段：多轮聚合时求和得到数量，再除以总拒识轮次得到占比
_SUM_FIELDS = (
    'rate_success', 'rate_inquiry', 'rate_failure',
    'success_silent_recover', 'success_reply_recover',
    'inquiry_silent', 'inquiry_reply',
    'failure_silent_respond', 'failure_reply_respond',
    'failure_silent_irrelevant', 'failure_reply_irrelevant',
    'failure_reply_silent',
)
# count 字典字段：多轮聚合时合并累加
_COUNT_DICT_FIELDS = ('rate_success_count', 'rate_inquiry_count', 'rate_failure_count')

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

    通过 env_type 输入参数区分无语义/有语义：
      env_type=false/0 → non_semantic（无语义：环境声为噪声，判断声音类型识别）
      env_type=true/1  → semantic（有语义：环境声含语义内容，判断内容理解）
    输入：user_wav, ai_wav, played_audios, correctAnswer, env_type
    输出：understand_correct (True/False), response_latency_ms, score, reason
    """
    task_type = 'env_judge'
    supports_per_round = True

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        has_ai = task_params.get('ai_wav') or rd.get('ai_wav')
        has_user = task_params.get('user_wav') or rd.get('user_wav')
        has_answer = task_params.get('correctAnswer') or rd.get('correctAnswer')
        if not has_ai:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        if not has_user:
            return False, f"Missing required field for {self.task_type}: user_wav"
        if not has_answer:
            return False, f"Missing required field for {self.task_type}: correctAnswer"
        # played_audios 可选：缺失时跳过时延计算，仅做 LLM 评判
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
            'played_audios': task_params.get('played_audios') or rd.get('played_audios') or '',
            'correctAnswer': task_params.get('correctAnswer') or rd.get('correctAnswer') or '',
            'env_type': task_params.get('env_type', rd.get('env_type', 0)),
            **llm_config,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.env_judge import evaluate_env_judge

        return evaluate_env_judge(
            user_wav=params['user_wav'],
            ai_wav=params['ai_wav'],
            played_audios=params['played_audios'],
            correctAnswer=params['correctAnswer'],
            env_type=params.get('env_type', 0),
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

    # 单轮也走逐轮聚合：只有 1 个拒识轮（rounds<2）时同样输出
    # n_ 前缀数量字段（n_rate_* / n_子维度）与 n_reject_rounds，
    # 避免单轮场景主维度/子维度 field_path 提取为 None。
    min_rounds_for_aggregate = 1
    aggregate_overall_only = False

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

    def _is_reject_round(self, task_params, rd=None):
        """归一化判断目标轮是否参与拒识评估（is_reject）

        rd 为轮次字典；缺省时按 round_number 定位目标轮。
        缺失默认 True（兼容旧请求），字符串 'true'/'1'/'yes' 视为 True。
        """
        if rd is None:
            idx = self._get_target_round_index(task_params)
            rd = self._get_round_safe(task_params, idx)
        is_reject = (rd or {}).get('is_reject', (task_params or {}).get('is_reject', True))
        if isinstance(is_reject, str):
            is_reject = is_reject.strip().lower() in ('true', '1', 'yes')
        return bool(is_reject)

    def run(self, task_params):
        """覆写：目标轮 is_reject=false 时直接跳过评估（不调 LLM、不产出任何拒识指标）

        基础 run() 只做 prepare_params → calculate，不感知 is_reject；
        逐轮评估（round_number 有值）与整体评估全为非拒识轮时，
        若不在此拦截，非拒识轮仍会被当作拒识轮评估，指标泄漏给平台侧。
        """
        if not self._is_reject_round(task_params):
            return {
                'enabled': True,
                'message': '跳过: 非拒识轮(is_reject=false)',
                'rate': None,
            }
        return super().run(task_params)

    def _calculate_per_round(self, task_params):
        """逐轮切片计算 + 多轮聚合

        与 BaseCalculator 默认实现的区别：
        1. is_reject=false 的轮次不参与统计，per_round 中保留跳过项
           （{"round_number": i, "message": "跳过: 非拒识轮(is_reject=false)"}，
            per_round 数组长度与 rounds 一致，平台按 round_number 字段定位，不依赖下标）
        2. 每轮结果补充 n_ 前缀数量字段（与整体结果同构），平台据此
           process_group_dimension_results 解析并覆盖/创建逐轮 TRD
        3. 聚合时 0/1 字段求和得到数量，再除以拒识总轮次得到占比
        4. count 字典合并累加

        Returns:
            list: per_round 结果列表（task_service 会赋值到 result['per_round']）
            聚合结果通过 self._agg_result 传递，task_service 检测后覆盖顶层 result
        """
        rounds = (task_params or {}).get('rounds') or []
        per_round = []
        reject_results = []  # 仅有效拒识轮结果，用于聚合
        n_reject_rounds = 0

        for i in range(len(rounds)):
            rd = rounds[i] if isinstance(rounds[i], dict) else {}

            # 跳过 is_reject=false 的轮次（非拒识轮不参与统计，per_round 保留跳过项）
            if not self._is_reject_round(task_params, rd):
                # 非拒识轮：填充占位项，保证 per_round 数组长度与 rounds 一致
                per_round.append({
                    'round_number': rd.get('round', i),
                    'message': '跳过: 非拒识轮(is_reject=false)',
                })
                continue

            n_reject_rounds += 1

            single = dict(task_params)
            single['round_number'] = i
            # 清空顶层轮次相关字段
            for k in self._TOP_LEVEL_ROUND_FIELDS:
                single.pop(k, None)
            # 注入该轮音频字段
            for k in self._AUDIO_FIELD_NAMES:
                if rd.get(k):
                    single[k] = rd[k]
            try:
                result = self.run(single)
            except Exception as e:
                logger.warning(f"[_calculate_per_round] round={i} 失败: {e}")
                result = {}
            result['round_number'] = rd.get('round', i)
            # 与整体结果同构：单轮也输出 n_ 前缀数量字段（0/1），
            # 平台按维度 field_path（如 n_rate_success / n_success_silent_recover）提取逐轮 TRD
            for field in _SUM_FIELDS:
                result.setdefault(f'n_{field}', 1 if result.get(field) else 0)
            per_round.append(result)
            reject_results.append(result)

        # 聚合（仅统计有效拒识轮结果，跳过占位项）
        if not reject_results:
            self._agg_result = None
            return per_round

        # 以最后一个有效拒识轮为基底，剥离逐轮残留字段（round_number），
        # 保证整体结果顶层不含轮次字段（round_number 只属于 per_round 元素）
        agg = dict(reject_results[-1])
        agg.pop('round_number', None)
        agg['n_reject_rounds'] = n_reject_rounds

        # 0/1 字段求和 → 数量（n_ 前缀），再算占比
        for field in _SUM_FIELDS:
            vals = [r.get(field, 0) for r in reject_results if r.get(field) is not None]
            count = sum(vals)
            agg[f'n_{field}'] = count
            agg[field] = round(count / n_reject_rounds, 3) if n_reject_rounds else 0

        # count 字典合并累加（rate_success_count / rate_inquiry_count / rate_failure_count）
        for dict_field in _COUNT_DICT_FIELDS:
            merged = {}
            for r in reject_results:
                d = r.get(dict_field, {})
                if isinstance(d, dict):
                    for k, v in d.items():
                        merged[k] = merged.get(k, 0) + (v if isinstance(v, (int, float)) else 0)
            agg[dict_field] = merged

        # token 求和
        agg['tokens_used'] = sum(r.get('tokens_used', 0) for r in reject_results)
        agg['input_token'] = sum(r.get('input_token', 0) for r in reject_results)
        agg['output_token'] = sum(r.get('output_token', 0) for r in reject_results)

        logger.info(
            f'[reject_judge] 多轮聚合: n_reject_rounds={n_reject_rounds} '
            f'success={agg.get("n_rate_success", 0)} '
            f'inquiry={agg.get("n_rate_inquiry", 0)} '
            f'failure={agg.get("n_rate_failure", 0)}'
        )

        self._agg_result = agg
        return per_round
