"""env_judge 策略类

参数模式：
  - 单轮：顶层 ai_wav / user_wav / start_ms / end_ms 等
  - 多轮：rounds 内每轮含同名字段，顶层优先 + rounds[0] 回退取音频和标量字段
    rounds 整体保留，传给 evaluate_env_judge 作额外上下文

  - 主音频：ai_wav（模型回复，被判定对象），顶层优先，rounds[0] 回退
  - 用户侧：user_wav（用户通道音频，生成 ASR 时间线）
  - 时间线：env_events / start_ms / end_ms / pcm_first_ms
  - LLM 配置：model / max_tokens / temperature / env_type
"""
from app.services.calculators.base import BaseCalculator


class EnvJudgeCalculator(BaseCalculator):
    task_type = 'env_judge'

    def validate(self, task_params):
        r0 = BaseCalculator._get_round0(task_params)
        if not (task_params.get('ai_wav') or r0.get('ai_wav')):
            return False, (
                f"Missing required field for {self.task_type}: "
                f"ai_wav(模型回复音频)"
            )
        return True, None

    def prepare_params(self, task_params):
        """单轮从顶层取，多轮从 rounds[0] 回退取音频和标量字段，rounds 整体保留"""
        r0 = BaseCalculator._get_round0(task_params)
        _rounds = task_params.get('rounds') or []

        return {
            'ai_wav': task_params.get('ai_wav') or r0.get('ai_wav') or '',
            'user_wav': task_params.get('user_wav') or r0.get('user_wav') or '',
            'env_events': task_params.get('env_events') or r0.get('env_events'),
            'start_ms': task_params.get('start_ms') or r0.get('start_ms'),
            'end_ms': task_params.get('end_ms') or r0.get('end_ms'),
            'pcm_first_ms': task_params.get('pcm_first_ms') or r0.get('pcm_first_ms'),
            'rounds': _rounds,
            'env_type': task_params.get('env_type') or r0.get('env_type') or '',
            'model': task_params.get('model') or r0.get('model') or '',
            'max_tokens': task_params.get('max_tokens') or r0.get('max_tokens') or 4096,
            'temperature': task_params.get('temperature') or r0.get('temperature') or 0.1,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.env_judge import evaluate_env_judge
        return evaluate_env_judge(
            ai_wav=params['ai_wav'],
            user_wav=params['user_wav'],
            env_events=params['env_events'],
            start_ms=params['start_ms'],
            end_ms=params['end_ms'],
            pcm_first_ms=params['pcm_first_ms'],
            rounds=params['rounds'],
            env_type=params['env_type'],
            model=params['model'],
            max_tokens=params['max_tokens'],
            temperature=params['temperature'],
        )
