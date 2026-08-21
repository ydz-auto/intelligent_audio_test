# -*- coding: utf-8 -*-
"""non_interactive_latency / noise_latency 策略类

单轮 vs 多轮区分：
  - round_number 有值（0/1/2...）→ 单轮评估，取 rounds[round_number]
  - round_number 不存在 → 多轮整体评估

各维度单轮/多轮取参方式：
  · non_interactive_latency：
      单轮 → 取当前轮双路音频算 1 次
      多轮 → 逐轮算时延，数值字段取平均
  · noise_latency：
      单轮 → 取当前轮 ai_wav + 时间参数算 1 次
      多轮 → 逐轮算时延，数值字段取平均
"""
import logging
from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class _RejectionBase(BaseCalculator):
    """rejection_scene_awareness 域公共基类：共享单轮/多轮取参逻辑"""

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

    @classmethod
    def _get_audio_from_round(cls, task_params, index):
        """从指定轮次取双路音频（顶层优先）"""
        rd = cls._get_round_safe(task_params, index)
        user_wav = task_params.get('user_wav') or rd.get('user_wav') or ''
        ai_wav = task_params.get('ai_wav') or rd.get('ai_wav') or ''
        return user_wav, ai_wav

    @staticmethod
    def _iter_rounds(task_params):
        """遍历所有轮次，yield (round_index, round_dict)"""
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


class NonInteractiveLatencyCalculator(_RejectionBase):
    """非交互意图时延：用户在模型回复期间说话的 stop / recovery 时延

    单轮：取当前轮双路音频算 1 次
    多轮：逐轮算时延，数值字段取平均
    """
    task_type = 'non_interactive_latency'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        if not user_wav:
            return False, f"Missing required field for {self.task_type}: user_wav"
        if not ai_wav:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        if self._is_multi_round(task_params):
            audio_list = []
            for i, rd in self._iter_rounds(task_params):
                user_wav = rd.get('user_wav') or ''
                ai_wav = rd.get('ai_wav') or ''
                if user_wav and ai_wav:
                    audio_list.append({'user_wav': user_wav, 'ai_wav': ai_wav})
            # 可选参数取最后一轮
            rd = self._get_round_safe(task_params, -1)
            kwargs = self._extract_kwargs(task_params, rd)
            return {'mode': 'multi', 'audio_list': audio_list, 'kwargs': kwargs}
        else:
            idx = self._get_target_round_index(task_params)
            user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
            rd = self._get_round_safe(task_params, idx)
            kwargs = self._extract_kwargs(task_params, rd)
            return {'mode': 'single', 'user_wav': user_wav, 'ai_wav': ai_wav, 'kwargs': kwargs}

    @staticmethod
    def _extract_kwargs(task_params, rd):
        kwargs = {}
        gap = task_params.get('seg_merge_gap_s') or rd.get('seg_merge_gap_s')
        if gap is not None:
            try:
                kwargs['seg_merge_gap_s'] = float(gap)
            except (ValueError, TypeError):
                pass
        tsi = task_params.get('target_segment_index') or rd.get('target_segment_index')
        if tsi is not None:
            try:
                kwargs['target_segment_index'] = int(tsi)
            except (ValueError, TypeError):
                pass
        return kwargs

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.non_interactive_latency import compute_non_interactive_latency

        if params.get('mode') == 'multi':
            per_round = []
            for a in params['audio_list']:
                per_round.append(
                    compute_non_interactive_latency(a['user_wav'], a['ai_wav'], **params['kwargs'])
                )
            return self._aggregate_results(per_round)
        else:
            return compute_non_interactive_latency(
                params['user_wav'], params['ai_wav'], **params['kwargs']
            )


