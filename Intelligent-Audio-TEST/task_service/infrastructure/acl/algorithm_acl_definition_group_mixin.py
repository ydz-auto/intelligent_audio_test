# -*- coding: utf-8 -*-
"""AlgorithmDefinitionGroupMixin - 算法定义/算法分组 gRPC 仓储 Mixin。

从 algorithm_acl_repository.py 按职责拆分，承担：
- 算法定义 CRUD（Find/Create/Update/SoftDelete/List/Count/BulkDelete）
- 算法分组 CRUD（FindGroupByName/GetGroup/CreateGroup/UpdateGroupAttrs/SoftDeleteGroup/ListGroups）

由 AlgorithmRepository 组合复用，不单独实例化。
"""
from __future__ import annotations

import json
from typing import List, Optional

from shared.proto import algorithm_service_pb2 as _pb
from shared.utils.grpc_json import loads as _loads
from task_service.domain.dto.task_acl_dto import (
    AlgorithmDefinitionDTO, AlgorithmGroupDTO, CreateAckDTO,
)

from task_service.infrastructure.acl.algorithm_acl_grpc_helpers import (
    _get_stub, _items, _one, _raise_on_failure,
)


class AlgorithmDefinitionGroupMixin:
    """算法定义/算法分组仓储 Mixin。"""

    # ========== 算法定义 ==========

    def find_algorithm_by_type(
        self, algo_type: str
    ):
        """按 type 查询未删除的算法定义。"""
        resp = _get_stub().FindAlgorithmByType(_pb.FindAlgorithmByTypeRequest(
            algorithm_type=algo_type or "",
        ))
        if not resp.success:
            return None
        return _one(resp, dto_cls=AlgorithmDefinitionDTO)

    def create_algorithm_definition(
        self, algo_data: dict
    ):
        """创建算法定义（gRPC 自动提交）。"""
        resp = _get_stub().CreateAlgorithmDefinition(
            _pb.CreateAlgorithmDefinitionRequest(
                data=json.dumps(algo_data or {}, ensure_ascii=False, default=str),
            )
        )
        _raise_on_failure(resp)
        return _one(resp, dto_cls=CreateAckDTO)

    def update_algorithm_definition_attrs(
        self, algo_def, data: dict
    ) -> None:
        """更新算法定义可变字段（gRPC 自动提交）。"""
        algo_id = algo_def.get("id") if isinstance(algo_def, dict) else getattr(algo_def, "id", None)
        if algo_id is None:
            raise RuntimeError("update_algorithm_definition_attrs: algo_def 缺少 id 字段")
        resp = _get_stub().UpdateAlgorithmDefinitionAttrs(
            _pb.UpdateAlgorithmDefinitionAttrsRequest(
                algorithm_id=int(algo_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            )
        )
        _raise_on_failure(resp)

    def soft_delete_algorithm(self, algo_def) -> None:
        """软删除算法定义（gRPC 自动提交）。"""
        algo_id = algo_def.get("id") if isinstance(algo_def, dict) else getattr(algo_def, "id", None)
        if algo_id is None:
            raise RuntimeError("soft_delete_algorithm: algo_def 缺少 id 字段")
        resp = _get_stub().SoftDeleteAlgorithm(_pb.SoftDeleteAlgorithmRequest(
            algorithm_id=int(algo_id),
        ))
        _raise_on_failure(resp)

    def list_algorithm_definitions(
        self,
        status: Optional[str] = None,
        group_id: Optional[int] = None,
    ) -> List:
        """查询未删除的算法定义列表。"""
        resp = _get_stub().ListAlgorithmDefinitions(_pb.ListAlgorithmDefinitionsRequest(
            status=status or "",
            group_id=int(group_id) if group_id else 0,
        ))
        return _items(resp, dto_cls=AlgorithmDefinitionDTO)

    def list_online_algorithm_definitions(self) -> List:
        """查询在线算法定义列表。"""
        resp = _get_stub().ListOnlineAlgorithmDefinitions(
            _pb.ListOnlineAlgorithmDefinitionsRequest()
        )
        return _items(resp, dto_cls=AlgorithmDefinitionDTO)

    def count_algorithms_in_group(self, group_id: int) -> int:
        """统计分组下未删除的算法定义数量。"""
        resp = _get_stub().CountAlgorithmsInGroup(_pb.CountAlgorithmsInGroupRequest(
            group_id=int(group_id),
        ))
        _raise_on_failure(resp)
        payload = _loads(resp.data, {}) or {}
        if isinstance(payload, dict):
            for k in ("count", "total", "num"):
                if isinstance(payload.get(k), (int, float)):
                    return int(payload[k])
            return 0
        if isinstance(payload, (int, float)):
            return int(payload)
        return 0

    def list_algorithm_definitions_for_bulk_delete(
        self, algorithm_types: List[str]
    ) -> List:
        """按 type 列表查询未删除的算法定义（供批量删除）。"""
        resp = _get_stub().ListAlgorithmDefinitionsForBulkDelete(
            _pb.ListAlgorithmDefinitionsForBulkDeleteRequest(
                algorithm_types=json.dumps(list(algorithm_types or []), ensure_ascii=False, default=str),
            )
        )
        return _items(resp, dto_cls=AlgorithmDefinitionDTO)

    # ========== 算法分组 ==========

    def find_group_by_name(
        self, name: str
    ):
        """按 name 查询未删除的算法分组。"""
        resp = _get_stub().FindGroupByName(_pb.FindGroupByNameRequest(name=name or ""))
        if not resp.success:
            return None
        return _one(resp, dto_cls=AlgorithmGroupDTO)

    def get_group(self, group_id: int):
        """按 ID 查询未删除的算法分组。"""
        resp = _get_stub().GetGroup(_pb.GetGroupRequest(group_id=int(group_id)))
        return _one(resp, dto_cls=AlgorithmGroupDTO)

    def create_group(self, data: dict):
        """创建算法分组（gRPC 自动提交）。"""
        resp = _get_stub().CreateGroup(_pb.CreateGroupRequest(
            data=json.dumps(data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=CreateAckDTO)

    def update_group_attrs(
        self, group, data: dict
    ) -> None:
        """更新分组可变字段（gRPC 自动提交）。"""
        group_id = group.get("id") if isinstance(group, dict) else getattr(group, "id", None)
        if group_id is None:
            raise RuntimeError("update_group_attrs: group 缺少 id 字段")
        resp = _get_stub().UpdateGroupAttrs(_pb.UpdateGroupAttrsRequest(
            group_id=int(group_id),
            data=json.dumps(data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)

    def soft_delete_group(self, group) -> None:
        """软删除算法分组（gRPC 自动提交）。"""
        group_id = group.get("id") if isinstance(group, dict) else getattr(group, "id", None)
        if group_id is None:
            raise RuntimeError("soft_delete_group: group 缺少 id 字段")
        resp = _get_stub().SoftDeleteGroup(_pb.SoftDeleteGroupRequest(group_id=int(group_id)))
        _raise_on_failure(resp)

    def list_groups(self) -> List:
        """查询未删除的算法分组列表。"""
        resp = _get_stub().ListGroups(_pb.ListGroupsRequest())
        return _items(resp, dto_cls=AlgorithmGroupDTO)

    def count_algorithms_in_group_for_group(
        self, group
    ) -> int:
        """统计指定分组对象下未删除的算法定义数量。"""
        group_id = group.get("id") if isinstance(group, dict) else getattr(group, "id", None)
        if group_id is None:
            return 0
        resp = _get_stub().CountAlgorithmsInGroupForGroup(
            _pb.CountAlgorithmsInGroupForGroupRequest(group_id=int(group_id))
        )
        _raise_on_failure(resp)
        payload = _loads(resp.data, {}) or {}
        if isinstance(payload, dict):
            for k in ("count", "total", "num"):
                if isinstance(payload.get(k), (int, float)):
                    return int(payload[k])
            return 0
        if isinstance(payload, (int, float)):
            return int(payload)
        return 0
