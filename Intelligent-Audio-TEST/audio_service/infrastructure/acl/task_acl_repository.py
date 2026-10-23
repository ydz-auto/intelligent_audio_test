# -*- coding: utf-8 -*-
"""Task 跨域 ACL 仓储实现 — 通过 gRPC 调用 task_service。

从 audio_service/infrastructure/persistence/audio_repository.py 迁出，
确保自有仓储不再混入跨域查询逻辑。
"""
from __future__ import annotations

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

    def check_audio_references_batch(self, audio_ids) -> dict:
        """批量检查音频被测试用例/任务引用计数（INT-1306）。

        经 task_service.CheckAudioReferences gRPC（DB 侧单次扫描 test_cases /
        test_tasks / task_case_relations config），替代逐页 ListTestCases /
        ListTasks 全量拉取。返回 {audio_id: {'testcase_audio': N,
        'testcase_noise': M, 'task': K}}；gRPC 失败时抛出异常（fail-closed：
        引用状态未知时不允许删除）。
        """
        from shared.clients.grpc_clients import get_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        audio_ids = list(audio_ids)
        stub = get_task_config_service_stub()
        resp = stub.CheckAudioReferences(task_pb.CheckAudioReferencesRequest(
            audio_ids=audio_ids,
        ))
        if not resp.success:
            raise RuntimeError(resp.message or '音频引用检查失败')
        data = _loads(resp.data, {}) or {}
        references = data.get('references', {}) or {}
        result = {}
        for audio_id in audio_ids:
            ref = references.get(str(audio_id), {}) if isinstance(references, dict) else {}
            result[audio_id] = {
                'testcase_audio': int(ref.get('testcase_audio', 0) or 0),
                'testcase_noise': int(ref.get('testcase_noise', 0) or 0),
                'task': int(ref.get('task', 0) or 0),
            }
        return result

    def _check_referenced(self, audio_id: int) -> dict:
        """按 audio_id 调 task_service.CheckAudioReferenced 定点查询引用数。

        INT-1449：替代旧实现 ListTestCases/ListTasks 全表分页 + config
        字符串客户端扫描（真实库 579 用例下 DELETE 22-35s 的根因）。
        返回 {testcases, background_noise, tasks} 计数；gRPC 异常时返回
        全 0（失败开放：不因检查链路故障阻断删除，与旧实现 except 回退一致）。
        """
        from shared.clients.grpc_clients import get_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_config_service_stub()
            resp = stub.CheckAudioReferenced(task_pb.CheckAudioReferencedRequest(
                audio_id=int(audio_id),
            ))
            if not resp.success:
                logger.warning("CheckAudioReferenced 返回失败: %s", resp.message)
                return {'testcases': 0, 'background_noise': 0, 'tasks': 0}
            data = _loads(resp.data, {})
            if not isinstance(data, dict):
                return {'testcases': 0, 'background_noise': 0, 'tasks': 0}
            return {
                'testcases': int(data.get('testcases', 0) or 0),
                'background_noise': int(data.get('background_noise', 0) or 0),
                'tasks': int(data.get('tasks', 0) or 0),
            }
        except Exception as e:
            logger.warning("CheckAudioReferenced 调用失败: %s", e, exc_info=True)
            return {'testcases': 0, 'background_noise': 0, 'tasks': 0}

    def check_audio_in_testcases(self, audio_id: int) -> int:
        """检查音频是否被测试用例引用（INT-1449 定点查询）"""
        return self._check_referenced(audio_id).get('testcases', 0)

    def check_audio_in_testcase_noise(self, audio_id: int) -> int:
        """检查音频是否被测试用例作为背景噪音引用（INT-1449 定点查询）"""
        return self._check_referenced(audio_id).get('background_noise', 0)

    def check_audio_in_tasks(self, audio_id: int) -> int:
        """检查音频是否被任务引用（INT-1449 定点查询：task_case_relations）"""
        return self._check_referenced(audio_id).get('tasks', 0)

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

    def has_running_e2e_tasks(self) -> bool:
        """查询 task_service 是否有运行中的 e2e（物理设备形态）任务

        通过 gRPC 调用 task_service.TaskConfigService.ListTasks（status=running）。
        差异#2 收尾：proto ListTasksRequest.type 字段改承载 device_type 过滤值，
        E2E 门禁按含物理设备用例的任务判定（type='physical'，对齐网关侧门禁）。
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
                type='physical',
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
