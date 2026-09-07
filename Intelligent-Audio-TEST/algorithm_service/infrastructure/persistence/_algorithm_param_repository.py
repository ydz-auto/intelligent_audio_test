# -*- coding: utf-8 -*-
"""设备/API 参数仓储实现（AlgorithmParamRepository）。

从 param_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）。

覆盖 AlgorithmDeviceParam / AlgorithmApiParam 两张结构相同的表，
通过 param_type_source（device/api）区分目标 PO。
遵循 ACL 模式：外部只看到 dict，不感知 ORM。
通过 shared.models.database.get_db_session() 的 scoped_session 访问数据。
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from shared.models.database import get_db_session
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    AlgorithmApiParam as AlgorithmApiParamPO,
)
from algorithm_service.domain.repositories.param_repositories import (
    IAlgorithmParamRepository,
)
from algorithm_service.infrastructure.persistence._param_converters import (
    _apply_update_fields,
    _po_to_dict,
    _resolve_param_model,
)


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

        - 键名兼容 camelCase（网关 update_param 原样透传前端请求体），
          未知字段忽略，避免 setattr 到非映射属性造成静默 no-op
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
            _apply_update_fields(po, fields)
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
