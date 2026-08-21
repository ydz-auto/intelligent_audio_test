"""llm_judge 策略类

使用 LLM 对设备回答进行评分（1-5分），基于 config.LLM_JUDGE 配置。
"""
import json
import re
import logging
import httpx
from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class LlmJudgeCalculator(BaseCalculator):
    task_type = 'llm_judge'

    def validate(self, task_params):
        if not task_params.get('rounds'):
            if not task_params.get('answer') or not task_params.get('correct_answer'):
                return False, "Missing required fields for llm_judge: answer, correct_answer (or 'rounds' for multi-round mode)"
        return True, None

    def prepare_params(self, task_params):
        """使用 TaskService._prepare_llm_judge_params 处理参数"""
        from app.services.task_service import TaskService
        return TaskService._prepare_llm_judge_params(task_params)

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

        # 多轮模式
        rounds = params.get('rounds')
        if rounds and isinstance(rounds, list):
            results = []
            total_score = 0
            for i, rd in enumerate(rounds):
                query = str(rd.get('query') or rd.get('question') or '')
                answer = str(rd.get('answer') or '')
                prompt = prompt_template.format(query=query, hypothesis=answer)
                score, reason = self._call_llm(api_base, api_key, model, prompt, timeout)
                results.append({'round': i, 'score': score, 'reason': reason})
                if score:
                    total_score += score
            avg = total_score / len(results) if results else 0
            return {'enabled': True, 'per_round': results, 'avg_score': avg, 'model': model}
        else:
            query = str(params.get('query') or params.get('question') or '')
            answer = str(params.get('answer') or '')
            prompt = prompt_template.format(query=query, hypothesis=answer)
            score, reason = self._call_llm(api_base, api_key, model, prompt, timeout)
            return {'enabled': True, 'score': score, 'reason': reason, 'model': model}

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
