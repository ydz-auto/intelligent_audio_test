# -*- coding: utf-8 -*-
"""AI 复核代理（INT-824）：task_service.ReviewService（AI 复核方法）gRPC 封装。

api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
所有方法返回 dict: {success, message, data, code}（TaskConfigResponse 统一解析）。
operator（复核操作人）经出站拦截器 x-user-id metadata 自动透传。
"""
import json

from shared.clients.grpc_clients import get_review_service_stub

from ._common import _attach_code, _grpc_call

from shared.proto import task_service_pb2 as task_pb


class _AiReviewProxy:
    """AI 复核代理：转发到 gRPC task_service.ReviewService（AI 复核方法，INT-822）。"""

    def _resp(self, resp):
        """统一解析 TaskConfigResponse 为 dict（业务码透传，INT-1759 proto code）"""
        data = json.loads(resp.data) if resp.data else None
        return _attach_code({'success': resp.success, 'message': resp.message,
                             'data': data}, resp)

    @property
    def stub(self):
        """获取 ReviewService stub（供需要直接调 RPC 的场景使用）"""
        return get_review_service_stub()

    def initiate_review(self, data: dict):
        def _call():
            resp = self.stub.InitiateAiReview(task_pb.AiReviewRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'AI 复核发起失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='AI 复核发起失败')

    def list_ai_review_history(self, task_id, filters: dict):
        def _call():
            resp = self.stub.ListAiReviewHistory(task_pb.AiReviewHistoryRequest(
                task_id=int(task_id),
                data=json.dumps(filters or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'AI 复核历史查询失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='AI 复核历史查询失败')

    def adopt_review(self, review_id, data: dict):
        def _call():
            resp = self.stub.AdoptAiReview(task_pb.AiReviewActionRequest(
                review_id=int(review_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'AI 复核采纳失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='AI 复核采纳失败')

    def reject_review(self, review_id):
        def _call():
            resp = self.stub.RejectAiReview(task_pb.AiReviewActionRequest(
                review_id=int(review_id)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'AI 复核驳回失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='AI 复核驳回失败')


# AI 复核代理模块级单例
ai_review_proxy = _AiReviewProxy()
