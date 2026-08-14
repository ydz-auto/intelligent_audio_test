# -*- coding: utf-8 -*-
"""task_service.TestCaseConfigService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import logging
from typing import Dict

from report_service.domain.dto import TestCaseDTO
from report_service.domain.repositories.acl.testcase_acl_repository import (
    TestCaseConfigAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
    return dto


class TestCaseConfigAclRepositoryImpl(TestCaseConfigAclRepository):
    """task_service.TestCaseConfigService 跨域只读查询 gRPC 实现。"""

    def list_testcases_by_ids(self, test_case_ids) -> Dict[int, TestCaseDTO]:
        if not test_case_ids:
            return {}
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_testcase_config_service_stub()
            id_set = {str(int(tid)) for tid in test_case_ids if tid is not None}
            result_map: Dict[int, TestCaseDTO] = {}
            page = 1
            per_page = 1000
            max_pages = 200
            while page <= max_pages:
                resp = stub.ListTestCases(task_pb.ListTestCasesRequest(
                    page=page, per_page=per_page, keyword='', tag='',
                    group_id='', type='', algorithm_type='', view='',
                    include_deleted=False,
                ))
                if not resp.success:
                    break
                data = _loads(resp.data, {})
                if isinstance(data, dict):
                    items = data.get('items', []) or data.get('list', [])
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
                if not items:
                    break
                for tc in items:
                    if not isinstance(tc, dict):
                        continue
                    tc_id = tc.get('id')
                    if tc_id is None:
                        continue
                    if str(int(tc_id)) in id_set:
                        result_map[int(tc_id)] = _attach(dict_to_dto(tc, TestCaseDTO), tc)
                if len(result_map) >= len(id_set) or len(items) < per_page:
                    break
                page += 1
            return result_map
        except Exception as e:
            logger.warning("list_testcases_by_ids gRPC failed: %s", e)
            return {}
