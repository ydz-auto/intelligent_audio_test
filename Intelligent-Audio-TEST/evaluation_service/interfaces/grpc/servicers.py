# -*- coding: utf-8 -*-
"""evaluation_service gRPC servicers

EvaluationServiceServicer: 评估执行（EvaluateCase / Reevaluate 等）
EvaluationConfigServiceServicer: 维度 CRUD
"""
from shared.proto import evaluation_service_pb2 as eval_pb
from shared.proto import evaluation_service_pb2_grpc as eval_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class EvaluationServiceServicer(eval_grpc.EvaluationServiceServicer):
    """评估执行服务 gRPC servicer"""

    def EvaluateCase(self, request, context=None):
        """评估单个用例结果"""
        try:
            task_id = int(request.task_id) if request.task_id else 0
            result_id = int(request.result_id) if request.result_id else 0
            test_case_id = request.test_case_id
            algorithm_result = _loads(request.algorithm_result, {})
            eval_params = _loads(request.eval_params, {})

            from evaluation_service.infrastructure.evaluation_service_host import evaluation_service
            evaluation_service.evaluate_case(
                task_id, result_id, test_case_id, algorithm_result,
                **eval_params,
            )
            return eval_pb.EvaluateCaseResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "result_id": str(result_id), "evaluated": True}),
            )
        except Exception as e:
            return eval_pb.EvaluateCaseResponse(success=False, message=str(e), data="")

    def Reevaluate(self, request, context=None):
        """重新评估（任务级批量重新评估）"""
        try:
            task_id = request.task_id
            reextract_device_output = request.reextract_device_output
            reevaluate_type = request.reevaluate_type or 'all'

            from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
            executor = ReevaluationExecutor.get_instance()
            success, message = executor.submit(
                task_id,
                reextract_device_output=reextract_device_output,
                reevaluate_type=reevaluate_type,
            )
            return eval_pb.ReevaluateResponse(
                success=success,
                message=message,
                data=_dumps({
                    "task_id": str(task_id),
                    "submitted": success,
                    "message": message,
                }),
            )
        except Exception as e:
            return eval_pb.ReevaluateResponse(success=False, message=str(e), data="")

    def ReevaluateMultiRound(self, request, context=None):
        """多轮用例重新评估"""
        try:
            task_id = request.task_id
            result = _loads(request.result_json, {})
            test_case_id = request.test_case_id
            algorithm_result = _loads(request.algorithm_result, {})
            test_type = request.test_type or 'api'
            algorithm_type = request.algorithm_type or 'translation'

            from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
            executor = ReevaluationExecutor.get_instance()
            executor._reevaluate_multi_round(
                task_id=task_id,
                result=result,
                test_case_id=test_case_id,
                algorithm_result=algorithm_result,
                test_type=test_type,
                algorithm_type=algorithm_type,
            )
            return eval_pb.ReevaluateMultiRoundResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "mode": "multi_round"}),
            )
        except Exception as e:
            return eval_pb.ReevaluateMultiRoundResponse(success=False, message=str(e), data="")

    def ReevaluateSingle(self, request, context=None):
        """单轮用例重新评估"""
        try:
            task_id = request.task_id
            result_id = request.result_id
            test_case_id = request.test_case_id
            algorithm_result = _loads(request.algorithm_result, {})
            reference_params = _loads(request.reference_params, {})
            test_type = request.test_type or 'api'
            algorithm_type = request.algorithm_type or 'translation'

            from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
            executor = ReevaluationExecutor.get_instance()
            executor._reevaluate_single(
                task_id=task_id,
                result_id=result_id,
                test_case_id=test_case_id,
                algorithm_result=algorithm_result,
                reference_params=reference_params,
                test_type=test_type,
                algorithm_type=algorithm_type,
            )
            return eval_pb.ReevaluateSingleResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "mode": "single"}),
            )
        except Exception as e:
            return eval_pb.ReevaluateSingleResponse(success=False, message=str(e), data="")


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


class EvaluationDataServiceServicer(eval_grpc.EvaluationDataServiceServicer):
    """评估数据查询 servicer — 供 task_service 跨服务查询/删除 TestResultDimension。

    TestResultDimension 是 evaluation_service 自有 PO，task_service 不能直接访问。
    本 servicer 提供按 result_id 列表批量查询/删除的接口。
    """

    @staticmethod
    def _resp(success, message='', data=None):
        return eval_pb.EvaluationDataResponse(
            success=success,
            message=message,
            data=_dumps(data) if data is not None else "",
        )

    def GetDimensionResultsByResultIds(self, request, context=None):
        """按 result_id 列表批量查询维度评估结果（含 dimension_name）。"""
        try:
            result_ids = _loads(request.result_ids, [])
            if not isinstance(result_ids, list) or not result_ids:
                return self._resp(True, '', {'items': []})

            # P1-3: 通过 Application Query Service，不直调 Repository
            from evaluation_service.application.queries.evaluation_query_service import (
                evaluation_query_service,
            )
            result = evaluation_query_service.get_dimension_results_by_result_ids(result_ids)
            return self._resp(result)
        except Exception as e:
            return self._resp(False, str(e))

    def DeleteDimensionResultsByResultIds(self, request, context=None):
        """按 result_id 列表批量删除维度评估记录。"""
        try:
            result_ids = _loads(request.result_ids, [])
            if not isinstance(result_ids, list) or not result_ids:
                return self._resp(True, 'no-op', {'deleted': 0})

            # P1-3: 通过 Application Command Service，不直调 Repository
            from evaluation_service.application.commands.evaluation_command_service import (
                evaluation_command_service,
            )
            result = evaluation_command_service.delete_dimension_results_by_result_ids(result_ids)
            return self._resp(result)
        except Exception as e:
            return self._resp(False, str(e))
