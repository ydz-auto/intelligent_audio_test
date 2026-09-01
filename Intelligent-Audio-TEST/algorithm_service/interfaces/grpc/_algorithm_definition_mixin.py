# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的算法定义/分组/导入/事务方法 mixin。

从 _param_mixin.py 拆分，包含以下 RPC 方法：
- 算法定义写操作（create/update attrs/soft delete）
- 算法分组写操作（create/update attrs/soft delete）
- 导入/重载（ImportAlgorithms/ReloadAlgorithmConfig）
- 事务控制（commit/rollback/flush）
"""
from __future__ import annotations

from shared.utils.grpc_json import loads as _loads

from algorithm_service.interfaces.grpc._param_helpers import _success, _failure, _ParamBaseMixin


class _AlgorithmDefinitionMixin(_ParamBaseMixin):
    """算法定义/分组 CRUD + 导入/重载 + 事务控制方法 mixin。"""

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
            )
            new_id = self.command_handler.handle_create_definition(cmd)
            self._invalidate_cache()
            return _success({"id": new_id, "name": cmd.name})
        except Exception as e:
            return _failure(str(e))

    def UpdateAlgorithmDefinitionAttrs(self, request, context=None):
        """更新算法定义可变字段。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                UpdateAlgorithmDefinitionCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateAlgorithmDefinitionCommand(
                id=int(request.algorithm_id),
                name=data.get("name", ""),
                description=data.get("description"),
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
