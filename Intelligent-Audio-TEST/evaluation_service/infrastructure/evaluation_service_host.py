# -*- coding: utf-8 -*-
"""评估服务宿主（Infrastructure 层组合体）

P0-1 DDD 改造：从 domain/services/evaluation_service/__init__.py 移至此处。
组合 Domain 业务 Mixin + Infrastructure 管理 Mixin（WorkerManagement / TaskDispatcher），
通过 EvaluationLoggerMixin.__init__ 注入 repository ABC 实例，
保持与原单文件完全一致的行为。

对外暴露 evaluation_service 模块级单例。
"""
from evaluation_service.domain.services.evaluation_logger import EvaluationLoggerMixin
from evaluation_service.domain.services.evaluation_service.round_data_builder import RoundDataBuilderMixin
from evaluation_service.domain.services.evaluation_service.case_evaluation import CaseEvaluationMixin
from evaluation_service.domain.services.evaluation_service.case_loader import CaseLoaderMixin
from evaluation_service.domain.services.evaluation_service.dimension_loader import DimensionLoaderMixin
from evaluation_service.domain.services.evaluation_service.dimension_result_recorder import DimensionResultRecorderMixin
from evaluation_service.domain.services.evaluation_service.post_evaluation import PostEvaluationMixin
from evaluation_service.infrastructure.evaluation_api.worker_management import WorkerManagementMixin
from evaluation_service.infrastructure.evaluation_api.task_dispatcher import TaskDispatcherMixin


class _EvaluationServiceHost(
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
    """评估服务宿主（Infrastructure 层组合体，含 Worker/线程池管理）

    组合 Domain 业务 Mixin + Infrastructure 管理 Mixin。
    Repository ABC 实例通过 EvaluationLoggerMixin.__init__ 注入到 self._task_acl_repo
    和 self._evaluation_dimension_repo，供所有 Domain Mixin 使用。
    """

    def __init__(self):
        # 注入 repository 实例（infrastructure 层单例）
        from evaluation_service.infrastructure.acl.task_acl_repository import task_acl_repository
        from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import evaluation_dimension_repository
        super().__init__(
            task_acl_repo=task_acl_repository,
            evaluation_dimension_repo=evaluation_dimension_repository,
        )


# 模块级单例（保持与原 domain/services/evaluation_service 导入路径兼容）
evaluation_service = _EvaluationServiceHost()
