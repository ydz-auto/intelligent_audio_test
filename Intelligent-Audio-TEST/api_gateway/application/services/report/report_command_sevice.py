# -*- coding: utf-8 -*-
"""报告命令 Service（BFF Application 层 - CQRS Command Side）

职责：参数校验 + gRPC 调用 report_service，不含业务逻辑。
"""
import logging
from typing import Dict, List, Tuple

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.report import (
    ReportUpdateRequest,
    GenerateTaskReportRequest,
    CompareReportsRequest,
    SecondaryCompareRequest,
    ReportShareCreateRequest,
)
from api_gateway.infrastructure.grpc_proxies import report_config_service
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)

# 分享访问口径 / 有效期取值（对齐卡面契约与 report_service 校验）
_SHARE_ACCESS_VALUES = ('login', 'specific', 'public')
_SHARE_EXPIRY_VALUES = ('none', '7d', '30d', 'custom')


def _resolve_recipients(raw_recipients: str) -> Tuple[List[Dict], List[str]]:
    """逗号分隔用户名/邮箱 → [{user_id, label}]；返回 (resolved, unrecognized)。

    逐项经 auth_service ListUsers(keyword) 模糊匹配后按 username/email
    精确比对（不新增 RPC、不改 auth_service）。label 供弹窗回显（用户名/邮箱）。
    """
    from api_gateway.infrastructure.grpc_proxies import auth_config_service
    from shared.proto import auth_service_pb2 as auth_pb

    resolved: List[Dict] = []
    unrecognized: List[str] = []
    seen_ids = set()
    for item in (raw_recipients or '').split(','):
        item = item.strip()
        if not item:
            continue
        try:
            resp = auth_config_service.stub.ListUsers(auth_pb.ListUsersRequest(
                keyword=item, page_size=100))
        except Exception as e:
            logger.warning('解析分享收件人失败 keyword=%s: %s', item, e)
            unrecognized.append(item)
            continue
        if not resp.success:
            unrecognized.append(item)
            continue
        users = _loads(resp.data, {}) or {}
        matched = [u for u in users.get('items', [])
                   if u.get('username') == item or u.get('email') == item]
        if not matched:
            unrecognized.append(item)
            continue
        u = matched[0]
        uid = u.get('id')
        if uid in seen_ids:
            continue  # 重复收件人去重
        seen_ids.add(uid)
        resolved.append({
            'user_id': uid,
            'label': u.get('username') or u.get('email') or item,
        })
    return resolved, unrecognized


def _build_share_url(report_id: int, token: str) -> str:
    """拼接分享链接：网关请求 base URL（或配置公开 origin）+ 前端路由形态。

    形态与前端路由 /report/:reportId?share= 一致。
    """
    from api_gateway.infrastructure.request_adapter import get_current_request
    from api_gateway.config.config import Config

    origin = None
    req = get_current_request()
    if req is not None:
        try:
            origin = str(req.base_url).rstrip('/')
        except Exception:
            origin = None
    if not origin:
        origin = (getattr(Config, 'PUBLIC_ORIGIN', '') or 'http://localhost:5000').rstrip('/')
    return f"{origin}/report/{report_id}?share={token}"


