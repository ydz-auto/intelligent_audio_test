# -*- coding: utf-8 -*-
"""评估数据查询 gRPC servicer（EvaluationDataServiceServicer）

从 servicers.py 拆分（P4-4 大文件拆分）：供 task_service 跨服务查询/删除
TestResultDimension（evaluation_service 自有 PO，task_service 不能直接访问）。
"""
from shared.proto import evaluation_service_pb2 as eval_pb
from shared.proto import evaluation_service_pb2_grpc as eval_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


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
