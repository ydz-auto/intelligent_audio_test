# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的维度关系与评估维度参数方法 mixin。

从 _param_mixin.py 拆分，包含以下 RPC 方法：
- 维度关系 CRUD（create/update/delete）
- 维度关系批量管理（按 dimension 物理删除/同步）
- 维度关联写操作（soft delete/update attrs）
- 评估维度参数管理（create/delete/find audio）
- 参数映射同步（sync_for_dimension）
"""
from __future__ import annotations

from shared.utils.grpc_json import loads as _loads

from algorithm_service.interfaces.grpc._param_helpers import _success, _failure, _ParamBaseMixin


class _DimensionMixin(_ParamBaseMixin):
    """维度关系 CRUD + 评估维度参数管理 + 参数映射同步方法 mixin。"""

    # ---- 维度关系 CRUD ----

    def CreateDimensionRelation(self, request, context=None):
        """创建算法-维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateDimensionRelationCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateDimensionRelationCommand(data=data)
            result = self.param_command_handler.handle_create_dimension_relation(cmd)
            self._invalidate_cache()
            return _success({"id": result.get("id"), "created": True})
        except Exception as e:
            return _failure(str(e))

    def UpdateDimensionRelation(self, request, context=None):
        """更新算法-维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateDimensionRelationAttrsCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateDimensionRelationAttrsCommand(
                relation_id=request.relation_id,
                data=data,
            )
            self.param_command_handler.handle_update_dimension_relation_attrs(cmd)
            self._invalidate_cache()
            return _success({"id": request.relation_id, "updated": True})
        except Exception as e:
            return _failure(str(e))

    def DeleteDimensionRelation(self, request, context=None):
        """删除算法-维度关联（软删除）。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteDimensionRelationCommand,
            )
            cmd = DeleteDimensionRelationCommand(relation_id=request.relation_id)
            result = self.param_command_handler.handle_delete_dimension_relation(cmd)
            self._invalidate_cache()
            return _success({"id": request.relation_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    # ---- 维度关系批量管理 ----

    def DeleteRelationsByDimension(self, request, context=None):
        """按 dimension_id 物理删除所有算法-维度关联。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_relation_query_repository,
            )
            dimension_relation_query_repository.delete_by_dimension(
                int(request.dimension_id)
            )
            self._invalidate_cache()
            return _success({"dimension_id": int(request.dimension_id), "deleted": True})
        except Exception as e:
            return _failure(str(e))

    def SyncDimensionRelations(self, request, context=None):
        """按 dimension_id 同步算法-维度关联。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_relation_query_repository,
            )
            data = _loads(request.data, []) if not isinstance(request, dict) else request
            dimension_id = int(request.dimension_id)
            dimension_relation_query_repository.sync_by_dimension(dimension_id, data)
            self._invalidate_cache()
            return _success({"dimension_id": dimension_id, "synced": True})
        except Exception as e:
            return _failure(str(e))

    # ---- 维度关联写操作 ----

    def SoftDeleteAlgorithmDimensionRelations(self, request, context=None):
        """按算法批量软删除维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                SoftDeleteAlgorithmDimensionRelationsCommand,
            )
            cmd = SoftDeleteAlgorithmDimensionRelationsCommand(
                algorithm_type=request.algorithm_type
            )
            result = self.param_command_handler.handle_soft_delete_algorithm_dimension_relations(cmd)
            self._invalidate_cache()
            return _success({"algorithm_type": request.algorithm_type, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def UpdateDimensionRelationAttrs(self, request, context=None):
        """更新维度关联属性。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateDimensionRelationAttrsCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateDimensionRelationAttrsCommand(
                relation_id=request.relation_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_dimension_relation_attrs(cmd)
            self._invalidate_cache()
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def SoftDeleteDimensionRelation(self, request, context=None):
        """软删除维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteDimensionRelationCommand,
            )
            cmd = DeleteDimensionRelationCommand(relation_id=request.relation_id)
            result = self.param_command_handler.handle_delete_dimension_relation(cmd)
            self._invalidate_cache()
            return _success({"id": request.relation_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    # ---- 评估维度参数管理 ----

    def CreateDimensionParam(self, request, context=None):
        """创建单条评估维度参数。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            result = dimension_param_repository.create(data)
            self._invalidate_cache()
            return _success({"id": result.get("id"), "created": True})
        except Exception as e:
            return _failure(str(e))

    def DeleteDimensionParamsByDirection(self, request, context=None):
        """按 dimension_id + param_direction 物理删除评估维度参数。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            dimension_param_repository.delete_by_dimension_and_direction(
                int(request.dimension_id), request.param_direction
            )
            self._invalidate_cache()
            return _success({
                "dimension_id": int(request.dimension_id),
                "param_direction": request.param_direction,
                "deleted": True,
            })
        except Exception as e:
            return _failure(str(e))

    def FindAudioDimensionIds(self, request, context=None):
        """查询需要音频文件参数的维度 ID 集合。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            dim_ids = _loads(request.dimension_ids, []) if not isinstance(request, dict) else request
            if not dim_ids:
                return _success({"audio_dimension_ids": []})
            result = dimension_param_repository.find_audio_dimension_ids(dim_ids)
            return _success({"audio_dimension_ids": result})
        except Exception as e:
            return _failure(str(e))

    # ---- 参数映射同步 ----

    def SyncParamMappings(self, request, context=None):
        """同步 ParamMapping。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                param_mapping_query_repository,
            )
            dimension_id = int(request.dimension_id)
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            params = data.get("params", [])
            direction = data.get("direction", "output")
            algorithm_type = data.get("algorithm_type", "voice_llm")

            if params is None:
                return _success({"dimension_id": dimension_id, "synced": True})

            params = self._normalize_param_list(params)
            param_mapping_query_repository.sync_for_dimension(
                dimension_id, params, direction, algorithm_type
            )
            self._invalidate_cache()
            return _success({"dimension_id": dimension_id, "synced": True})
        except Exception as e:
            return _failure(str(e))

    @staticmethod
    def _normalize_param_list(params):
        """将参数归一化为 list（字符串尝试 JSON 解析，非 list 则置空）。"""
        import json as _json
        if isinstance(params, str):
            try:
                params = _json.loads(params)
            except _json.JSONDecodeError:
                params = []
        if not isinstance(params, list):
            params = []
        return params
