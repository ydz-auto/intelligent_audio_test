"""env_judge 策略类"""
from app.services.calculators.base import BaseCalculator


class EnvJudgeCalculator(BaseCalculator):
    task_type = 'env_judge'

    def validate(self, task_params):
        if not task_params.get('video_path') and not task_params.get('record_file'):
            return False, f"Missing required field for {self.task_type}: video_path (录屏文件路径)"
        return True, None

    def prepare_params(self, task_params):
        """从 task_params 或 rounds[0] 提取所需字段"""
        _rounds = task_params.get('rounds') or []
        _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
        video_path = task_params.get('video_path') or task_params.get('record_file') or _r0.get('video_path') or _r0.get('record_file')
        env_type = task_params.get('env_type') or _r0.get('env_type') or ''
        model = task_params.get('model') or _r0.get('model') or ''
        max_tokens = task_params.get('max_tokens') or _r0.get('max_tokens') or 4096
        temperature = task_params.get('temperature') or _r0.get('temperature') or 0.1
        return {
            'video_path': video_path,
            'env_type': env_type,
            'model': model,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'task_type_inner': task_params.get('task_type', 'env_judge'),
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.env_judge import evaluate_env_judge
        return evaluate_env_judge(
            params['video_path'],
            task_type=params['task_type_inner'],
            env_type=params['env_type'],
            model=params['model'],
            max_tokens=params['max_tokens'],
            temperature=params['temperature'],
        )
