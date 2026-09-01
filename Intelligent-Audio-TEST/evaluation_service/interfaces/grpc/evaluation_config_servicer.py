# -*- coding: utf-8 -*-
"""评估维度及分类 CRUD gRPC servicer（EvaluationConfigServiceServicer）

从 servicers.py 拆分（P4-4 大文件拆分）：委托给 EvaluationConfigHandler（CQRS）。
"""
from shared.proto import evaluation_service_pb2 as eval_pb
from shared.proto import evaluation_service_pb2_grpc as eval_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class EvaluationConfigServiceServicer(eval_grpc.EvaluationConfigServiceServicer):
    """评估维度及分类 CRUD servicer，委托给 EvaluationConfigHandler（CQRS）"""

    def __init__(self):
        self._handler = None

    @property
    def handler(self):
        if self._handler is None:
            from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
            self._handler = evaluation_config_handler
        return self._handler

    @staticmethod
    def _resp(result):
        return eval_pb.EvaluationConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(result.get('data')) if result.get('data') is not None else "",
        )

    # ---- 分类 CRUD ----

    def CreateCategory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.handler.create_category(data))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def UpdateCategory(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.handler.update_category(request.cat_id, data))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def DeleteCategory(self, request, context=None):
        try:
            return self._resp(self.handler.delete_category(request.cat_id))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def ListCategories(self, request, context=None):
        try:
            return self._resp(self.handler.list_categories())
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    # ---- 维度 CRUD ----

    def CreateDimension(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.handler.create_dimension(data))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def UpdateDimension(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.handler.update_dimension(request.dim_id, data))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def DeleteDimension(self, request, context=None):
        try:
            return self._resp(self.handler.delete_dimension(request.dim_id))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def BatchActionDimension(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.handler.batch_action(data))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def CalculateScore(self, request, context=None):
        try:
            data = _loads(request.data, {})
            return self._resp(self.handler.calculate_score(request.dim_id, data))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    # ---- 读操作 ----

    def ListDimensions(self, request, context=None):
        try:
            return self._resp(self.handler.list_dimensions(
                category_id=request.category_id or None,
                page=request.page,
                per_page=request.per_page,
                search=request.search,
            ))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def GetDimensionOptions(self, request, context=None):
        try:
            return self._resp(self.handler.get_dimension_options(request.algorithm_type))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def GetDimensionByIds(self, request, context=None):
        """按 dim_id 列表批量查询维度基础信息（id/name/type/description）。

        供 task_service 跨服务获取 Dimension（evaluation_service 自有 PO）。
        """
        try:
            dim_ids = _loads(request.dim_ids, [])
            if not isinstance(dim_ids, list) or not dim_ids:
                return self._resp({'success': True, 'message': '', 'data': {'items': []}})

            # P1-3: 通过 Application Query Service，不直调 Repository
            from evaluation_service.application.queries.evaluation_query_service import (
                evaluation_query_service,
            )
            result = evaluation_query_service.get_dimension_basics_by_ids(dim_ids)
            return self._resp(result)
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")

    def HealthCheck(self, request, context=None):
        try:
            return self._resp(self.handler.health_check(request.dim_id))
        except Exception as e:
            return eval_pb.EvaluationConfigResponse(success=False, message=str(e), data="")
