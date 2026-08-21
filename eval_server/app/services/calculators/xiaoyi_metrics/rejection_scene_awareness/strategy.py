"""non_interactive_latency / noise_latency 策略类

参数模式：
  - 单轮：顶层 ai_wav / user_wav / start_ms / end_ms / pcm_first_ms
  - 多轮：rounds 内每轮含同名字段，顶层优先 + rounds[0] 回退取音频路径和时间参数
    内部自动调 ASR 服务把 wav 转成词级时间戳

  non_interactive_latency：
    - user_wav: 用户语音 wav 路径，顶层优先，rounds[0] 回退
    - ai_wav: 模型语音 wav 路径，顶层优先，rounds[0] 回退
    - 可选：seg_merge_gap_s / target_segment_index

  noise_latency：
    - ai_wav: 模型语音 wav 路径，顶层优先，rounds[0] 回退
    - start_ms / end_ms: 噪声播放起止时间（绝对毫秒），顶层或 rounds[0]
    - pcm_first_ms: 模型 PCM 文件创建时间（绝对毫秒），顶层或 rounds[0]
    - 可选：seg_merge_gap_s
"""
from app.services.calculators.base import BaseCalculator


class NonInteractiveLatencyCalculator(BaseCalculator):
    task_type = 'non_interactive_latency'

    def validate(self, task_params):
        r0 = BaseCalculator._get_round0(task_params)
        if not (task_params.get('user_wav') or r0.get('user_wav')):
            return False, f"Missing required field for {self.task_type}: user_wav (用户语音 wav)"
        if not (task_params.get('ai_wav') or r0.get('ai_wav')):
            return False, f"Missing required field for {self.task_type}: ai_wav (模型语音 wav)"
        return True, None

    def prepare_params(self, task_params):
        """单轮从顶层取，多轮从 rounds[0] 回退取 wav 路径"""
        r0 = BaseCalculator._get_round0(task_params)

        user_wav = task_params.get('user_wav') or r0.get('user_wav') or ''
        ai_wav = task_params.get('ai_wav') or r0.get('ai_wav') or ''

        kwargs = {}
        gap = task_params.get('seg_merge_gap_s') or r0.get('seg_merge_gap_s')
        if gap is not None:
            kwargs['seg_merge_gap_s'] = gap
        tsi = task_params.get('target_segment_index') or r0.get('target_segment_index')
        if tsi is not None:
            kwargs['target_segment_index'] = tsi

        return {'user_wav': user_wav, 'ai_wav': ai_wav, 'kwargs': kwargs}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.non_interactive_latency import compute_non_interactive_latency
        return compute_non_interactive_latency(params['user_wav'], params['ai_wav'], **params['kwargs'])


class NoiseLatencyCalculator(BaseCalculator):
    task_type = 'noise_latency'

    def validate(self, task_params):
        r0 = BaseCalculator._get_round0(task_params)
        if not (task_params.get('ai_wav') or r0.get('ai_wav')):
            return False, f"Missing required field for {self.task_type}: ai_wav (模型语音 wav)"
        missing = [
            f for f in ('start_ms', 'end_ms', 'pcm_first_ms')
            if task_params.get(f) is None and r0.get(f) is None
        ]
        if missing:
            return False, f"Missing required fields for {self.task_type}: {', '.join(missing)}"
        return True, None

    def prepare_params(self, task_params):
        """单轮从顶层取，多轮从 rounds[0] 回退取 wav 路径和时间参数"""
        r0 = BaseCalculator._get_round0(task_params)

        ai_wav = task_params.get('ai_wav') or r0.get('ai_wav') or ''
        start_ms = task_params.get('start_ms') or r0.get('start_ms')
        end_ms = task_params.get('end_ms') or r0.get('end_ms')
        pcm_first_ms = task_params.get('pcm_first_ms') or r0.get('pcm_first_ms')

        kwargs = {}
        gap = task_params.get('seg_merge_gap_s') or r0.get('seg_merge_gap_s')
        if gap is not None:
            kwargs['seg_merge_gap_s'] = gap

        return {
            'ai_wav': ai_wav,
            'start_ms': start_ms,
            'end_ms': end_ms,
            'pcm_first_ms': pcm_first_ms,
            'kwargs': kwargs,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.noise_latency import compute_noise_latency
        return compute_noise_latency(
            params['ai_wav'],
            params['start_ms'],
            params['end_ms'],
            params['pcm_first_ms'],
            **params['kwargs'],
        )
