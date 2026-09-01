# -*- coding: utf-8 -*-
"""算法聚合根仓储实现（分组/定义）。

从 algorithm_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- AlgorithmGroupRepository: 算法分组聚合根仓储（返回 AlgorithmGroupAggregate）
- AlgorithmDefinitionRepository: 算法定义聚合根仓储（返回 AlgorithmDefinitionAggregate）

遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
通过 shared.models.database.get_db_session() 的 scoped_session 访问数据。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from shared.models.database import get_db_session
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmGroup as AlgorithmGroupPO,
    AlgorithmDefinition as AlgorithmDefinitionPO,
)
from algorithm_service.domain.entities.algorithm_group import AlgorithmGroupAggregate
from algorithm_service.domain.entities.algorithm_definition import AlgorithmDefinitionAggregate
from algorithm_service.domain.repositories.algorithm_repositories import (
    IAlgorithmGroupRepository,
    IAlgorithmDefinitionRepository,
)
from algorithm_service.infrastructure.persistence._algorithm_converters import (
    _group_po_to_entity,
    _apply_group_to_po,
    _definition_po_to_entity,
    _apply_definition_to_po,
    _status_to_po_str,
)


class AlgorithmGroupRepository(IAlgorithmGroupRepository):
    """算法分组聚合根仓储。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    通过 shared.models.database.get_db_session() 的 scoped_session 访问数据。
    """

    def get_by_id(self, group_id: int) -> Optional[AlgorithmGroupAggregate]:
        """按 ID 加载未删除的算法分组聚合根。"""
        session = get_db_session()
        po = session.query(AlgorithmGroupPO).filter_by(
            id=group_id, deleted=False
        ).first()
        if po is None:
            return None
        return _group_po_to_entity(po)

    def get_all(self) -> List[AlgorithmGroupAggregate]:
        """查询全部未删除的算法分组聚合根（按 display_order、id 排序）。"""
        session = get_db_session()
        pos = session.query(AlgorithmGroupPO).filter_by(deleted=False).order_by(
            AlgorithmGroupPO.display_order, AlgorithmGroupPO.id
        ).all()
        return [_group_po_to_entity(po) for po in pos]

    def save(self, aggregate: AlgorithmGroupAggregate) -> None:
        """持久化算法分组聚合根变更（含 commit）。

        仅更新已存在的聚合根，若不存在则抛出 ValueError。
        """
        session = get_db_session()
        try:
            po = session.get(AlgorithmGroupPO, aggregate.id)
            if po is None:
                raise ValueError(
                    f"AlgorithmGroup id={aggregate.id} 不存在，无法 save"
                )
            _apply_group_to_po(aggregate, po)
            session.commit()
        except Exception:
            session.rollback()
            raise

    def add(self, aggregate: AlgorithmGroupAggregate) -> int:
        """新增算法分组聚合根，返回新 ID。

        新增后将生成的 ID 回写聚合根。
        """
        session = get_db_session()
        try:
            po = AlgorithmGroupPO(
                name=aggregate.name,
                description=aggregate.description,
                deleted=aggregate.deleted,
            )
            session.add(po)
            session.flush()
            new_id = po.id
            session.commit()
            # 将生成的 ID 回写聚合根
            aggregate.id = new_id
            return new_id
        except Exception:
            session.rollback()
            raise

    def soft_delete(self, group_id: int) -> bool:
        """软删除算法分组，返回是否成功。"""
        session = get_db_session()
        try:
            po = session.get(AlgorithmGroupPO, group_id)
            if po is None:
                return False
            po.deleted = True
            po.updated_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise


class AlgorithmDefinitionRepository(IAlgorithmDefinitionRepository):
    """算法定义聚合根仓储。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    通过 shared.models.database.get_db_session() 的 scoped_session 访问数据。
    """

    def get_by_id(self, definition_id: int) -> Optional[AlgorithmDefinitionAggregate]:
        """按 ID 加载未删除的算法定义聚合根（含聚合内子实体）。"""
        session = get_db_session()
        po = session.query(AlgorithmDefinitionPO).filter_by(
            id=definition_id, deleted=False
        ).first()
        if po is None:
            return None
        return _definition_po_to_entity(po)

    def get_by_group(self, group_id: int) -> List[AlgorithmDefinitionAggregate]:
        """按分组 ID 加载未删除的算法定义聚合根列表。"""
        session = get_db_session()
        pos = session.query(AlgorithmDefinitionPO).filter_by(
            group_id=group_id, deleted=False
        ).order_by(
            AlgorithmDefinitionPO.display_order, AlgorithmDefinitionPO.id
        ).all()
        return [_definition_po_to_entity(po) for po in pos]

    def get_by_type(self, algorithm_type: str) -> Optional[AlgorithmDefinitionAggregate]:
        """按算法类型代码加载未删除的算法定义聚合根。"""
        session = get_db_session()
        po = session.query(AlgorithmDefinitionPO).filter_by(
            type=algorithm_type, deleted=False
        ).first()
        if po is None:
            return None
        return _definition_po_to_entity(po)

    def list_all_active(self) -> List[AlgorithmDefinitionAggregate]:
        """查询全部上线状态（active / online）的算法定义聚合根。"""
        session = get_db_session()
        pos = session.query(AlgorithmDefinitionPO).filter_by(
            status='online', deleted=False
        ).order_by(
            AlgorithmDefinitionPO.display_order, AlgorithmDefinitionPO.id
        ).all()
        return [_definition_po_to_entity(po) for po in pos]

    def save(self, aggregate: AlgorithmDefinitionAggregate) -> None:
        """持久化算法定义聚合根变更（含 commit）。

        仅同步聚合根自身字段，子实体变更需由调用方通过子仓储维护。
        """
        session = get_db_session()
        try:
            po = session.get(AlgorithmDefinitionPO, aggregate.id)
            if po is None:
                raise ValueError(
                    f"AlgorithmDefinition id={aggregate.id} 不存在，无法 save"
                )
            _apply_definition_to_po(aggregate, po)
            session.commit()
        except Exception:
            session.rollback()
            raise

    def add(self, aggregate: AlgorithmDefinitionAggregate) -> int:
        """新增算法定义聚合根，返回新 ID。

        新增后将生成的 ID 回写聚合根。
        """
        session = get_db_session()
        try:
            po = AlgorithmDefinitionPO(
                type=aggregate.algorithm_type,
                name=aggregate.name,
                group_id=aggregate.group_id,
                description=aggregate.description,
                status=_status_to_po_str(aggregate.status),
                deleted=aggregate.deleted,
            )
            session.add(po)
            session.flush()
            new_id = po.id
            session.commit()
            # 将生成的 ID 回写聚合根
            aggregate.id = new_id
            return new_id
        except Exception:
            session.rollback()
            raise

    def soft_delete(self, definition_id: int) -> bool:
        """软删除算法定义，返回是否成功。"""
        session = get_db_session()
        try:
            po = session.get(AlgorithmDefinitionPO, definition_id)
            if po is None:
                return False
            po.deleted = True
            po.updated_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
