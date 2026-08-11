# -*- coding: utf-8 -*-
"""task_service.TestCaseConfigService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import logging
from typing import Optional

from api_test_service.domain.dto import TestCaseDetailDTO
from api_test_service.domain.repositories.acl.testcase_acl_repository import (
    TestCaseConfigAclRepository,
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


class TestCaseConfigAclRepositoryImpl(TestCaseConfigAclRepository):
    """task_service.TestCaseConfigService 跨域只读查询 gRPC 实现。"""

    def get_test_case_detail(self, test_case_id) -> Optional[TestCaseDetailDTO]:
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseDetail(task_pb.GetTestCaseDetailRequest(tc_id=str(test_case_id)))
            if not resp.success:
                return None
            data = _loads(resp.data, {}) or None
            return _attach(dict_to_dto(data, TestCaseDetailDTO), data)
        except Exception as e:
            logger.warning("get_test_case_detail gRPC failed: %s", e)
            return None
