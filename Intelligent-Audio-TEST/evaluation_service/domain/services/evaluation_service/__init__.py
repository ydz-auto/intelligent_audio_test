"""
评估服务包（由原 evaluation_service.py 拆分而来）

P0-1 DDD 改造：
- Domain 层只保留纯业务逻辑 Mixin（评分、维度加载、用例加载、结果记录、后评估）
- WorkerManagementMixin / TaskDispatcherMixin 移至 Infrastructure 层（线程池/Worker 生命周期是基础设施逻辑）
- Infrastructure 层的 EvaluationServiceHost 组合所有 Mixin，对外暴露 evaluation_service 单例
- Domain 层 Mixin 通过 EvaluationLoggerMixin.__init__ 接受 repository ABC 注入，
  不再在方法内延迟 import infrastructure 层

对外导出：
- EvaluationService: 领域评估服务（仅业务逻辑，不含 Worker/线程池）
- evaluation_service 单例已移至 infrastructure/evaluation_service_host.py
"""
from evaluation_service.domain.services.evaluation_logger import EvaluationLoggerMixin
from evaluation_service.domain.services.evaluation_service.round_data_builder import RoundDataBuilderMixin
from evaluation_service.domain.services.evaluation_service.case_evaluation import CaseEvaluationMixin
from evaluation_service.domain.services.evaluation_service.case_loader import CaseLoaderMixin
from evaluation_service.domain.services.evaluation_service.dimension_loader import DimensionLoaderMixin
from evaluation_service.domain.services.evaluation_service.dimension_result_recorder import DimensionResultRecorderMixin
from evaluation_service.domain.services.evaluation_service.post_evaluation import PostEvaluationMixin


class EvaluationService(
    RoundDataBuilderMixin,
    CaseEvaluationMixin,
    CaseLoaderMixin,
    DimensionLoaderMixin,
    DimensionResultRecorderMixin,
    PostEvaluationMixin,
    EvaluationLoggerMixin,
):
    """评估领域服务（仅业务逻辑，不含 Worker/线程池管理）

    Worker/线程池/端点调度逻辑已移至 infrastructure/evaluation_api/。
    Repository ABC 通过 EvaluationLoggerMixin.__init__ 注入。
    """
    pass


def __getattr__(name):
    if name == 'evaluation_service':
        raise ImportError(
            "evaluation_service 单例已迁移至 infrastructure 层，"
            "请改为：from evaluation_service.infrastructure.evaluation_service_host "
            "import evaluation_service"
        )
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
