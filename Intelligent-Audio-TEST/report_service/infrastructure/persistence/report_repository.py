# -*- coding: utf-8 -*-
"""ReportRepository - 报告聚合根仓储实现（聚合模块，P4-5 大文件拆分）。

原单文件 978 行，按职责拆分为 5 个内部模块，本文件保持
`from report_service.infrastructure.persistence.report_repository import ...`
的全部导入路径不变：

- _report_converters.py：PO ↔ Entity 显式转换（ReportAggregate 及各子实体）
- _report_query_mixin.py：ReportQueryMixin — 主表查询/原始 PO 查询/趋势数据
- _report_children_load_mixin.py：ReportChildrenLoadMixin — 子实体集合加载/完整导出数据
- _report_children_write_mixin.py：ReportChildrenWriteMixin — 子实体直接写入（入参 dict）
- _report_persist_mixin.py：ReportPersistMixin — 主表写入/状态流转/删除

仓储职责：
- 从 DB 加载 Report PO 及关联子表，并转换为 ReportAggregate 聚合根
- 将聚合根的变更持久化回 DB（Entity → PO 字段映射）
- 提供按条件查询聚合根的方法

仓储只处理写模型，读取走 read_models（查询处理器）。

P5+DOMAIN 改造：PO ↔ Entity 显式转换，聚合根不再持有 ORM 引用，
领域层与 SQLAlchemy 完全隔离。
"""
from shared.utils.db_session import SoftDeleteMixin
from report_service.domain.repositories.report_repository_abc import (
    ReportRepositoryABC,
)
from report_service.infrastructure.persistence._report_query_mixin import (
    ReportQueryMixin,
)
from report_service.infrastructure.persistence._report_children_load_mixin import (
    ReportChildrenLoadMixin,
)
from report_service.infrastructure.persistence._report_children_write_mixin import (
    ReportChildrenWriteMixin,
)
from report_service.infrastructure.persistence._report_persist_mixin import (
    ReportPersistMixin,
)

# 向后兼容：转换函数历史上定义在本模块，供潜在外部引用
from report_service.infrastructure.persistence._report_converters import (  # noqa: F401
    _safe_json_loads,
    _safe_json_dumps,
    _summary_po_to_entity,
    _case_po_to_entity,
    _metric_stats_po_to_entity,
    _raw_data_po_to_entity,
    _comparison_po_to_entity,
    _report_po_to_entity,
    _apply_summary_entity_to_po,
    _apply_case_entity_to_po,
    _apply_metric_stats_entity_to_po,
    _apply_raw_data_entity_to_po,
    _apply_comparison_entity_to_po,
    _apply_report_to_po,
)
from report_service.infrastructure.persistence.models import (  # noqa: F401
    Report,
)


class ReportRepository(
    ReportQueryMixin,
    ReportChildrenLoadMixin,
    ReportChildrenWriteMixin,
    ReportPersistMixin,
    SoftDeleteMixin,
    ReportRepositoryABC,
):
    """报告聚合根仓储（组合各职责 Mixin）。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    使用 @with_session 装饰器自动管理 session 生命周期，
    soft_delete 由 SoftDeleteMixin 提供。

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，聚合根不再持有 ORM 引用。
    """

    # PO_CLASS 由 ReportQueryMixin/ReportPersistMixin 声明，此处绑定 Report
    PO_CLASS = Report


# 模块级单例
report_repository = ReportRepository()
