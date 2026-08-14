# -*- coding: utf-8 -*-
"""device_service 结果采集 ACL 仓储 — gRPC 实现

封装 device_service.DeviceResultService gRPC 调用，供 evaluation_service application 层使用。
替代直接 import shared.infrastructure.base_executor._DeviceResultCollectorProxy + gRPC stub。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DeviceResultAclRepository:
    """device_service 结果采集 ACL 仓储

    封装对 gRPC DeviceResultService 的调用，
    evaluation_service application 层通过此仓储访问设备结果，不直接操作 gRPC stub。
    """

    def _get_stub(self):
        from shared.clients.grpc_clients import get_device_result_service_stub
        return get_device_result_service_stub()

    def convert_results(self, all_results: List[Dict], algorithm_type: str) -> List[Dict]:
        """转换设备原始结果格式"""
        from shared.proto import device_service_pb2
        try:
            req = device_service_pb2.CollectResultRequest(
                task_id='',
                collect_config=json.dumps({
                    'action': 'convert_results',
                    'all_results': all_results,
                    'algorithm_type': algorithm_type,
                })
            )
            resp = self._get_stub().CollectResult(req)
            if not resp.success or not resp.data:
                return all_results
            return json.loads(resp.data)
        except Exception as e:
            logger.error("convert_results 失败: %s", e)
            return all_results

    def reextract_result(self, task_id: str, reevaluate_type: str = 'all') -> Dict[str, Any]:
        """重新提取设备输出"""
        from shared.proto import device_service_pb2
        from shared.utils.status_constants import EvaluationStatus
        try:
            config = {
                'evaluation_status': None if reevaluate_type == 'all' else EvaluationStatus.FAILED,
            }
            resp = self._get_stub().ReextractResult(
                device_service_pb2.ReextractResultRequest(
                    task_id=str(task_id),
                    reextract_config=json.dumps(config),
                )
            )
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }
        except Exception as e:
            logger.error("reextract_result 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None}

    def build_case_result_log(self, algorithm_type: str, res: Dict, ref_fields=None, **kwargs) -> str:
        """构建用例结果日志"""
        from shared.proto import device_service_pb2
        try:
            req = device_service_pb2.CollectResultRequest(
                task_id='',
                collect_config=json.dumps({
                    'action': 'build_case_result_log',
                    'algorithm_type': algorithm_type,
                    'res': res,
                    'ref_fields': ref_fields,
                    'kwargs': kwargs,
                })
            )
            resp = self._get_stub().CollectResult(req)
            if not resp.success or not resp.data:
                return ''
            return resp.data
        except Exception as e:
            logger.error("build_case_result_log 失败: %s", e)
            return ''


# 模块级单例
device_result_acl_repository = DeviceResultAclRepository()