class NoiseLatencyCalculator(_RejectionBase):
    """噪声打断时延：噪声播放期间模型"停得下、恢复得来"

    单轮：取当前轮 ai_wav + 时间参数算 1 次
    多轮：start_ms/end_ms 取第二轮（index=1），其他字段取最后一轮，算 1 次
    """
    task_type = 'noise_latency'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        if not (task_params.get('ai_wav') or rd.get('ai_wav')):
            return False, f"Missing required field for {self.task_type}: ai_wav"
        if self._is_multi_round(task_params):
            # 多轮：start_ms/end_ms 取第二轮，pcm_first_ms 取最后一轮
            rd2 = self._get_round_safe(task_params, 1)
            rd_last = self._get_round_safe(task_params, -1)
            missing = [
                f for f in ('start_ms', 'end_ms')
                if task_params.get(f) is None and rd2.get(f) is None
            ]
            # pcm_first_ms 缺失时有兜底逻辑 (start_ms - 1000)，不作为必填
            if missing:
                return False, f"Missing required fields for {self.task_type}: {', '.join(missing)}"
        else:
            missing = [
                f for f in ('start_ms', 'end_ms')
                if task_params.get(f) is None and rd.get(f) is None
            ]
            # pcm_first_ms 缺失时有兜底逻辑 (start_ms - 1000)，不作为必填
            if missing:
                return False, f"Missing required fields for {self.task_type}: {', '.join(missing)}"
        return True, None

    @staticmethod
    def _to_float(val):
        """安全转 float：空字符串/None 返回 None"""
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    def prepare_params(self, task_params):
        if self._is_multi_round(task_params):
            # 多轮：start_ms/end_ms 取第二轮（index=1），其他取最后一轮
            rd2 = self._get_round_safe(task_params, 1)
            rd_last = self._get_round_safe(task_params, -1)
            ai_wav = task_params.get('ai_wav') or rd_last.get('ai_wav') or ''
            start_ms = self._to_float(task_params.get('start_ms') or rd2.get('start_ms'))
            end_ms = self._to_float(task_params.get('end_ms') or rd2.get('end_ms'))
            pcm_first_ms = self._to_float(task_params.get('pcm_first_ms') or rd_last.get('pcm_first_ms'))
            # pcm_first_ms 缺失时用 start_ms - 1000 作为基准
            if pcm_first_ms is None and start_ms is not None:
                pcm_first_ms = start_ms - 1000
            kwargs = self._extract_kwargs(task_params, rd_last)
            return {
                'mode': 'single', 'ai_wav': ai_wav, 'start_ms': start_ms,
                'end_ms': end_ms, 'pcm_first_ms': pcm_first_ms, 'kwargs': kwargs,
            }
        else:
            idx = self._get_target_round_index(task_params)
            rd = self._get_round_safe(task_params, idx)
            ai_wav = task_params.get('ai_wav') or rd.get('ai_wav') or ''
            start_ms = self._to_float(task_params.get('start_ms') or rd.get('start_ms'))
            end_ms = self._to_float(task_params.get('end_ms') or rd.get('end_ms'))
            pcm_first_ms = self._to_float(task_params.get('pcm_first_ms') or rd.get('pcm_first_ms'))
            if pcm_first_ms is None and start_ms is not None:
                pcm_first_ms = start_ms - 1000
            kwargs = self._extract_kwargs(task_params, rd)
            return {
                'mode': 'single', 'ai_wav': ai_wav, 'start_ms': start_ms,
                'end_ms': end_ms, 'pcm_first_ms': pcm_first_ms, 'kwargs': kwargs,
            }

    @staticmethod
    def _extract_kwargs(task_params, rd):
        kwargs = {}
        gap = task_params.get('seg_merge_gap_s') or rd.get('seg_merge_gap_s')
        if gap is not None:
            try:
                kwargs['seg_merge_gap_s'] = float(gap)
            except (ValueError, TypeError):
                pass
        return kwargs

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.rejection_scene_awareness.noise_latency import compute_noise_latency

        return compute_noise_latency(
            params['ai_wav'], params['start_ms'], params['end_ms'],
            params['pcm_first_ms'], **params['kwargs']
        )
