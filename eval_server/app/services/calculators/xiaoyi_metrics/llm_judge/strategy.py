"""LLM Judge Calculator"""
from app.services.calculators.base import BaseCalculator
from app.services.task_service import TaskService


class LlmJudgeCalculator(BaseCalculator):
    task_type = 'llm_judge'

    def validate(self, task_params):
        # answer/correct_answer 在有 rounds 时从 rounds 取，否则从顶层取
        # model/prompt 有默认值，不是必填
        if not task_params.get('rounds'):
            required_fields = ['answer', 'correct_answer']
            missing = [f for f in required_fields if not task_params.get(f)]
            if missing:
                return False, f"Missing required fields for {self.task_type}: {', '.join(missing)}"
        return True, None

    def prepare_params(self, task_params):
        """llm_judge 使用独立的参数准备逻辑"""
        return TaskService._prepare_llm_judge_params(task_params)

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.llm_judge.llm_judge_calculator import evaluate_with_llm
        return evaluate_with_llm(
            answer=params.get('answer', ''),
            correct_answer=params.get('correct_answer', ''),
            question=params.get('question', ''),
            query=params.get('query', ''),
            record_file=params.get('record_file', ''),
            rounds=params.get('rounds'),
            model=params['model'],
            prompt=params['prompt'],
            max_tokens=params['max_tokens'],
            temperature=params['temperature'],
            scoring_criteria=params['scoring_criteria'],
            **params['extra_kwargs'],
        )
