# -*- coding: utf-8 -*-
"""INT-65 专项：任务/用例批量软删除恢复（restore）。

覆盖：
- 任务批量 restore：仅已删除行恢复（deleted=True → deleted=False + deleted_at=None），
  未删除/不存在的 ID 不计入；batch_action('restore') 契约与前端对齐；
  空 task_ids 返回 400
- 用例批量 restore：batch_action('restore') 走幂等防护 + 事件发布主链路，
  消息携带实际恢复数
仓储以 fake/MagicMock 替身注入（不依赖 DB）。
"""
import importlib
import os
from datetime import datetime, timezone, timedelta

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock

import pytest

# 包 __init__ 将 task_crud_service 名绑定为单例实例，遮蔽同名子模块；
# importlib 直取 sys.modules 中的真实模块用于打桩
crud_mod = importlib.import_module('task_service.application.task.task_crud_service')
from task_service.application.task.task_crud_service import TaskCrudService
from task_service.application.testcase.testcase_batch_service import TestCaseBatchService
from task_service.infrastructure.persistence.task_repository import task_repository

_UTC8 = timezone(timedelta(hours=8))


# ---------- 任务批量 restore ----------

class FakeTaskRepoRestore:
    """task_repository 替身：仅捕获 batch_restore 调用。"""

    def __init__(self, restored=2):
        self.calls = []
        self._restored = restored

    def batch_restore(self, task_ids):
        self.calls.append(list(task_ids))
        return self._restored


class FakeQuery:
    """query 服务替身（restore 链路不触达，防御性占位）。"""

    def get_task_detail(self, task_id):
        return {'success': True, 'data': {'status': 'stopped'}}


def _make_crud(fake_repo, monkeypatch):
    monkeypatch.setattr(crud_mod, 'task_repository', fake_repo)
    svc = TaskCrudService()
    monkeypatch.setattr(type(svc), 'query', property(lambda self: FakeQuery()))
    # 统计缓存刷新依赖 api_gateway（跨服务），测试环境降级路径已存在，直接放行
    return svc


class TestTaskBatchRestore:
    """task_crud_service.batch_action('restore')。"""

    def test_restore_calls_repo_and_returns_count(self, monkeypatch):
        fake_repo = FakeTaskRepoRestore(restored=2)
        svc = _make_crud(fake_repo, monkeypatch)

        result = svc.batch_action({'action': 'restore', 'task_ids': [7, 8, 9]})

        assert result['success'] is True
        assert result['data'] == {'restored_count': 2}
        assert fake_repo.calls == [[7, 8, 9]]

    def test_restore_empty_task_ids_rejected(self, monkeypatch):
        fake_repo = FakeTaskRepoRestore()
        svc = _make_crud(fake_repo, monkeypatch)

        result = svc.batch_action({'action': 'restore', 'task_ids': []})

        assert result['success'] is False
        assert result['code'] == 400
        assert fake_repo.calls == []

    def test_restore_rejects_unknown_action(self, monkeypatch):
        fake_repo = FakeTaskRepoRestore()
        svc = _make_crud(fake_repo, monkeypatch)

        result = svc.batch_action({'action': 'nope', 'task_ids': [1]})

        assert result['success'] is False
        assert result['code'] == 400


class TestTaskRepositoryBatchRestore:
    """task_repository.batch_restore 仅恢复已删除行（真实 SQL 谓词验证）。"""

    def test_batch_restore_filters_deleted_true(self):
        from shared.models.database import (
            Base, init_db, get_engine, get_db_session, remove_db_session,
        )
        from task_service.infrastructure.persistence.models import Task

        init_db(pool_size=2)
        Base.metadata.create_all(bind=get_engine(), tables=[Task.__table__])

        session = get_db_session()
        try:
            t1 = Task(name='INT65_restore_已删除', type='api', status='stopped',
                      deleted=True, deleted_at=datetime.now(_UTC8), total_cases=0)
            t2 = Task(name='INT65_restore_存活', type='api', status='completed',
                      deleted=False, total_cases=0)
            session.add_all([t1, t2])
            session.commit()
            ids = [t1.id, t2.id]
        finally:
            remove_db_session()

        try:
            restored = task_repository.batch_restore(ids)
            assert restored == 1

            session = get_db_session()
            try:
                rows = {t.id: t for t in session.query(Task).filter(Task.id.in_(ids)).all()}
            finally:
                remove_db_session()
            assert rows[t1.id].deleted is False
            assert rows[t1.id].deleted_at is None
            assert rows[t2.id].deleted is False
        finally:
            session = get_db_session()
            try:
                session.query(Task).filter(Task.id.in_(ids)).delete(synchronize_session=False)
                session.commit()
            finally:
                remove_db_session()


# ---------- 用例批量 restore ----------

class TestTestcaseBatchRestore:
    """testcase_batch_service batch_action('restore')。"""

    def _service(self, restored):
        store = MagicMock()
        store.lookup.return_value = None
        store.reserve.return_value = True
        repo = MagicMock()
        repo.restore_testcases_by_ids.return_value = restored
        svc = TestCaseBatchService(repo=repo, idempotency_store=store)
        return svc, repo

    def test_restore_handler_registered(self):
        svc, repo = self._service(3)
        result = svc.batch_action({'action': 'restore', 'ids': ['a', 'b', 'c']})

        assert result['success'] is True
        assert '3' in result['message']
        repo.restore_testcases_by_ids.assert_called_once_with(['a', 'b', 'c'])
        repo.commit.assert_called_once()

    def test_restore_reports_actual_count_not_request_size(self):
        svc, repo = self._service(restored=1)
        result = svc.batch_action({'action': 'restore', 'ids': ['a', 'b']})

        assert result['success'] is True
        assert '1' in result['message']

    def test_restore_unknown_action_rejected(self):
        svc, repo = self._service(0)
        result = svc.batch_action({'action': 'undo', 'ids': ['a']})

        assert result['success'] is False
        assert result['code'] == 400
        repo.commit.assert_not_called()

    def test_restore_publishes_case_event(self, monkeypatch):
        """restore 经主链路发布 CASE_EVENTS / case_batch_action_completed（status=completed）。"""
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

        svc, repo = self._service(3)
        published = []

        def fake_publish(_self, channel, event_type, payload):
            published.append({'channel': channel, 'event_type': event_type, 'payload': payload})

        monkeypatch.setattr(EventBus, 'publish', fake_publish)

        result = svc.batch_action({'action': 'restore', 'ids': ['a', 'b', 'c']})

        assert result['success'] is True
        assert len(published) == 1
        ev = published[0]
        assert ev['channel'] == EventChannel.CASE_EVENTS
        assert ev['event_type'] == EventType.CASE_BATCH_ACTION_COMPLETED
        assert ev['payload']['action'] == 'restore'
        assert ev['payload']['ids'] == ['a', 'b', 'c']
        assert ev['payload']['status'] == 'completed'
