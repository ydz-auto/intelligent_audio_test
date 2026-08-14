# -*- coding: utf-8 -*-
"""算法分组/算法定义领域仓储 — 返回领域实体（Aggregate），做 PO ↔ Entity 显式转换。

与 task_service/infrastructure/persistence/algorithm_repository.py 的区别：
- task_service 版本: 旧式仓储，返回 PO（ORM 对象），供 CRUD handler 用
- algorithm_service 版本（本文件）: 新式 DDD 仓储，返回领域聚合根，
  供领域服务用，隔离领域层与 ORM

PO ↔ Entity 转换规则：
- AlgorithmGroup PO → AlgorithmGroupAggregate 聚合根
- AlgorithmDefinition PO → AlgorithmDefinitionAggregate 聚合根
  （含 device_params / api_params / dimension_relations 子实体）
- AlgorithmDeviceParam / AlgorithmApiParam / AlgorithmReferenceParam PO
  → AlgorithmParamEntity（通过 param_kind 区分类别）

字段映射注意事项：
- AlgorithmGroup PO 无 algorithm_type 列，实体该字段加载为 None
- AlgorithmDefinition PO.type ↔ Entity.algorithm_type
- AlgorithmDefinition PO.status（'online'/'offline'）↔ AlgorithmStatus 枚举
  （active→online / deprecated→offline / draft→draft）
- AlgorithmDefinition PO 无 version 列，实体使用默认 '1.0.0'
- 参数 PO 通过 algorithm_type 关联，Entity 用 definition_id；
  转换时由 _definition_po_to_entity 传入聚合根 id 回填
- AlgorithmDefinition PO 无 reference_params 关系，实体该列表加载为空
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from shared.models.database import get_db_session
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmGroup as AlgorithmGroupPO,
    AlgorithmDefinition as AlgorithmDefinitionPO,
    AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    AlgorithmApiParam as AlgorithmApiParamPO,
    AlgorithmReferenceParam as AlgorithmReferenceParamPO,
    AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
)
from algorithm_service.domain.entities.algorithm_group import AlgorithmGroupAggregate
from algorithm_service.domain.entities.algorithm_definition import (
    AlgorithmDefinitionAggregate,
    AlgorithmStatus,
)
from algorithm_service.domain.entities.algorithm_param import (
    AlgorithmParamEntity,
    AlgorithmDimensionRelationEntity,
)
from algorithm_service.domain.repositories.algorithm_repositories import (
    IAlgorithmGroupRepository,
    IAlgorithmDefinitionRepository,
    IAlgorithmDefinitionQueryRepository,
    IAlgorithmGroupQueryRepository,
    IDeviceParamRepository,
    IDimensionParamRepository,
    IDimensionRelationQueryRepository,
    IParamMappingQueryRepository,
)


# ========== 辅助函数 ==========

def _parse_json_value(raw):
    """解析 PO 中 JSON 文本字段为 Python 对象（空值返回 None）。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _status_from_po(po_status: Optional[str]) -> AlgorithmStatus:
    """PO status 字符串 → AlgorithmStatus 枚举。

    兼容历史数据：online → active，offline → deprecated，draft → draft。
    """
    if po_status == 'online':
        return AlgorithmStatus.ACTIVE
    if po_status == 'offline':
        return AlgorithmStatus.DEPRECATED
    if po_status == 'draft':
        return AlgorithmStatus.DRAFT
    # 容错：未知值按草稿处理
    return AlgorithmStatus.DRAFT


def _status_to_po_str(status: AlgorithmStatus) -> str:
    """AlgorithmStatus 枚举 → PO status 字符串（写回 PO）。"""
    if status == AlgorithmStatus.ACTIVE:
        return 'online'
    if status == AlgorithmStatus.DEPRECATED:
        return 'offline'
    return 'draft'


# ========== PO → Entity 转换 ==========

def _group_po_to_entity(po: AlgorithmGroupPO) -> AlgorithmGroupAggregate:
    """AlgorithmGroup PO → AlgorithmGroupAggregate 聚合根。

    说明：PO 表 algorithm_groups 无 algorithm_type 列，
    该字段在实体上加载为 None（分组本身不持有算法类型，
    由其下算法定义的 algorithm_type 间接关联）。
    """
    return AlgorithmGroupAggregate(
        id=po.id,
        name=po.name,
        description=po.description,
        algorithm_type=None,
        deleted=po.deleted or False,
    )


