# -*- coding: utf-8 -*-
"""turn_taking 策略类：主维度 + 子维度各自实现 Calculator

架构：
  - TurnTakingCalculator（主维度）：遍历所有子维度 Calculator，各自用自己的
    prepare_params 取参 + calculate 计算，最后合并结果。
  - 各子维度独立 Calculator（tor/false_takeover/takeover_latency/
    high_freq_turn_taking/high_freq_llm_judge/interruption_metrics）：
    继承 TurnTakingBase，各自实现 prepare_params（区分单轮/多轮）和 calculate。

单轮 vs 多轮区分：
  - round_number 有值（0/1/2...）→ 单轮评估，取 rounds[round_number]
  - round_number 不存在 → 多轮整体评估

各子维度单轮/多轮取参方式：
  · tor / takeover_latency：
      单轮 → 取当前轮双路音频算 1 次
      多轮 → 逐轮算 tor/latency，结果取平均或最后一轮
  · false_takeover：
      单轮 → 取当前轮 ai_wav + user_wav 算 pause
      多轮 → 逐轮算 pause 抢话，聚合结果
  · high_freq_turn_taking：
      单轮 → 取当前轮双路音频（单段，无多轮匹配意义）
      多轮 → 取 rounds[-1] 的双路完整音频（含多段对话）
  · high_freq_llm_judge：
      单轮 → rounds 只有 1 个元素，ai_wav 取当前轮
      多轮 → rounds 整体保留逐轮处理，ai_wav 取最后一轮
  · interruption_metrics：
      单轮 → 取当前轮双路音频
      多轮 → 取最后一轮双路音频（打断场景通常在最后一轮）
"""
import logging
from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class TurnTakingBase(BaseCalculator):
    """turn_taking 域公共基类：共享 ASR 调用和单轮/多轮取参逻辑"""

    # ─── 轮次定位 ───

    @staticmethod
    def _is_multi_round(task_params):
        """是否多轮评估（round_number 不存在）"""
        return task_params.get('round_number') is None

    @staticmethod
    def _get_target_round_index(task_params):
        """获取目标轮次索引

        单轮：round_number（0-indexed）
        多轮：-1（最后一轮）
        """
        rn = task_params.get('round_number')
        if rn is not None:
            return rn
        return -1

    @staticmethod
    def _get_round_safe(task_params, index):
        """安全获取 rounds[index]，越界或不存在返回 {}"""
        rounds = (task_params or {}).get('rounds')
        if not (rounds and isinstance(rounds, list)):
            return {}
        idx = index if index >= 0 else len(rounds) + index
        if 0 <= idx < len(rounds) and isinstance(rounds[idx], dict):
            return rounds[idx]
        return {}

    # ─── 音频取参（单轮/多轮通用）───

    @classmethod
    def _get_audio_from_round(cls, task_params, index):
        """从指定轮次取双路音频（顶层优先）"""
        rd = cls._get_round_safe(task_params, index)
        user_wav = task_params.get('user_wav') or rd.get('user_wav') or ''
        ai_wav = task_params.get('ai_wav') or rd.get('ai_wav') or ''
        return user_wav, ai_wav

    # ─── 多轮遍历 ───

    @staticmethod
    def _iter_rounds(task_params):
        """遍历所有轮次，yield (round_index, round_dict)

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

    # ─── ASR 共享 ───

    @staticmethod
    def _get_asr_chunks(wav_path):
        from app.services.calculators.xiaoyi_metrics.turn_taking import _get_asr_chunks
        return _get_asr_chunks(wav_path)

    @staticmethod
    def _get_asr_word_chunks(wav_path):
        from app.services.calculators.xiaoyi_metrics.turn_taking import _get_asr_word_chunks
        return _get_asr_word_chunks(wav_path)

    @staticmethod
    def _compute_pause_intervals(user_chunks):
        """从 user_wav ASR 结果自动计算停顿区间"""
        if not user_chunks:
            return []
        pause_intervals = []
        for i in range(len(user_chunks) - 1):
            prev_end = user_chunks[i]['timestamp'][1]
            next_start = user_chunks[i + 1]['timestamp'][0]
            gap = next_start - prev_end
            if 0.2 <= gap <= 3.0:
                pause_intervals.append({'text': '[PAUSE]', 'timestamp': [prev_end, next_start]})
        return pause_intervals

    @staticmethod
    def _aggregate_results(per_round_results, agg_keys=None):
        """聚合多轮结果：标量字段取平均，非标量字段取最后一轮

        Args:
            per_round_results: [{...}, {...}, ...] 每轮结果
            agg_keys: 需要取平均的数值字段名列表，为 None 则自动检测
        """
        if not per_round_results:
            return {}
        if len(per_round_results) == 1:
            return dict(per_round_results[0])

        # 取最后一轮作为基础
        result = dict(per_round_results[-1])
        # 数值字段取平均
        first = per_round_results[0]
        for k, v in first.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals = [r.get(k) for r in per_round_results if r.get(k) is not None]
                if vals:
                    result[k] = round(sum(vals) / len(vals), 3)
        result['n_rounds'] = len(per_round_results)
        result['per_round'] = per_round_results
        return result


# ─────────── 主维度：遍历子维度 ───────────

# 主维度管理的子维度列表（按计算顺序）
_SUB_DIMENSIONS = ['tor', 'false_takeover', 'takeover_latency',
                   'interruption_metrics', 'non_interactive_latency',
                   'high_freq_turn_taking', 'high_freq_llm_judge']


class TurnTakingCalculator(TurnTakingBase):
    """话轮接管主维度：遍历各子维度 Calculator，各自取参 + 计算，合并结果"""
    task_type = 'turn_taking'

    def validate(self, task_params):
        user_wav, ai_wav = self._get_audio_from_round(
            task_params, self._get_target_round_index(task_params)
        )
        if not (user_wav or ai_wav):
            return False, (
                f"Missing required field for {self.task_type}: "
                f"user_wav / ai_wav，至少需要一个"
            )
        return True, None

    def prepare_params(self, task_params):
        """直接透传 task_params，由 calculate 遍历子维度各自处理"""
        return task_params

    def calculate(self, params):
        """遍历所有子维度 Calculator，各自 prepare_params + calculate，合并结果"""
        from app.services.task_service import TaskService

        results = {}
        for sub_task_type in _SUB_DIMENSIONS:
            calculator = TaskService.CALCULATORS.get(sub_task_type)
            if calculator is None:
                logger.warning(f"[turn_taking] 子维度 {sub_task_type} 未注册，跳过")
                continue
            try:
                # 校验
                is_valid, err = calculator.validate(params)
                if not is_valid:
                    logger.info(f"[turn_taking] 子维度 {sub_task_type} 校验失败: {err}，跳过")
                    results[sub_task_type] = {'message': f'跳过: {err}'}
                    continue
                # 取参 + 计算
                sub_params = calculator.prepare_params(params)
                results[sub_task_type] = calculator.calculate(sub_params)
                logger.info(f"[turn_taking] 子维度 {sub_task_type} 计算完成")
            except Exception as e:
                logger.warning(f"[turn_taking] 子维度 {sub_task_type} 计算失败: {e}")
                results[sub_task_type] = {'message': f'计算失败: {e}'}

        return results


# ─────────── 子维度：TOR（接话率）───────────

class TorCalculator(TurnTakingBase):
    """接话率：用户结束说话后模型是否正确开始回复

    单轮：取当前轮双路音频算 1 次
    多轮：取最后一轮双路音频算 1 次
    """
    task_type = 'tor'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        if not user_wav or not ai_wav:
            return False, f"Missing required fields for {self.task_type}: user_wav, ai_wav"
        return True, None

    def prepare_params(self, task_params):
        """单轮取当前轮，多轮取最后一轮"""
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        return {'mode': 'single', 'user_wav': user_wav, 'ai_wav': ai_wav}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.tor import compute_tor

        user_chunks = self._get_asr_chunks(params['user_wav']) or []
        ai_chunks = self._get_asr_chunks(params['ai_wav']) or []
        return compute_tor(user_chunks=user_chunks, ai_chunks=ai_chunks)


# ─────────── 子维度：False Takeover（误接管率）───────────

class FalseTakeoverCalculator(TurnTakingBase):
    """误接管率：用户停顿期间模型是否错误接管（抢话）

    单轮：取当前轮 ai_wav + user_wav 算 pause
    多轮：取最后一轮 ai_wav + user_wav 算 1 次
    """
    task_type = 'false_takeover'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        _, ai_wav = self._get_audio_from_round(task_params, idx)
        if not ai_wav:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        return {'mode': 'single', 'user_wav': user_wav, 'ai_wav': ai_wav}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.false_takeover import compute_false_takeover

        user_chunks = self._get_asr_chunks(params['user_wav']) if params.get('user_wav') else None
        pause = self._compute_pause_intervals(user_chunks)
        ai_word_chunks = (self._get_asr_word_chunks(params['ai_wav']) or []) if params.get('ai_wav') else []
        return compute_false_takeover(ai_word_chunks, pause)


# ─────────── 子维度：Takeover Latency（接管时延）───────────

class TakeoverLatencyCalculator(TurnTakingBase):
    """接管时延：ai_wav 首字开始 - user_wav 末字结束

    单轮：取当前轮双路音频算 1 次
    多轮：取最后一轮双路音频算 1 次
    """
    task_type = 'takeover_latency'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        if not user_wav or not ai_wav:
            return False, f"Missing required fields for {self.task_type}: user_wav, ai_wav"
        return True, None

    def prepare_params(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        return {'mode': 'single', 'user_wav': user_wav, 'ai_wav': ai_wav}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.takeover_latency import compute_takeover_latency_from_raw

        user_chunks = self._get_asr_chunks(params['user_wav']) or []
        ai_chunks = self._get_asr_chunks(params['ai_wav']) or []
        return compute_takeover_latency_from_raw(
            first_frame_ms=None, asr_hyp=None, start_ms=None,
            input_words=[], offset_ms=40,
            user_chunks=user_chunks, ai_chunks=ai_chunks,
        )


# ─────────── 子维度：High Freq Turn Taking（高频轮换时延）───────────

class HighFreqTurnTakingCalculator(TurnTakingBase):
    """高频轮换：每轮回复时延（飞花令/成语接龙/快问快答）

    单轮：取当前轮双路音频
    多轮整体：所有字段取最后一轮 rounds[-1]（音频含完整多段对话）
    """
    task_type = 'high_freq_turn_taking'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        if not user_wav or not ai_wav:
            return False, f"Missing required fields for {self.task_type}: user_wav, ai_wav"
        return True, None

    def prepare_params(self, task_params):
        # 单轮和多轮都取目标轮次（多轮时 idx=-1 即最后一轮）
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)

        # 可选参数也从目标轮取
        rd = self._get_round_safe(task_params, idx)
        merge_gap = task_params.get('seg_merge_gap_s') or rd.get('seg_merge_gap_s')

        result = {'user_wav': user_wav, 'ai_wav': ai_wav}
        if merge_gap is not None:
            result['seg_merge_gap_s'] = float(merge_gap)
        return result

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_turn_taking import compute_high_freq_turn_taking

        user_chunks = self._get_asr_chunks(params['user_wav']) or []
        ai_chunks = self._get_asr_chunks(params['ai_wav']) or []

        kwargs = {}
        if 'seg_merge_gap_s' in params:
            kwargs['seg_merge_gap_s'] = params['seg_merge_gap_s']

        return compute_high_freq_turn_taking(user_chunks=user_chunks, ai_chunks=ai_chunks, **kwargs)


# ─────────── 子维度：High Freq LLM Judge（高频轮换 LLM 裁判）───────────

class HighFreqLlmJudgeCalculator(TurnTakingBase):
    """高频轮换 LLM 裁判：发送模型回复音频(ai_wav)给多模态 LLM，逐轮判断

    单轮：取当前轮的 ai_wav 和 rounds[round_number]
    多轮整体：所有字段取最后一轮 rounds[-1]（ai_wav、scenario_type 等）
    """
    task_type = 'high_freq_llm_judge'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)
        if not (task_params.get('ai_wav') or rd.get('ai_wav')):
            return False, f"Missing required field for {self.task_type}: ai_wav"
        if not rd.get('rounds'):
            rounds = task_params.get('rounds')
            if not (rounds and isinstance(rounds, list)):
                return False, f"Missing required field for {self.task_type}: rounds"
        return True, None

    def prepare_params(self, task_params):
        """所有字段取目标轮次（单轮=round_number，多轮=-1）"""
        idx = self._get_target_round_index(task_params)
        rd = self._get_round_safe(task_params, idx)

        # 所有字段：顶层优先，目标轮回退
        ai_wav = task_params.get('ai_wav') or rd.get('ai_wav') or ''
        rounds = rd.get('rounds') or task_params.get('rounds') or []
        # 多轮时只取最后一轮的 rounds（LLM 裁判处理最后一轮的对话上下文）
        if self._is_multi_round(task_params) and isinstance(rounds, list) and rounds:
            rounds = [rounds[-1]] if isinstance(rounds[-1], dict) else rounds

        return {
            'ai_wav': ai_wav,
            'rounds': rounds,
            'scenario_type': task_params.get('scenario_type') or rd.get('scenario_type') or '',
            'scenario_rules': task_params.get('scenario_rules') or rd.get('scenario_rules') or '',
            'model': task_params.get('llm_model') or rd.get('llm_model') or task_params.get('model') or '',
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or 4096),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or 0.1),
        }

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import evaluate_high_freq_llm
        return evaluate_high_freq_llm(
            rounds=params['rounds'],
            scenario_type=params['scenario_type'],
            scenario_rules=params['scenario_rules'],
            model=params['model'],
            max_tokens=params['max_tokens'],
            temperature=params['temperature'],
            ai_wav=params['ai_wav'],
        )


# ─────────── 子维度：Interruption Metrics（打断指标）───────────

class InterruptionMetricsCalculator(TurnTakingBase):
    """打断指标：用户打断模型时，衡量"停得下、恢复得来"

    单轮：取当前轮双路音频
    多轮：取最后一轮双路音频算 1 次
    """
    task_type = 'interruption_metrics'

    def validate(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        if not user_wav:
            return False, f"Missing required field for {self.task_type}: user_wav"
        if not ai_wav:
            return False, f"Missing required field for {self.task_type}: ai_wav"
        return True, None

    def prepare_params(self, task_params):
        idx = self._get_target_round_index(task_params)
        user_wav, ai_wav = self._get_audio_from_round(task_params, idx)
        rd = self._get_round_safe(task_params, idx)
        user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or rd.get('user_asr')
        model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or rd.get('model_asr')
        return {'mode': 'single', 'user_wav': user_wav, 'ai_wav': ai_wav,
                'user_asr': user_asr, 'model_asr': model_asr,
                'task_params': task_params}

    def calculate(self, params):
        # 委托给 turn_taking.calculate_interruption_metrics 统一入口：
        # 该入口内部完成 wav→ASR、时序指标(compute_interruption_metrics)、
        # 可选 LLM 评估(enable_llm_eval)、以及 n_events=0 时的 success 兜底。
        # 直接调 compute_interruption_metrics 会跳过 LLM/兜底（refactor 回归），此处修正。
        from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_interruption_metrics
        return calculate_interruption_metrics(params.get('task_params') or {})
