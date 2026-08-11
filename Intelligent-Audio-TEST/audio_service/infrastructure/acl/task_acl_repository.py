# -*- coding: utf-8 -*-
"""Task 跨域 ACL 仓储实现 — 通过 gRPC 调用 task_service。

从 audio_service/infrastructure/persistence/audio_repository.py 迁出，
确保自有仓储不再混入跨域查询逻辑。
"""
from __future__ import annotations

import json as _json
import logging
from typing import List, Optional

from audio_service.domain.dto import TestCaseDTO
from audio_service.domain.repositories.acl.task_acl_repository import (
    TaskACLRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


class TaskACLRepositoryImpl(TaskACLRepository):
    """task_service 跨域只读查询 gRPC 实现。"""

    def check_audio_in_testcases(self, audio_id: int) -> int:
        """检查音频是否被测试用例引用"""
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_testcase_config_service_stub()
            count = 0
            page = 1
            per_page = 100
            while True:
                resp = stub.ListTestCases(task_pb.ListTestCasesRequest(
                    page=page,
                    per_page=per_page,
                ))
                if not resp.success:
                    return 0
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    return 0
                items = data.get('items', []) or []
                for tc in items:
                    config = tc.get('config')
                    if not config:
                        continue
                    config_str = _json.dumps(config, ensure_ascii=False) if not isinstance(config, str) else config
                    if f'"audio_id": {audio_id}' in config_str or f'"audio_id":{audio_id}' in config_str:
                        count += 1
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    return count
                page += 1
        except Exception:
            return 0

    def check_audio_in_testcase_noise(self, audio_id: int) -> int:
        """检查音频是否被测试用例作为背景噪音引用"""
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_testcase_config_service_stub()
            count = 0
            page = 1
            per_page = 100
            while True:
                resp = stub.ListTestCases(task_pb.ListTestCasesRequest(
                    page=page,
                    per_page=per_page,
                ))
                if not resp.success:
                    return 0
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    return 0
                items = data.get('items', []) or []
                for tc in items:
                    config = tc.get('config')
                    if not config:
                        continue
                    config_str = _json.dumps(config, ensure_ascii=False) if not isinstance(config, str) else config
                    if (f'"background_noise": {{"audio_id": {audio_id}}}' in config_str or
                        f'"background_noise":{{"audio_id":{audio_id}}}' in config_str):
                        count += 1
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    return count
                page += 1
        except Exception:
            return 0

    def check_audio_in_tasks(self, audio_id: int) -> int:
        """检查音频是否被任务引用"""
        from shared.clients.grpc_clients import get_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_config_service_stub()
            count = 0
            page = 1
            per_page = 100
            while True:
                resp = stub.ListTasks(task_pb.ListTasksRequest(
                    page=page,
                    per_page=per_page,
                ))
                if not resp.success:
                    return 0
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    return 0
                items = data.get('items', []) or []
                for task_item in items:
                    config = task_item.get('config')
                    if not config:
                        continue
                    config_str = _json.dumps(config, ensure_ascii=False) if not isinstance(config, str) else config
                    if str(audio_id) in config_str:
                        count += 1
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    return count
                page += 1
        except Exception:
            return 0

    def get_testcase_by_id(self, testcase_id) -> Optional[TestCaseDTO]:
        """按 ID 查询 TestCase（返回 TestCaseDTO）"""
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseDetail(task_pb.GetTestCaseDetailRequest(tc_id=str(testcase_id)))
            if not resp.success:
                return None
            return dict_to_dto(_loads(resp.data, {}), TestCaseDTO)
        except Exception:
            return None

    def get_testcase_config_audios(self, testcase_id) -> List[dict]:
        """查询 TestCase config 中 audios 配置列表（只读）"""
        tc = self.get_testcase_by_id(testcase_id)
        if not tc:
            return []
        config = tc.config or {}
        return config.get('audios', []) if isinstance(config, dict) else []

    def get_testcase_test_type(self, testcase_id) -> Optional[str]:
        """查询 TestCase 的 test_type（只读）"""
        tc = self.get_testcase_by_id(testcase_id)
        return tc.test_type if tc else None

    def has_running_e2e_tasks(self) -> bool:
        """查询 task_service 是否有运行中的 e2e 任务

        通过 gRPC 调用 task_service.TaskConfigService.ListTasks（status=running, type=e2e）
        替代原 shared.utils.task_utils.has_running_e2e_tasks 直连。
        gRPC 不可用时回退到无运行任务。
        """
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import loads as _loads

            stub = get_task_config_service_stub()
            resp = stub.ListTasks(task_pb.ListTasksRequest(
                page=1,
                per_page=1,
                status='running',
                type='e2e',
            ))
            if not resp.success:
                return False
            data = _loads(resp.data, {}) or {}
            # 兼容分页结构：{'items': [...]} 或 {'total': N}
            if isinstance(data, dict):
                total = data.get('total')
                if total is not None:
                    return int(total) > 0
                items = data.get('items') or data.get('list') or []
                return len(items) > 0
            if isinstance(data, list):
                return len(data) > 0
            return False
        except Exception:
            return False
