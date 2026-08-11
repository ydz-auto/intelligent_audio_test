# -*- coding: utf-8 -*-
"""api_test_service.APITestService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from report_service.domain.dto import ApiConfigDTO
from report_service.domain.repositories.acl.apitest_acl_repository import (
    ApiTestAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


class ApiTestAclRepositoryImpl(ApiTestAclRepository):
    """api_test_service.APITestService 跨域只读查询 gRPC 实现。"""

    def get_api(self, api_id) -> Optional[ApiConfigDTO]:
        from shared.clients.grpc_clients import get_api_test_service_stub
        from shared.proto import api_test_service_pb2 as api_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_api_test_service_stub()
            resp = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=int(api_id)))
            if not resp.success:
                return None
            data = _loads(resp.data, None)
            return _attach(dict_to_dto(data, ApiConfigDTO), data)
        except Exception as e:
            logger.warning("get_api gRPC failed: %s", e)
            return None

    def get_apis_by_ids(self, api_ids) -> Dict[int, ApiConfigDTO]:
        if not api_ids:
            return {}
        result: Dict[int, ApiConfigDTO] = {}
        for aid in api_ids:
            a = self.get_api(aid)
            if a is not None and a.id is not None:
                try:
                    result[int(a.id)] = a
                except Exception:
                    pass
        return result
