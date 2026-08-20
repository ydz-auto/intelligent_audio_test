"""turn_taking / interruption_metrics 策略类"""
from app.services.calculators.base import BaseCalculator


class TurnTakingCalculator(BaseCalculator):
    task_type = 'turn_taking'

    def prepare_params(self, task_params):
        """turn_taking 直接透传 task_params，由内部函数处理"""
        return task_params

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_xiaoyi_metrics
        return calculate_xiaoyi_metrics(params)


class InterruptionMetricsCalculator(BaseCalculator):
    task_type = 'interruption_metrics'

    def validate(self, task_params):
        has_user = task_params.get('user_asr') or task_params.get('user_chunks') or task_params.get('user_wav')
        if not has_user:
            return False, f"Missing required field for {self.task_type}: user_wav or user_asr (用户打断 wav 或 ASR)"
        has_model = task_params.get('model_asr') or task_params.get('model_chunks') or task_params.get('ai_wav') or task_params.get('model_wav')
        if not has_model:
            return False, f"Missing required field for {self.task_type}: ai_wav or model_asr (模型恢复 wav 或 ASR)"
        return True, None

    def prepare_params(self, task_params):
        """interruption_metrics 直接透传 task_params"""
        return task_params

    def calculate(self, params):
        from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_interruption_metrics
        return calculate_interruption_metrics(params)
