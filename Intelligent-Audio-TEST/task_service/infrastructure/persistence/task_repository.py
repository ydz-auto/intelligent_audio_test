# -*- coding: utf-8 -*-
"""TaskRepository - 任务聚合根仓储实现（聚合模块，P4-5 大文件拆分）。

原单文件 1032 行，按职责拆分为 5 个内部模块，本文件保持
`from task_service.infrastructure.persistence.task_repository import ...`
的全部导入路径不变：

- _task_converters.py：PO ↔ Entity 显式转换（TaskAggregate / TaskCaseEntity）
- _task_aggregate_mixin.py：TaskAggregateMixin — 聚合根 CRUD / 用例实体持久化 / 计数
- _task_crud_mixin.py：TaskCrudMixin — 任务创建/合并/编辑/导出/运行计数
- _task_case_stats_mixin.py：TaskCaseStatsMixin — dict 序列化 / TaskCase 状态 / 统计
- _task_lifecycle_mixin.py：TaskLifecycleMixin — 生命周期辅助（重置/预检/清理）

仓储职责：
- 从 DB 加载 Task PO 并转换为 TaskAggregate 聚合根
- 将聚合根的变更持久化回 DB（Entity → PO 字段映射）
- 提供按条件查询聚合根的方法

仓储只处理写模型，读取走 read_models（查询处理器）。

P5+DOMAIN 改造：移除对 aggregate.orm 的依赖，改为 PO ↔ Entity 显式转换。
聚合根不再持有 PO 引用，领域层与 ORM 完全隔离。
"""
from shared.utils.db_session import SoftDeleteMixin
from task_service.domain.repositories.task_repository import TaskRepositoryABC
from task_service.domain.repositories.task_case_repository import TaskCaseRepositoryABC
from task_service.infrastructure.persistence._task_aggregate_mixin import (
    TaskAggregateMixin,
)
from task_service.infrastructure.persistence._task_crud_mixin import (
    TaskCrudMixin,
)
from task_service.infrastructure.persistence._task_case_stats_mixin import (
    TaskCaseStatsMixin,
)
from task_service.infrastructure.persistence._task_lifecycle_mixin import (
    TaskLifecycleMixin,
)

# 向后兼容：转换函数历史上定义在本模块，供潜在外部引用（如 audio_repository 的对等实现）
from task_service.infrastructure.persistence._task_converters import (  # noqa: F401
    _UTC_PLUS_8,
    _task_po_to_entity,
    _apply_aggregate_to_po,
    _task_case_po_to_entity,
    _apply_case_entity_to_po,
)


class TaskRepository(
    SoftDeleteMixin,
    TaskAggregateMixin,
    TaskCrudMixin,
    TaskCaseStatsMixin,
    TaskLifecycleMixin,
    TaskRepositoryABC,
    TaskCaseRepositoryABC,
):
    """任务聚合根仓储（组合各职责 Mixin）。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    使用 @with_session 装饰器自动管理 session 生命周期，
    soft_delete 由 SoftDeleteMixin 提供。

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，聚合根不再持有 ORM 引用。
    """

    # PO_CLASS 由 TaskAggregateMixin 提供（PO_CLASS = Task）


# 模块级单例
task_repository = TaskRepository()
