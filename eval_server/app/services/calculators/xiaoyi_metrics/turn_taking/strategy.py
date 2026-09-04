# -*- coding: utf-8 -*-
"""turn_taking 策略类：主维度 + 子维度各自实现 Calculator

架构：
  - TurnTakingCalculator（主维度）：遍历所有子维度 Calculator，各自用自己的
    prepare_params 取参 + calculate 计算，最后合并结果。
  - 各子维度独立 Calculator（tor/false_takeover/takeover_latency/
    high_freq_turn_taking/high_freq_llm_judge）：继承 TurnTakingBase，
    各自实现 prepare_params（区分单轮/多轮）和 calculate。
  - interruption_metrics 子维度已迁移到 interruptibility/strategy.py，
    主维度通过 TaskService.CALCULATORS 查找它。

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
  · interruption_metrics（在 interruptibility/strategy.py）：
      单轮 → 取当前轮双路音频
      多轮 → 取最后一轮双路音频（打断场景通常在最后一轮）
"""
import logging
from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.asr_utils import compute_pause_intervals
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    TAKEOVER_OFFSET_MS,
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class TurnTakingBase(BaseCalculator):
    """turn_taking 域公共基类：共享 ASR 调用和单轮/多轮取参逻辑

    单轮/多轮公共方法（_is_multi_round / _get_target_round_index /
    _get_round_safe / _get_audio_from_round / _iter_rounds /
    _aggregate_results）由 BaseCalculator 统一提供。
    """

    # ─── ASR 共享 ───

    @staticmethod
    def _get_asr_chunks(wav_path, filter_punct=True):
        from app.services.calculators.xiaoyi_metrics.turn_taking import _get_asr_chunks
        return _get_asr_chunks(wav_path, filter_punct=filter_punct)

    @staticmethod
    def _compute_pause_intervals(user_chunks):
        """从 user_wav ASR 结果自动计算停顿区间（复用 shared.asr_utils）"""
        return compute_pause_intervals(user_chunks or [])


# ─────────── 主维度：遍历子维度 ───────────

