# -*- coding: utf-8 -*-
"""task_service Cherry-Pick 挑选合并 PO（INT-339）

归属：task_service（挑选合并上下文）
表：cherry_pick_cart_items / task_cherry_pick_relations
    / cherry_pick_sets / cherry_pick_set_items

裁定口径（设计文档 §5.1/§5.4，前向可行性评审 2026-10-14）：
- 结果持有方式 = 引用（方案 A）：容器任务经 task_cherry_pick_relations
  以 result_id + 溯源字段引用源执行结果，test_results.task_id 禁止改挂
  （红线：源任务保持原样，无「搬家」语义）
- cherry-pick 容器任务以专有关系表存在性判定（与 TaskMergeRelation 对
  merged 容器的判定方式同构）；不使用 task.type（已物理删除，INT-263）
- 购物车按用户持久化（user_id 来自 JWT x-user-id metadata，AUTH_MODE=off
  时为 NULL 禁止写入，对齐 Favorite 模式）
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, JSON,
    UniqueConstraint, Index, ForeignKey,
)

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


class CherryPickCartItem(Base):
    """购物车条目（per-user，挑选结果加入购物车）

    - user_id 来自 JWT（x-user-id metadata），未认证 NULL 禁止写入
    - result_id 引用源执行结果（test_results.id），禁止修改源行
    - source_task_id / source_case_id / source_device_id 为结果级溯源快照
      （源行只读，溯源字段冗余存储供分组展示/失效校验）
    """
    __tablename__ = 'cherry_pick_cart_items'
    __table_args__ = (
        # 幂等：同一用户对同一结果只加购一次
        UniqueConstraint('user_id', 'result_id', name='uq_cherry_cart_user_result'),
        Index('idx_cherry_cart_user', 'user_id'),
        Index('idx_cherry_cart_user_source', 'user_id', 'source_task_id'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(BigInteger, nullable=False, index=True,
                     comment='购物车归属用户ID（JWT，未认证 NULL 禁止写入）')
    result_id = Column(Integer, nullable=False, comment='源执行结果ID（test_results.id，引用不复制）')
    source_task_id = Column(Integer, nullable=False, comment='来源任务ID（溯源）')
    source_task_name = Column(String(255), nullable=True, comment='来源任务名称快照（加购时点）')
    source_case_id = Column(String(50), nullable=True, comment='来源用例ID（溯源）')
    source_device_id = Column(Integer, nullable=True, comment='来源设备ID（溯源）')
    source_api_id = Column(Integer, nullable=True, comment='来源API ID（溯源）')
    execution_status = Column(String(20), nullable=True, comment='加购时结果执行状态快照')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='加购时间')


class TaskCherryPickRelation(Base):
    """cherry-pick 容器任务 ↔ 源执行结果关联（引用方案 A，设计文档 §5.1）

    - merged/cherry-pick 容器分类判定：本表 cherry_pick_task_id 存在性
      （对齐 TaskMergeRelation.merged_task_id 对 merged 容器的判定，§5.4）
    - result 引用不复制：源结果重评估后容器视图随之更新
    - 溯源字段冗余快照（下单时点）：源任务被删后详情仍可标注缺失来源
    """
    __tablename__ = 'task_cherry_pick_relations'
    __table_args__ = (
        # 同一容器任务同一结果只引用一次
        UniqueConstraint('cherry_pick_task_id', 'result_id',
                         name='uq_cherry_rel_task_result'),
        Index('idx_cherry_rel_container', 'cherry_pick_task_id'),
        Index('idx_cherry_rel_source_task', 'source_task_id'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    cherry_pick_task_id = Column(Integer, ForeignKey('test_tasks.id'), nullable=False,
                                 comment='cherry-pick 容器任务ID')
    result_id = Column(Integer, nullable=False, comment='引用的源执行结果ID（test_results.id）')
    source_task_id = Column(Integer, nullable=False, comment='来源任务ID（溯源快照）')
    source_task_name = Column(String(255), nullable=True, comment='来源任务名称快照（下单时点）')
    source_case_id = Column(String(50), nullable=True, comment='来源用例ID（溯源快照）')
    source_device_id = Column(Integer, nullable=True, comment='来源设备ID（溯源快照）')
    source_api_id = Column(Integer, nullable=True, comment='来源API ID（溯源快照）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='下单操作人ID（JWT，INT-141 口径）')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='下单时间')


class CherryPickSet(Base):
    """挑选集（可复用的命名快照，另存/恢复两向，设计文档 §3 购物车口径）

    同名挑选集允许重复保存（设计文档 §10 异常处理）。
    """
    __tablename__ = 'cherry_pick_sets'
    __table_args__ = (
        Index('idx_cherry_set_user', 'user_id'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(BigInteger, nullable=False, index=True,
                     comment='挑选集归属用户ID（JWT，未认证 NULL 禁止写入）')
    name = Column(String(255), nullable=False, comment='挑选集名称')
    description = Column(Text, nullable=True, comment='挑选集描述')
    created_by_user_id = Column(BigInteger, nullable=True, comment='创建者用户ID（JWT）')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')


class CherryPickSetItem(Base):
    """挑选集条目（挑选集内容 = 结果引用集合，与购物车条目同构）"""
    __tablename__ = 'cherry_pick_set_items'
    __table_args__ = (
        UniqueConstraint('set_id', 'result_id', name='uq_cherry_set_item_result'),
        Index('idx_cherry_set_item_set', 'set_id'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    set_id = Column(_PK_BIGINT, ForeignKey('cherry_pick_sets.id'), nullable=False,
                    comment='所属挑选集ID')
    result_id = Column(Integer, nullable=False, comment='源执行结果ID（test_results.id，引用不复制）')
    source_task_id = Column(Integer, nullable=False, comment='来源任务ID（溯源）')
    source_task_name = Column(String(255), nullable=True, comment='来源任务名称快照（另存时点）')
    source_case_id = Column(String(50), nullable=True, comment='来源用例ID（溯源）')
    source_device_id = Column(Integer, nullable=True, comment='来源设备ID（溯源）')
    source_api_id = Column(Integer, nullable=True, comment='来源API ID（溯源）')
    execution_status = Column(String(20), nullable=True, comment='另存时结果执行状态快照')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='加入挑选集时间')
