# -*- coding: utf-8 -*-
"""用例参数/参考参数仓储实现（CaseParamRepository / ReferenceParamRepository）。

从 param_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- CaseParamRepository: 用例参数仓储（CaseAlgorithmParam PO）
- ReferenceParamRepository: 参考参数仓储（AlgorithmReferenceParam PO）

遵循 ACL 模式：外部只看到 dict，不感知 ORM。
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from shared.models.database import get_db_session
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmReferenceParam as AlgorithmReferenceParamPO,
    CaseAlgorithmParam as CaseAlgorithmParamPO,
)
from algorithm_service.domain.repositories.param_repositories import (
    ICaseParamRepository,
    IReferenceParamRepository,
)
from algorithm_service.infrastructure.persistence._param_converters import (
    _apply_update_fields,
    _po_to_dict,
)


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

        - 键名兼容 camelCase，未知字段忽略（见 _apply_update_fields）
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
            _apply_update_fields(po, fields)
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
        """恢复软删除的用例参数并更新字段，返回更新后的 dict。"""
        session = get_db_session()
        try:
            po = session.query(CaseAlgorithmParamPO).filter_by(
                id=param_id
            ).first()
            if po is None:
                raise ValueError(
                    f"Case parameter id={param_id} 不存在，无法恢复"
                )
            po.deleted = False
            for field, value in data.items():
                if value is not None and hasattr(po, field):
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

        - 键名兼容 camelCase，未知字段忽略（见 _apply_update_fields）
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
            _apply_update_fields(po, fields)
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