def _param_po_to_entity(po, definition_id: int = 0) -> AlgorithmParamEntity:
    """算法参数 PO → AlgorithmParamEntity 实体。

    兼容三类参数 PO（通过 isinstance 区分）：
    - AlgorithmDeviceParam: param_code / required / ui_order / default_value
    - AlgorithmApiParam:    param_code / required / ui_order / default_value
    - AlgorithmReferenceParam: code（无 required / ui_order / default_value 列）

    通过 param_kind 标识参数类别，供领域层区分来源。
    """
    if isinstance(po, AlgorithmApiParamPO):
        # API 参数
        param_kind = 'api'
        param_name = po.param_code
        is_required = po.required or False
        sort_order = po.ui_order or 0
        default_value = _parse_json_value(po.default_value)
    elif isinstance(po, AlgorithmReferenceParamPO):
        # 参考参数（字段结构与 device/api 不同）
        param_kind = 'reference'
        param_name = po.code
        is_required = False  # reference 参数无 required 列
        sort_order = 0       # reference 参数无 ui_order 列
        default_value = None
    else:
        # 设备参数（默认分支）
        param_kind = 'device'
        param_name = po.param_code
        is_required = po.required or False
        sort_order = po.ui_order or 0
        default_value = _parse_json_value(po.default_value)

    return AlgorithmParamEntity(
        id=po.id,
        definition_id=definition_id,
        param_name=param_name or '',
        param_type=po.param_type,
        default_value=default_value,
        is_required=is_required,
        sort_order=sort_order,
        param_kind=param_kind,
    )


def _definition_po_to_entity(po: AlgorithmDefinitionPO) -> AlgorithmDefinitionAggregate:
    """AlgorithmDefinition PO → AlgorithmDefinitionAggregate 聚合根。

    聚合内加载未删除的子实体：
    - device_params: 设备参数列表
    - api_params: API 参数列表
    - dimension_relations: 算法-维度关联列表
    - reference_params: PO 无直接 relationship，加载为空（如需可单独查询）
    """
    # 设备参数：过滤已删除项，回填 definition_id
    device_params = [
        _param_po_to_entity(p, definition_id=po.id)
        for p in (po.device_params or [])
        if not getattr(p, 'deleted', False)
    ]
    # API 参数：同上
    api_params = [
        _param_po_to_entity(p, definition_id=po.id)
        for p in (po.api_params or [])
        if not getattr(p, 'deleted', False)
    ]
    # 算法-维度关联：PO.is_default → Entity.mapping_type
    dimension_relations = [
        AlgorithmDimensionRelationEntity(
            id=r.id,
            definition_id=po.id,
            dimension_id=r.dimension_id,
            mapping_type='default' if r.is_default else 'normal',
        )
        for r in (po.dimension_relations or [])
        if not getattr(r, 'deleted', False)
    ]

    return AlgorithmDefinitionAggregate(
        id=po.id,
        group_id=po.group_id,
        name=po.name,
        algorithm_type=po.type,
        description=po.description,
        version='1.0.0',  # PO 无 version 列，使用实体默认值
        status=_status_from_po(po.status),
        device_params=device_params,
        api_params=api_params,
        reference_params=[],  # PO 无直接关联关系，单独加载
        dimension_relations=dimension_relations,
        deleted=po.deleted or False,
    )


# ========== Entity → PO 字段写回 ==========

def _apply_group_to_po(aggregate: AlgorithmGroupAggregate, po: AlgorithmGroupPO) -> None:
    """将 AlgorithmGroupAggregate 可写字段映射回 AlgorithmGroup PO。

    说明：PO 表无 algorithm_type 列，不写回该字段。
    只更新可变字段，不覆盖 id / created_at 等不可变元数据。
    """
    po.name = aggregate.name
    po.description = aggregate.description
    po.deleted = aggregate.deleted
    po.updated_at = datetime.now()


def _apply_definition_to_po(aggregate: AlgorithmDefinitionAggregate, po: AlgorithmDefinitionPO) -> None:
    """将 AlgorithmDefinitionAggregate 可写字段映射回 AlgorithmDefinition PO。

    说明：
    - PO 无 version 列，不写回该字段
    - status 做 AlgorithmStatus → PO 字符串映射
      （active→online / deprecated→offline / draft→draft）
    - 子实体（device_params / api_params / dimension_relations）的变更
      由调用方通过相应子仓储维护，本方法只同步聚合根自身字段
    """
    po.type = aggregate.algorithm_type
    po.name = aggregate.name
    po.group_id = aggregate.group_id
    po.description = aggregate.description
    po.status = _status_to_po_str(aggregate.status)
    po.deleted = aggregate.deleted
    po.updated_at = datetime.now()


# ========== Repository 类 ==========

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


# ========== dict 查询扩展（供 handler 复用，避免直连 PO） ==========

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


