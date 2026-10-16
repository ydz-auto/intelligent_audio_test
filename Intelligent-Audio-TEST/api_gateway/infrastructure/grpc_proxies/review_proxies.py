# -*- coding: utf-8 -*-
"""Review 人工复核代理（INT-340）：task_service.ReviewService gRPC 封装。

api_gateway 的 ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
所有方法返回 dict: {success, message, data, code}（TaskConfigResponse 统一解析）。
operator（复核操作人）经出站拦截器 x-user-id metadata 自动透传。
"""
import json

from shared.clients.grpc_clients import get_review_service_stub

from ._common import _grpc_call

from shared.proto import task_service_pb2 as task_pb


class _ReviewProxy:
    """人工复核代理：转发到 gRPC task_service.ReviewService。"""

    def _resp(self, resp):
        """统一解析 TaskConfigResponse 为 dict（业务码透传，INT-141 F2 口径）。"""
        data = json.loads(resp.data) if resp.data else None
        result = {'success': resp.success, 'message': resp.message, 'data': data}
        if not resp.success and isinstance(data, dict) and isinstance(data.get('code'), int):
            result['code'] = data['code']
        return result

    @property
    def stub(self):
        """获取 ReviewService stub（供需要直接调 RPC 的场景使用）"""
        return get_review_service_stub()

    def submit_review(self, data: dict):
        def _call():
            resp = self.stub.SubmitReview(task_pb.ReviewSubmitRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'复核提交失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='复核提交失败')

    def get_review_count(self, task_id):
        def _call():
            resp = self.stub.GetReviewCount(task_pb.ReviewTaskRequest(task_id=int(task_id)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'复核计数查询失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='复核计数查询失败')

    def list_review_history(self, task_id):
        def _call():
            resp = self.stub.ListReviewHistory(task_pb.ReviewTaskRequest(task_id=int(task_id)))
            return self._resp(resp)
        return _grpc_call(_call,
                          default_return=lambda e: {'success': False, 'message': f'复核历史查询失败: {e}', 'data': None, 'code': 500},
                          error_msg_prefix='复核历史查询失败')


# 人工复核代理模块级单例
review_service = _ReviewProxy()
