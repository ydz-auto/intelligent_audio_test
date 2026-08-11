# -*- coding: utf-8 -*-
"""算法参数/映射/维度关联仓储实现 — 返回 dict（ACL DTO），做 PO ↔ dict 转换。

归属：algorithm_service.infrastructure.persistence

与 algorithm_repository.py 的区别：
- algorithm_repository.py: 旧式 DDD 仓储，返回领域聚合根（Aggregate），
  供 group/definition 领域服务用，做 PO ↔ Entity 显式转换。
- param_repository.py（本文件）: ACL 仓储，返回 dict，
  供 param/mapping/relation 命令/查询 handler 用，隔离 PO 与应用层。

PO ↔ dict 转换规则：
- AlgorithmDeviceParam / AlgorithmApiParam PO → dict（含 default_value/validation JSON 解析）
- AlgorithmReferenceParam PO → dict（type 字段重命名）
- CaseAlgorithmParam PO → dict（含 scope/min/max/step/unit 等扩展字段）
- ParamMapping PO → dict（source/source_param/target_param/transform_type）
- AlgorithmDimensionRelation PO → dict（is_default/weight）
- 所有 dict 通过 _po_to_dict(po) 生成：优先调用 po.to_dict()，
  否则回退到遍历 __table__.columns（与 servicers.py 中的 _po_to_dict 一致）

字段映射注意事项：
- AlgorithmReferenceParam PO.param_type → dict.type（to_dict 已映射）
- ParamMapping PO.source ← data.source_type（servicer 用 source_type 传参，
  PO 字段名为 source，映射时做转换）
- AlgorithmDimensionRelation 软删除按 algorithm_type 批量 update deleted=True
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any

from shared.models.database import get_db_session
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    AlgorithmApiParam as AlgorithmApiParamPO,
    AlgorithmReferenceParam as AlgorithmReferenceParamPO,
    CaseAlgorithmParam as CaseAlgorithmParamPO,
    ParamMapping as ParamMappingPO,
    AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
)
from algorithm_service.domain.repositories.param_repositories import (
    IAlgorithmParamRepository,
    ICaseParamRepository,
    IReferenceParamRepository,
    IMappingRepository,
    IDimensionRelationRepository,
)


# ========== 辅助函数 ==========

def _po_to_dict(po) -> Dict[str, Any]:
    """将 PO 序列化为 dict（优先调用 PO.to_dict）。

    与 servicers.py 中的 _po_to_dict 行为一致：
    - 优先调用 po.to_dict()
    - 否则遍历 __table__.columns 生成 {name: value}
    """
    if po is None:
        return None  # type: ignore[return-value]
    if hasattr(po, "to_dict"):
        return po.to_dict()
    return {
        c.name: getattr(po, c.name, None)
        for c in po.__table__.columns
    }


def _resolve_param_model(param_type_source: str):
    """根据 param_type_source 解析目标 PO 类。

    - "api" → AlgorithmApiParamPO
    - 其他（默认 device / 未指定）→ AlgorithmDeviceParamPO
    """
    if param_type_source == "api":
        return AlgorithmApiParamPO
    return AlgorithmDeviceParamPO


# ========== AlgorithmParamRepository ==========

class AlgorithmParamRepository(IAlgorithmParamRepository):
    """设备/API 参数仓储实现。

    覆盖 AlgorithmDeviceParam / AlgorithmApiParam 两张结构相同的表，
    通过 param_type_source（device/api）区分目标 PO。
    遵循 ACL 模式：外部只看到 dict，不感知 ORM。
    通过 shared.models.database.get_db_session() 的 scoped_session 访问数据。
    """

    def find_by_code(
        self,
        algorithm_type: str,
        param_code: str,
        direction: str,
        param_type_source: str,
    ) -> Optional[Dict[str, Any]]:
        """按 算法/参数代码/方向 查找未删除的设备或 API 参数。"""
        session = get_db_session()
        model = _resolve_param_model(param_type_source)
        po = session.query(model).filter_by(
            algorithm_type=algorithm_type,
            param_code=param_code,
            direction=direction,
            deleted=False,
        ).first()
        return _po_to_dict(po) if po is not None else None

    def get_by_id(
        self, param_id: int, param_type_source: str
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的设备或 API 参数。

        当 param_type_source 指定时，只查对应 PO；
        当未指定（空值）时，先查 device 再查 api（兼容旧 servicer 行为）。
        """
        session = get_db_session()
        if param_type_source:
            model = _resolve_param_model(param_type_source)
            po = session.query(model).filter_by(
                id=param_id, deleted=False
            ).first()
            return _po_to_dict(po) if po is not None else None
        # 未指定来源：先查 device 再查 api
        po = session.query(AlgorithmDeviceParamPO).filter_by(
            id=param_id, deleted=False
        ).first()
        if po is None:
            po = session.query(AlgorithmApiParamPO).filter_by(
                id=param_id, deleted=False
            ).first()
        return _po_to_dict(po) if po is not None else None

    def list_by_algorithm(
        self, algorithm_type: str, param_type: str
    ) -> List[Dict[str, Any]]:
        """按算法类型查询参数列表（param_type 为 device/api）。

        - algorithm_type 为空时返回全部未删除参数
        - 按 ui_order 排序
        """
        session = get_db_session()
        model = _resolve_param_model(param_type)
        query = session.query(model).filter_by(deleted=False)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)
        params = query.order_by(model.ui_order).all()
        return [_po_to_dict(p) for p in params]

    def create(
        self, data: Dict[str, Any], param_type_source: str
    ) -> Dict[str, Any]:
        """创建设备或 API 参数，返回新参数 dict。

        字段映射与 servicers.py CreateParam 一致：
        - param_code / param_name / label / param_type / direction / required
        - default_value / validation_rules / help_text / ui_order / hidden
        """
        session = get_db_session()
        try:
            model = _resolve_param_model(param_type_source)
            po = model(
                algorithm_type=data.get("algorithm_type"),
                param_code=data.get("param_code"),
                param_name=data.get("param_name"),
                label=data.get("label"),
                param_type=data.get("param_type") or "text",
                direction=data.get("direction") or "input",
                required=data.get("required") or False,
                default_value=data.get("default_value"),
                validation_rules=data.get("validation_rules"),
                help_text=data.get("help_text"),
                ui_order=data.get("ui_order") or 0,
                hidden=data.get("hidden") or False,
            )
            session.add(po)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def update_attrs(
        self, param_id: int, fields: Dict[str, Any], param_type_source: str
    ) -> Dict[str, Any]:
        """按 ID 更新设备或 API 参数可写字段，返回更新后的 dict。

        - 仅更新 fields 中非 None 的字段
        - 当 param_type_source 指定时只查对应 PO；未指定时先查 device 再查 api
        """
        session = get_db_session()
        try:
            po = None
            if param_type_source:
                model = _resolve_param_model(param_type_source)
                po = session.query(model).filter_by(
                    id=param_id, deleted=False
                ).first()
            else:
                po = session.query(AlgorithmDeviceParamPO).filter_by(
                    id=param_id, deleted=False
                ).first()
                if po is None:
                    po = session.query(AlgorithmApiParamPO).filter_by(
                        id=param_id, deleted=False
                    ).first()
            if po is None:
                raise ValueError(f"Parameter id={param_id} 不存在，无法更新")
            for field, value in fields.items():
                if value is not None:
                    setattr(po, field, value)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def soft_delete(
        self, param_id: int, param_type_source: str
    ) -> bool:
        """按 ID 软删除设备或 API 参数，返回是否成功。"""
        session = get_db_session()
        try:
            po = None
            if param_type_source:
                model = _resolve_param_model(param_type_source)
                po = session.query(model).filter_by(
                    id=param_id, deleted=False
                ).first()
            else:
                po = session.query(AlgorithmDeviceParamPO).filter_by(
                    id=param_id, deleted=False
                ).first()
                if po is None:
                    po = session.query(AlgorithmApiParamPO).filter_by(
                        id=param_id, deleted=False
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


# ========== CaseParamRepository ==========

class CaseParamRepository(ICaseParamRepository):
    """用例参数仓储实现（CaseAlgorithmParam PO）。

    遵循 ACL 模式：外部只看到 dict，不感知 ORM。
    """

    def find_by_code(
        self,
        algorithm_type: str,
        param_code: str,
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """按 算法/参数代码 查找用例参数（可包含软删项）。"""
        session = get_db_session()
        query = session.query(CaseAlgorithmParamPO).filter_by(
            algorithm_type=algorithm_type,
            param_code=param_code,
        )
        if not bool(include_deleted):
            query = query.filter_by(deleted=False)
        po = query.first()
        return _po_to_dict(po) if po is not None else None

    def get_by_id(self, param_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的用例参数。"""
        session = get_db_session()
        po = session.query(CaseAlgorithmParamPO).filter_by(
            id=param_id, deleted=False
        ).first()
        return _po_to_dict(po) if po is not None else None

    def list_by_algorithm(
        self, algorithm_type: str, scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """按算法查询用例参数列表（可按 scope 过滤）。

        - algorithm_type 为空时返回全部未删除用例参数
        - 按 ui_order 排序
        """
        session = get_db_session()
        query = session.query(CaseAlgorithmParamPO).filter_by(deleted=False)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)
        if scope:
            query = query.filter_by(scope=scope)
        params = query.order_by(CaseAlgorithmParamPO.ui_order).all()
        return [_po_to_dict(p) for p in params]

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建用例参数，返回新参数 dict。

        字段映射与 servicers.py CreateCaseParam 一致：
        - param_code / param_name / label / param_type / required
        - default_value / help_text / ui_order / hidden / scope
        - min_value / max_value / step / unit
        """
        session = get_db_session()
        try:
            po = CaseAlgorithmParamPO(
                algorithm_type=data.get("algorithm_type"),
                param_code=data.get("param_code"),
                param_name=data.get("param_name"),
                label=data.get("label"),
                param_type=data.get("param_type") or "text",
                required=data.get("required") or False,
                default_value=data.get("default_value"),
                help_text=data.get("help_text"),
                ui_order=data.get("ui_order") or 0,
                hidden=data.get("hidden") or False,
                scope=data.get("scope") or "common",
                min_value=data.get("min_value"),
                max_value=data.get("max_value"),
                step=data.get("step"),
                unit=data.get("unit"),
            )
            session.add(po)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def update_attrs(
        self, param_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新用例参数可写字段，返回更新后的 dict。

        - 仅更新 fields 中非 None 的字段
        """
        session = get_db_session()
        try:
            po = session.query(CaseAlgorithmParamPO).filter_by(
                id=param_id, deleted=False
            ).first()
            if po is None:
                raise ValueError(
                    f"Case parameter id={param_id} 不存在，无法更新"
                )
            for field, value in fields.items():
                if value is not None:
                    setattr(po, field, value)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def soft_delete(self, param_id: int) -> bool:
        """按 ID 软删除用例参数，返回是否成功。"""
        session = get_db_session()
        try:
            po = session.query(CaseAlgorithmParamPO).filter_by(
                id=param_id, deleted=False
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

    def revive(
        self, param_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """恢复软删除的用例参数并更新字段，返回更新后的 dict。

        字段映射与 servicers.py ReviveCaseParam 一致：
        - param_name / param_type / required / default_value / help_text
        - ui_order / hidden / scope / min_value / max_value / step / unit
        """
        session = get_db_session()
        try:
            po = session.get(CaseAlgorithmParamPO, param_id)
            if po is None:
                raise ValueError(
                    f"Case parameter id={param_id} 不存在，无法恢复"
                )
            po.deleted = False
            updatable_fields = {
                "param_name": data.get("param_name"),
                "param_type": data.get("param_type"),
                "required": data.get("required"),
                "default_value": data.get("default_value"),
                "help_text": data.get("help_text"),
                "ui_order": data.get("ui_order"),
                "hidden": data.get("hidden"),
                "scope": data.get("scope"),
                "min_value": data.get("min_value"),
                "max_value": data.get("max_value"),
                "step": data.get("step"),
                "unit": data.get("unit"),
            }
            for field, value in updatable_fields.items():
                if value is not None:
                    setattr(po, field, value)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise


# ========== ReferenceParamRepository ==========

class ReferenceParamRepository(IReferenceParamRepository):
    """参考参数仓储实现（AlgorithmReferenceParam PO）。

    遵循 ACL 模式：外部只看到 dict，不感知 ORM。
    """

    def find_by_code(
        self, algorithm_type: str, code: str
    ) -> Optional[Dict[str, Any]]:
        """按 算法/code 查找未删除的参考参数。"""
        session = get_db_session()
        po = session.query(AlgorithmReferenceParamPO).filter_by(
            algorithm_type=algorithm_type,
            code=code,
            deleted=False,
        ).first()
        return _po_to_dict(po) if po is not None else None

    def get_by_id(self, param_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的参考参数。"""
        session = get_db_session()
        po = session.query(AlgorithmReferenceParamPO).filter_by(
            id=param_id, deleted=False
        ).first()
        return _po_to_dict(po) if po is not None else None

    def list_by_algorithm(
        self, algorithm_type: str
    ) -> List[Dict[str, Any]]:
        """按算法查询参考参数列表。

        - algorithm_type 为空时返回全部未删除参考参数
        - 按 id 排序
        """
        session = get_db_session()
        query = session.query(AlgorithmReferenceParamPO).filter_by(deleted=False)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)
        params = query.order_by(AlgorithmReferenceParamPO.id).all()
        return [_po_to_dict(p) for p in params]

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建参考参数，返回新参数 dict。

        字段映射与 servicers.py CreateReferenceParam 一致：
        - code / name / param_type / annotation_code / annotation_format
        - field_path / merge_mode / help_text
        """
        session = get_db_session()
        try:
            po = AlgorithmReferenceParamPO(
                algorithm_type=data.get("algorithm_type"),
                code=data.get("code"),
                name=data.get("name") or "",
                param_type=data.get("param_type") or "text",
                annotation_code=data.get("annotation_code"),
                annotation_format=data.get("annotation_format"),
                field_path=data.get("field_path"),
                merge_mode=data.get("merge_mode") or "join",
                help_text=data.get("help_text") or "",
            )
            session.add(po)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def update_attrs(
        self, param_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新参考参数可写字段，返回更新后的 dict。

        - 仅更新 fields 中非 None 的字段
        """
        session = get_db_session()
        try:
            po = session.query(AlgorithmReferenceParamPO).filter_by(
                id=param_id, deleted=False
            ).first()
            if po is None:
                raise ValueError(
                    f"Reference parameter id={param_id} 不存在，无法更新"
                )
            for field, value in fields.items():
                if value is not None:
                    setattr(po, field, value)
            session.flush()
            session.commit()
            return _po_to_dict(po)
        except Exception:
            session.rollback()
            raise

    def soft_delete(self, param_id: int) -> bool:
        """按 ID 软删除参考参数，返回是否成功。"""
        session = get_db_session()
        try:
            po = session.query(AlgorithmReferenceParamPO).filter_by(
                id=param_id, deleted=False
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


# ========== 模块级单例 ==========

algorithm_param_repository = AlgorithmParamRepository()
case_param_repository = CaseParamRepository()
reference_param_repository = ReferenceParamRepository()
mapping_repository = MappingRepository()
dimension_relation_repository = DimensionRelationRepository()