class DeviceParamRepository(IDeviceParamRepository):
    """设备参数仓储（ACL 风格，返回 dict）。

    供 AlgorithmParamCommandHandler.handle_create_import_device_param 复用，
    避免 handler 直连 PO。
    """

    def create_import_device_param(self, data: dict) -> dict:
        """导入场景创建设备参数（仅 add，不 flush/commit）。

        字段映射：code → param_code, name → param_name, type → param_type
        """
        session = get_db_session()
        po = AlgorithmDeviceParamPO(
            algorithm_type=data.get("algorithm_type"),
            param_code=data.get("code"),
            param_name=data.get("name"),
            label=data.get("label"),
            param_type=data.get("type") or "text",
            direction="input",
            required=data.get("required") or False,
            default_value=data.get("default_value"),
            ui_order=data.get("ui_order") or 0,
            hidden=data.get("hidden") or False,
        )
        session.add(po)
        return {"added": True}


class DimensionParamRepository(IDimensionParamRepository):
    """评估维度参数仓储（ACL 风格，返回 dict）。

    供 AlgorithmParamQueryHandler.handle_list_dimension_params 复用，
    避免 handler 直连 EvaluationDimensionParam PO。
    """

    def list_by_dimension(self, dimension_id: int) -> List[dict]:
        """查询评估维度的参数列表（按 ui_order 排序）。"""
        from algorithm_service.infrastructure.persistence.models import (
            EvaluationDimensionParam as EvaluationDimensionParamPO,
        )
        session = get_db_session()
        items = session.query(EvaluationDimensionParamPO).filter_by(
            dimension_id=int(dimension_id), deleted=False
        ).order_by(EvaluationDimensionParamPO.ui_order).all()
        return [_po_to_dict(po) for po in items]

    def list_with_code_name(self, dimension_id: int) -> List[dict]:
        """查询评估维度参数列表，附加 code/name 字段（供 servicer GetDimensionParams）。"""
        from algorithm_service.infrastructure.persistence.models import (
            EvaluationDimensionParam as EvaluationDimensionParamPO,
        )
        session = get_db_session()
        items = session.query(EvaluationDimensionParamPO).filter_by(
            dimension_id=int(dimension_id), deleted=False
        ).order_by(EvaluationDimensionParamPO.ui_order).all()
        result = []
        for p in items:
            d = _po_to_dict(p)
            d["code"] = p.param_code
            d["name"] = p.param_name
            result.append(d)
        return result

    def create(self, data: dict) -> dict:
        """创建评估维度参数。"""
        from algorithm_service.infrastructure.persistence.models import (
            EvaluationDimensionParam as EvaluationDimensionParamPO,
        )
        session = get_db_session()
        try:
            po = EvaluationDimensionParamPO(**data)
            session.add(po)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def delete_by_dimension_and_direction(self, dimension_id: int, param_direction: str) -> bool:
        """按 dimension_id + param_direction 物理删除评估维度参数。"""
        from algorithm_service.infrastructure.persistence.models import (
            EvaluationDimensionParam as EvaluationDimensionParamPO,
        )
        session = get_db_session()
        try:
            session.query(EvaluationDimensionParamPO).filter_by(
                dimension_id=int(dimension_id),
                param_direction=param_direction,
            ).delete()
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

    def find_audio_dimension_ids(self, dimension_ids: list) -> list:
        """查询需要音频文件参数的维度 ID 集合。"""
        from algorithm_service.infrastructure.persistence.models import (
            EvaluationDimensionParam as EvaluationDimensionParamPO,
        )
        if not dimension_ids:
            return []
        session = get_db_session()
        audio_params = session.query(EvaluationDimensionParamPO).filter(
            EvaluationDimensionParamPO.dimension_id.in_(dimension_ids),
            EvaluationDimensionParamPO.field_type == "audio",
            EvaluationDimensionParamPO.param_direction == "input",
            EvaluationDimensionParamPO.deleted == False,  # noqa: E712
        ).all()
        return list({p.dimension_id for p in audio_params})


