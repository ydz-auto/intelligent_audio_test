# -*- coding: utf-8 -*-
"""xiaoyi_metrics 主包：全域编排器

XiaoyiMetricsCalculator 是小艺评估所有域的唯一编排入口：
  - 统一调一次双路 ASR（user_wav / ai_wav），结果共享给所有子维度
  - 按域聚合子维度结果：turn_taking / interruption / rejection_scene_awareness
  - 支持task_params['sub_tasks'] 指定只算部分子维度

编排关系（只引用注册表，不直接 import 各域实现）：
    xiaoyi_metrics（本编排器）
    ├── turn_taking/      TurnTakingCalculator（tor / false_takeover / takeover_latency）
    │                     HighFreqTurnTakingCalculator / HighFreqLlmJudgeCalculator
    ├── interruptibility/ InterruptionMetricsCalculator
    └── rejection_scene_awareness/ NonInteractiveLatencyCalculator
"""
import logging

from app.services.calculators.base import BaseCalculator

logger = logging.getLogger(__name__)


class XiaoyiMetricsCalculator(BaseCalculator):
    """小艺全域编排器：统一共享 ASR，按域聚合各子维度结果

    可通过 task_params['sub_tasks'] 指定只计算部分子维度，例如:
        sub_tasks: ['tor', 'takeover_latency']  # 只算这两个
    未指定时默认计算全部子维度。

    输出按 result_key 分组，各组内是子维度原始结果：
        {
            'tor': {...}, 'false_takeover': {...}, 'takeover_latency': {...},
            'interruption': {...}, 'non_interactive_latency': {...},
            'high_freq_turn_taking': {...}, 'high_freq_llm_judge': {...},
        }
    """
    task_type = 'xiaoyi_metrics'

    # 编排的子维度注册表（key = 输出结果 key，value = TaskService.CALCULATORS 查找 key）
    _SUB_DIMENSIONS = {
        # turn_taking 域
        'tor': 'tor',
        'false_takeover': 'false_takeover',
        'takeover_latency': 'takeover_latency',
        # interruptibility 域
        'interruption': 'interruption_metrics',
        # rejection_scene_awareness 域
        'non_interactive_latency': 'non_interactive_latency',
        # turn_taking 域（高频轮换）
        'high_freq_turn_taking': 'high_freq_turn_taking',
        'high_freq_llm_judge': 'high_freq_llm_judge',
    }

    def validate(self, task_params):
        from app.services.calculators.base import BaseCalculator as _B
        user_wav, ai_wav = _B._get_audio_from_round(
            task_params, _B._get_target_round_index(task_params)
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
        from app.services.task_service import TaskService
        from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingBase

        sub_tasks = params.get('sub_tasks')  # None 或 list
        results = {}

        # ── 统一调一次 ASR，共享给所有子维度 ──
        idx = self._get_target_round_index(params)
        user_wav, ai_wav = self._get_audio_from_round(params, idx)
        shared_asr = {}
        if user_wav:
            # 记录来源 wav：子维度按来源匹配复用，防止多轮场景错用其他轮的识别结果
            shared_asr['user_wav'] = user_wav
            shared_asr['user_chunks'] = TurnTakingBase._get_asr_chunks(user_wav)
        if ai_wav:
            shared_asr['ai_wav'] = ai_wav
            shared_asr['ai_chunks'] = TurnTakingBase._get_asr_chunks(ai_wav)
            shared_asr['ai_word_chunks'] = TurnTakingBase._get_asr_chunks(ai_wav, filter_punct=False)
        # pause 区间也从 user_chunks 统一算一次
        if shared_asr.get('user_chunks'):
            shared_asr['pause_intervals'] = TurnTakingBase._compute_pause_intervals(shared_asr['user_chunks'])
        else:
            shared_asr['pause_intervals'] = []

        logger.info(
            f"[xiaoyi_metrics] 共享 ASR 完成: "
            f"user_chunks={len(shared_asr.get('user_chunks') or [])}, "
            f"ai_chunks={len(shared_asr.get('ai_chunks') or [])}, "
            f"ai_word_chunks={len(shared_asr.get('ai_word_chunks') or [])}, "
            f"pause={len(shared_asr.get('pause_intervals') or [])}"
        )

        for result_key, calc_key in self._SUB_DIMENSIONS.items():
            if sub_tasks and result_key not in sub_tasks:
                logger.info(f"[xiaoyi_metrics] 子维度 {calc_key} 不在 sub_tasks 中，跳过")
                continue
            calculator = TaskService.CALCULATORS.get(calc_key)
            if calculator is None:
                logger.warning(f"[xiaoyi_metrics] 子维度 {calc_key} 未注册，跳过")
                continue
            try:
                # 校验
                is_valid, err = calculator.validate(params)
                if not is_valid:
                    logger.info(f"[xiaoyi_metrics] 子维度 {calc_key} 校验失败: {err}，跳过")
                    results[result_key] = {'message': f'跳过: {err}'}
                    continue
                # 取参 + 注入共享 ASR + 计算
                sub_params = calculator.prepare_params(params)
                sub_params['_shared_asr'] = shared_asr
                results[result_key] = calculator.calculate(sub_params)
                logger.info(f"[xiaoyi_metrics] 子维度 {calc_key} 计算完成")
            except Exception as e:
                logger.warning(f"[xiaoyi_metrics] 子维度 {calc_key} 计算失败: {e}")
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
            logger.info("[xiaoyi_metrics] false_takeover.tor=1，tor 和 takeover_latency 置 null")

        return results
