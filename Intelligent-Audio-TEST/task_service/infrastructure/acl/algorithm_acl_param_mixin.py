# -*- coding: utf-8 -*-
"""AlgorithmParamMixin - 设备/API/用例专属/参考参数 gRPC 仓储 Mixin。

从 algorithm_acl_repository.py 按职责拆分，承担四类参数的 CRUD：
- 设备参数 / API 参数（CreateParam/FindParamByCode/GetParam/ListParams/UpdateParam/DeleteParam）
- 用例专属参数（CaseParam 系列 RPC）
- 参考参数（ReferenceParam 系列 RPC）

由 AlgorithmRepository 组合复用，不单独实例化。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from shared.proto import algorithm_service_pb2 as _pb
from task_service.domain.dto.task_acl_dto import (
    DeviceParamDTO, ApiParamDTO, CaseParamDTO, ReferenceParamDTO, CreateAckDTO,
)

from task_service.infrastructure.acl.algorithm_acl_grpc_helpers import (
    _get_stub, _items, _one, _raise_on_failure,
)


class AlgorithmParamMixin:
    """参数仓储 Mixin：设备/API 参数 + 用例专属参数 + 参考参数 CRUD。"""

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

    # ========== 参考参数导入 ==========

    def create_import_device_param(self, param_data: dict):
        """导入场景下创建设备参数（gRPC 自动提交）。"""
        resp = _get_stub().CreateImportDeviceParam(_pb.CreateImportDeviceParamRequest(
            data=json.dumps(param_data or {}, ensure_ascii=False, default=str),
        ))
        _raise_on_failure(resp)
        return _one(resp, dto_cls=CreateAckDTO)

    def create_import_device_param_ack(self, param_data: dict):
        """导入场景下创建设备参数（返回 CreateAckDTO，供显式区分）。"""
        return self.create_import_device_param(param_data)
