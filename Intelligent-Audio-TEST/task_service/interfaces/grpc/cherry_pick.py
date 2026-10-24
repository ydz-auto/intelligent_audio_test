# -*- coding: utf-8 -*-
"""CherryPickService servicer（INT-339 挑选合并）。

协议适配：反序列化请求 → 委托 cherry_pick_service（application 层）→ 序列化响应。
per-user 操作（购物车/挑选集）user_id 从 x-user-id metadata 读取（get_current_user_id，
网关出站拦截器自动透传，与收藏同口径）。
"""
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps
from shared.infrastructure.user_context import set_current_user_id, user_id_from_context


class CherryPickServiceServicer(task_grpc.CherryPickServiceServicer):
    """挑选合并 servicer（购物车/挑选集/候选/下单/溯源）。"""

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

    # ---- 购物车 ----

    def GetCherryPickCart(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(context, cherry_pick_service.cart_get))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def AddCherryPickCartItems(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            data = _loads(request.data, {})
            return self._resp(self._with_user(
                context, lambda: cherry_pick_service.cart_add(data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def RemoveCherryPickCartItems(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(
                context, lambda: cherry_pick_service.cart_remove(list(request.item_ids))))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ClearCherryPickCart(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(context, cherry_pick_service.cart_clear))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 挑选集 ----

    def SaveCherryPickSet(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            data = _loads(request.data, {})
            return self._resp(self._with_user(
                context, lambda: cherry_pick_service.cart_save_as_set(data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ListCherryPickSets(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(context, cherry_pick_service.sets_list))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetCherryPickSet(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(
                context, lambda: cherry_pick_service.set_detail(int(request.set_id))))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def DeleteCherryPickSet(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(
                context, lambda: cherry_pick_service.set_delete(int(request.set_id))))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def RestoreCherryPickSetToCart(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(
                context, lambda: cherry_pick_service.set_to_cart(int(request.set_id))))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 挑选候选查询（S2）----

    def ListCherryPickCandidates(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            data = _loads(request.data, {})
            return self._resp(cherry_pick_service.list_candidates(data))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ListCherryPickPickableTasks(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            data = _loads(request.data, {})
            return self._resp(cherry_pick_service.pickable_tasks(data))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ListCherryPickCandidateTree(self, request, context=None):
        """阶段 2 候选树聚合（INT-1510 §8.2；聚合在仓储单条 SQL，网关只透传）。"""
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            data = _loads(request.data, {})
            return self._resp(cherry_pick_service.candidate_tree(data))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 下单（三出口 + 预览）----

    def CherryPickPreview(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(self._with_user(context, cherry_pick_service.preview))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def CherryPickCheckout(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            data = _loads(request.data, {})
            return self._resp(self._with_user(
                context, lambda: cherry_pick_service.checkout(data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 溯源 ----

    def GetCherryPickSource(self, request, context=None):
        try:
            from task_service.application.task.cherry_pick_service import cherry_pick_service
            return self._resp(cherry_pick_service.source_trace(request.task_id))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")
