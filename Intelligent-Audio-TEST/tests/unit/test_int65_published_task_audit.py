# -*- coding: utf-8 -*-
"""INT-65 专项：已发布任务审计事件 + 操作人回填。

覆盖：
- publish：published_by 回填 operator_user_id；PUBLISHED_TASK_CREATED 落 logs
- create_version：新版本 published_by 持久化 + PUBLISHED_TASK_VERSION_CREATED 落 logs
- execute：PUBLISHED_TASK_EXECUTED 落 logs（含 new_task_id/operator_user_id）
- archive：archived_by 回填 + PUBLISHED_TASK_ARCHIVED 落 logs；幂等归档不重复审计
- AUTH_MODE=off 兜底：operator 缺失时保持 None，审计事件仍落库（published_by=None）
- 网关 _current_operator_user_id：0/空 → None，JWT user_id → int
仓储与日志仓储以 fake 替身注入（不依赖 DB/gRPC）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.common_enums import AuditEvent

import task_service.application.services.published_task_service as pts_module
from task_service.application.services.published_task_service import (
    PublishedTaskService,
    published_task_service,
)


def make_task(**overrides):
    """来源日常任务替身（Task PO 形状）。"""
    task = type('TaskPO', (), {})()
    task.id = 123
    task.deleted = False
    task.status = 'completed'
    task.config = {}
    task.algorithm_type = None
    task.algorithm_params = {}
    for k, v in overrides.items():
        setattr(task, k, v)
    return task


def make_pt(**overrides):
    """已发布任务 PO 替身。"""
    pt = type('PublishedTaskPO', (), {})()
    pt.id = 1001
    pt.task_group_id = 1001
    pt.source_task_id = 123
    pt.name = '已发布任务'
    pt.description = None
    pt.type = 'e2e'
    pt.status = 'published'
    pt.benchmark = False
    pt.version = 1
    pt.is_current = True
    pt.snapshot_config = {'caseIds': [1], 'deviceIds': [], 'apiIds': [], 'tags': []}
    pt.published_by = None
    pt.published_at = None
    pt.archived_at = None
    pt.created_at = None
    for k, v in overrides.items():
        setattr(pt, k, v)
    return pt


class FakeRepo:
    """published_task_repository 替身。"""

    def __init__(self, source_task=None, current_pt=None, new_task_id=555):
        self.source_task = source_task or make_task()
        self.current_pt = current_pt or make_pt()
        self.new_task_id = new_task_id
        self.create_kwargs = None
        self.create_version_kwargs = None
        self.archive_kwargs = None

    # ---- publish 链路 ----
    def get_task(self, task_id):
        return self.source_task

    def get_task_case_devices(self, task_id):
        return []

    def get_task_case_ids(self, task_id):
        return [1, 2]

    def get_task_device_ids(self, task_id):
        return []

    def get_task_api_ids(self, task_id):
        return []

    def get_task_tag_names(self, task_id):
        return []

    def get_existing_case_ids(self, case_ids):
        return set(case_ids)

    def freeze_report_snapshot(self, source_task_id):
        return None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return make_pt(**{
            'id': 1001,
            'benchmark': kwargs.get('benchmark', False),
            'published_by': kwargs.get('published_by'),
        })

    # ---- create_version 链路 ----
    def get_by_id(self, published_task_id):
        return self.current_pt

    def get_current_version(self, group_id):
        return self.current_pt

    def create_version(self, **kwargs):
        self.create_version_kwargs = kwargs
        return make_pt(**{
            'id': 1002,
            'version': kwargs.get('version', 2),
            'benchmark': kwargs.get('benchmark', False),
            'published_by': kwargs.get('published_by'),
            'task_group_id': self.current_pt.task_group_id,
        })

    # ---- execute 链路 ----
    def create_daily_task(self, **kwargs):
        return self.new_task_id

    def update_task_trace(self, task_id, **kwargs):
        pass

    # ---- archive 链路 ----
    def archive(self, published_task_id, archived_by=None):
        self.archive_kwargs = {'published_task_id': published_task_id, 'archived_by': archived_by}
        self.current_pt.status = 'archived'
        self.current_pt.archived_by = archived_by
        return self.current_pt


class FakeLogRepo:
    """log_repository 替身：捕获审计写入。"""

    def __init__(self):
        self.batch = []

    def batch_create(self, logs):
        self.batch.extend(logs)
        return list(range(len(self.batch)))


@pytest.fixture
def env(monkeypatch):
    """注入 fake repo 与 fake log_repository，返回可断言的容器。"""
    fake_repo = FakeRepo()
    fake_log = FakeLogRepo()
    monkeypatch.setattr(pts_module, 'repo', fake_repo)
    monkeypatch.setattr(pts_module, 'log_repository', fake_log)
    return {'repo': fake_repo, 'log': fake_log}


def _events(log_repo):
    """logs 批次中的事件名 → content 映射（保持写入顺序）。"""
    out = []
    for item in log_repo.batch:
        content = json.loads(item['content'])
        out.append(content)
    return out


class TestPublishAudit:
    """发布：操作人回填 + PUBLISHED_TASK_CREATED。"""

    def test_publish_backfills_operator_and_audits(self, env):
        result = published_task_service.publish({
            'source_task_id': 123,
            'name': '审计任务',
            'operator_user_id': 42,
        })
        assert result['success'] is True
        assert env['repo'].create_kwargs['published_by'] == 42

        events = _events(env['log'])
        created = [e for e in events if e['event'] == AuditEvent.PUBLISHED_TASK_CREATED.value]
        assert len(created) == 1
        assert created[0]['published_task_id'] == 1001
        assert created[0]['published_by'] == 42
        assert created[0]['result'] == 'success'

    def test_publish_without_operator_keeps_none_and_still_audits(self, env):
        result = published_task_service.publish({'source_task_id': 123, 'name': '无操作人'})
        assert result['success'] is True
        assert env['repo'].create_kwargs['published_by'] is None

        events = _events(env['log'])
        created = [e for e in events if e['event'] == AuditEvent.PUBLISHED_TASK_CREATED.value]
        assert len(created) == 1
        assert created[0]['published_by'] is None


class TestCreateVersionAudit:
    """新版本：published_by 持久化 + PUBLISHED_TASK_VERSION_CREATED。"""

    def test_create_version_persists_operator_and_audits(self, env):
        result = published_task_service.create_version(1001, {'operator_user_id': 7})
        assert result['success'] is True
        assert env['repo'].create_version_kwargs['published_by'] == 7

        events = _events(env['log'])
        created = [e for e in events
                   if e['event'] == AuditEvent.PUBLISHED_TASK_VERSION_CREATED.value]
        assert len(created) == 1
        assert created[0]['version'] == 2
        assert created[0]['published_by'] == 7
        assert created[0]['previous_version_id'] == 1001


class TestExecuteAudit:
    """执行：PUBLISHED_TASK_EXECUTED。"""

    def test_execute_audits_with_new_task_id(self, env):
        result = published_task_service.execute(1001, operator_user_id=9)
        assert result['success'] is True
        assert result['data']['task_id'] == 555

        events = _events(env['log'])
        executed = [e for e in events if e['event'] == AuditEvent.PUBLISHED_TASK_EXECUTED.value]
        assert len(executed) == 1
        assert executed[0]['new_task_id'] == 555
        assert executed[0]['operator_user_id'] == 9


class TestArchiveAudit:
    """归档：archived_by 回填 + PUBLISHED_TASK_ARCHIVED。"""

    def test_archive_backfills_archived_by_and_audits(self, env):
        result = published_task_service.archive(1001, operator_user_id=33)
        assert result['success'] is True
        assert env['repo'].archive_kwargs['archived_by'] == 33

        events = _events(env['log'])
        archived = [e for e in events if e['event'] == AuditEvent.PUBLISHED_TASK_ARCHIVED.value]
        assert len(archived) == 1
        assert archived[0]['archived_by'] == 33

    def test_archive_idempotent_no_extra_audit(self, env):
        env['repo'].current_pt.status = 'archived'
        result = published_task_service.archive(1001, operator_user_id=33)
        assert result['success'] is True
        assert env['repo'].archive_kwargs is None
        assert env['log'].batch == []


class TestGatewayOperator:
    """网关操作人归一化：0/空/无请求 → None，合法 JWT user_id → int。"""

    @staticmethod
    def _with_request(monkeypatch, user_id):
        import api_gateway.application.services.published_task.published_task_service as gw

        class Req:
            class state:
                pass

        if user_id is not None:
            Req.state.user_id = user_id
        monkeypatch.setattr(gw, 'get_current_request', lambda: Req())
        return gw

    def test_zero_and_missing_map_to_none(self, monkeypatch):
        gw = self._with_request(monkeypatch, user_id=0)
        assert gw._current_operator_user_id() is None

    def test_no_request_context_returns_none(self, monkeypatch):
        import api_gateway.application.services.published_task.published_task_service as gw
        monkeypatch.setattr(gw, 'get_current_request', lambda: None)
        assert gw._current_operator_user_id() is None

    def test_jwt_user_id_normalized_to_int(self, monkeypatch):
        gw = self._with_request(monkeypatch, user_id='77')
        assert gw._current_operator_user_id() == 77
