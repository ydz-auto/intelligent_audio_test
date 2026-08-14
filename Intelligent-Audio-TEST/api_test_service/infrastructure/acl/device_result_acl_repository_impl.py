# -*- coding: utf-8 -*-
"""DeviceResultService ACL 仓储 — gRPC 实现

封装 device_service.DeviceResultService gRPC 调用，供 api_test_service application 层使用。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DeviceResultAclRepositoryImpl:
    """DeviceResultService ACL 仓储实现"""

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
                }, default=str)
            )
            resp = self._get_stub().CollectResult(req)
            if not resp.success or not resp.data:
                return all_results
            return json.loads(resp.data)
        except Exception as e:
            logger.error("convert_results 失败: %s", e)
            return all_results

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
                }, default=str)
            )
            resp = self._get_stub().CollectResult(req)
            if not resp.success or not resp.data:
                return ''
            return resp.data
        except Exception as e:
            logger.error("build_case_result_log 失败: %s", e)
            return ''
