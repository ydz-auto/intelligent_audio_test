# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的算法定义/分组/导入/事务方法 mixin。

从 _param_mixin.py 拆分，包含以下 RPC 方法：
- 算法定义写操作（create/update attrs/soft delete）
- 算法定义全量保存（SaveAlgorithmDefinition + 草稿保存/恢复，INT-589）
- 算法分组写操作（create/update attrs/soft delete）
- 导入/重载（ImportAlgorithms/ReloadAlgorithmConfig）
- 事务控制（commit/rollback/flush）
"""
from __future__ import annotations

from typing import Any, Dict

from shared.proto import algorithm_service_pb2 as _pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from algorithm_service.interfaces.grpc.mixins.param_helpers import _success, _failure, _ParamBaseMixin
from algorithm_service.domain.value_objects.algorithm_save_code import AlgorithmSaveCode


def _success_with_code(data: Any, message: str, code: str):
    """成功响应（带机器可读 code）。"""
    return _pb.AlgorithmResponse(
        success=True,
        message=message,
        data=_dumps(data) if data is not None else "",
        code=code,
    )


def _failure_with_code(message: str, code: str, data: Any = None):
    """失败响应（带机器可读 code）。"""
    return _pb.AlgorithmResponse(
        success=False,
        message=message,
        data=_dumps(data) if data is not None else "",
        code=code,
    )


class _AlgorithmDefinitionMixin(_ParamBaseMixin):
    """算法定义/分组 CRUD + 导入/重载 + 全量保存 + 事务控制方法 mixin。"""

    # ---- 算法定义全量保存（INT-589）----

    def SaveAlgorithmDefinition(self, request, context=None):
        """算法定义全量保存（聚合事务 + 乐观锁）。

        请求字段（SaveAlgorithmDefinitionRequest.data JSON）：
        id（可选）/ algorithm_type / name / group_id / description / status /
        icon / display_order / device_params / api_params / case_params /
        reference_params / mappings / associated_dimensions /
        expected_updated_at（更新路径必填，乐观锁版本）

        返回 AlgorithmResponse.code：
        - SAVED：新建成功
        - OK：更新成功
        - CONFLICT：乐观锁冲突（并发双写，前端提示「有他人改动，请刷新」）
        - VALIDATION_FAILED：校验失败（必填缺失 / 维度不存在 / type 已存在）
        """
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            from algorithm_service.application.commands.algorithm_commands import (
                SaveAlgorithmDefinitionCommand,
            )
            cmd = SaveAlgorithmDefinitionCommand(
                id=data.get('id'),
                algorithm_type=data.get('algorithm_type') or data.get('type') or '',
                name=data.get('name', ''),
                group_id=data.get('group_id'),
                description=data.get('description'),
                status=data.get('status'),
                icon=data.get('icon'),
                display_order=data.get('display_order'),
                device_params=data.get('device_params') or [],
                api_params=data.get('api_params') or [],
                case_params=data.get('case_params') or [],
                reference_params=data.get('reference_params') or [],
                mappings=data.get('mappings'),
                associated_dimensions=data.get('associated_dimensions') or [],
                expected_updated_at=data.get('expected_updated_at'),
            )
            result = self.command_handler.handle_save_definition(cmd)
            code = result.get('code')
            if code == AlgorithmSaveCode.CONFLICT.value:
                return _failure_with_code(
                    '有他人改动，请刷新后重试', AlgorithmSaveCode.CONFLICT.value, result
                )
            self._invalidate_cache()
            return _success_with_code(result, 'ok', code)
        except Exception as e:
            return _failure_with_code(
                str(e), AlgorithmSaveCode.VALIDATION_FAILED.value
            )

    def SaveAlgorithmDefinitionDraft(self, request, context=None):
        """草稿自动保存（30s 快照，不落正式六表）。

        请求字段（SaveAlgorithmDefinitionDraftRequest.data JSON）：
        algorithm_type + 完整定义快照（基础字段 + 六类子实体）。

        响应 data：{saved: true, algorithm_type, saved_at}，
        saved_at 为服务端最后保存时间（draft PO.updated_at，ISO，INT-683），
        供前端 footer「上次保存 HH:mm:ss」消费。
        """
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            algorithm_type = data.get('algorithm_type') or data.get('type') or ''
            saved_at = self.command_handler.handle_save_draft(algorithm_type, data)
            resp = {'saved': True, 'algorithm_type': algorithm_type}
            if saved_at is not None:
                resp['saved_at'] = (
                    saved_at.isoformat()
                    if hasattr(saved_at, 'isoformat') else str(saved_at)
                )
            return _success(resp)
        except Exception as e:
            return _failure(str(e))

    def GetAlgorithmDefinitionDraft(self, request, context=None):
        """草稿恢复：读取草稿快照（data 为快照 JSON，无草稿返回空对象）。"""
        try:
            if isinstance(request, dict):
                algorithm_type = request.get('algorithm_type', '')
            else:
                algorithm_type = getattr(request, 'algorithm_type', '')
            snapshot = self.query_handler.handle_get_definition_draft(algorithm_type)
            return _success(snapshot if snapshot is not None else {})
        except Exception as e:
            return _failure(str(e))

    # ---- 导入/重载 ----

    def ImportAlgorithms(self, request, context=None):
        """导入算法定义（批量）。"""
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            return _failure("ImportAlgorithms 暂未实现", {"received_keys": list(data.keys())})
        except Exception as e:
            return _failure(str(e))

    def ReloadAlgorithmConfig(self, request, context=None):
        """重新加载算法配置（热更新）。"""
        try:
            from algorithm_service.infrastructure.persistence.config_cache import get_config_cache
            cache = get_config_cache()
            reloaded = cache.reload()
            return _success({
                "success": True,
                "message": f"Config reloaded: {reloaded}",
                "reload_time": cache.get_last_reload_time(),
            })
        except Exception as e:
            return _failure(str(e))

    # ---- 算法定义写操作 ----

    def CreateAlgorithmDefinition(self, request, context=None):
        """创建算法定义。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                CreateAlgorithmDefinitionCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateAlgorithmDefinitionCommand(
                group_id=data.get("group_id"),
                name=data.get("name", ""),
                algorithm_type=data.get("algorithm_type") or data.get("type") or "",
                description=data.get("description"),
                status=data.get("status"),
                icon=data.get("icon"),
                display_order=data.get("display_order"),
            )
            new_id = self.command_handler.handle_create_definition(cmd)
            self._invalidate_cache()
            return _success({"id": new_id, "name": cmd.name})
        except Exception as e:
            return _failure(str(e))

    def UpdateAlgorithmDefinitionAttrs(self, request, context=None):
        """更新算法定义可变字段（PATCH 语义：data 中未携带的字段不改动现值）。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                UpdateAlgorithmDefinitionCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateAlgorithmDefinitionCommand(
                id=int(request.algorithm_id),
                name=data.get("name"),
                description=data.get("description"),
                group_id=data.get("group_id"),
                status=data.get("status"),
                icon=data.get("icon"),
                display_order=data.get("display_order"),
            )
            self.command_handler.handle_update_definition(cmd)
            self._invalidate_cache()
            return _success({"id": cmd.id, "updated": True})
        except Exception as e:
            return _failure(str(e))

    def SoftDeleteAlgorithm(self, request, context=None):
        """软删除算法定义。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                DeleteAlgorithmDefinitionCommand,
            )
            cmd = DeleteAlgorithmDefinitionCommand(id=int(request.algorithm_id))
            ok = self.command_handler.handle_delete_definition(cmd)
            self._invalidate_cache()
            return _success({"id": cmd.id, "deleted": ok})
        except Exception as e:
            return _failure(str(e))

    # ---- 算法分组写操作 ----

    def CreateGroup(self, request, context=None):
        """创建算法分组。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                CreateAlgorithmGroupCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateAlgorithmGroupCommand(
                name=data.get("name", ""),
                description=data.get("description"),
                algorithm_type=data.get("algorithm_type"),
                icon=data.get("icon"),
                display_order=data.get("display_order", 0),
            )
            new_id = self.command_handler.handle_create_group(cmd)
            self._invalidate_cache()
            return _success({"id": new_id, "name": cmd.name})
        except Exception as e:
            return _failure(str(e))

    def UpdateGroupAttrs(self, request, context=None):
        """更新算法分组可变字段。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                UpdateAlgorithmGroupCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            group_id = request.group_id or data.get("group_id") or data.get("id")
            cmd = UpdateAlgorithmGroupCommand(
                id=int(group_id),
                name=data.get("name", ""),
                description=data.get("description"),
                icon=data.get("icon"),
                display_order=data.get("display_order"),
            )
            self.command_handler.handle_update_group(cmd)
            self._invalidate_cache()
            return _success({"id": cmd.id, "updated": True})
        except Exception as e:
            return _failure(str(e))

    def SoftDeleteGroup(self, request, context=None):
        """软删除算法分组。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                DeleteAlgorithmGroupCommand,
            )
            cmd = DeleteAlgorithmGroupCommand(id=int(request.group_id))
            ok = self.command_handler.handle_delete_group(cmd)
            self._invalidate_cache()
            return _success({"id": cmd.id, "deleted": ok})
        except Exception as e:
            return _failure(str(e))

    # ---- 事务控制 ----

    def CommitTransaction(self, request, context=None):
        """提交当前事务。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import commit_transaction
            commit_transaction()
            return _success({"committed": True})
        except Exception as e:
            return _failure(str(e))

    def RollbackTransaction(self, request, context=None):
        """回滚当前事务。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import rollback_transaction
            rollback_transaction()
            return _success({"rolled_back": True})
        except Exception as e:
            return _failure(str(e))

    def FlushTransaction(self, request, context=None):
        """flush 当前 session。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import flush_transaction
            flush_transaction()
            return _success({"flushed": True})
        except Exception as e:
            return _failure(str(e))
