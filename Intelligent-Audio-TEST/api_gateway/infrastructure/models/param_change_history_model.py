# -*- coding: utf-8 -*-
"""参数变更历史 PO（设备 / API 参数与映射的版本快照）。

归属：api_gateway（审计 / 运维上下文，表由迁移
``scripts/migrations/202611/add_param_change_history.py`` 建出）。

快照 payload 结构（只含该作用域的**覆盖行**，不含算法级默认与策略层）：

    {"params": [...], "mappings": [...]}

每行字段与写接口同口径（snake_case），回滚时可直接回灌。
"""
from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, JSON, String, func

from shared.models.database import Base, utc8now


class ParamChangeHistory(Base):
    """一条参数变更版本快照。"""

    __tablename__ = 'param_change_history'
    __table_args__ = (
        Index(
            'uq_param_change_history_version',
            'scope', 'scope_id', 'algorithm_type', 'version',
            unique=True,
        ),
        Index(
            'idx_param_change_history_scope',
            'scope', 'scope_id', 'algorithm_type', 'id',
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # device / api
    scope = Column(String(16), nullable=False, comment='作用域：device / api')
    scope_id = Column(Integer, nullable=False, comment='设备 ID 或 API 实例 ID')
    algorithm_type = Column(String(50), nullable=False, comment='算法类型')
    version = Column(Integer, nullable=False, comment='同作用域内自增版本号')
    # save / restore
    action = Column(String(16), nullable=False, default='save', comment='变更动作')
    payload = Column(JSON, nullable=False, default=dict, comment='覆盖行快照')
    operator = Column(String(100), nullable=True, comment='操作人')
    created_at = Column(
        DateTime, default=utc8now, server_default=func.now(),
        nullable=False, comment='创建时间',
    )
