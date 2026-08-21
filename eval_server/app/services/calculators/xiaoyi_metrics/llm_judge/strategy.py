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
import json
import logging
import httpx
from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class LlmJudgeCalculator(BaseCalculator):
    """LLM 裁判：发送设备回答给 LLM 评分

    单轮：取当前轮 query/answer 算 1 次
    多轮：逐轮评分，分数取平均
    """
    task_type = 'llm_judge'

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
        """遍历轮次，yield (round_index, round_dict)

        单轮：只 yield (round_number, rounds[round_number])
        多轮：yield 每一轮
        """
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
        """聚合多轮结果：数值字段取平均，非数值取最后一轮"""
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
        from app.config import config

        llm_config = getattr(config, 'LLM_JUDGE', {})
        default_model = llm_config.get('default_model', 'gpt-4')
        default_prompt = llm_config.get('prompt_template', '')
        default_timeout = llm_config.get('timeout', 120)

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
    def _unwrap_value(val):
        """提取参数值：如果是 {'text': '...', 'json': [...]} 格式则取 text 字段"""
        if isinstance(val, dict) and 'text' in val:
            return val['text']
        return val

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
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or 1024),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or 0.1),
            'scoring_criteria': task_params.get('scoring_criteria') or rd.get('scoring_criteria'),
            'timeout': default_timeout,
        }

    def calculate(self, params):
        from app.config import config

        llm_config = getattr(config, 'LLM_JUDGE', {})
        api_base = llm_config.get('api_base_url', '')
        api_key = llm_config.get('api_key', '')
        timeout = llm_config.get('timeout', 120)

        if not api_base or not api_key:
            return {'enabled': False, 'message': 'LLM 评估未配置'}

        model = params.get('model') or llm_config.get('default_model', 'gpt-4')
        prompt_template = params.get('prompt') or llm_config.get('prompt_template', '')

        if params.get('mode') == 'multi':
            per_round = []
            for item in params['round_items']:
                if not item.get('answer'):
                    continue
                query = str(item.get('query') or '')
                answer = str(item.get('answer') or '')
                correct = str(item.get('correct_answer') or '')
                try:
                    prompt = prompt_template.format(query=query, hypothesis=answer)
                except (KeyError, IndexError):
                    prompt = prompt_template
                score, reason = self._call_llm(api_base, api_key, model, prompt, timeout)
                per_round.append({
                    'enabled': True,
                    'llm_judge_score': score,
                    'reasoning': reason,
                    'model': model,
                    'query': query,
                    'answer': answer,
                    'correct_answer': correct,
                })
            if not per_round:
                return {'enabled': False, 'message': '所有轮次均无有效 answer'}
            agg = self._aggregate_results(per_round)
            # 确保聚合后有 enabled 和 model 字段
            agg.setdefault('enabled', True)
            agg.setdefault('model', model)
            return agg
        else:
            query = str(params.get('query') or '')
            answer = str(params.get('answer') or '')
            try:
                prompt = prompt_template.format(query=query, hypothesis=answer)
            except (KeyError, IndexError):
                prompt = prompt_template
            score, reason = self._call_llm(api_base, api_key, model, prompt, timeout)
            return {
                'enabled': True,
                'llm_judge_score': score,
                'criteria_scores': None,
                'reasoning': reason,
                'model': model,
            }

    def _call_llm(self, api_base, api_key, model, prompt, timeout):
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 1024,
            'temperature': 0.1,
            'response_format': {'type': 'json_object'},
        }
        try:
            with httpx.Client(trust_env=False, timeout=timeout) as client:
                resp = client.post(
                    f'{api_base.rstrip("/")}/chat/completions',
                    headers=headers,
                    json=payload
                )
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content']
            parsed = json.loads(content)
            return parsed.get('score', 0), parsed.get('reason', '')
        except Exception as e:
            logger.error(f'LLM judge failed: {e}')
            return 0, str(e)
