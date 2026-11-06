# -*- coding: utf-8 -*-
"""INT-41 修复单测：应用层入口对字符串 case_ids 的幂等类型规范化。

跨服务 gRPC test_config 以 JSON 传 case_ids，json.loads 不保 int 类型：
task_service 引擎发送侧 str() 化后，api_test_service 执行链以 int 主键比对
（tc.get('id') == tc_rel_id），2 == '2' 恒 False → 用例被静默跳过、任务永久
卡 running。修复落在 CreateAPITestCommandHandler.handle（gRPC servicer 与
HTTP admin 两个入口的共同必经点）：数值字符串经 dataclasses.replace 重建为
int，与 CreateAPITestCommand.case_ids 的 List[int] 声明对齐。

真实链路守卫见 tests/integration/test_task_execute_real_chain.py::
TestKnownExecuteChainDefects::test_int41_case_ids_normalized_at_api_boundary
（需真实 Postgres）；本文件以替身 start_task 做无 DB 快速验证。
"""
import os
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import api_test_service.core.api_test_service as core_svc
from api_test_service.application.commands.api_test_commands import (
    CreateAPITestCommand,
)
from api_test_service.application.handlers.command_handlers import (
    CreateAPITestCommandHandler,
    _normalize_case_ids,
)


def _capture_start_task(monkeypatch):
    """替身 start_task：捕获 handler 实际传入的 case_ids。"""
    captured = {}

    def _fake_start_task(task_id, case_ids, api_ids):
        captured['task_id'] = task_id
        captured['case_ids'] = list(case_ids)
        captured['api_ids'] = list(api_ids)
        return {'success': True, 'task_id': task_id, 'message': 'ok',
                'case_count': len(case_ids)}

    monkeypatch.setattr(core_svc.api_test_service, 'start_task', _fake_start_task)
    return captured


class TestInt41CommandCaseIdsNormalization:

    def test_numeric_strings_normalized_to_int(self, monkeypatch):
        """原缺陷失败面：字符串 case_ids 到达 start_task 前必须已是 int。"""
        captured = _capture_start_task(monkeypatch)
        result = CreateAPITestCommandHandler().handle(
            CreateAPITestCommand(task_id=1, case_ids=['2', '35'], api_ids=[]))
        assert captured['case_ids'] == [2, 35]
        assert all(isinstance(c, int) for c in captured['case_ids'])
        assert result['case_count'] == 2

    def test_int_case_ids_pass_through_idempotently(self, monkeypatch):
        """已是 int 的 case_ids 原样透传（规范化幂等，不重建命令）。"""
        captured = _capture_start_task(monkeypatch)
        CreateAPITestCommandHandler().handle(
            CreateAPITestCommand(task_id=1, case_ids=[7, 9], api_ids=[]))
        assert captured['case_ids'] == [7, 9]

    def test_mixed_and_non_numeric_strings_keep_boundary_semantics(self, monkeypatch):
        """混合类型：数值字符串转 int，非数值字符串原样保留（与隔离替身语义一致）。"""
        captured = _capture_start_task(monkeypatch)
        CreateAPITestCommandHandler().handle(
            CreateAPITestCommand(task_id=1, case_ids=['2', 3, 'x35'], api_ids=[]))
        assert captured['case_ids'] == [2, 3, 'x35']

    def test_empty_case_ids_no_rebuild(self, monkeypatch):
        """空列表不触发规范化分支，start_task 照常收到空列表。"""
        captured = _capture_start_task(monkeypatch)
        CreateAPITestCommandHandler().handle(
            CreateAPITestCommand(task_id=1, case_ids=[], api_ids=[5]))
        assert captured['case_ids'] == []
        assert captured['api_ids'] == [5]

    def test_rebuild_preserves_frozen_command_other_fields(self, monkeypatch):
        """frozen dataclass 经 replace 重建后 task_id / api_ids 保持不变。"""
        captured = _capture_start_task(monkeypatch)
        CreateAPITestCommandHandler().handle(
            CreateAPITestCommand(task_id=42, case_ids=['8'], api_ids=[3]))
        assert captured['task_id'] == 42
        assert captured['api_ids'] == [3]

    def test_normalize_helper_rejects_nothing(self):
        """助手本身：数值串转 int、非数值串透传、空列表返回空列表。"""
        assert _normalize_case_ids(['2', 3, '045', 'x', '']) == [2, 3, 45, 'x', '']
        assert _normalize_case_ids([]) == []
