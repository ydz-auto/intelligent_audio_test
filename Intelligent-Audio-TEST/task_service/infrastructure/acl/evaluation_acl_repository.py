# -*- coding: utf-8 -*-
"""evaluation_service / device_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 evaluation_service / device_service 的跨域 gRPC 调用，
消除 application 层对 shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_evaluation_service_stub
- shared.clients.grpc_clients.get_device_result_service_stub
- shared.clients.grpc_clients.submit_reevaluate

proto：shared/proto/evaluation_service_pb2 / device_service_pb2
"""
import json
import logging

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)


class EvaluationAclRepository:
    """evaluation_service / device_result 防腐层仓储（gRPC ACL 适配层）。"""

    # ========== 重新评估（evaluation_service.EvaluationService）==========

    def submit_reevaluate(self, task_id, reextract_device_output=True, reevaluate_type='all'):
        """提交任务级重新评估。

        封装 shared.clients.grpc_clients.submit_reevaluate，
        通过 evaluation_service.EvaluationService.Reevaluate RPC。
        """
        from shared.clients.grpc_clients import submit_reevaluate
        return submit_reevaluate(
            task_id=task_id,
            reextract_device_output=reextract_device_output,
            reevaluate_type=reevaluate_type,
        )

    def get_evaluation_service_stub(self):
        """获取 EvaluationService gRPC stub。

        封装 shared.clients.grpc_clients.get_evaluation_service_stub，
        供需要直接调用 stub 的场景使用（如 ReevaluateMultiRound / ReevaluateSingle）。
        """
        from shared.clients.grpc_clients import get_evaluation_service_stub
        return get_evaluation_service_stub()

    def reevaluate_multi_round(self, task_id, result_id, test_case_id,
                               algorithm_result, test_type='api',
                               algorithm_type='translation'):
        """多轮重新评估。

        封装 evaluation_service.EvaluationService.ReevaluateMultiRound RPC。
        """
        from shared.proto import evaluation_service_pb2 as eval_pb
        stub = self.get_evaluation_service_stub()
        resp = stub.ReevaluateMultiRound(eval_pb.ReevaluateMultiRoundRequest(
            task_id=str(task_id),
            result_json=json.dumps(result_id, ensure_ascii=False, default=str),
            test_case_id=str(test_case_id or ''),
            algorithm_result=json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
            test_type=test_type or 'api',
            algorithm_type=algorithm_type or 'translation',
        ))
        return resp

    def reevaluate_single(self, task_id, result_id, test_case_id,
                          algorithm_result, reference_params,
                          test_type='api', algorithm_type='translation'):
        """单轮重新评估。

        封装 evaluation_service.EvaluationService.ReevaluateSingle RPC。
        """
        from shared.proto import evaluation_service_pb2 as eval_pb
        stub = self.get_evaluation_service_stub()
        resp = stub.ReevaluateSingle(eval_pb.ReevaluateSingleRequest(
            task_id=str(task_id),
            result_id=str(result_id or ''),
            test_case_id=str(test_case_id or ''),
            algorithm_result=json.dumps(algorithm_result or {}, ensure_ascii=False, default=str),
            reference_params=json.dumps(reference_params or {}, ensure_ascii=False, default=str),
            test_type=test_type or 'api',
            algorithm_type=algorithm_type or 'translation',
        ))
        return resp

    # ========== 重新提取设备结果（device_service.DeviceResultService）==========

    def get_device_result_service_stub(self):
        """获取 DeviceResultService gRPC stub。

        封装 shared.clients.grpc_clients.get_device_result_service_stub，
        供需要直接调用 stub 的场景使用（如 ReextractResult）。
        """
        from shared.clients.grpc_clients import get_device_result_service_stub
        return get_device_result_service_stub()

    def reextract_result(self, task_id, execution_status=None, evaluation_status=None):
        """重新提取设备结果。

        封装 device_service.DeviceResultService.ReextractResult RPC。
        返回 dict: {success, message, data}。
        """
        from shared.proto import device_service_pb2 as e2e_pb
        stub = self.get_device_result_service_stub()
        reextract_config = {
            'execution_status': execution_status,
            'evaluation_status': evaluation_status,
        }
        resp = stub.ReextractResult(e2e_pb.ReextractResultRequest(
            task_id=str(task_id),
            reextract_config=json.dumps(reextract_config),
        ))
        result = _loads(resp.data, {}) if resp.success else {}
        return {
            'success': resp.success,
            'message': resp.message,
            'data': result,
        }


# 模块级单例
evaluation_acl_repository = EvaluationAclRepository()
