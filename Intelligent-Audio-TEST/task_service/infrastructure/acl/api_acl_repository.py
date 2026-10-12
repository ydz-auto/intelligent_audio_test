# -*- coding: utf-8 -*-
"""api_test_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 api_test_service 的跨域 gRPC 调用，
消除引擎/仓储层对 shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_api_test_service_stub

proto：shared/proto/api_test_service_pb2
"""
import logging
from typing import Optional

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)


class ApiAclRepository:
    """api_test_service 防腐层仓储（gRPC ACL 适配层）。"""

    def test_api_connection(self, api_id: int) -> Optional[dict]:
        """健康检查单个 API（封装 api_test_service.APITestService.TestAPIConnection）。

        Returns:
            {'id', 'status'('online'/'offline'), 'error', ...} dict；
            gRPC 失败/异常返回 None（调用方按"不阻塞启动"策略处理）。
        """
        from shared.clients.grpc_clients import get_api_test_service_stub
        from shared.proto import api_test_service_pb2 as api_pb
        try:
            stub = get_api_test_service_stub()
            resp = stub.TestAPIConnection(api_pb.TestAPIConnectionRequest(api_id=int(api_id)))
            if not resp.success:
                _logger.warning("TestAPIConnection gRPC 失败 (api_id=%s): %s", api_id, resp.message)
                return None
            return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("TestAPIConnection gRPC 异常 (api_id=%s): %s", api_id, e)
            return None


# 模块级单例
api_acl_repository = ApiAclRepository()