class ReportCommandService:
    """报告命令 BFF Service：参数校验 → gRPC 调用 → 响应组装"""

    # ------------------------------------------------------------------
    # 删除报告
    # ------------------------------------------------------------------

    @staticmethod
    def delete(report_id):
        try:
            stub = report_config_service.stub
            resp = stub.DeleteReport(report_pb.DeleteReportRequest(
                report_id=int(report_id)))
            if not resp.success:
                return error_response(resp.message or '删除失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'删除报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 更新报告
    # ------------------------------------------------------------------

    @staticmethod
    def update(report_id):
        try:
            body = request.get_json() or {}
            req = ReportUpdateRequest.model_validate(body)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.UpdateReport(report_pb.UpdateReportRequest(
                report_id=int(report_id),
                data=_dumps(req.model_dump(by_alias=False, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '更新失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'更新报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 发布报告
    # ------------------------------------------------------------------

    @staticmethod
    def publish(report_id):
        try:
            stub = report_config_service.stub
            resp = stub.UpdateReportStatus(report_pb.UpdateReportStatusRequest(
                report_id=int(report_id),
                status='published'))
            if not resp.success:
                return error_response(resp.message or '发布失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'发布报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 批量删除
    # ------------------------------------------------------------------

    @staticmethod
    def batch_delete():
        try:
            body = request.get_json() or {}
            ids = body.get('ids', [])
            if not ids or not isinstance(ids, list):
                return error_response('ids 列表不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.BatchActionReports(report_pb.BatchActionReportsRequest(
                data=_dumps({
                    'ids': [int(i) for i in ids],
                    'action': 'delete',
                    'hard_delete': bool(body.get('hard_delete', False)),
                })))
            if not resp.success:
                return error_response(resp.message or '批量删除失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'批量删除报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 对比报告
    # ------------------------------------------------------------------

    @staticmethod
    def compare():
        try:
            body = request.get_json() or {}
            req = CompareReportsRequest.model_validate(body)
            if not req.task_ids:
                return error_response('taskIds 不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GenerateCompareReport(report_pb.GenerateCompareReportRequest(
                data=_dumps({
                    'task_ids': req.task_ids,
                    'name': req.name or '',
                    'description': req.description or '',
                })))
            if not resp.success:
                return error_response(resp.message or '生成对比报告失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'生成对比报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 二次对比报告
    # ------------------------------------------------------------------

    @staticmethod
    def secondary_compare():
        try:
            body = request.get_json() or {}
            req = SecondaryCompareRequest.model_validate(body)
            if not req.report_ids:
                return error_response('reportIds 不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GenerateSecondaryCompareReport(report_pb.GenerateSecondaryCompareReportRequest(
                data=_dumps({
                    'report_ids': req.report_ids,
                    'description': req.description or '',
                })))
            if not resp.success:
                return error_response(resp.message or '生成二次对比报告失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'生成二次对比报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 生成任务报告
    # ------------------------------------------------------------------

    @staticmethod
    def generate_task_report():
        try:
            body = request.get_json() or {}
            req = GenerateTaskReportRequest.model_validate(body)
            if not req.task_id:
                return error_response('taskId 不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GenerateTaskReport(report_pb.GenerateTaskReportRequest(
                task_id=int(req.task_id),
                name=req.name or '',
                description=req.description or ''))
            if not resp.success:
                return error_response(resp.message or '生成任务报告失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'生成任务报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 重新生成报告（删除旧报告后异步重新生成）
    # ------------------------------------------------------------------

    @staticmethod
    def regenerate_report(report_id):
        """重新生成报告（对齐旧库语义）。

        流程：查询报告 → 校验"仅任务报告" → 捕获原名称/描述 →
        软删除旧报告（保留历史快照）→ 携带原名称/描述异步重新生成。
        """
        try:
            stub = report_config_service.stub
            # 先查询报告：类型校验 + task_id / 原名称 / 原描述捕获（删前读，避免元数据丢失）
            detail_resp = stub.GetReportDetail(report_pb.GetReportDetailRequest(
                report_id=int(report_id)))
            if not detail_resp.success:
                return error_response('未找到测试报告', code=404, http_code=404)
            report = _loads(detail_resp.data, {}) or {}
            if report.get('report_type') != 'task':
                return error_response('仅支持任务报告重新生成')
            task_id = report.get('task_id')
            if not task_id:
                return error_response('报告未关联任务，无法重新生成', 400)
            name = report.get('name') or ''
            description = report.get('description') or ''

            del_resp = stub.DeleteReport(report_pb.DeleteReportRequest(
                report_id=int(report_id)))
            if not del_resp.success:
                return error_response(del_resp.message or '删除旧报告失败')
            resp = stub.GenerateTaskReport(report_pb.GenerateTaskReportRequest(
                task_id=int(task_id),
                name=name,
                description=description))
            if not resp.success:
                return error_response(resp.message or '重新生成报告失败')
            result = _loads(resp.data, {}) or {}
            return success_response(result)
        except Exception as e:
            return error_response(f'重新生成报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 报告分享（INT-971）
    # ------------------------------------------------------------------

    @staticmethod
    def create_share(report_id):
        """创建报告分享链接（POST /reports/{report_id}/share，report:update）。

        recipients（仅 access=specific）经 auth_service ListUsers 解析为
        [{user_id, label}]；存在未识别项 → 400 带明细。share_url 由网关拼接。
        """
        try:
            body = request.get_json() or {}
            req = ReportShareCreateRequest.model_validate(body)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        access = req.access
        if access not in _SHARE_ACCESS_VALUES:
            return error_response('access 仅支持 login / specific / public', 400)
        if req.expiry not in _SHARE_EXPIRY_VALUES:
            return error_response('expiry 仅支持 none / 7d / 30d / custom', 400)
        if req.expiry == 'custom' and not req.expires_at:
            return error_response('expiry=custom 时 expires_at 必填', 400)
        if access == 'specific':
            if not req.recipients:
                return error_response('access=specific 时 recipients 必填', 400)
            resolved, unrecognized = _resolve_recipients(req.recipients)
            if unrecognized:
                return error_response(
                    '存在未识别的收件人: ' + '、'.join(unrecognized),
                    400, detail={'unrecognized': unrecognized})
            recipients = resolved
        else:
            recipients = []

        try:
            stub = report_config_service.stub
            resp = stub.CreateReportShare(report_pb.CreateReportShareRequest(
                data=_dumps({
                    'report_id': int(report_id),
                    'access': access,
                    'expiry': req.expiry,
                    'expires_at': req.expires_at or None,
                    'password': req.password or '',
                    'recipients': recipients,
                })))
            if not resp.success:
                return error_response(resp.message or '创建分享失败',
                                      http_code=resp.code or 400,
                                      detail=_loads(resp.data, {}) or None)
            data = _loads(resp.data, {}) or {}
            data['share_url'] = _build_share_url(int(report_id), data.get('token'))
            return success_response(data)
        except Exception as e:
            return error_response(f'创建分享失败: {str(e)}')

    @staticmethod
    def revoke_share(report_id, token):
        """撤销报告分享（DELETE /reports/{report_id}/share/{token}，report:update）。

        软撤销幂等：已撤销再次撤销仍 200；token 不存在/不属于该报告 → 404。
        """
        if not token:
            return error_response('缺少分享 token', 400)
        try:
            stub = report_config_service.stub
            resp = stub.RevokeReportShare(report_pb.RevokeReportShareRequest(
                data=_dumps({'report_id': int(report_id), 'token': token})))
            if not resp.success:
                return error_response(resp.message or '撤销分享失败',
                                      http_code=resp.code or 404,
                                      detail=_loads(resp.data, {}) or None)
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'撤销分享失败: {str(e)}')
