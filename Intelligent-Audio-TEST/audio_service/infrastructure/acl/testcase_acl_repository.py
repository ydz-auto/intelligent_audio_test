# -*- coding: utf-8 -*-
"""TestCaseConfig 跨域 ACL 仓储实现 — 通过 gRPC 调用 task_service。

封装 task_service 的测试用例 CRUD（创建/列表/更新），
使 application 层不再直接 import shared.clients.grpc_clients。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from audio_service.domain.repositories.acl.testcase_acl_repository import (
    TestCaseConfigACLRepository,
)

logger = logging.getLogger(__name__)


class TestCaseConfigACLRepositoryImpl(TestCaseConfigACLRepository):
    """task_service 测试用例跨域读写 gRPC 实现。"""

    def list_testcases(self, page: int = 1, per_page: int = 50,
                       keyword: str = '', include_deleted: bool = False) -> dict:
        """分页查询测试用例列表（ListTestCases）

        gRPC 不可用时返回空 dict。
        """
        try:
            from shared.clients.grpc_clients import get_testcase_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import loads as _loads

            stub = get_testcase_config_service_stub()
            req = task_pb.ListTestCasesRequest(
                page=page, per_page=per_page, keyword=keyword,
                include_deleted=include_deleted,
            )
            resp = stub.ListTestCases(req)
            if resp.success:
                return _loads(resp.data, {}) or {}
        except Exception as e:
            logger.error(f"ListTestCases gRPC 调用失败 (page={page}): {e}")
        return {}

    def list_all_testcases(self, include_deleted: bool = False) -> List[dict]:
        """分页获取所有测试用例（自动翻页）

        返回完整的用例 dict 列表。
        """
        all_items: List[dict] = []
        page = 1
        per_page = 100
        while True:
            data = self.list_testcases(
                page=page, per_page=per_page, include_deleted=include_deleted
            )
            if not data:
                break
            items = data.get('items', [])
            total = data.get('total', 0)
            all_items.extend(items)
            if page * per_page >= total or not items:
                break
            page += 1
        return all_items

    def create_testcase_config(self, data: dict) -> Optional[dict]:
        """创建测试用例（CreateTestCaseConfig）

        返回创建结果 dict（含 id），失败返回 None。
        """
        try:
            from shared.clients.grpc_clients import get_testcase_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import loads as _loads, dumps as _dumps

            stub = get_testcase_config_service_stub()
            req = task_pb.CreateTestCaseConfigRequest(data=_dumps(data))
            resp = stub.CreateTestCaseConfig(req)
            if resp.success:
                return _loads(resp.data, {}) or {}
            else:
                logger.error(f"创建测试用例失败: {resp.message}")
        except Exception as e:
            logger.error(f"CreateTestCaseConfig gRPC 调用失败: {e}")
        return None

    def update_testcase_config(self, tc_id: str, data: dict) -> Optional[dict]:
        """更新测试用例（UpdateTestCaseConfig）

        返回更新结果 dict，失败返回 None。
        """
        try:
            from shared.clients.grpc_clients import get_testcase_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import loads as _loads, dumps as _dumps

            stub = get_testcase_config_service_stub()
            req = task_pb.UpdateTestCaseConfigRequest(
                tc_id=str(tc_id), data=_dumps(data)
            )
            resp = stub.UpdateTestCaseConfig(req)
            if resp.success:
                return _loads(resp.data, {}) or {}
            else:
                logger.warning(f"更新用例 {tc_id} 失败: {resp.message}")
        except Exception as e:
            logger.warning(f"UpdateTestCaseConfig gRPC 调用失败 ({tc_id}): {e}")
        return None
