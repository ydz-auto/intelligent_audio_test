# -*- coding: utf-8 -*-
"""评估执行服务 gRPC servicer（EvaluationServiceServicer）

从 servicers.py 拆分（P4-4 大文件拆分）：仅保留评估执行相关 RPC，
维度 CRUD 见 evaluation_config_servicer.py，评估数据查询见 evaluation_data_servicer.py。
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
