# -*- coding: utf-8 -*-
"""algorithm_service HTTP API 路由（FastAPI APIRouter 骨架）。

归属：algorithm_service.interfaces.api

路由清单：
- 算法分组 CRUD：
  POST   /api/algorithm/groups           创建算法组
  GET    /api/algorithm/groups           列出算法组
  GET    /api/algorithm/groups/<id>      获取算法组
  PUT    /api/algorithm/groups/<id>      更新算法组
  DELETE /api/algorithm/groups/<id>      删除算法组
- 算法定义 CRUD 及状态变更：
  POST   /api/algorithm/definitions              创建算法定义
  GET    /api/algorithm/definitions              列出算法定义
  GET    /api/algorithm/definitions/<id>         获取算法定义
  PUT    /api/algorithm/definitions/<id>         更新算法定义
  DELETE /api/algorithm/definitions/<id>         删除算法定义
  POST   /api/algorithm/definitions/<id>/activate   激活算法
  POST   /api/algorithm/definitions/<id>/deprecate   废弃算法

每个路由调用 application 层 AlgorithmCommandHandler / AlgorithmQueryHandler。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from algorithm_service.application.commands.algorithm_commands import (
    ActivateAlgorithmCommand,
    CreateAlgorithmDefinitionCommand,
    CreateAlgorithmGroupCommand,
    DeleteAlgorithmDefinitionCommand,
    DeleteAlgorithmGroupCommand,
    DeprecateAlgorithmCommand,
    UpdateAlgorithmDefinitionCommand,
    UpdateAlgorithmGroupCommand,
)
from algorithm_service.application.handlers.algorithm_handlers import (
    AlgorithmCommandHandler,
    AlgorithmQueryHandler,
)
from algorithm_service.application.queries.algorithm_queries import (
    GetAlgorithmDefinitionByTypeQuery,
    GetAlgorithmDefinitionQuery,
    GetAlgorithmGroupQuery,
    ListActiveAlgorithmDefinitionsQuery,
    ListAlgorithmDefinitionsByGroupQuery,
    ListAlgorithmGroupsQuery,
)

# APIRouter 实例，供 api_gateway 或 FastAPI app 注册
router = APIRouter(prefix="/api/algorithm", tags=["algorithm"])

# Handler 单例（进程级复用）
_command_handler = AlgorithmCommandHandler()
_query_handler = AlgorithmQueryHandler()


# ========== Pydantic 请求模型 ==========


class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None
    algorithm_type: Optional[str] = None


class UpdateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None


class CreateDefinitionRequest(BaseModel):
    group_id: Optional[int] = None
    name: str
    algorithm_type: str
    description: Optional[str] = None


class UpdateDefinitionRequest(BaseModel):
    name: str
    description: Optional[str] = None


def _group_to_dict(aggregate) -> Dict[str, Any]:
    """将 AlgorithmGroupAggregate 序列化为 dict"""
    return {
        "id": aggregate.id,
        "name": aggregate.name,
        "description": aggregate.description,
        "algorithm_type": aggregate.algorithm_type,
    }


def _definition_to_dict(aggregate) -> Dict[str, Any]:
    """将 AlgorithmDefinitionAggregate 序列化为 dict"""
    return {
        "id": aggregate.id,
        "group_id": aggregate.group_id,
        "name": aggregate.name,
        "algorithm_type": aggregate.algorithm_type,
        "description": aggregate.description,
        "version": aggregate.version,
        "status": str(aggregate.status) if aggregate.status else None,
    }


# ========== 算法分组路由 ==========

@router.post("/groups")
def create_group(body: CreateGroupRequest):
    """创建算法组

    Body: {"name": str, "description": str?, "algorithm_type": str?}
    """
    try:
        cmd = CreateAlgorithmGroupCommand(
            name=body.name,
            description=body.description,
            algorithm_type=body.algorithm_type,
        )
        new_id = _command_handler.handle_create_group(cmd)
        return {"success": True, "message": "ok", "data": {"id": new_id, "name": cmd.name}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/groups")
def list_groups(
    page: int = Query(1),
    page_size: int = Query(20),
):
    """列出算法组

    Query: page=1&page_size=20
    """
    try:
        query = ListAlgorithmGroupsQuery(page=page, page_size=page_size)
        aggregates, total = _query_handler.handle_list_groups(query)
        items = [_group_to_dict(agg) for agg in aggregates]
        return {"success": True, "message": "ok", "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/groups/{group_id}")
def get_group(group_id: int):
    """获取算法组"""
    try:
        query = GetAlgorithmGroupQuery(id=group_id)
        aggregate = _query_handler.handle_get_group(query)
        if aggregate is None:
            raise HTTPException(status_code=404, detail=f"算法分组 id={group_id} 不存在")
        return {"success": True, "message": "ok", "data": _group_to_dict(aggregate)}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.put("/groups/{group_id}")
def update_group(group_id: int, body: UpdateGroupRequest):
    """更新算法组

    Body: {"name": str, "description": str?}
    """
    try:
        cmd = UpdateAlgorithmGroupCommand(
            id=group_id,
            name=body.name,
            description=body.description,
        )
        _command_handler.handle_update_group(cmd)
        return {"success": True, "message": "ok", "data": {"id": group_id, "updated": True}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int):
    """删除算法组（软删除）"""
    try:
        cmd = DeleteAlgorithmGroupCommand(id=group_id)
        ok = _command_handler.handle_delete_group(cmd)
        return {"success": True, "message": "ok", "data": {"id": group_id, "deleted": ok}}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ========== 算法定义路由 ==========

@router.post("/definitions")
def create_definition(body: CreateDefinitionRequest):
    """创建算法定义

    Body: {"group_id": int?, "name": str, "algorithm_type": str, "description": str?}
    """
    try:
        cmd = CreateAlgorithmDefinitionCommand(
            group_id=body.group_id,
            name=body.name,
            algorithm_type=body.algorithm_type,
            description=body.description,
        )
        new_id = _command_handler.handle_create_definition(cmd)
        return {"success": True, "message": "ok", "data": {"id": new_id, "name": cmd.name}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/definitions")
def list_definitions(
    group_id: Optional[int] = Query(None),
    active: Optional[int] = Query(None),
    algorithm_type: Optional[str] = Query(None),
):
    """列出算法定义

    Query: group_id=int（按分组过滤）/ active=1（仅上线）/ algorithm_type=str
    """
    try:
        if active:
            query = ListActiveAlgorithmDefinitionsQuery()
            aggregates = _query_handler.handle_list_active_definitions(query)
        elif group_id is not None:
            query = ListAlgorithmDefinitionsByGroupQuery(group_id=group_id)
            aggregates = _query_handler.handle_list_definitions_by_group(query)
        elif algorithm_type:
            query = GetAlgorithmDefinitionByTypeQuery(algorithm_type=algorithm_type)
            aggregate = _query_handler.handle_get_definition_by_type(query)
            aggregates = [aggregate] if aggregate else []
        else:
            # 默认列出全部上线算法定义
            query = ListActiveAlgorithmDefinitionsQuery()
            aggregates = _query_handler.handle_list_active_definitions(query)

        items = [_definition_to_dict(agg) for agg in aggregates]
        return {"success": True, "message": "ok", "data": {"items": items}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/definitions/{definition_id}")
def get_definition(definition_id: int):
    """获取算法定义"""
    try:
        query = GetAlgorithmDefinitionQuery(id=definition_id)
        aggregate = _query_handler.handle_get_definition(query)
        if aggregate is None:
            raise HTTPException(status_code=404, detail=f"算法定义 id={definition_id} 不存在")
        return {"success": True, "message": "ok", "data": _definition_to_dict(aggregate)}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.put("/definitions/{definition_id}")
def update_definition(definition_id: int, body: UpdateDefinitionRequest):
    """更新算法定义

    Body: {"name": str, "description": str?}
    """
    try:
        cmd = UpdateAlgorithmDefinitionCommand(
            id=definition_id,
            name=body.name,
            description=body.description,
        )
        _command_handler.handle_update_definition(cmd)
        return {"success": True, "message": "ok", "data": {"id": definition_id, "updated": True}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.delete("/definitions/{definition_id}")
def delete_definition(definition_id: int):
    """删除算法定义（软删除）"""
    try:
        cmd = DeleteAlgorithmDefinitionCommand(id=definition_id)
        ok = _command_handler.handle_delete_definition(cmd)
        return {"success": True, "message": "ok", "data": {"id": definition_id, "deleted": ok}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/definitions/{definition_id}/activate")
def activate_algorithm(definition_id: int):
    """激活算法（状态置为 active）"""
    try:
        cmd = ActivateAlgorithmCommand(id=definition_id)
        _command_handler.handle_activate_algorithm(cmd)
        return {"success": True, "message": "ok", "data": {"id": definition_id, "status": "active"}}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/definitions/{definition_id}/deprecate")
def deprecate_algorithm(definition_id: int):
    """废弃算法（状态置为 deprecated）"""
    try:
        cmd = DeprecateAlgorithmCommand(id=definition_id)
        _command_handler.handle_deprecate_algorithm(cmd)
        return {"success": True, "message": "ok", "data": {"id": definition_id, "status": "deprecated"}}
    except Exception as e:
        return {"success": False, "message": str(e)}
