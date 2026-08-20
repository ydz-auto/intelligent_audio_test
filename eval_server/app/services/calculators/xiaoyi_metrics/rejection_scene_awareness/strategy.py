"""non_interactive_latency / noise_latency 策略类"""
from app.services.calculators.base import BaseCalculator


class NonInteractiveLatencyCalculator(BaseCalculator):
    task_type = 'non_interactive_latency'

    def validate(self, task_params):
        if not task_params.get('user_asr') and not task_params.get('user_chunks'):
            return False, f"Missing required field for {self.task_type}: user_asr (用户 ASR)"
        if not task_params.get('model_asr') and not task_params.get('model_chunks'):
            return False, f"Missing required field for {self.task_type}: model_asr (模型 ASR)"
        return True, None

    def prepare_params(self, task_params):
        """从 task_params 或 rounds[0] 提取所需字段"""
        _rounds = task_params.get('rounds') or []
        _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
        user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or _r0.get('user_asr') or _r0.get('user_chunks')
        model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or _r0.get('model_asr') or _r0.get('model_chunks')
        kwargs = {}
        gap = task_params.get('seg_merge_gap_s') or _r0.get('seg_merge_gap_s')
        if gap is not None:
            kwargs['seg_merge_gap_s'] = gap
        tsi = task_params.get('target_segment_index') or _r0.get('target_segment_index')
        if tsi is not None:
            kwargs['target_segment_index'] = tsi
        return {'user_asr': user_asr, 'model_asr': model_asr, 'kwargs': kwargs}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.non_interactive_latency import compute_non_interactive_latency
        return compute_non_interactive_latency(params['user_asr'], params['model_asr'], **params['kwargs'])


class NoiseLatencyCalculator(BaseCalculator):
    task_type = 'noise_latency'

    def validate(self, task_params):
        if not task_params.get('model_asr') and not task_params.get('model_chunks'):
            return False, f"Missing required field for {self.task_type}: model_asr (模型 ASR)"
        missing = [f for f in ['start_ms', 'end_ms', 'pcm_first_ms'] if task_params.get(f) is None]
        if missing:
            return False, f"Missing required fields for {self.task_type}: {', '.join(missing)}"
        return True, None

    def prepare_params(self, task_params):
        """从 task_params 或 rounds[0] 提取所需字段"""
        _rounds = task_params.get('rounds') or []
        _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
        model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or _r0.get('model_asr') or _r0.get('model_chunks')
        start_ms = task_params.get('start_ms') or _r0.get('start_ms')
        end_ms = task_params.get('end_ms') or _r0.get('end_ms')
        pcm_first_ms = task_params.get('pcm_first_ms') or _r0.get('pcm_first_ms')
        kwargs = {}
        gap = task_params.get('seg_merge_gap_s') or _r0.get('seg_merge_gap_s')
        if gap is not None:
            kwargs['seg_merge_gap_s'] = gap
        return {
            'model_asr': model_asr,
            'start_ms': start_ms,
            'end_ms': end_ms,
            'pcm_first_ms': pcm_first_ms,
            'kwargs': kwargs,
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.noise_latency import compute_noise_latency
        return compute_noise_latency(
            params['model_asr'],
            params['start_ms'],
            params['end_ms'],
            params['pcm_first_ms'],
            **params['kwargs'],
        )
