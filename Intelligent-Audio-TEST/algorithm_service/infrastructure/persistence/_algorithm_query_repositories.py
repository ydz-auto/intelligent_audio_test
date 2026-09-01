# -*- coding: utf-8 -*-
"""算法 dict 查询仓储实现（ACL 风格）。

从 algorithm_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- AlgorithmDefinitionQueryRepository: 算法定义查询仓储（返回 dict）
- AlgorithmGroupQueryRepository: 算法分组查询仓储（返回 dict）

供 AlgorithmParamQueryHandler 复用，避免 handler 直连 PO。
"""
from __future__ import annotations

from typing import List, Optional

from shared.models.database import get_db_session
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmGroup as AlgorithmGroupPO,
    AlgorithmDefinition as AlgorithmDefinitionPO,
)
from algorithm_service.domain.repositories.algorithm_repositories import (
    IAlgorithmDefinitionQueryRepository,
    IAlgorithmGroupQueryRepository,
)


# ========== 辅助：PO → dict（供 handler/servicer 查询复用） ==========

def _po_to_dict(po) -> Optional[dict]:
    """将 PO 序列化为 dict（优先调用 PO.to_dict）。"""
    if po is None:
        return None
    if hasattr(po, "to_dict"):
        return po.to_dict()
    return {
        c.name: getattr(po, c.name, None)
        for c in po.__table__.columns
    }


# ========== dict 查询仓储（供 handler 复用，避免直连 PO） ==========

class AlgorithmDefinitionQueryRepository(IAlgorithmDefinitionQueryRepository):
    """算法定义查询仓储（返回 dict，ACL 风格）。

    供 AlgorithmParamQueryHandler 复用，避免 handler 直连 PO。
    """

    def list_definitions(
        self,
        status: Optional[str] = None,
        group_id: Optional[int] = None,
    ) -> List[dict]:
        """查询未删除的算法定义列表（按 display_order、id 排序）。"""
        session = get_db_session()
        q = session.query(AlgorithmDefinitionPO).filter_by(deleted=False)
        if status:
            q = q.filter_by(status=status)
        if group_id:
            q = q.filter_by(group_id=group_id)
        items = q.order_by(
            AlgorithmDefinitionPO.display_order, AlgorithmDefinitionPO.id
        ).all()
        return [_po_to_dict(po) for po in items]

    def list_online_definitions(self) -> List[dict]:
        """查询在线算法定义列表（按 display_order 排序）。"""
        session = get_db_session()
        items = session.query(AlgorithmDefinitionPO).filter_by(
            status="online", deleted=False
        ).order_by(AlgorithmDefinitionPO.display_order).all()
        return [_po_to_dict(po) for po in items]

    def find_by_type(self, algorithm_type: str) -> Optional[dict]:
        """按 type 查询未删除的算法定义，返回 dict 或 None。"""
        session = get_db_session()
        po = session.query(AlgorithmDefinitionPO).filter_by(
            type=algorithm_type, deleted=False
        ).first()
        return _po_to_dict(po) if po is not None else None

    def count_in_group(self, group_id: int) -> int:
        """统计分组下未删除的算法定义数量。"""
        session = get_db_session()
        return session.query(AlgorithmDefinitionPO).filter_by(
            group_id=group_id, deleted=False
        ).count()

    def list_for_bulk_delete(self, algorithm_types: list) -> List[dict]:
        """按 type 列表查询未删除的算法定义（供批量删除）。"""
        session = get_db_session()
        items = session.query(AlgorithmDefinitionPO).filter(
            AlgorithmDefinitionPO.type.in_(algorithm_types),
            AlgorithmDefinitionPO.deleted == False,  # noqa: E712
        ).all()
        return [_po_to_dict(po) for po in items]

    def bulk_soft_delete(self, algorithm_types: list) -> List[str]:
        """批量软删除算法定义，返回已删除的 type 列表。"""
        session = get_db_session()
        try:
            items = session.query(AlgorithmDefinitionPO).filter(
                AlgorithmDefinitionPO.type.in_(algorithm_types),
                AlgorithmDefinitionPO.deleted == False,  # noqa: E712
            ).all()
            for po in items:
                po.deleted = True
            session.flush()
            session.commit()
            return [po.type for po in items]
        except Exception:
            session.rollback()
            raise


class AlgorithmGroupQueryRepository(IAlgorithmGroupQueryRepository):
    """算法分组查询仓储（返回 dict，ACL 风格）。

    供 AlgorithmParamQueryHandler 复用，避免 handler 直连 PO。
    """

    def find_by_name(self, name: str) -> Optional[dict]:
        """按 name 查询未删除的算法分组，返回 dict 或 None。"""
        session = get_db_session()
        po = session.query(AlgorithmGroupPO).filter_by(
            name=name, deleted=False
        ).first()
        return _po_to_dict(po) if po is not None else None

    def get_by_id(self, group_id: int) -> Optional[dict]:
        """按 ID 查询未删除的算法分组，返回 dict 或 None。"""
        session = get_db_session()
        po = session.query(AlgorithmGroupPO).filter_by(
            id=group_id, deleted=False
        ).first()
        return _po_to_dict(po) if po is not None else None

    def list_all(self) -> List[dict]:
        """查询未删除的算法分组列表（按 display_order、id 排序）。"""
        session = get_db_session()
        items = session.query(AlgorithmGroupPO).filter_by(
            deleted=False
        ).order_by(
            AlgorithmGroupPO.display_order, AlgorithmGroupPO.id
        ).all()
        return [_po_to_dict(po) for po in items]

    def count_algorithms_in_group(self, group_id: int) -> int:
        """统计指定分组下未删除的算法定义数量。

        先确认分组存在，再统计其下算法定义数量。
        分组不存在时抛出 ValueError。
        """
        session = get_db_session()
        group = session.get(AlgorithmGroupPO, group_id)
        if group is None:
            raise ValueError(
                f"Algorithm group id={group_id} 不存在"
            )
        return group.algorithms.filter_by(deleted=False).count()