class DimensionRelationQueryRepository(IDimensionRelationQueryRepository):
    """维度关联查询仓储（返回 dict，ACL 风格）。

    供 servicer 复用，避免直连 AlgorithmDimensionRelation PO。
    """

    def list_by_dimension(self, dimension_id: int) -> List[dict]:
        """按 dimension_id 查询未删除的算法-维度关联列表。"""
        session = get_db_session()
        items = session.query(AlgorithmDimensionRelationPO).filter_by(
            dimension_id=int(dimension_id), deleted=False
        ).all()
        return [_po_to_dict(po) for po in items]

    def list_by_algorithm_definition(self, definition_id: int) -> List[dict]:
        """按 algorithm definition_id 查询未删除的算法-维度关联列表。"""
        session = get_db_session()
        # definition_id → algorithm type
        def_po = session.query(AlgorithmDefinitionPO).filter_by(
            id=int(definition_id), deleted=False
        ).first()
        if not def_po:
            return []
        items = session.query(AlgorithmDimensionRelationPO).filter_by(
            algorithm_type=def_po.type, deleted=False
        ).all()
        return [_po_to_dict(po) for po in items]

    def delete_by_dimension(self, dimension_id: int) -> bool:
        """按 dimension_id 物理删除所有算法-维度关联。"""
        session = get_db_session()
        try:
            session.query(AlgorithmDimensionRelationPO).filter_by(
                dimension_id=int(dimension_id)
            ).delete()
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise

    def sync_by_dimension(self, dimension_id: int, data: list) -> bool:
        """按 dimension_id 同步算法-维度关联（软删旧的活跃记录再插入新的）。"""
        session = get_db_session()
        try:
            session.query(AlgorithmDimensionRelationPO).filter_by(
                dimension_id=dimension_id,
                deleted=False,
            ).update({'deleted': True})
            for item in data:
                rel = AlgorithmDimensionRelationPO(
                    algorithm_type=item.get("algorithm_type"),
                    dimension_id=dimension_id,
                    is_default=item.get("is_default", False),
                    weight=item.get("weight", 1.0),
                )
                session.add(rel)
            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise


class ParamMappingQueryRepository(IParamMappingQueryRepository):
    """参数映射查询仓储（返回 dict，ACL 风格）。

    供 servicer 复用，避免直连 ParamMapping PO。
    """

    def list_by_dimension(self, dimension_id: int) -> List[dict]:
        """ABC 接口 — 委托到 list_for_dimension。"""
        return self.list_for_dimension(dimension_id)

    def list_for_dimension(self, dimension_id: int) -> List[dict]:
        """查询某维度所有 ParamMapping（含软删除项）。"""
        from algorithm_service.infrastructure.persistence.models import (
            ParamMapping as ParamMappingPO,
        )
        session = get_db_session()
        items = session.query(ParamMappingPO).filter_by(
            dimension_id=int(dimension_id),
            source="evaluation",
        ).all()
        return [_po_to_dict(po) for po in items]

    def sync_for_dimension(
        self, dimension_id: int, params: list, direction: str = "output",
        algorithm_type: str = "voice_llm",
    ) -> bool:
        """同步 ParamMapping：当评估维度的输入/输出字段变更时，
        自动为该维度创建/更新/删除对应的 ParamMapping 记录。
        """
        from algorithm_service.infrastructure.persistence.models import (
            ParamMapping as ParamMappingPO,
        )
        session = get_db_session()
        try:
            active_mappings = session.query(ParamMappingPO).filter_by(
                dimension_id=dimension_id,
                source="evaluation",
                deleted=False,
            ).all()
            active_map = {m.source_param: m for m in active_mappings}

            submitted_codes = set()

            for p in params:
                param_code = p.get("param_code", p.get("key", ""))
                if not param_code:
                    continue
                submitted_codes.add(param_code)

                if param_code in active_map:
                    m = active_map[param_code]
                    m.target_param = param_code
                    m.source_direction = direction
                else:
                    new_mapping = ParamMappingPO(
                        algorithm_type=p.get("algorithm_type", algorithm_type),
                        source="evaluation",
                        source_param=param_code,
                        source_direction=direction,
                        dimension_id=dimension_id,
                        target_param=param_code,
                        transform_type="none",
                    )
                    session.add(new_mapping)
                    active_map[param_code] = new_mapping

            for code, m in active_map.items():
                if code not in submitted_codes:
                    m.deleted = True

            session.flush()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise


# 模块级单例
algorithm_group_repository = AlgorithmGroupRepository()
algorithm_definition_repository = AlgorithmDefinitionRepository()
algorithm_definition_query_repository = AlgorithmDefinitionQueryRepository()
algorithm_group_query_repository = AlgorithmGroupQueryRepository()
device_param_repository = DeviceParamRepository()
dimension_param_repository = DimensionParamRepository()
dimension_relation_query_repository = DimensionRelationQueryRepository()
param_mapping_query_repository = ParamMappingQueryRepository()


# ========== 事务控制包装（供 servicer 委托，不直连 get_db_session） ==========

def commit_transaction():
    """提交当前 DB 事务。"""
    get_db_session().commit()


def rollback_transaction():
    """回滚当前 DB 事务。"""
    get_db_session().rollback()


def flush_transaction():
    """flush 当前 DB session。"""
    get_db_session().flush()
