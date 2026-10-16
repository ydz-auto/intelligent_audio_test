# -*- coding: utf-8 -*-
"""ReviewService servicer（INT-340 测试结果人工复核）。

协议适配：反序列化请求 → 委托 review_service（application 层）→ 序列化响应。
operator（复核操作人）从 x-user-id metadata 读取（get_current_user_id，网关出站
拦截器自动透传，与收藏/挑选合并同口径）。
"""
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps
from shared.infrastructure.user_context import set_current_user_id, user_id_from_context


class ReviewServiceServicer(task_grpc.ReviewServiceServicer):
    """人工复核 servicer（提交/计数/历史）。"""

    @staticmethod
    def _resp(result):
        """统一包装返回结果为 TaskConfigResponse（含业务码透传，INT-141 F2 口径）。"""
        data = result.get('data')
        if (not result.get('success')) and isinstance(data, dict) and isinstance(data.get('code'), int):
            data = dict(data)
            data.pop('code', None)
            return task_pb.TaskConfigResponse(
                success=False, message=result.get('message', ''),
                data=_dumps(data) if data else "",
            )
        return task_pb.TaskConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(data) if data is not None else "",
        )

    @classmethod
    def _with_user(cls, context, func):
        """x-user-id metadata → set_current_user_id（application 层 get_current_user_id 读取）。"""
        user_id = user_id_from_context(context)
        set_current_user_id(user_id)
        try:
            return func()
        finally:
            set_current_user_id(None)

    def SubmitReview(self, request, context=None):
        try:
            from task_service.application.task.review_service import review_service
            data = _loads(request.data, {})
            return self._resp(self._with_user(
                context, lambda: review_service.submit_review(data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetReviewCount(self, request, context=None):
        try:
            from task_service.application.task.review_service import review_service
            return self._resp(review_service.review_count(request.task_id))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ListReviewHistory(self, request, context=None):
        try:
            from task_service.application.task.review_service import review_service
            return self._resp(review_service.review_history(request.task_id))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")
