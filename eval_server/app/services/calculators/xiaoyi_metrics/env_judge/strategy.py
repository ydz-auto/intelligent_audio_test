"""env_judge 策略类"""
from app.services.calculators.base import BaseCalculator


class EnvJudgeCalculator(BaseCalculator):
    task_type = 'env_judge'

    def validate(self, task_params):
        # 录屏(video_path/record_file)没了时，用模型回复音频 ai_wav 作为主输入
        _rounds = task_params.get('rounds') or []
        _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
        has_audio = (
            task_params.get('ai_wav') or _r0.get('ai_wav')
            or task_params.get('video_path') or task_params.get('record_file')
            or _r0.get('video_path') or _r0.get('record_file')
        )
        if not has_audio:
            return False, (
                f"Missing required field for {self.task_type}: "
                f"ai_wav(模型回复音频) 或 video_path(录屏)，至少需要一个"
            )
        return True, None

    def prepare_params(self, task_params):
        """从 task_params 或 rounds[0] 提取所需字段（含 ai_wav/时间线相关）"""
        _rounds = task_params.get('rounds') or []
        _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
        video_path = (
            task_params.get('video_path') or task_params.get('record_file')
            or _r0.get('video_path') or _r0.get('record_file')
        )
        return {
            'video_path': video_path,
            'ai_wav': task_params.get('ai_wav') or _r0.get('ai_wav') or '',
            'user_wav': task_params.get('user_wav') or _r0.get('user_wav') or '',
            'env_events': task_params.get('env_events') or _r0.get('env_events'),
            'start_ms': task_params.get('start_ms') or _r0.get('start_ms'),
            'end_ms': task_params.get('end_ms') or _r0.get('end_ms'),
            'pcm_first_ms': task_params.get('pcm_first_ms') or _r0.get('pcm_first_ms'),
            'rounds': _rounds,
            'env_type': task_params.get('env_type') or _r0.get('env_type') or '',
            'model': task_params.get('model') or _r0.get('model') or '',
            'max_tokens': task_params.get('max_tokens') or _r0.get('max_tokens') or 4096,
            'temperature': task_params.get('temperature') or _r0.get('temperature') or 0.1,
            'task_type_inner': task_params.get('task_type', 'env_judge'),
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.env_judge.env_judge import evaluate_env_judge
        return evaluate_env_judge(
            video_path=params['video_path'],
            task_type=params['task_type_inner'],
            env_type=params['env_type'],
            model=params['model'],
            max_tokens=params['max_tokens'],
            temperature=params['temperature'],
            ai_wav=params['ai_wav'],
            user_wav=params['user_wav'],
            env_events=params['env_events'],
            start_ms=params['start_ms'],
            end_ms=params['end_ms'],
            pcm_first_ms=params['pcm_first_ms'],
            rounds=params['rounds'],
        )
