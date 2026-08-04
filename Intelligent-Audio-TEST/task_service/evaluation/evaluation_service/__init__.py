"""
评估服务包（由原 evaluation_service.py 拆分而来）

将原 47KB 单文件按职责拆分为多个 Mixin 子模块，通过多重继承组装为
最终的 EvaluationService 类。所有逻辑保持不变，仅做结构拆分。

对外导出：
- EvaluationService: 评估服务类
- evaluation_service: 模块级单例（保持与原文件一致的导入路径）
"""
from task_service.evaluation.evaluation_mixin import EvaluationLoggerMixin
from task_service.evaluation.evaluation_service.worker_management import WorkerManagementMixin
from task_service.evaluation.evaluation_service.round_data_builder import RoundDataBuilderMixin
from task_service.evaluation.evaluation_service.case_evaluation import CaseEvaluationMixin
from task_service.evaluation.evaluation_service.case_loader import CaseLoaderMixin
from task_service.evaluation.evaluation_service.dimension_loader import DimensionLoaderMixin
from task_service.evaluation.evaluation_service.dimension_result_recorder import DimensionResultRecorderMixin
from task_service.evaluation.evaluation_service.task_dispatcher import TaskDispatcherMixin
from task_service.evaluation.evaluation_service.post_evaluation import PostEvaluationMixin


class EvaluationService(
    WorkerManagementMixin,
    RoundDataBuilderMixin,
    CaseEvaluationMixin,
    CaseLoaderMixin,
    DimensionLoaderMixin,
    DimensionResultRecorderMixin,
    TaskDispatcherMixin,
    PostEvaluationMixin,
    EvaluationLoggerMixin,
):
    """评估服务（由多个 Mixin 组合而成，逻辑与原单文件完全一致）"""
    pass


evaluation_service = EvaluationService()
