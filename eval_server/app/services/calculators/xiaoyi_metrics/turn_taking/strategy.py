"""turn_taking / interruption_metrics 策略类

参数模式：
  - 单轮：顶层 user_wav / ai_wav
  - 多轮：rounds 内每轮含同名字段，顶层优先 + rounds[0] 回退
    rounds 整体保留透传给内部函数（calculate_xiaoyi_metrics / calculate_interruption_metrics）
    内部会从 rounds[0] 取音频路径，并保留 rounds 给 high_freq_llm_judge / interruption_llm 逐轮处理

  - 核心音频字段：ai_wav（模型回复通道） / user_wav（用户说话通道）
  - rounds：多轮文本上下文，整体保留透传
"""
from app.services.calculators.base import BaseCalculator


class TurnTakingCalculator(BaseCalculator):
    task_type = 'turn_taking'

    def validate(self, task_params):
        r0 = BaseCalculator._get_round0(task_params)
        has_audio = (
            task_params.get('user_wav') or r0.get('user_wav')
            or task_params.get('ai_wav') or r0.get('ai_wav')
        )
        if not has_audio:
            return False, (
                f"Missing required field for {self.task_type}: "
                f"user_wav / ai_wav，至少需要一个"
            )
        return True, None

    def prepare_params(self, task_params):
        """直接透传 task_params，由 calculate_xiaoyi_metrics 内部处理

        turn_taking 统一入口内部会：
        1. 从顶层或 rounds[0] 取 user_wav / ai_wav 调 ASR
        2. 保留 rounds 整体传给 high_freq_llm_judge 逐轮处理
        """
        return task_params

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_xiaoyi_metrics
        return calculate_xiaoyi_metrics(params)


class InterruptionMetricsCalculator(BaseCalculator):
    task_type = 'interruption_metrics'

    def validate(self, task_params):
        r0 = BaseCalculator._get_round0(task_params)
        has_user = task_params.get('user_wav') or r0.get('user_wav')
        if not has_user:
            return False, (
                f"Missing required field for {self.task_type}: user_wav (用户打断音频)"
            )
        has_model = task_params.get('ai_wav') or r0.get('ai_wav')
        if not has_model:
            return False, (
                f"Missing required field for {self.task_type}: ai_wav (模型恢复音频)"
            )
        return True, None

    def prepare_params(self, task_params):
        """直接透传 task_params，由 calculate_interruption_metrics 内部处理

        interruption_metrics 内部会：
        1. 从顶层或 rounds[0] 取 user_wav / ai_wav 调 ASR
        2. 保留 rounds 整体传给 interruption_llm 逐轮 LLM 评估
        """
        return task_params

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_interruption_metrics
        return calculate_interruption_metrics(params)
