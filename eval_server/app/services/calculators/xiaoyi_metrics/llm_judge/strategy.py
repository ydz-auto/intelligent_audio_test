# -*- coding: utf-8 -*-
"""llm_judge 策略类

使用 LLM 对设备回答进行评分（1-5分），基于 config.LLM_JUDGE 配置。

单轮 vs 多轮区分：
  - round_number 有值（0/1/2...）→ 单轮评估，取 rounds[round_number] 的 query/answer
  - round_number 不存在 → 多轮整体评估，逐轮评分后取平均

取参方式：
  单轮 → 取当前轮的 query/answer/correct_answer，算 1 次
  多轮 → 逐轮取 query/answer/correct_answer，逐轮评分后聚合（数值字段取平均）
"""
import logging
from typing import Any, Dict

from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm,
    parse_json,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_TIMEOUT,
    LLM_JUDGE_MAX_TOKENS,
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class LlmJudgeCalculator(BaseCalculator):
    """LLM 裁判：发送设备回答给 LLM 评分

    单轮：取当前轮 query/answer 算 1 次
    多轮：逐轮评分，分数取平均

    单轮/多轮公共方法（_is_multi_round / _get_target_round_index /
    _get_round_safe / _iter_rounds / _aggregate_results）由
    BaseCalculator 统一提供。
    """
    task_type = 'llm_judge'

    # ─── Calculator 实现 ───

    def validate(self, task_params):
        """校验：单轮取当前轮，多轮至少有一轮有 query/answer"""
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        answer = task_params.get('answer') or rd.get('answer')
        if not answer:
            # 多轮模式：至少一轮需要有 answer
            if self._is_multi_round(task_params):
                has_any = any(
                    (rd.get('answer') for _, rd in self._iter_rounds(task_params))
                )
                if has_any:
                    return True, None
            return False, (
                f"Missing required field for {self.task_type}: answer "
                f"(单轮取 rounds[{idx}].answer，多轮逐轮取 rd.answer)"
            )
        return True, None

    def prepare_params(self, task_params):
        """单轮取当前轮 query/answer，多轮逐轮收集"""
        llm_config = get_llm_config()
        default_model = resolve_model(dimension='llm_judge')
        default_prompt = llm_config.get('prompt_template', '')
        default_timeout = llm_config.get('timeout', LLM_DEFAULT_TIMEOUT)

        unwrap = self._unwrap_value

        if self._is_multi_round(task_params):
            # 多轮：逐轮收集 query/answer/correct_answer
            round_items = []
            for i, rd in self._iter_rounds(task_params):
                item = self._extract_round_fields(task_params, rd, unwrap)
                round_items.append(item)
            # LLM 配置取顶层或最后一轮
            rd_last = self._get_round_safe(task_params, -1)
            llm_cfg = self._extract_llm_config(task_params, rd_last, default_model, default_prompt, default_timeout)
            return {
                'mode': 'multi',
                'round_items': round_items,
                **llm_cfg,
            }
        else:
            # 单轮
            idx = self._get_target_round_index(task_params)
            rd = self._get_round_safe(task_params, idx)
            item = self._extract_round_fields(task_params, rd, unwrap)
            llm_cfg = self._extract_llm_config(task_params, rd, default_model, default_prompt, default_timeout)
            return {
                'mode': 'single',
                **item,
                **llm_cfg,
            }

    @staticmethod
    def _extract_round_fields(task_params, rd, unwrap):
        """从顶层或指定轮取 query/answer/correct_answer"""
        return {
            'query': unwrap(task_params.get('query') or rd.get('query') or
                            task_params.get('question') or rd.get('question') or ''),
            'answer': unwrap(task_params.get('answer') or rd.get('answer') or ''),
            'correct_answer': unwrap(task_params.get('correct_answer') or rd.get('correct_answer') or ''),
        }

    @staticmethod
    def _extract_llm_config(task_params, rd, default_model, default_prompt, default_timeout):
        """提取 LLM 配置参数"""
        return {
            'model': task_params.get('model') or rd.get('model') or default_model,
            'prompt': task_params.get('prompt') or rd.get('prompt') or default_prompt,
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or LLM_JUDGE_MAX_TOKENS),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or LLM_DEFAULT_TEMPERATURE),
            'scoring_criteria': task_params.get('scoring_criteria') or rd.get('scoring_criteria'),
            'timeout': default_timeout,
        }

    @staticmethod
    def _score_one(model: str, prompt: str, max_tokens: int,
                   temperature: float) -> Dict[str, Any]:
        """单次 LLM 评分调用，返回 {score, reason}。

        调用失败或解析失败时 score=0，不抛异常（单轮失败不阻断整体）。
        """
        try:
            response = call_llm(
                model=model, prompt=prompt,
                max_tokens=max_tokens, temperature=temperature,
            )
            parsed = parse_json(response['content'])
            if parsed:
                return {
                    'score': parsed.get('score', 0),
                    'reason': parsed.get('reason', ''),
                }
            return {'score': 0, 'reason': 'LLM 输出解析失败'}
        except Exception as e:
            logger.error(f'LLM judge failed: {e}')
            return {'score': 0, 'reason': str(e)}

    @staticmethod
    def _build_prompt(prompt_template: str, query: str, answer: str) -> str:
        """按 query/hypothesis 渲染模板；模板占位符不匹配时原样返回"""
        try:
            return prompt_template.format(query=query, hypothesis=answer)
        except (KeyError, IndexError):
            return prompt_template

    def calculate(self, params):
        model = params.get('model', '')
        prompt_template = params.get('prompt', '')
        max_tokens = int(params.get('max_tokens') or LLM_DEFAULT_MAX_TOKENS)
        temperature = float(params.get('temperature') or LLM_DEFAULT_TEMPERATURE)

        if params.get('mode') == 'multi':
            per_round = []
            for item in params['round_items']:
                if not item.get('answer'):
                    continue
                query = str(item.get('query') or '')
                answer = str(item.get('answer') or '')
                correct = str(item.get('correct_answer') or '')
                prompt = self._build_prompt(prompt_template, query, answer)
                res = self._score_one(model, prompt, max_tokens, temperature)
                per_round.append({
                    'enabled': True,
                    'llm_judge_score': res['score'],
                    'reasoning': res['reason'],
                    'model': model,
                    'query': query,
                    'answer': answer,
                    'correct_answer': correct,
                })
            if not per_round:
                return {'enabled': False, 'message': '所有轮次均无有效 answer'}
            agg = self._aggregate_results(per_round)
            agg.setdefault('enabled', True)
            agg.setdefault('model', model)
            return agg

        query = str(params.get('query') or '')
        answer = str(params.get('answer') or '')
        prompt = self._build_prompt(prompt_template, query, answer)
        res = self._score_one(model, prompt, max_tokens, temperature)
        return {
            'enabled': True,
            'llm_judge_score': res['score'],
            'criteria_scores': None,
            'reasoning': res['reason'],
            'model': model,
        }
