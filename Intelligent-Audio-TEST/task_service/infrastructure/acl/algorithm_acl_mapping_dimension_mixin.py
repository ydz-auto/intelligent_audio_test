# -*- coding: utf-8 -*-
"""AlgorithmMappingDimensionMixin - 参数映射/维度关联/维度参数 gRPC 仓储 Mixin。

从 algorithm_acl_repository.py 按职责拆分，承担：
- 参数映射 CRUD（CreateMapping/GetMapping/ListMappings/UpdateMapping/DeleteMapping）
- 算法-维度关联 CRUD（CreateDimensionRelation/.../SoftDeleteDimensionRelation）
- 评估维度参数查询（ListDimensionParams）

由 AlgorithmRepository 组合复用，不单独实例化。
"""
from __future__ import annotations

import json
from typing import List, Optional

from shared.proto import algorithm_service_pb2 as _pb
from task_service.domain.dto.task_acl_dto import (
    ParamMappingDTO, DimensionRelationDTO, DimensionParamDTO, CreateAckDTO,
)

from task_service.infrastructure.acl.algorithm_acl_grpc_helpers import (
    _get_stub, _items, _one, _raise_on_failure,
)


class AlgorithmMappingDimensionMixin:
    """参数映射/维度关联仓储 Mixin。"""

    # ========== 参数映射 CRUD ==========

    def create_mapping(self, data: dict):
        """创建参数映射（gRPC 自动提交）。"""
        resp = _get_stub().CreateMapping(_pb.CreateMappingRequest(
            data=json.dumps(data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=ParamMappingDTO)

    def get_mapping(self, mapping_id: int):
        """按 ID 查询未删除的参数映射。"""
        resp = _get_stub().GetMapping(_pb.GetMappingRequest(mapping_id=int(mapping_id)))
        return _one(resp, dto_cls=ParamMappingDTO)

    def list_mappings(
        self,
        algorithm_type: Optional[str] = None,
        source_type: Optional[str] = None,
        dimension_id: Optional[int] = None,
    ) -> List:
        """查询参数映射列表（带可选过滤，本地二次过滤）。"""
        resp = _get_stub().ListMappings(_pb.ListMappingsRequest(
            algorithm_type=algorithm_type or "",
        ))
        items = _items(resp, dto_cls=ParamMappingDTO)
        if source_type:
            items = [it for it in items if it.source == source_type]
        if dimension_id:
            items = [it for it in items
                     if it.dimension_id == int(dimension_id)]
        return items

    def update_mapping_attrs(self, mapping, data: dict) -> None:
        """更新参数映射属性（gRPC 自动提交）。"""
        mapping_id = mapping.get("id") if isinstance(mapping, dict) else getattr(mapping, "id", None)
        if mapping_id is None:
            raise RuntimeError("update_mapping_attrs: mapping 缺少 id 字段")
        resp = _get_stub().UpdateMapping(_pb.UpdateMappingRequest(
            mapping_id=int(mapping_id),
            data=json.dumps(data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)

    def soft_delete_mapping(self, mapping) -> None:
        """软删除参数映射（gRPC 自动提交）。"""
        mapping_id = mapping.get("id") if isinstance(mapping, dict) else getattr(mapping, "id", None)
        if mapping_id is None:
            raise RuntimeError("soft_delete_mapping: mapping 缺少 id 字段")
        resp = _get_stub().DeleteMapping(_pb.DeleteMappingRequest(mapping_id=int(mapping_id)))
        _raise_on_failure(resp)

    # ========== 维度关联 CRUD ==========

    def soft_delete_algorithm_dimension_relations(self, algorithm_type: str) -> None:
        """按算法批量软删除维度关联（gRPC 自动提交）。"""
        resp = _get_stub().SoftDeleteAlgorithmDimensionRelations(
            _pb.SoftDeleteAlgorithmDimensionRelationsRequest(
                algorithm_type=algorithm_type or "",
            )
        )
        _raise_on_failure(resp)

    def create_dimension_relation(self, data: dict):
        """创建单条维度关联（gRPC 自动提交）。"""
        resp = _get_stub().CreateDimensionRelation(
            _pb.CreateDimensionRelationRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            )
        )
        _raise_on_failure(resp)
        return _one(resp, dto_cls=CreateAckDTO)

    def find_dimension_relation(
        self, algorithm_type: str, dimension_id: int
    ):
        """按算法/维度查找未删除的维度关联。"""
        resp = _get_stub().FindDimensionRelation(_pb.FindDimensionRelationRequest(
            algorithm_type=algorithm_type or "",
            dimension_id=int(dimension_id),
        ))
        if not resp.success:
            return None
        return _one(resp, dto_cls=DimensionRelationDTO)

    def get_dimension_relation(self, relation_id: int):
        """按 ID 查询维度关联（含软删项）。"""
        resp = _get_stub().GetDimensionRelation(_pb.GetDimensionRelationRequest(
            relation_id=int(relation_id),
        ))
        return _one(resp, dto_cls=DimensionRelationDTO)

    def list_dimension_relations(
        self, algorithm_type: str
    ) -> List:
        """查询算法关联的未删除维度关联列表。"""
        resp = _get_stub().ListDimensionRelations(_pb.ListDimensionRelationsRequest(
            algorithm_type=algorithm_type or "",
        ))
        return _items(resp, dto_cls=DimensionRelationDTO)

    def update_dimension_relation_attrs(
        self, relation, data: dict
    ) -> None:
        """更新维度关联属性（gRPC 自动提交）。"""
        relation_id = relation.get("id") if isinstance(relation, dict) else getattr(relation, "id", None)
        if relation_id is None:
            raise RuntimeError("update_dimension_relation_attrs: relation 缺少 id 字段")
        resp = _get_stub().UpdateDimensionRelationAttrs(
            _pb.UpdateDimensionRelationAttrsRequest(
                relation_id=int(relation_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            )
        )
        _raise_on_failure(resp)

    def soft_delete_dimension_relation(
        self, relation
    ) -> None:
        """软删除维度关联（gRPC 自动提交）。"""
        relation_id = relation.get("id") if isinstance(relation, dict) else getattr(relation, "id", None)
        if relation_id is None:
            raise RuntimeError("soft_delete_dimension_relation: relation 缺少 id 字段")
        resp = _get_stub().SoftDeleteDimensionRelation(
            _pb.SoftDeleteDimensionRelationRequest(relation_id=int(relation_id))
        )
        _raise_on_failure(resp)

    # ========== 评估维度参数 ==========

    def list_dimension_params(
        self, dimension_id: int
    ) -> List:
        """查询评估维度的参数列表。"""
        resp = _get_stub().ListDimensionParams(_pb.ListDimensionParamsRequest(
            dimension_id=int(dimension_id),
        ))
        return _items(resp, dto_cls=DimensionParamDTO)
