# -*- coding: utf-8 -*-
"""task_service 已发布任务 PO 定义

归属：task_service（测试任务上下文）
表：published_tasks

业务语义（对齐《任务发布功能设计文档》）：
- 从日常任务发布得到，保存发布时的完整配置快照（不可变版本）
- 不承担执行进度，执行时读取快照创建新的日常任务（test_tasks 带追溯字段）
- 版本链：首个版本 ID 作为 task_group_id 锚点，新版本 vN+1 且旧版本 is_current=False
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, Boolean, JSON, Index,
)

# 已发布任务类型取值（对齐 V9.7.10 published_tasks.type：api/e2e）
# 新架构 task.type 已废弃，发布时由快照用例级 device_type 派生
PUBLISHED_TASK_TYPE_API = 'api'
PUBLISHED_TASK_TYPE_E2E = 'e2e'


class PublishedTask(Base):
    """已发布任务模型 (Published Task Model)

    从日常任务发布得到，保存发布时的完整配置快照（不可变版本）。
    不承担执行进度，执行时读取快照创建新的日常任务。
    """
    __tablename__ = 'published_tasks'
    __table_args__ = (
        Index('idx_published_task_status', 'status'),
        Index('idx_published_task_source', 'source_task_id'),
        Index('idx_published_task_is_current', 'is_current'),
        Index('idx_published_task_benchmark_status', 'benchmark', 'status'),
        Index('idx_published_task_algorithm_type', 'algorithm_type'),
        Index('idx_published_task_created_by_user_id', 'created_by_user_id'),
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment='已发布任务 ID')
    task_group_id = Column(Integer, comment='已发布任务逻辑分组 ID（首个版本 ID，版本链锚点）')
    source_task_id = Column(Integer, comment='来源日常任务 ID，可为空')
    created_by_user_id = Column(BigInteger, nullable=True, comment='创建者用户ID（INT-423 数据可见性 owner）')
    visibility = Column(String(20), nullable=False, default='shared', server_default='shared', comment='数据可见性 (shared/private，INT-423)')
    name = Column(String(255), nullable=False, comment='已发布任务名称')
    description = Column(Text, comment='说明')
    type = Column(String(50), comment='任务类型 (api/e2e)，发布时由快照用例级 device_type 派生（对齐 V9.7.10）')
    algorithm_type = Column(String(50), comment='关联算法类型（冗余：发布时从快照冻结，列表筛选直查本列，对齐 V9.7.10）')
    status = Column(String(20), nullable=False, default='published', comment='状态 (published/archived)')
    benchmark = Column(Boolean, nullable=False, default=False, comment='是否参与 Benchmark 排行（实测轨数据源标记）')
    version = Column(Integer, nullable=False, default=1, comment='版本号，从 1 开始')
    is_current = Column(Boolean, nullable=False, default=True, comment='是否当前版本')
    snapshot_config = Column(JSON, comment='发布时的完整配置快照（camelCase 结构；含 taskSnapshot 任务详情冻结体，INT-303）')
    report_snapshot = Column(JSON, comment='发布时冻结的源任务真实报告快照（引用 sourceReportId + 报告 7 表冻结数据，INT-258 双轨语义）')
    publish_reason = Column(Text, comment='发布说明')
    published_by = Column(String(50), comment='发布人')
    published_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='发布时间')
    archived_by = Column(String(50), comment='归档人')
    archived_at = Column(DateTime, comment='归档时间')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
