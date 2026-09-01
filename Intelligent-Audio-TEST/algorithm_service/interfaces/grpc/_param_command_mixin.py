# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的参数写操作方法 mixin。

从 _param_mixin.py 拆分，包含以下写 RPC 方法：
- 设备/API 参数写操作（create/update/delete/find）
- 用例专属参数写操作
- 参考参数写操作
- 参数映射写操作（create/update/delete/get）
- 批量删除算法定义
- 导入场景下创建设备参数
"""
from __future__ import annotations

from shared.utils.grpc_json import loads as _loads

from algorithm_service.interfaces.grpc._param_helpers import _success, _failure, _ParamBaseMixin


class _ParamCommandMixin(_ParamBaseMixin):
    """设备/API/用例/参考参数与参数映射的写操作方法 mixin。"""

    # ---- 设备/API 参数写操作 ----

    def CreateParam(self, request, context=None):
        """创建设备参数或 API 参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateParamCommand(
                data=data,
                param_type_source=data.get("param_type_source") or "device",
            )
            result = self.param_command_handler.handle_create_param(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateParam(self, request, context=None):
        """更新设备参数或 API 参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateParamCommand(
                param_id=request.param_id,
                data=data,
                param_type_source="",
            )
            result = self.param_command_handler.handle_update_param(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteParam(self, request, context=None):
        """软删除设备参数或 API 参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteParamCommand,
            )
            cmd = DeleteParamCommand(
                param_id=request.param_id,
                param_type_source="",
            )
            result = self.param_command_handler.handle_delete_param(cmd)
            self._invalidate_cache()
            return _success({"id": request.param_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def FindParamByCode(self, request, context=None):
        """按算法/参数代码/方向查找未删除的设备参数或 API 参数。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindParamByCodeQuery,
            )
            query = FindParamByCodeQuery(
                algorithm_type=request.algorithm_type,
                param_code=request.param_code,
                direction=request.direction,
                param_type_source=request.param_type_source or "device",
            )
            result = self.param_query_handler.handle_find_param_by_code(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 用例参数写操作 ----

    def CreateCaseParam(self, request, context=None):
        """创建用例专属参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateCaseParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateCaseParamCommand(data=data)
            result = self.param_command_handler.handle_create_case_param(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateCaseParam(self, request, context=None):
        """更新用例专属参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateCaseParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateCaseParamCommand(
                param_id=request.param_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_case_param(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteCaseParam(self, request, context=None):
        """软删除用例专属参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteCaseParamCommand,
            )
            cmd = DeleteCaseParamCommand(param_id=request.param_id)
            result = self.param_command_handler.handle_delete_case_param(cmd)
            self._invalidate_cache()
            return _success({"id": request.param_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def FindCaseParamByCode(self, request, context=None):
        """按算法/参数代码查找用例专属参数（可包含软删项）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindCaseParamByCodeQuery,
            )
            query = FindCaseParamByCodeQuery(
                algorithm_type=request.algorithm_type,
                param_code=request.param_code,
                include_deleted=bool(request.include_deleted),
            )
            result = self.param_query_handler.handle_find_case_param_by_code(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 参考参数写操作 ----

    def CreateReferenceParam(self, request, context=None):
        """创建参考参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateReferenceParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateReferenceParamCommand(data=data)
            result = self.param_command_handler.handle_create_reference_param(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateReferenceParam(self, request, context=None):
        """更新参考参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateReferenceParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateReferenceParamCommand(
                param_id=request.param_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_reference_param(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteReferenceParam(self, request, context=None):
        """软删除参考参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteReferenceParamCommand,
            )
            cmd = DeleteReferenceParamCommand(param_id=request.param_id)
            result = self.param_command_handler.handle_delete_reference_param(cmd)
            self._invalidate_cache()
            return _success({"id": request.param_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def FindReferenceParam(self, request, context=None):
        """按算法/代码查找未删除的参考参数。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindReferenceParamQuery,
            )
            query = FindReferenceParamQuery(
                algorithm_type=request.algorithm_type,
                code=request.code,
            )
            result = self.param_query_handler.handle_find_reference_param(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 参数映射写操作 ----

    def CreateMapping(self, request, context=None):
        """创建参数映射。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateMappingCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateMappingCommand(data=data)
            result = self.param_command_handler.handle_create_mapping(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateMapping(self, request, context=None):
        """更新参数映射。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateMappingCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateMappingCommand(
                mapping_id=request.mapping_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_mapping(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteMapping(self, request, context=None):
        """软删除参数映射。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteMappingCommand,
            )
            cmd = DeleteMappingCommand(mapping_id=request.mapping_id)
            result = self.param_command_handler.handle_delete_mapping(cmd)
            self._invalidate_cache()
            return _success({"id": request.mapping_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def GetMapping(self, request, context=None):
        """按 ID 获取未删除的参数映射。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                GetMappingQuery,
            )
            query = GetMappingQuery(mapping_id=request.mapping_id)
            result = self.param_query_handler.handle_get_mapping(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 导入场景写操作 ----

    def CreateImportDeviceParam(self, request, context=None):
        """导入场景下创建设备参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateImportDeviceParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateImportDeviceParamCommand(data=data)
            result = self.param_command_handler.handle_create_import_device_param(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def BulkDeleteAlgorithms(self, request, context=None):
        """批量软删除算法定义。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                BulkDeleteAlgorithmsCommand,
            )
            algorithm_types = _loads(request.algorithm_types, [])
            if not isinstance(algorithm_types, list):
                algorithm_types = []
            cmd = BulkDeleteAlgorithmsCommand(algorithm_types=algorithm_types)
            result = self.param_command_handler.handle_bulk_delete_algorithms(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))
