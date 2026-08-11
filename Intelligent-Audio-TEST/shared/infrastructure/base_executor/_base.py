# -*- coding: utf-8 -*-
"""
BaseExecutor — 执行器基类（共享内核 / Shared Kernel）

由 task_service/core/base_executor.py 迁移至 shared/infrastructure/，
供 api_test_service 与 task_service 共用。

迁移说明：
- 原直接调用 `from task_service.evaluation.evaluation_service import evaluation_service`
  改为通过 gRPC 调用 evaluation_service 的 EvaluationService.EvaluateCase
  （`submit_evaluate_case` 位于 shared.clients.grpc_clients）。
  `_evaluate_result` 不再直接调用 evaluation_service，而是委托给
  `submit_evaluate_case`。

重构说明（拆分）：
- 原 base_executor.py 拆分为多个 mixin 模块，按职责分组：
  - _control_mixin.py：暂停 / 停止控制
  - _logging_mixin.py：统一日志记录
  - _params_mixin.py：算法额外参数处理 / 结果映射器获取
  - _results_mixin.py：测试结果处理与评估提交
  - _db_mixin.py：数据库操作（校验、状态更新、结果保存）
  - _proxy.py：_DeviceResultCollectorProxy 代理类
- 本模块通过多继承组装最终 BaseExecutor 类，保持原有全部行为不变。
"""
import threading
from datetime import timezone, timedelta

from shared.infrastructure.base_executor._control_mixin import ControlMixin
from shared.infrastructure.base_executor._logging_mixin import LoggingMixin
from shared.infrastructure.base_executor._params_mixin import ParamsMixin
from shared.infrastructure.base_executor._results_mixin import ResultsMixin
from shared.infrastructure.base_executor._db_mixin import DbMixin


class BaseExecutor(ControlMixin, LoggingMixin, ParamsMixin, ResultsMixin, DbMixin):
    """执行器基类"""

    def __init__(self, execution_engine=None):
        self.execution_engine = execution_engine
        self._thread_ctx = threading.local()
        self.current_test_case_id = None
        self.current_case_field_values = {}
        self.utc_plus_8 = timezone(timedelta(hours=8))
