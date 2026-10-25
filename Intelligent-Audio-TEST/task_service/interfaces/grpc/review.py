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
        """统一包装返回结果为 TaskConfigResponse（业务码走 proto code，INT-1759）"""
        data = result.get('data')
        if (not result.get('success')) and isinstance(data, dict) and isinstance(data.get('code'), int):
            data = dict(data)
            data.pop('code', None)
        return task_pb.TaskConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(data) if data is not None else "",
            code=int(result.get('code') or 0),
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

    # ==================== AI 复核（INT-822/INT-800） ====================

    def InitiateAiReview(self, request, context=None):
        """发起 AI 复核：{result_ids, dimension_ids?, force?} → {items, reused, skipped}。"""
        try:
            from task_service.application.task.ai_review_service import ai_review_service
            data = _loads(request.data, {})
            return self._resp(self._with_user(
                context, lambda: ai_review_service.initiate_review(data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ListAiReviewHistory(self, request, context=None):
        """任务 AI 复核历史（时间倒序；data JSON: {result_id?, dimension_id?, status?}）。"""
        try:
            from task_service.application.task.ai_review_service import ai_review_service
            filters = _loads(request.data, {})
            return self._resp(ai_review_service.review_history(request.task_id, filters))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def AdoptAiReview(self, request, context=None):
        """采纳 AI 复核结论：data JSON {execution_status?, evaluation_status?, comment}。"""
        try:
            from task_service.application.task.ai_review_service import ai_review_service
            data = _loads(request.data, {})
            return self._resp(self._with_user(
                context,
                lambda: ai_review_service.adopt_review(request.review_id, data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def RejectAiReview(self, request, context=None):
        """驳回 AI 复核结论（原判定不变）。"""
        try:
            from task_service.application.task.ai_review_service import ai_review_service
            return self._resp(self._with_user(
                context, lambda: ai_review_service.reject_review(request.review_id)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")
