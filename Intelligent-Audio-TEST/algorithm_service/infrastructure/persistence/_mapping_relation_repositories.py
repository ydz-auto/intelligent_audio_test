# -*- coding: utf-8 -*-
"""参数映射/维度关联仓储实现（MappingRepository / DimensionRelationRepository）。

从 param_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- MappingRepository: 参数映射仓储（ParamMapping PO）
- DimensionRelationRepository: 维度关联仓储（AlgorithmDimensionRelation PO）

遵循 ACL 模式：外部只看到 dict，不感知 ORM。
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from shared.models.database import get_db_session
from algorithm_service.infrastructure.persistence.models import (
    ParamMapping as ParamMappingPO,
    AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
)
from algorithm_service.domain.repositories.param_repositories import (
    IMappingRepository,
    IDimensionRelationRepository,
)
from algorithm_service.infrastructure.persistence._param_converters import (
    _po_to_dict,
)


# ========== MappingRepository ==========

class MappingRepository(IMappingRepository):
    """参数映射仓储实现（ParamMapping PO）。

    遵循 ACL 模式：外部只看到 dict，不感知 ORM。
    """

    def get_by_id(self, mapping_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的参数映射。"""
        session = get_db_session()
        po = session.query(ParamMappingPO).filter_by(
            id=mapping_id, deleted=False
        ).first()
        return _po_to_dict(po) if po is not None else None

    def list_by_algorithm(
        self,
        algorithm_type: str,
        source_type: Optional[str] = None,
        dimension_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """按算法查询参数映射列表（可按 source_type / dimension_id 过滤）。

        - algorithm_type 为空时返回全部未删除映射
        - source_type 过滤对应 PO.source 字段
        """
        session = get_db_session()
        query = session.query(ParamMappingPO).filter_by(deleted=False)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)
        if source_type:
            query = query.filter_by(source=source_type)
        if dimension_id is not None:
            query = query.filter_by(dimension_id=dimension_id)
        mappings = query.all()
        return [_po_to_dict(m) for m in mappings]

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建参数映射，返回新映射 dict。

        字段映射与 servicers.py CreateMapping 一致：
        - source ← data.source_type（servicer 传参为 source_type，PO 字段为 source）
        - source_param / source_direction / dimension_id / target_param / transform_type
        """
        session = get_db_session()
        try:
            po = ParamMappingPO(
                algorithm_type=data.get("algorithm_type"),
                source=data.get("source_type"),
                source_param=data.get("source_param"),
                source_direction=data.get("source_direction") or "output",
                dimension_id=data.get("dimension_id"),
                target_param=data.get("target_param"),
                transform_type=data.get("transform_type") or "none",
            )
            session.add(po)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def update_attrs(
        self, mapping_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新参数映射可写字段，返回更新后的 dict。

        字段映射与 servicers.py UpdateMapping 一致：
        - 显式处理 source / source_param / source_direction
          / dimension_id / target_param / transform_type
        """
        session = get_db_session()
        try:
            po = session.query(ParamMappingPO).filter_by(
                id=mapping_id, deleted=False
            ).first()
            if po is None:
                raise ValueError(
                    f"Param mapping id={mapping_id} 不存在，无法更新"
                )
            if fields.get("source") is not None:
                po.source = fields["source"]
            if fields.get("source_param") is not None:
                po.source_param = fields["source_param"]
            if fields.get("source_direction") is not None:
                po.source_direction = fields["source_direction"]
            if fields.get("dimension_id") is not None:
                po.dimension_id = fields["dimension_id"]
            if fields.get("target_param") is not None:
                po.target_param = fields["target_param"]
            if fields.get("transform_type") is not None:
                po.transform_type = fields["transform_type"]
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def soft_delete(self, mapping_id: int) -> bool:
        """按 ID 软删除参数映射，返回是否成功。"""
        session = get_db_session()
        try:
            po = session.query(ParamMappingPO).filter_by(
                id=mapping_id, deleted=False
            ).first()
            if po is None:
                return False
            po.deleted = True
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise


# ========== DimensionRelationRepository ==========

class DimensionRelationRepository(IDimensionRelationRepository):
    """维度关联仓储实现（AlgorithmDimensionRelation PO）。

    遵循 ACL 模式：外部只看到 dict，不感知 ORM。
    """

    def find(
        self, algorithm_type: str, dimension_id: int
    ) -> Optional[Dict[str, Any]]:
        """按 算法/维度 查找未删除的维度关联。"""
        session = get_db_session()
        po = session.query(AlgorithmDimensionRelationPO).filter_by(
            algorithm_type=algorithm_type,
            dimension_id=dimension_id,
            deleted=False,
        ).first()
        return _po_to_dict(po) if po is not None else None

    def get_by_id(self, relation_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取维度关联（含软删项）。

        与 servicers.py GetDimensionRelation 一致，使用 session.get，
        不过滤 deleted（可查询已软删项）。
        """
        session = get_db_session()
        po = session.get(AlgorithmDimensionRelationPO, relation_id)
        return _po_to_dict(po) if po is not None else None

    def list_by_algorithm(
        self, algorithm_type: str
    ) -> List[Dict[str, Any]]:
        """按算法查询未删除的维度关联列表。"""
        session = get_db_session()
        items = session.query(AlgorithmDimensionRelationPO).filter_by(
            algorithm_type=algorithm_type, deleted=False
        ).all()
        return [_po_to_dict(po) for po in items]

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建维度关联，返回新关联 dict。

        字段映射与 servicers.py CreateDimensionRelation 一致：
        - algorithm_type / dimension_id / is_default / weight
        """
        session = get_db_session()
        try:
            po = AlgorithmDimensionRelationPO(
                algorithm_type=data.get("algorithm_type"),
                dimension_id=data.get("dimension_id"),
                is_default=data.get("is_default"),
                weight=data.get("weight"),
            )
            session.add(po)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def update_attrs(
        self, relation_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新维度关联可写字段，返回更新后的 dict。

        字段映射与 servicers.py UpdateDimensionRelationAttrs 一致：
        - 显式处理 weight / is_default / dimension_id
        """
        session = get_db_session()
        try:
            po = session.query(AlgorithmDimensionRelationPO).filter_by(
                id=relation_id, deleted=False
            ).first()
            if po is None:
                raise ValueError(
                    f"Dimension relation id={relation_id} 不存在，无法更新"
                )
            if fields.get("weight") is not None:
                po.weight = fields["weight"]
            if fields.get("is_default") is not None:
                po.is_default = fields["is_default"]
            if fields.get("dimension_id") is not None:
                po.dimension_id = fields["dimension_id"]
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def soft_delete(self, relation_id: int) -> bool:
        """按 ID 软删除维度关联，返回是否成功。"""
        session = get_db_session()
        try:
            po = session.query(AlgorithmDimensionRelationPO).filter_by(
                id=relation_id, deleted=False
            ).first()
            if po is None:
                return False
            po.deleted = True
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

    def soft_delete_by_algorithm(self, algorithm_type: str) -> bool:
        """按算法批量软删除维度关联，返回是否成功。

        与 servicers.py SoftDeleteAlgorithmDimensionRelations 一致，
        使用 update({"deleted": True}) 批量更新（包含已软删项也无副作用）。
        """
        session = get_db_session()
        try:
            session.query(AlgorithmDimensionRelationPO).filter_by(
                algorithm_type=algorithm_type
            ).update({"deleted": True})
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
