# -*- coding: utf-8 -*-
"""收藏 / 回收站路由（INT-141）。

收藏（per-user）：POST/DELETE /{entity}/{id}/favorite；收藏 ID 列表 GET /favorites。
回收站：列表走各实体列表接口的 favorite/deleted 过滤参数；恢复（单个+批量）
与彻底删除 purge 走本路由；purge 权限 admin/owner 由服务端按 metadata 校验。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List

from api_gateway.application.services.favorite_trash_service import FavoriteTrashService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_auth, require_permission

router = APIRouter()


class _IdsBody(BaseModel):
    ids: List = []


def _favorite_response(result: dict):
    """收藏/取消收藏统一响应：业务失败按 code 映射 HTTP 状态。"""
    code = result.get('code', 500)
    if code == 200 or 'data' in result:
        return to_response(({'success': True, 'message': 'ok', 'data': result.get('data')}, 200))
    status = {400: 400, 401: 401, 403: 403, 404: 404}.get(code, 500)
    return to_response(({'success': False, 'message': result.get('message', '操作失败')}, status))


# ==================== 收藏 ID 列表 ====================

@router.get('/favorites')
def list_favorites(entity_type: str = '', _: None = Depends(require_auth)):
    result = FavoriteTrashService.list_favorite_ids(entity_type)
    if 'code' in result:
        return to_response(({'success': False, 'message': result.get('message', '')},
                            result.get('code', 500)))
    return to_response(({'success': True, 'message': 'ok', 'data': result.get('data')}, 200))


# ==================== 任务 ====================

@router.post('/tasks/{task_id}/favorite')
def favorite_task(task_id: int, _: None = require_permission('task:read')):
    return _favorite_response(FavoriteTrashService.favorite('task', task_id))


@router.delete('/tasks/{task_id}/favorite')
def unfavorite_task(task_id: int, _: None = require_permission('task:read')):
    return _favorite_response(FavoriteTrashService.unfavorite('task', task_id))


@router.post('/tasks/{task_id}/restore')
def restore_task(task_id: int, _: None = require_permission('task:delete')):
    result = FavoriteTrashService.restore('task', [task_id])
    return _favorite_response(result)


@router.post('/tasks/restore')
def restore_tasks_batch(body: _IdsBody, _: None = require_permission('task:delete')):
    return _favorite_response(FavoriteTrashService.restore('task', body.ids))


@router.delete('/tasks/{task_id}/purge')
def purge_task(task_id: int, _: None = require_permission('task:delete')):
    return _favorite_response(FavoriteTrashService.purge('task', [task_id]))


@router.post('/tasks/purge')
def purge_tasks_batch(body: _IdsBody, _: None = require_permission('task:delete')):
    return _favorite_response(FavoriteTrashService.purge('task', body.ids))


# ==================== 测试用例 ====================

@router.post('/testcases/{tc_id}/favorite')
def favorite_testcase(tc_id: str, _: None = require_permission('testcase:read')):
    return _favorite_response(FavoriteTrashService.favorite('testcase', tc_id))


@router.delete('/testcases/{tc_id}/favorite')
def unfavorite_testcase(tc_id: str, _: None = require_permission('testcase:read')):
    return _favorite_response(FavoriteTrashService.unfavorite('testcase', tc_id))


@router.post('/testcases/{tc_id}/restore')
def restore_testcase(tc_id: str, _: None = require_permission('testcase:delete')):
    return _favorite_response(FavoriteTrashService.restore('testcase', [tc_id]))


@router.post('/testcases/restore')
def restore_testcases_batch(body: _IdsBody, _: None = require_permission('testcase:delete')):
    return _favorite_response(FavoriteTrashService.restore('testcase', body.ids))


@router.delete('/testcases/{tc_id}/purge')
def purge_testcase(tc_id: str, _: None = require_permission('testcase:delete')):
    return _favorite_response(FavoriteTrashService.purge('testcase', [tc_id]))


@router.post('/testcases/purge')
def purge_testcases_batch(body: _IdsBody, _: None = require_permission('testcase:delete')):
    return _favorite_response(FavoriteTrashService.purge('testcase', body.ids))


# ==================== 报告 ====================

@router.post('/reports/{report_id}/favorite')
def favorite_report(report_id: int, _: None = require_permission('report:read')):
    return _favorite_response(FavoriteTrashService.favorite('report', report_id))


@router.delete('/reports/{report_id}/favorite')
def unfavorite_report(report_id: int, _: None = require_permission('report:read')):
    return _favorite_response(FavoriteTrashService.unfavorite('report', report_id))


@router.post('/reports/{report_id}/restore')
def restore_report(report_id: int, _: None = require_permission('report:delete')):
    return _favorite_response(FavoriteTrashService.restore('report', [report_id]))


@router.post('/reports/restore')
def restore_reports_batch(body: _IdsBody, _: None = require_permission('report:delete')):
    return _favorite_response(FavoriteTrashService.restore('report', body.ids))


@router.delete('/reports/{report_id}/purge')
def purge_report(report_id: int, _: None = require_permission('report:delete')):
    return _favorite_response(FavoriteTrashService.purge('report', [report_id]))


@router.post('/reports/purge')
def purge_reports_batch(body: _IdsBody, _: None = require_permission('report:delete')):
    return _favorite_response(FavoriteTrashService.purge('report', body.ids))
