# -*- coding: utf-8 -*-
"""维度/映射/设备参数 ACL 仓储实现。

从 algorithm_repository.py 拆分而来（原文件过大，按职责拆分为多个实现模块）：
- DeviceParamRepository: 导入场景设备参数仓储
- DimensionParamRepository: 评估维度参数仓储
- DimensionRelationQueryRepository: 算法-维度关联查询仓储
- ParamMappingQueryRepository: 参数映射查询仓储

供 handler/servicer 复用，避免直连 PO。
"""
from __future__ import annotations

from typing import List, Optional

from shared.models.database import get_db_session
from shared.models.common_enums import FieldType
from algorithm_service.infrastructure.persistence.models import (
    AlgorithmDefinition as AlgorithmDefinitionPO,
    AlgorithmDeviceParam as AlgorithmDeviceParamPO,
    AlgorithmDimensionRelation as AlgorithmDimensionRelationPO,
)
from algorithm_service.domain.repositories.algorithm_repositories import (
    IDeviceParamRepository,
    IDimensionParamRepository,
    IDimensionRelationQueryRepository,
    IParamMappingQueryRepository,
)
from algorithm_service.infrastructure.persistence._algorithm_query_repositories import (
    _po_to_dict,
)


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

    def list_by_dimensions(self, dimension_ids: List[int]) -> List[dict]:
        """批量查询多个评估维度的参数（INT-1666 配置缓存重载用）。

        一次 ``IN`` 查询取回全部维度的参数并按 (dimension_id, ui_order)
        排序，调用方分组即可——消除原「逐条维度关系 list_by_dimension」
        的 N+1。dimension_ids 为空时返回空列表（不发查询）。
        """
        from algorithm_service.infrastructure.persistence.models import (
            EvaluationDimensionParam as EvaluationDimensionParamPO,
        )
        ids = [int(i) for i in dimension_ids or [] if i is not None]
        if not ids:
            return []
        session = get_db_session()
        items = session.query(EvaluationDimensionParamPO).filter(
            EvaluationDimensionParamPO.dimension_id.in_(ids),
            EvaluationDimensionParamPO.deleted == False,  # noqa: E712
        ).order_by(
            EvaluationDimensionParamPO.dimension_id,
            EvaluationDimensionParamPO.ui_order,
        ).all()
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
            EvaluationDimensionParamPO.field_type == FieldType.AUDIO.value,
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


def _filter_api_scope(query, po_cls, api_id: Optional[int]):
    """按 api_id 作用域过滤 param_mappings 查询。

    ``api_id is None``（维度页 / 评估维度同步的默认口径）= 只取算法类型级行
    （``api_id IS NULL``），API 实例级行不参与；传值时只取该 API 的作用域行
    （INT-1863：作用域由调用方显式指定，不靠「查全部再按 source_param 合并」）。
    """
    if api_id is None:
        return query.filter(po_cls.api_id.is_(None))
    return query.filter(po_cls.api_id == int(api_id))


class ParamMappingQueryRepository(IParamMappingQueryRepository):
    """参数映射查询仓储（返回 dict，ACL 风格）。

    供 servicer 复用，避免直连 ParamMapping PO。

    INT-1863：``param_mappings`` 自 C6a（INT-1756）起带 ``api_id`` 作用域，
    本类只按调用方给定作用域读写，默认（``api_id=None``）为算法类型级。
    """

    def list_by_dimension(
        self, dimension_id: int, api_id: Optional[int] = None
    ) -> List[dict]:
        """ABC 接口 — 委托到 list_for_dimension。"""
        return self.list_for_dimension(dimension_id, api_id=api_id)

    def list_for_dimension(
        self, dimension_id: int, api_id: Optional[int] = None
    ) -> List[dict]:
        """查询某维度指定作用域下所有 ParamMapping（含软删除项）。

        默认只返回算法级行（``api_id IS NULL``），API 实例级行由 API 作用域
        自己的写路径管理，不混进维度级结果。
        """
        from algorithm_service.infrastructure.persistence.models import (
            ParamMapping as ParamMappingPO,
        )
        session = get_db_session()
        query = _filter_api_scope(
            session.query(ParamMappingPO), ParamMappingPO, api_id
        )
        items = query.filter_by(
            dimension_id=int(dimension_id),
            source="evaluation",
        ).all()
        return [_po_to_dict(po) for po in items]

    def sync_for_dimension(
        self, dimension_id: int, params: list, direction: str = "output",
        algorithm_type: str = "voice_llm", api_id: Optional[int] = None,
    ) -> bool:
        """同步 ParamMapping：当评估维度的输入/输出字段变更时，
        自动为该维度创建/更新/删除对应的 ParamMapping 记录。

        INT-1863：只管理调用方给定作用域（默认算法级 ``api_id IS NULL``）的行。
        评估维度保存走默认口径，绝不会改写或软删 API 实例级维度映射；新建行
        显式落 ``api_id``，与查询口径保持一致。
        """
        from algorithm_service.infrastructure.persistence.models import (
            ParamMapping as ParamMappingPO,
        )
        session = get_db_session()
        try:
            active_mappings = _filter_api_scope(
                session.query(ParamMappingPO), ParamMappingPO, api_id
            ).filter_by(
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
                        api_id=api_id,
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
