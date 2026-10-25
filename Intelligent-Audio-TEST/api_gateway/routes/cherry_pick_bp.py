# -*- coding: utf-8 -*-
"""挑选合并路由（INT-339，设计文档 §8 接口草案）。

前缀 /tasks/cherry-picks（设计文档 §8 契约路径；页面文案一律中文，
路由路径为技术标识不受文案红线约束）。

权限点（seed_rbac.py INT-339 新增）：task:cherry_pick 挑选合并全操作；
查询侧对齐任务列表口径放行 task:read（挑选器数据源即任务结果只读）。

挂载：app.py 中 include_router(cherry_pick_router, prefix='/api/v1/tasks/cherry-picks')。
"""
from fastapi import APIRouter

from api_gateway.application.services.task.cherry_pick_service import CherryPickService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()

# ---- 购物车（per-user，x-user-id metadata 透传）----

@router.get('/cart')
def get_cart(_: None = require_permission('task:read')):
    return to_response(CherryPickService.get_cart())


@router.post('/cart/items')
def add_cart_items(_: None = require_permission('task:cherry_pick')):
    return to_response(CherryPickService.add_cart_items())


@router.post('/cart/items/remove')
def remove_cart_items(_: None = require_permission('task:cherry_pick')):
    return to_response(CherryPickService.remove_cart_items())


@router.delete('/cart/items')
def clear_cart(_: None = require_permission('task:cherry_pick')):
    return to_response(CherryPickService.clear_cart())


# ---- 挑选集 ----

@router.post('/cart/save-as-set')
def save_as_set(_: None = require_permission('task:cherry_pick')):
    return to_response(CherryPickService.save_set())


@router.get('/sets')
def list_sets(_: None = require_permission('task:read')):
    return to_response(CherryPickService.list_sets())


@router.get('/sets/{set_id}')
def get_set(set_id: int, _: None = require_permission('task:read')):
    return to_response(CherryPickService.get_set(set_id))


@router.delete('/sets/{set_id}')
def delete_set(set_id: int, _: None = require_permission('task:cherry_pick')):
    return to_response(CherryPickService.delete_set(set_id))


@router.post('/sets/{set_id}/to-cart')
def restore_set_to_cart(set_id: int, _: None = require_permission('task:cherry_pick')):
    return to_response(CherryPickService.restore_set_to_cart(set_id))


# ---- 挑选候选查询（S2 多条件 AND）----

@router.get('/candidates')
def list_candidates(_: None = require_permission('task:read')):
    return to_response(CherryPickService.list_candidates())


# INT-1510 §8.2：阶段 2 候选树聚合（任务→用例→设备/API→result_type，节点计数 +
# result_id 集，服务端一次聚合）。网关只做参数校验（task_ids 必填 1–200）与信封。
@router.get('/candidates/tree')
def list_candidate_tree(_: None = require_permission('task:read')):
    return to_response(CherryPickService.list_candidate_tree())


# INT-1496 §8.1：挑选向导阶段 1「可挑选任务清单」（任务级聚合，服务端分页；
# 替代 candidates 首页 200 行的客户端聚合）。网关只做参数校验与信封，不做聚合。
@router.get('/pickable-tasks')
def list_pickable_tasks(_: None = require_permission('task:read')):
    return to_response(CherryPickService.list_pickable_tasks())


# INT-577 §11-4：全选当前筛选——返回当前筛选命中全部 result_id 集合（跨页全选语义）
@router.post('/candidates/select-all')
def select_all_candidates(_: None = require_permission('task:read')):
    return to_response(CherryPickService.select_all_candidates())


# ---- 下单（三出口 + 预览）----

@router.post('/preview')
def preview(_: None = require_permission('task:read')):
    return to_response(CherryPickService.preview())


@router.post('/cart/checkout')
def checkout(_: None = require_permission('task:cherry_pick')):
    return to_response(CherryPickService.checkout())


# ---- 溯源（§8 GET /tasks/{taskId}/cherry-pick-source）----

@router.get('/{task_id}/source')
def get_source(task_id: int, _: None = require_permission('task:read')):
    return to_response(CherryPickService.get_source(task_id))
