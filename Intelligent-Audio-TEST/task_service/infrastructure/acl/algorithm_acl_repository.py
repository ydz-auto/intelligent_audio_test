# -*- coding: utf-8 -*-
"""算法参数/映射/维度关联仓储 — gRPC ACL 适配层。

本模块原为直接访问 algorithm_service PO 的仓储，现已改为通过
algorithm_service gRPC 接口访问，彻底消除跨服务 PO / DB 耦合。

- 写操作（Create/Update/Delete/SoftDelete/Revive/...）通过
  AlgorithmDefinitionService / AlgorithmGroupService 的 RPC 完成，
  每个 RPC 自动提交事务。
- 读操作（Find/Get/List/Count）同样通过 gRPC，返回 dict（不再返回 ORM 对象）。
- 事务控制方法 commit/rollback/flush 保留向后兼容，现已为 gRPC 等价 RPC
  的 no-op 形式（每条写 RPC 均自动提交，无法跨调用回滚）。
- 跨域 Dimension 查询保持原有 evaluation_service gRPC 调用不变。

相关 stub：shared.clients.grpc_clients.get_algorithm_definition_service_stub /
get_algorithm_group_service_stub
proto：shared/proto/algorithm_service.proto
"""
import json
import logging
from typing import Any, Dict, List, Optional

from shared.clients.grpc_clients import (
    get_algorithm_definition_service_stub,
    get_algorithm_group_service_stub,
)
from shared.proto import algorithm_service_pb2 as _pb
from shared.utils.grpc_json import loads as _loads
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto
from task_service.domain.dto.task_acl_dto import (
    AlgorithmDefinitionDTO, AlgorithmGroupDTO, DeviceParamDTO, ApiParamDTO,
    CaseParamDTO, ReferenceParamDTO, ParamMappingDTO, DimensionRelationDTO,
    DimensionParamDTO, DimensionDTO, CreateAckDTO,
)
from task_service.domain.repositories.algorithm_acl_repository import AlgorithmAclRepository

_logger = logging.getLogger(__name__)


def _get_stub():
    """获取 AlgorithmDefinitionService gRPC stub（便捷封装）。"""
    return get_algorithm_definition_service_stub()


def _group_stub():
    """获取 AlgorithmGroupService gRPC stub（便捷封装）。"""
    return get_algorithm_group_service_stub()


def _items(resp, key: str = "items", dto_cls=None) -> list:
    """从列表型 gRPC 响应中提取条目列表，可选包装为 DTO。

    兼容 servicer 返回的 {"items": [...]} / {"parameters": [...]} /
    {"mappings": [...]} / {"relations": [...]} 等不同键名。
    """
    if not resp.success:
        raise RuntimeError(resp.message)
    payload = _loads(resp.data, None)
    if not payload:
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for candidate in (key, "parameters", "mappings", "relations", "params"):
            items = payload.get(candidate)
            if isinstance(items, list):
                break
        if items is None:
            return []
    else:
        return []
    if dto_cls is not None:
        return dict_list_to_dto(items, dto_cls)
    return items


def _one(resp, dto_cls=None):
    """从单条查询 gRPC 响应中提取 dict/DTO，无数据返回 None。"""
    if not resp.success:
        return None
    if not resp.data:
        return None
    payload = _loads(resp.data, None)
    if not payload:
        return None
    if not isinstance(payload, dict):
        return None
    if dto_cls is not None:
        return dict_to_dto(payload, dto_cls)
    return payload


def _raise_on_failure(resp):
    """写操作统一失败处理：success=False 即抛 RuntimeError。"""
    if not resp.success:
        raise RuntimeError(resp.message or "algorithm_service gRPC 调用失败")


