# -*- coding: utf-8 -*-
"""数据可见性（INT-423/466）网关侧服务：资源:share 端点 + 路由层 owner 校验。

语义（数据可见性设计文档 §六 / INT-466 卡面）：
- `PATCH /{id}/visibility`：`require_permission('资源:share')` + owner 校验
  （admin 豁免）；成功后写审计事件。
- audios 可见性修改**不走独立端点**（跟随用例，见 423-3），audio:share 权限点
  保留但不暴露端点——故本服务只实现 task / testcase / group / tag / report /
  dimension 六类。
- 资源（owner, visibility）一律经现有查询服务/代理取，禁止从业务表反查当前
  用户身份。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class VisibilityService:
    """网关侧可见性切换服务（只经 ACL/查询服务，不直连 DB）。"""

    # ---- 公共助手 ----

    @staticmethod
    def get_identity() -> Tuple[Optional[int], bool]:
        """从 request.state 取 (user_id, is_admin)。

        AuthMiddleware 注入：user_id（JWT 载荷）、permissions（admin 通配 '*'）。
        AUTH_MODE=off 时注入 dev 身份（user_id=None, permissions=['*'] → admin）。
        """
        from api_gateway.infrastructure.request_adapter import get_current_request
        req = get_current_request()
        if req is None:
            return None, False
        user_id = getattr(req.state, 'user_id', None)
        perms = getattr(req.state, 'permissions', None) or []
        is_admin = '*' in perms
        return user_id, bool(is_admin)

    @staticmethod
    def validate_visibility(value) -> Optional[str]:
        """校验可见性取值；非法返回 None（调用方按 400 处理）。"""
        from shared.models.common_enums import Visibility
        if value in (Visibility.SHARED.value, Visibility.PRIVATE.value):
            return value
        return None

    @staticmethod
    def check_share_owner(resource_type: str, resource_id: Any, owner: Optional[int]) -> Tuple[Optional[int], bool]:
        """share 端点 owner 校验：owner 或 admin 放行，其余抛 HTTPException 403。

        注意与 check_visible 的差异：share 切换不看资源当前可见性，只看归属
        （非 owner 即使资源 shared 也不得代改可见性）。
        """
        user_id, is_admin = VisibilityService.get_identity()
        if is_admin:
            return user_id, is_admin
        if user_id is not None and owner is not None and user_id == owner:
            return user_id, is_admin
        raise HTTPException(status_code=403, detail='仅资源所有者或管理员可修改可见性')

    @staticmethod
    def audit_visibility_change(resource_type: str, resource_id: Any,
                                owner: Optional[int], old_vis: str, new_vis: str,
                                action: str = 'update_visibility') -> None:
        """成功切换可见性后写审计（旁路，失败不影响业务）。

        PRIVATE_RESOURCE_ACCESS 触发语义：admin 操作（设计文档 §五）或本次切换
        触碰私有态（旧/新任一为 private）——共享→共享的纯 no-op 不落审计。
        """
        from shared.models.common_enums import Visibility
        user_id, is_admin = VisibilityService.get_identity()
        if not (is_admin or old_vis == Visibility.PRIVATE.value
                or new_vis == Visibility.PRIVATE.value):
            return
        try:
            from api_gateway.application.services.visibility.visibility_audit import (
                write_private_access_audit,
            )
            write_private_access_audit(
                resource_type, resource_id, action, operator_id=user_id)
        except Exception:
            logger.warning('PRIVATE_RESOURCE_ACCESS 审计失败 resource_type=%s id=%s',
                           resource_type, resource_id, exc_info=True)

    # ---- 六类资源切换 ----

    @staticmethod
    def update_task_visibility(task_id: int, visibility: str) -> Tuple[Dict[str, Any], int]:
        from api_gateway.application.services.task.task_query_service import TaskQueryService
        from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl

        vis = VisibilityService.validate_visibility(visibility)
        if vis is None:
            return _err('visibility 仅支持 shared/private', 400)

        resp = TaskQueryService.get_one(task_id)
        payload, http_code = resp
        if http_code != 200 or not payload.get('success'):
            return _err(payload.get('message', '任务不存在或无权访问'),
                        http_code if http_code in (404, 403) else 404)
        data = payload.get('data') or {}
        owner = data.get('created_by_user_id')
        old_vis = data.get('visibility') or 'shared'
        try:
            VisibilityService.check_share_owner('task', task_id, owner)
        except HTTPException as e:
            return _err(e.detail, e.status_code)

        result = TaskConfigAclRepositoryImpl().update(task_id, {'visibility': vis})
        if not result.get('success'):
            return _err(result.get('message', '可见性更新失败'),
                        result.get('code', 500) if result.get('code') else 500)
        VisibilityService.audit_visibility_change('task', task_id, owner, old_vis, vis)
        return _ok({'id': task_id, 'visibility': vis}, '任务可见性更新成功')

    @staticmethod
    def update_testcase_visibility(tc_id: str, visibility: str) -> Tuple[Dict[str, Any], int]:
        from api_gateway.application.services.testcase.testcase_query_service import (
            TestCaseQueryService,
        )
        from api_gateway.infrastructure.acl import TestCaseConfigAclRepositoryImpl

        vis = VisibilityService.validate_visibility(visibility)
        if vis is None:
            return _err('visibility 仅支持 shared/private', 400)

        resp = TestCaseQueryService.get_one(tc_id)
        payload, http_code = resp
        if http_code != 200 or not payload.get('success'):
            return _err(payload.get('message', '测试用例不存在或无权访问'),
                        http_code if http_code in (404, 403) else 404)
        data = payload.get('data') or {}
        owner = data.get('created_by_user_id')
        old_vis = data.get('visibility') or 'shared'
        try:
            VisibilityService.check_share_owner('testcase', tc_id, owner)
        except HTTPException as e:
            return _err(e.detail, e.status_code)

        result = TestCaseConfigAclRepositoryImpl().update(tc_id, {'visibility': vis})
        if not result.get('success'):
            return _err(result.get('message', '可见性更新失败'),
                        result.get('code', 500) if result.get('code') else 500)
        VisibilityService.audit_visibility_change('testcase', tc_id, owner, old_vis, vis)
        return _ok({'id': tc_id, 'visibility': vis}, '用例可见性更新成功')

    @staticmethod
    def update_group_visibility(group_id: str, visibility: str) -> Tuple[Dict[str, Any], int]:
        from api_gateway.infrastructure.grpc_proxies import task_data_service

        vis = VisibilityService.validate_visibility(visibility)
        if vis is None:
            return _err('visibility 仅支持 shared/private', 400)

        try:
            group = task_data_service.get_testcase_group_by_id(group_id)
        except Exception as e:
            logger.warning('查询分组 %s 失败', group_id, exc_info=True)
            group = None
        if not group:
            return _err('分组不存在或无权访问', 404)
        owner = group.get('created_by_user_id')
        old_vis = group.get('visibility') or 'shared'
        try:
            VisibilityService.check_share_owner('group', group_id, owner)
        except HTTPException as e:
            return _err(e.detail, e.status_code)

        try:
            updated = task_data_service.update_testcase_group(
                group_id=group_id, visibility=vis)
        except Exception:
            # 读取后并发删除 → 分组已不存在，映射 404，不回显内部异常文本
            logger.warning('更新分组可见性失败 group_id=%s', group_id, exc_info=True)
            return _err('分组不存在或无权访问', 404)
        if not updated or not updated.get('id'):
            return _err('分组不存在或无权访问', 404)
        VisibilityService.audit_visibility_change('group', group_id, owner, old_vis, vis)
        return _ok({'id': group_id, 'visibility': vis}, '分组可见性更新成功')

    @staticmethod
    def update_tag_visibility(tag_id: int, visibility: str) -> Tuple[Dict[str, Any], int]:
        from api_gateway.application.services.tag.tag_query_service import TagQueryService
        from api_gateway.infrastructure.acl import TagConfigAclRepositoryImpl

        vis = VisibilityService.validate_visibility(visibility)
        if vis is None:
            return _err('visibility 仅支持 shared/private', 400)

        resp = TagQueryService.get_one(tag_id)
        payload, http_code = resp
        if http_code != 200 or not payload.get('success'):
            return _err(payload.get('message', '标签不存在或无权访问'),
                        http_code if http_code in (404, 403) else 404)
        data = payload.get('data') or {}
        owner = data.get('created_by_user_id')
        old_vis = data.get('visibility') or 'shared'
        try:
            VisibilityService.check_share_owner('tag', tag_id, owner)
        except HTTPException as e:
            return _err(e.detail, e.status_code)

        result = TagConfigAclRepositoryImpl().update_tag(tag_id, {'visibility': vis})
        if not result.get('success'):
            return _err(result.get('message', '可见性更新失败'),
                        result.get('code', 500) if result.get('code') else 500)
        VisibilityService.audit_visibility_change('tag', tag_id, owner, old_vis, vis)
        return _ok({'id': tag_id, 'visibility': vis}, '标签可见性更新成功')

    @staticmethod
    def update_report_visibility(report_id: int, visibility: str) -> Tuple[Dict[str, Any], int]:
        from api_gateway.application.services.report.report_query_sevice import (
            ReportQueryService,
        )

        vis = VisibilityService.validate_visibility(visibility)
        if vis is None:
            return _err('visibility 仅支持 shared/private', 400)

        resp = ReportQueryService.get_one(report_id)
        payload, http_code = resp
        if http_code != 200 or not payload.get('success'):
            return _err(payload.get('message', '报告不存在或无权访问'),
                        http_code if http_code in (404, 403) else 404)
        data = payload.get('data') or {}
        owner = data.get('created_by_user_id')
        old_vis = data.get('visibility') or 'shared'
        try:
            VisibilityService.check_share_owner('report', report_id, owner)
        except HTTPException as e:
            return _err(e.detail, e.status_code)

        try:
            from api_gateway.infrastructure.grpc_proxies import report_config_service
            from shared.proto import report_service_pb2 as report_pb
            import json as _json
            stub = report_config_service.stub
            resp = stub.UpdateReport(report_pb.UpdateReportRequest(
                report_id=int(report_id),
                data=_json.dumps({'visibility': vis}, ensure_ascii=False),
            ))
            if not resp.success:
                return _err(resp.message or '可见性更新失败', 500)
        except Exception:
            logger.warning('更新报告可见性失败 report_id=%s', report_id, exc_info=True)
            return _err('可见性更新失败', 500)
        VisibilityService.audit_visibility_change('report', report_id, owner, old_vis, vis)
        return _ok({'id': report_id, 'visibility': vis}, '报告可见性更新成功')

    @staticmethod
    def update_dimension_visibility(dim_id: int, visibility: str) -> Tuple[Dict[str, Any], int]:
        from api_gateway.application.services.evaluation.evaluation_query_service import (
            EvaluationQueryService,
        )
        from api_gateway.infrastructure.acl import EvaluationConfigAclRepositoryImpl

        vis = VisibilityService.validate_visibility(visibility)
        if vis is None:
            return _err('visibility 仅支持 shared/private', 400)

        resp = EvaluationQueryService.get_one(dim_id)
        payload, http_code = resp
        if http_code != 200 or not payload.get('success'):
            return _err(payload.get('message', '评估维度不存在或无权访问'),
                        http_code if http_code in (404, 403) else 404)
        data = payload.get('data') or {}
        owner = data.get('created_by_user_id')
        old_vis = data.get('visibility') or 'shared'
        try:
            VisibilityService.check_share_owner('dimension', dim_id, owner)
        except HTTPException as e:
            return _err(e.detail, e.status_code)

        result = EvaluationConfigAclRepositoryImpl().update_dimension(dim_id, {'visibility': vis})
        if not result.get('success'):
            return _err(result.get('message', '可见性更新失败'),
                        result.get('code', 500) if result.get('code') else 500)
        VisibilityService.audit_visibility_change('dimension', dim_id, owner, old_vis, vis)
        return _ok({'id': dim_id, 'visibility': vis}, '评估维度可见性更新成功')


def _ok(data, message='操作成功'):
    from api_gateway.utils.response import success_response
    return success_response(data, message)


def _err(message: str, http_code: int):
    from api_gateway.utils.response import error_response
    return error_response(message, http_code=http_code)
