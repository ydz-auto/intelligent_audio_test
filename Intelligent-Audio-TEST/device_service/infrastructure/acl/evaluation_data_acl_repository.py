# -*- coding: utf-8 -*-
"""evaluation_service.EvaluationDataService 防腐层仓储（ACL Repository）

封装对 evaluation_service.EvaluationDataService 的 gRPC 调用，
替代 device_service application 层中对 shared.clients.grpc_clients 的直接 import。

- 写操作通过 gRPC 完成，返回 bool，不返回 ORM 对象。
- 与 device_service/infrastructure/acl/task_acl_repository.py 风格一致，
  采用具体类 + 模块级单例（device_service ACL 层无统一 ABC）。
"""
import logging

logger = logging.getLogger(__name__)


class EvaluationDataACLRepository:
    """evaluation_service.EvaluationDataService 防腐层仓储

    封装 gRPC 调用，提供 application 层可用的返回值。
    所有方法返回纯 bool，不返回 ORM 对象。
    """

    def delete_dimension_results_by_result_ids(self, result_ids: list) -> bool:
        """按测试结果 ID 列表删除维度评估记录

        通过 gRPC 调用 evaluation_service.EvaluationDataService.DeleteDimensionResultsByResultIds。
        返回是否成功；gRPC 异常时返回 False。
        """
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import dumps as _dumps
        try:
            stub = get_evaluation_data_service_stub()
            stub.DeleteDimensionResultsByResultIds(
                eval_pb.DeleteDimensionResultsByResultIdsRequest(
                    result_ids=_dumps([int(oid) for oid in result_ids])
                )
            )
            return True
        except Exception as e:
            logger.warning(f"delete_dimension_results_by_result_ids gRPC 调用失败: {e}")
            return False


# 模块级单例
evaluation_data_acl_repository = EvaluationDataACLRepository()