class AlgorithmRepository(AlgorithmAclRepository):
    """算法参数/映射/维度关联仓储（gRPC ACL 适配层）。

    继承 domain ABC 实现依赖倒置。
    """

    # ========== 设备参数 / API 参数 CRUD ==========

    def create_device_param(self, data: dict):
        """创建设备参数（gRPC 自动提交）。"""
        payload = dict(data)
        payload["param_type_source"] = "device"
        resp = _get_stub().CreateParam(_pb.CreateParamRequest(
            data=json.dumps(payload, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=DeviceParamDTO)

    def create_api_param(self, data: dict):
        """创建 API 参数（gRPC 自动提交）。"""
        payload = dict(data)
        payload["param_type_source"] = "api"
        resp = _get_stub().CreateParam(_pb.CreateParamRequest(
            data=json.dumps(payload, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=ApiParamDTO)

    def find_device_param_by_code(
        self, algorithm_type: str, param_code: str, direction: str
    ):
        """按算法/参数代码/方向查找未删除的设备参数。"""
        resp = _get_stub().FindParamByCode(_pb.FindParamByCodeRequest(
            algorithm_type=algorithm_type or "",
            param_code=param_code or "",
            direction=direction or "",
            param_type_source="device",
        ))
        if not resp.success:
            return None
        return _one(resp, dto_cls=DeviceParamDTO)

    def find_api_param_by_code(
        self, algorithm_type: str, param_code: str, direction: str
    ):
        """按算法/参数代码/方向查找未删除的 API 参数。"""
        resp = _get_stub().FindParamByCode(_pb.FindParamByCodeRequest(
            algorithm_type=algorithm_type or "",
            param_code=param_code or "",
            direction=direction or "",
            param_type_source="api",
        ))
        if not resp.success:
            return None
        return _one(resp, dto_cls=ApiParamDTO)

    def get_device_param(self, param_id: int):
        """按 ID 查询未删除的设备参数。"""
        resp = _get_stub().GetParam(_pb.GetParamRequest(param_id=int(param_id)))
        return _one(resp, dto_cls=DeviceParamDTO)

    def get_api_param(self, param_id: int):
        """按 ID 查询未删除的 API 参数。"""
        resp = _get_stub().GetParam(_pb.GetParamRequest(param_id=int(param_id)))
        return _one(resp, dto_cls=ApiParamDTO)

    def list_device_params(
        self, algorithm_type: Optional[str] = None
    ) -> List:
        """查询设备参数列表。"""
        resp = _get_stub().ListParams(_pb.ListParamsRequest(
            algorithm_type=algorithm_type or "",
            param_type="device",
        ))
        return _items(resp, dto_cls=DeviceParamDTO)

    def list_api_params(
        self, algorithm_type: Optional[str] = None
    ) -> List:
        """查询 API 参数列表。"""
        resp = _get_stub().ListParams(_pb.ListParamsRequest(
            algorithm_type=algorithm_type or "",
            param_type="api",
        ))
        return _items(resp, dto_cls=ApiParamDTO)

    def update_param_attrs(self, param, fields: Dict[str, Any]) -> None:
        """更新参数属性（gRPC 自动提交）。

        param 为 dict（来自先前 gRPC 查询），取 param['id'] 定位记录。
        仅用于设备参数和 API 参数（UpdateParam RPC）。
        """
        param_id = param.get("id") if isinstance(param, dict) else getattr(param, "id", None)
        if param_id is None:
            raise RuntimeError("update_param_attrs: param 缺少 id 字段")
        resp = _get_stub().UpdateParam(_pb.UpdateParamRequest(
            param_id=int(param_id),
            data=json.dumps(fields or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)

    def update_case_param_attrs(self, param, fields: Dict[str, Any]) -> None:
        """更新用例专属参数属性（gRPC 自动提交）。

        使用 UpdateCaseParam RPC，目标表为 CaseAlgorithmParamPO。
        """
        param_id = param.get("id") if isinstance(param, dict) else getattr(param, "id", None)
        if param_id is None:
            raise RuntimeError("update_case_param_attrs: param 缺少 id 字段")
        resp = _get_stub().UpdateCaseParam(_pb.UpdateCaseParamRequest(
            param_id=int(param_id),
            data=json.dumps(fields or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)

    def update_reference_param_attrs(self, param, fields: Dict[str, Any]) -> None:
        """更新参考参数属性（gRPC 自动提交）。

        使用 UpdateReferenceParam RPC，目标表为 AlgorithmReferenceParamPO。
        """
        param_id = param.get("id") if isinstance(param, dict) else getattr(param, "id", None)
        if param_id is None:
            raise RuntimeError("update_reference_param_attrs: param 缺少 id 字段")
        resp = _get_stub().UpdateReferenceParam(_pb.UpdateReferenceParamRequest(
            param_id=int(param_id),
            data=json.dumps(fields or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)

    def soft_delete_param(self, param) -> None:
        """软删除设备/API 参数（gRPC 自动提交）。"""
        param_id = param.get("id") if isinstance(param, dict) else getattr(param, "id", None)
        if param_id is None:
            raise RuntimeError("soft_delete_param: param 缺少 id 字段")
        resp = _get_stub().DeleteParam(_pb.DeleteParamRequest(param_id=int(param_id)))
        _raise_on_failure(resp)

    def soft_delete_case_param(self, param) -> None:
        """软删除用例专属参数（gRPC 自动提交）。"""
        param_id = param.get("id") if isinstance(param, dict) else getattr(param, "id", None)
        if param_id is None:
            raise RuntimeError("soft_delete_case_param: param 缺少 id 字段")
        resp = _get_stub().DeleteCaseParam(_pb.DeleteCaseParamRequest(param_id=int(param_id)))
        _raise_on_failure(resp)

    def soft_delete_reference_param(self, param) -> None:
        """软删除参考参数（gRPC 自动提交）。"""
        param_id = param.get("id") if isinstance(param, dict) else getattr(param, "id", None)
        if param_id is None:
            raise RuntimeError("soft_delete_reference_param: param 缺少 id 字段")
        resp = _get_stub().DeleteReferenceParam(_pb.DeleteReferenceParamRequest(param_id=int(param_id)))
        _raise_on_failure(resp)

    # ========== 用例专属参数 CRUD ==========

    def find_case_param_by_code(
        self, algorithm_type: str, param_code: str, deleted: bool = False
    ):
        """按算法/参数代码查找用例专属参数（可指定 deleted 查软删项）。"""
        resp = _get_stub().FindCaseParamByCode(_pb.FindCaseParamByCodeRequest(
            algorithm_type=algorithm_type or "",
            param_code=param_code or "",
            include_deleted=bool(deleted),
        ))
        if not resp.success:
            return None
        return _one(resp, dto_cls=CaseParamDTO)

    def create_case_param(self, data: dict):
        """创建用例专属参数（gRPC 自动提交）。"""
        resp = _get_stub().CreateCaseParam(_pb.CreateCaseParamRequest(
            data=json.dumps(data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=CaseParamDTO)

    def get_case_param(self, param_id: int):
        """按 ID 查询未删除的用例专属参数。

        proto 暂未提供 GetCaseParam，使用 ListCaseParams 全量后本地过滤。
        """
        resp = _get_stub().ListCaseParams(_pb.ListCaseParamsRequest(algorithm_type=""))
        items = _items(resp, dto_cls=CaseParamDTO)
        for item in items:
            if item.id == int(param_id):
                return item
        return None

    def list_case_params(
        self,
        algorithm_type: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> List:
        """查询用例专属参数列表（scope 过滤含 common）。"""
        resp = _get_stub().ListCaseParams(_pb.ListCaseParamsRequest(
            algorithm_type=algorithm_type or "",
        ))
        items = _items(resp, dto_cls=CaseParamDTO)
        if scope:
            items = [it for it in items if it.scope == "common"
                      or it.scope == scope]
        return items

    def list_case_params_for_schema(
        self, algorithm_type: str
    ) -> List:
        """查询算法表单 Schema 用的用例专属参数（不含 hidden）。"""
        resp = _get_stub().ListCaseParams(_pb.ListCaseParamsRequest(
            algorithm_type=algorithm_type or "",
        ))
        items = _items(resp, dto_cls=CaseParamDTO)
        return [it for it in items if not it.hidden]

    # ========== 参考参数 CRUD ==========

    def find_reference_param(
        self, algorithm_type: str, code: str
    ):
        """按算法/代码查找未删除的参考参数。"""
        resp = _get_stub().FindReferenceParam(_pb.FindReferenceParamRequest(
            algorithm_type=algorithm_type or "",
            code=code or "",
        ))
        if not resp.success:
            return None
        return _one(resp, dto_cls=ReferenceParamDTO)

    def create_reference_param(self, data: dict):
        """创建参考参数（gRPC 自动提交）。"""
        resp = _get_stub().CreateReferenceParam(_pb.CreateReferenceParamRequest(
            data=json.dumps(data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=ReferenceParamDTO)

    def get_reference_param(self, param_id: int):
        """按 ID 查询未删除的参考参数。

        proto 暂未提供 GetReferenceParam，使用 ListReferenceParams 全量后本地过滤。
        """
        resp = _get_stub().ListReferenceParams(_pb.ListReferenceParamsRequest(algorithm_type=""))
        items = _items(resp, dto_cls=ReferenceParamDTO)
        for item in items:
            if item.id == int(param_id):
                return item
        return None

    def list_reference_params(
        self, algorithm_type: str
    ) -> List:
        """查询参考参数列表。"""
        resp = _get_stub().ListReferenceParams(_pb.ListReferenceParamsRequest(
            algorithm_type=algorithm_type or "",
        ))
        return _items(resp, dto_cls=ReferenceParamDTO)

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

    def create_import_device_param(self, param_data: dict):
        """导入场景下创建设备参数（gRPC 自动提交）。"""
        resp = _get_stub().CreateImportDeviceParam(_pb.CreateImportDeviceParamRequest(
            data=json.dumps(param_data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=CreateAckDTO)

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

    # ========== 跨域查询：Dimension（evaluation_service gRPC，保持不变）==========

    def _fetch_dimensions_via_grpc(self, dim_ids: List[int]) -> list:
        """通过 gRPC 批量查询 Dimension 基础信息。

        Dimension 是 evaluation_service 自有 PO，通过
        evaluation_service.EvaluationConfigService.GetDimensionByIds 获取。
        失败时返回空列表（仅日志告警）。
        """
        if not dim_ids:
            return []

        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb

        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=json.dumps(list(dim_ids)),
            ))
            if not resp.success:
                _logger.warning("GetDimensionByIds gRPC 失败: %s", resp.message)
                return []
            payload = _loads(resp.data, {}) if resp.data else {}
        except Exception as e:
            _logger.warning("GetDimensionByIds gRPC 异常: %s", e)
            return []

        if not isinstance(payload, dict):
            return []
        items = payload.get('items', []) or []
        return dict_list_to_dto(items, DimensionDTO)

    def get_dimension_by_id(self, dim_id):
        """按 ID 查询单个评价维度（返回 DimensionDTO 或 None）。"""
        if not dim_id:
            return None
        dims = self._fetch_dimensions_via_grpc([dim_id])
        return dims[0] if dims else None

    def list_dimensions_by_ids(
        self, dim_ids: List[int], only_not_deleted: bool = True
    ) -> list:
        """按 ID 列表查询评价维度（返回 DimensionDTO 列表）。

        only_not_deleted 参数保留向后兼容，gRPC 端默认只查未删除。
        """
        return self._fetch_dimensions_via_grpc(dim_ids)

    def list_dimensions_map_by_ids(
        self, dim_ids: List[int], only_not_deleted: bool = True
    ) -> Dict[int, Any]:
        """按 ID 列表查询评价维度，返回 {id: DimensionDTO} 映射。"""
        dims = self.list_dimensions_by_ids(dim_ids, only_not_deleted)
        return {d.id: d for d in dims if d.id is not None}

    def list_dimension_names_map_by_ids(
        self, dim_ids: List[int], only_not_deleted: bool = True
    ) -> Dict[int, str]:
        """按 ID 列表查询评价维度名称，返回 {id: name} 映射。"""
        dims = self.list_dimensions_by_ids(dim_ids, only_not_deleted)
        return {d.id: d.name for d in dims if d.id is not None}

    # ========== 事务控制（gRPC auto-commit，保留为兼容 no-op）==========

    def commit(self):
        """提交事务（gRPC 每条写 RPC 均自动提交，本调用为兼容 no-op）。"""
        try:
            _get_stub().CommitTransaction(_pb.CommitTransactionRequest())
        except Exception as e:  # noqa: BLE001
            _logger.debug("CommitTransaction no-op 失败（可忽略）: %s", e)

    def rollback(self):
        """回滚事务（gRPC 已自动提交的写操作无法回滚，本调用为兼容 no-op）。"""
        try:
            _get_stub().RollbackTransaction(_pb.RollbackTransactionRequest())
        except Exception as e:  # noqa: BLE001
            _logger.debug("RollbackTransaction no-op 失败（可忽略）: %s", e)

    def flush(self):
        """flush session（gRPC 每条写 RPC 均自动提交，本调用为兼容 no-op）。"""
        try:
            _get_stub().FlushTransaction(_pb.FlushTransactionRequest())
        except Exception as e:  # noqa: BLE001
            _logger.debug("FlushTransaction no-op 失败（可忽略）: %s", e)

    # ========== 算法查询服务封装（AlgorithmQueryService）==========

    def algo_load_reference_params_file(self, filepath: str = ''):
        """从 OSS 加载参考参数文件内容。

        封装 shared.clients.grpc_clients.algo_load_reference_params_file，
        通过 algorithm_service AlgorithmQueryService.LoadReferenceParamsFile RPC。
        """
        from shared.clients.grpc_clients import algo_load_reference_params_file
        return algo_load_reference_params_file(filepath)

    def algo_get_full_field_mapping(self, algorithm_type: str):
        """获取算法完整字段映射。

        封装 shared.clients.grpc_clients.algo_get_full_field_mapping，
        通过 algorithm_service AlgorithmQueryService.GetFullFieldMapping RPC。
        """
        from shared.clients.grpc_clients import algo_get_full_field_mapping
        return algo_get_full_field_mapping(algorithm_type)

    def algo_get_output_fields(self, algorithm_type: str, test_type: str = None):
        """获取算法结果输出字段。

        封装 shared.clients.grpc_clients.algo_get_output_fields，
        通过 algorithm_service AlgorithmQueryService.GetOutputFields RPC。
        """
        from shared.clients.grpc_clients import algo_get_output_fields
        return algo_get_output_fields(algorithm_type, test_type)

    def algo_generate_reference_params(self, test_case_config=None, round_data=None):
        """生成参考参数。

        封装 shared.clients.grpc_clients.algo_generate_reference_params，
        通过 algorithm_service AlgorithmQueryService.GenerateReferenceParams RPC。
        """
        from shared.clients.grpc_clients import algo_generate_reference_params
        return algo_generate_reference_params(test_case_config, round_data)

    def algo_get_all_reference_params(self, reference_params_col=None):
        """获取所有参考参数。

        封装 shared.clients.grpc_clients.algo_get_all_reference_params，
        通过 algorithm_service AlgorithmQueryService.GetAllReferenceParams RPC。
        """
        from shared.clients.grpc_clients import algo_get_all_reference_params
        return algo_get_all_reference_params(reference_params_col)

    def algo_extract_case_all_params(self, case_config=None):
        """提取用例全部算法参数。

        封装 shared.clients.grpc_clients.algo_extract_case_all_params，
        通过 algorithm_service AlgorithmQueryService.ExtractCaseAllParams RPC。
        """
        from shared.clients.grpc_clients import algo_extract_case_all_params
        return algo_extract_case_all_params(case_config)

    def algo_reload_config(self):
        """重新加载算法配置缓存（热更新）。

        封装 shared.clients.grpc_clients.algo_reload_config，
        通过 algorithm_service AlgorithmQueryService.ReloadConfig RPC。
        """
        from shared.clients.grpc_clients import algo_reload_config
        return algo_reload_config()
