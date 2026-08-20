"""BaseCalculator：模板方法基类。

子类需实现 validate()、prepare_params()、calculate()。
validate() 用于在 API 层拦截参数缺失，返回 (is_valid, error_msg)。
prepare_params() 默认走通用 _prepare_params，子类可覆写。
"""


class BaseCalculator:
    """策略基类：run() 为模板方法，子类实现 validate() + calculate()。

    用法：
        class WerCalculator(BaseCalculator):
            task_type = 'wer'
            def validate(self, task_params):
                if not task_params.get('asr_ref') and 'rounds' not in task_params:
                    return False, "Missing required fields: asr_ref, asr_hyp"
                return True, None
            def calculate(self, params):
                return calculate_wer(params['asr_ref'], ...)
    """

    task_type: str = ''

    def run(self, task_params):
        """模板方法：prepare_params -> calculate"""
        params = self.prepare_params(task_params)
        return self.calculate(params)

    def validate(self, task_params):
        """参数校验：返回 (is_valid, error_msg)。

        子类应覆写此方法，检查必填字段是否齐全。
        """
        return True, None

    def prepare_params(self, task_params):
        """默认实现：使用 TaskService._prepare_params 提取通用字段。

        子类可覆写此方法，实现任务特定的参数提取。
        """
        # 延迟导入避免循环依赖
        from app.services.task_service import TaskService
        return TaskService._prepare_params(task_params, self.task_type)

    def calculate(self, params):
        """子类必须实现：接收 prepare_params 的返回值，执行计算。"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 calculate()")
