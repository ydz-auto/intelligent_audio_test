# -*- coding: utf-8 -*-
"""api_adapter_service.AdapterService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import json as _json
import logging

from api_test_service.domain.dto import AdapterRoundResultDTO
from api_test_service.domain.repositories.acl.adapter_acl_repository import (
    AdapterAclRepository,
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


class AdapterAclRepositoryImpl(AdapterAclRepository):
    """api_adapter_service.AdapterService 跨域调用 gRPC 实现。"""

    def send_round(self, request) -> AdapterRoundResultDTO:
        from shared.clients.grpc_clients import get_adapter_service_stub
        stub = get_adapter_service_stub()
        response = stub.SendRound(request)
        if not response.success:
            raise RuntimeError(f"adapter gRPC SendRound failed: {response.message}")
        task_result = _json.loads(response.data) if response.data else {}
        return _attach(dict_to_dto(task_result, AdapterRoundResultDTO), task_result)