# turn_taking 域内子维度（跨域编排由 XiaoyiMetricsCalculator 负责）
_SUB_DIMENSIONS = {
    'tor': 'tor',
    'false_takeover': 'false_takeover',
    'takeover_latency': 'takeover_latency',
    'high_freq_turn_taking': 'high_freq_turn_taking',
    'high_freq_llm_judge': 'high_freq_llm_judge',
}


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
        """遍历所有子维度 Calculator，各自 prepare_params + calculate，合并结果

        可通过 task_params['sub_tasks'] 指定只计算部分子维度，例如:
            sub_tasks: ['tor', 'takeover_latency']  # 只算这两个，不算 false_takeover 等
        未指定时默认计算全部子维度。

        ASR 共享：主维度统一调一次双路 ASR（user_wav + ai_wav），
        结果注入各子维度的 params，子维度优先用已注入的 chunks，避免重复调用 ASR。
        """
        from app.services.task_service import TaskService

        sub_tasks = params.get('sub_tasks')  # None 或 list
        results = {}

        # ── ASR 共享：优先使用上层编排器（XiaoyiMetricsCalculator）注入的结果 ──
        shared_asr = params.get('_shared_asr')
        if not shared_asr:
            idx = self._get_target_round_index(params)
            user_wav, ai_wav = self._get_audio_from_round(params, idx)
            shared_asr = {}
            if user_wav:
                shared_asr['user_chunks'] = self._get_asr_chunks(user_wav)
            if ai_wav:
                shared_asr['ai_chunks'] = self._get_asr_chunks(ai_wav)
                shared_asr['ai_word_chunks'] = self._get_asr_chunks(ai_wav, filter_punct=False)
            # pause 区间也从 user_chunks 统一算一次
            if shared_asr.get('user_chunks'):
                shared_asr['pause_intervals'] = self._compute_pause_intervals(shared_asr['user_chunks'])
            else:
                shared_asr['pause_intervals'] = []

        logger.info(
            f"[turn_taking] 共享 ASR 完成: "
            f"user_chunks={len(shared_asr.get('user_chunks') or [])}, "
            f"ai_chunks={len(shared_asr.get('ai_chunks') or [])}, "
            f"ai_word_chunks={len(shared_asr.get('ai_word_chunks') or [])}, "
            f"pause={len(shared_asr.get('pause_intervals') or [])}"
        )

        for result_key, calc_key in _SUB_DIMENSIONS.items():
            if sub_tasks and result_key not in sub_tasks:
                logger.info(f"[turn_taking] 子维度 {calc_key} 不在 sub_tasks 中，跳过")
                continue
            calculator = TaskService.CALCULATORS.get(calc_key)
            if calculator is None:
                logger.warning(f"[turn_taking] 子维度 {calc_key} 未注册，跳过")
                continue
            try:
                # 校验
                is_valid, err = calculator.validate(params)
                if not is_valid:
                    logger.info(f"[turn_taking] 子维度 {calc_key} 校验失败: {err}，跳过")
                    results[result_key] = {'message': f'跳过: {err}'}
                    continue
                # 取参 + 注入共享 ASR + 计算
                sub_params = calculator.prepare_params(params)
                sub_params['_shared_asr'] = shared_asr
                results[result_key] = calculator.calculate(sub_params)
                logger.info(f"[turn_taking] 子维度 {calc_key} 计算完成")
            except Exception as e:
                logger.warning(f"[turn_taking] 子维度 {calc_key} 计算失败: {e}")
                results[result_key] = {'message': f'计算失败: {e}'}

        # 后处理：检测到误接管（抢话）时，接话率和接管时延不适用，置 null
        ft_result = results.get('false_takeover') or {}
        if ft_result.get('tor') == 1:
            _msg = '检测到误接管（抢话），接话率不适用'
            results['tor'] = {
                'tor': None, 'n_words': None, 'duration': None,
                'hit_words': None, 'user_last_word_end_s': None,
                'message': _msg,
            }
            _msg2 = '检测到误接管（抢话），接管时延不适用'
            results['takeover_latency'] = {
                'takeover_latency_ms': None,
                'user_last_word_end_ms': None,
                'ai_first_word_start_ms': None,
                'message': _msg2,
            }
            logger.info("[turn_taking] false_takeover.tor=1，tor 和 takeover_latency 置 null")

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

    def run(self, task_params):
        """独立调用入口：结果包装为 {'tor': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'tor': result}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.tor import compute_tor

        shared = params.get('_shared_asr') or {}
        user_chunks = shared.get('user_chunks')
        if user_chunks is None:
            user_chunks = self._get_asr_chunks(params['user_wav']) or []
        ai_chunks = shared.get('ai_chunks')
        if ai_chunks is None:
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
        return {'mode': 'single', 'user_wav': user_wav, 'ai_wav': ai_wav,
                'task_params': task_params}

    def run(self, task_params):
        """独立调用入口：结果包装为 {'false_takeover': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'false_takeover': result}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.false_takeover import (
            compute_false_takeover, compute_false_takeover_llm,
        )

        shared = params.get('_shared_asr') or {}
        user_chunks = shared.get('user_chunks')
        if user_chunks is None:
            user_wav = params.get('user_wav')
            user_chunks = self._get_asr_chunks(user_wav) if user_wav else None
        pause = shared.get('pause_intervals')
        if pause is None:
            pause = self._compute_pause_intervals(user_chunks)
        ai_word_chunks = shared.get('ai_word_chunks')
        if ai_word_chunks is None:
            ai_wav = params.get('ai_wav')
            ai_word_chunks = (self._get_asr_chunks(ai_wav, filter_punct=False) or []) if ai_wav else []

        result = compute_false_takeover(ai_word_chunks, pause)

        # LLM 补充判断：时间戳 tor=0 时用 LLM 做语义判断
        _ft_tor = result.get('tor', 0)
        if _ft_tor == 0 and user_chunks and ai_word_chunks:
            try:
                llm_result = compute_false_takeover_llm(
                    user_chunks, ai_word_chunks, pause, params.get('task_params'),
                )
                if llm_result is not None:
                    result['llm_eval'] = llm_result
                    if llm_result.get('false_takeover', 0) == 1:
                        result['tor'] = 1
                else:
                    result['llm_eval'] = {'false_takeover': _ft_tor, 'reason': 'LLM未配置或无数据'}
            except Exception as e:
                result['llm_eval'] = {'false_takeover': _ft_tor, 'reason': f'LLM评估失败: {e}'}
        elif _ft_tor == 1:
            result['llm_eval'] = {'false_takeover': 1, 'reason': '时间戳算法已判定抢话'}
        else:
            result['llm_eval'] = {'false_takeover': 0, 'reason': '无用户或模型ASR数据'}

        return result


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

    def run(self, task_params):
        """独立调用入口：结果包装为 {'takeover_latency': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'takeover_latency': result}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.takeover_latency import compute_takeover_latency_from_raw

        shared = params.get('_shared_asr') or {}
        user_chunks = shared.get('user_chunks')
        if user_chunks is None:
            user_chunks = self._get_asr_chunks(params['user_wav']) or []
        ai_chunks = shared.get('ai_chunks')
        if ai_chunks is None:
            ai_chunks = self._get_asr_chunks(params['ai_wav']) or []
        return compute_takeover_latency_from_raw(
            first_frame_ms=None, asr_hyp=None, start_ms=None,
            input_words=[], offset_ms=TAKEOVER_OFFSET_MS,
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

    def run(self, task_params):
        """独立调用入口：结果包装为 {'high_freq_turn_taking': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'high_freq_turn_taking': result}

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_turn_taking import compute_high_freq_turn_taking

        shared = params.get('_shared_asr') or {}
        user_chunks = shared.get('user_chunks')
        if user_chunks is None:
            user_chunks = self._get_asr_chunks(params['user_wav']) or []
        ai_chunks = shared.get('ai_chunks')
        if ai_chunks is None:
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
            'max_tokens': int(task_params.get('max_tokens') or rd.get('max_tokens') or LLM_DEFAULT_MAX_TOKENS),
            'temperature': float(task_params.get('temperature') or rd.get('temperature') or LLM_DEFAULT_TEMPERATURE),
        }

    def run(self, task_params):
        """独立调用入口：结果包装为 {'high_freq_llm_judge': result}"""
        params = self.prepare_params(task_params)
        result = self.calculate(params)
        return {'high_freq_llm_judge': result}

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


# InterruptionMetricsCalculator 已迁移到 interruptibility/strategy.py
# （该子维度属 interruptibility 域，不应由 turn_taking 域承载）
