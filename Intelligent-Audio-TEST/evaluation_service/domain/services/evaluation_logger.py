# -*- coding: utf-8 -*-
"""评估服务统一日志混入（Domain 层）

所有评估领域服务 Mixin 继承此类即可获得 _log 方法。
同时作为 repository 注入点：Infrastructure 层在 __init__ 中传入 ABC 实例，
Domain 层 Mixin 通过 self._task_acl_repo / self._evaluation_dimension_repo 访问。
不依赖 infrastructure 层，仅依赖 shared.utils.log_handler 和 domain ABC。
"""
from shared.domain.ports.logging_port import log_and_emit


class EvaluationLoggerMixin:
    """统一日志记录混入，提供 _log 方法，同时持有 repository 注入点"""

    def __init__(self, task_acl_repo=None, evaluation_dimension_repo=None, **kwargs):
        """接受 repository 注入（domain ABC 类型），供所有 Mixin 使用。

        Args:
            task_acl_repo: TaskAclRepository ABC 实例（infrastructure 注入）
            evaluation_dimension_repo: EvaluationDimensionRepository ABC 实例
        """
        self._task_acl_repo = task_acl_repo
        self._evaluation_dimension_repo = evaluation_dimension_repo
        super().__init__(**kwargs)

    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None,
             device_id=None, algorithm_type=None, **kwargs):
        """统一日志入口"""
        log_and_emit(
            level=level,
            module='Evaluation',
            content=content,
            category=kwargs.pop('category', 'execution'),
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            device_id=device_id,
            algorithm_type=algorithm_type,
            **kwargs
        )
