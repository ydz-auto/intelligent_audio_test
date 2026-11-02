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

import logging

from shared.utils.grpc_json import loads as _loads

from algorithm_service.interfaces.grpc.mixins.param_helpers import (
    _success,
    _failure,
    _ParamBaseMixin,
    _normalize_dimension_param_data,
)

logger = logging.getLogger(__name__)


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
            self._invalidate_cache(
                algorithm_types=[data.get('algorithm_type')],
                dimension_ids=[data.get('dimension_id')],
            )
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
            self._invalidate_cache(
                dimension_ids=[data.get('dimension_id')],
            )
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
            self._invalidate_cache(
                algorithm_types=[
                    item.get('algorithm_type') for item in data
                    if isinstance(item, dict)
                ],
                dimension_ids=[dimension_id],
            )
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
            self._invalidate_cache(
                dimension_ids=[data.get('dimension_id')],
            )
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
        """创建单条评估维度参数。

        写侧先归一数值/布尔字段（INT-1683）：空串 → NULL，非法值直接失败，
        不再让数据库解析报错把整条参数静默丢弃。
        """
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            data = _normalize_dimension_param_data(data)
            result = dimension_param_repository.create(data)
            self._invalidate_cache(
                dimension_ids=[data.get('dimension_id')],
            )
            return _success({"id": result.get("id"), "created": True})
        except Exception as e:
            logger.warning("CreateDimensionParam 失败: %s", e)
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
            self._invalidate_cache(
                dimension_ids=[int(request.dimension_id)],
            )
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
            # INT-2355：algorithm_type 必须来自调用方显式关联的算法，缺失时
            # 报错而不是回落到真实算法名（否则会写入在用算法的映射）。
            algorithm_type = (data.get("algorithm_type") or "").strip()

            if params is None:
                return _success({"dimension_id": dimension_id, "synced": True})

            if not algorithm_type:
                logger.warning(
                    "SyncParamMappings 缺少 algorithm_type，拒绝同步: dimension_id=%s",
                    dimension_id,
                )
                return _failure("缺少 algorithm_type，未同步参数映射")

            params = self._normalize_param_list(params)
            param_mapping_query_repository.sync_for_dimension(
                dimension_id, params, direction, algorithm_type
            )
            self._invalidate_cache(
                algorithm_types=[algorithm_type],
                dimension_ids=[dimension_id],
            )
            return _success({"dimension_id": dimension_id, "synced": True})
        except Exception as e:
            return _failure(str(e))

    def DeleteParamMappingsByDimension(self, request, context=None):
        """软删所有作用域下指向给定维度（树）的 ParamMapping（INT-2353）。

        evaluation_service 删除评估维度后调用，清掉算法级 / API 实例级 /
        设备级三种作用域残留的「指向已删维度」活动映射。
        """
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                param_mapping_query_repository,
            )
            raw = request.dimension_ids
            dim_ids = _loads(raw, []) if isinstance(raw, str) else list(raw or [])
            dim_ids = [int(d) for d in dim_ids if d is not None]
            if not dim_ids:
                return _success({"dimension_ids": [], "deleted": 0})
            # 先取受影响的算法类型（软删后这些行就不再是活动映射），再软删。
            # INT-2353 打回修复：只按 dimension_ids 失效时 config_cache 仅重载
            # evaluation_dimension_params 切片，不会重建 mappings 桶，缓存读路径
            # （/algorithm/mappings、评估取值）会继续返回指向已删维度的旧映射。
            # 按受影响算法类型 + 维度一起失效，两个切片同步刷新。
            algorithm_types = (
                param_mapping_query_repository.list_algorithm_types_by_dimension_ids(
                    dim_ids)
            )
            deleted = param_mapping_query_repository.delete_by_dimension_ids(dim_ids)
            self._invalidate_cache(
                algorithm_types=algorithm_types,
                dimension_ids=dim_ids,
            )
            return _success({
                "dimension_ids": dim_ids,
                "algorithm_types": algorithm_types,
                "deleted": deleted,
            })
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
