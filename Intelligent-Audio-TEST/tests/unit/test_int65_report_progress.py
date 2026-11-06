# -*- coding: utf-8 -*-
"""INT-65 专项：报告生成进度查询（GET /reports/{id}/progress 读侧）。

覆盖：
- 报告不存在 → handler 返回 None（网关转 404）
- 生成锁被持有 → status='generating'，progress 按任务完成用例数推导
- 锁未持有 → status='completed'，progress=100，携带 report_status
- 任务进度推导：无任务数据/零用例回退 0
is_generation_locked 与任务查询以 monkeypatch 替身注入（不依赖 Redis/gRPC）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from report_service.application.handlers.report_handlers import ReportQueryHandler
from report_service.application.queries.report_queries import GetReportProgressQuery


class FakeAggregate:
    def __init__(self, report_id, task_id, status='published'):
        self.id = report_id
        self.task_id = task_id
        self.status = status


class FakeRepo:
    def __init__(self, aggregate=None):
        self.aggregate = aggregate

    def get_by_id(self, report_id):
        return self.aggregate


def _handler(monkeypatch, aggregate, locked=False, task=None):
    repo = FakeRepo(aggregate)
    handler = ReportQueryHandler(repository=repo)
    monkeypatch.setattr(
        'report_service.application.services.report_task_generator.is_generation_locked',
        lambda task_id: locked,
    )
    if task is not None:
        import report_service.infrastructure.clients.grpc_clients as clients_mod
        monkeypatch.setattr(clients_mod, '_grpc_get_tasks_by_ids', lambda ids: [task])
    return handler


class TestReportProgress:
    """handle_get_report_progress 状态推导。"""

    def test_missing_report_returns_none(self, monkeypatch):
        handler = _handler(monkeypatch, aggregate=None)
        assert handler.handle_get_report_progress(GetReportProgressQuery(report_id=9)) is None

    def test_generating_when_lock_held(self, monkeypatch):
        task = {'id': 5, 'total_cases': 8, 'completed_cases': 4}
        handler = _handler(monkeypatch, FakeAggregate(1, 5), locked=True, task=task)
        data = handler.handle_get_report_progress(GetReportProgressQuery(report_id=1))
        assert data['status'] == 'generating'
        assert data['task_id'] == 5
        assert data['progress'] == 50

    def test_completed_when_no_lock(self, monkeypatch):
        handler = _handler(monkeypatch, FakeAggregate(2, 6, status='published'), locked=False)
        data = handler.handle_get_report_progress(GetReportProgressQuery(report_id=2))
        assert data['status'] == 'completed'
        assert data['progress'] == 100
        assert data['report_status'] == 'published'

    def test_generation_progress_falls_back_to_zero(self, monkeypatch):
        handler = _handler(monkeypatch, FakeAggregate(3, 7), locked=True, task=None)
        data = handler.handle_get_report_progress(GetReportProgressQuery(report_id=3))
        assert data['status'] == 'generating'
        assert data['progress'] == 0

    def test_zero_total_cases_progress_zero(self, monkeypatch):
        task = {'id': 8, 'total_cases': 0, 'completed_cases': 0}
        handler = _handler(monkeypatch, FakeAggregate(4, 8), locked=True, task=task)
        data = handler.handle_get_report_progress(GetReportProgressQuery(report_id=4))
        assert data['progress'] == 0


class TestGenerationLockProbe:
    """is_generation_locked 探测：键存在判定 + 异常降级。"""

    def test_true_when_key_exists(self, monkeypatch):
        import report_service.application.services.report_task_generator as gen_mod
        import shared.utils.distributed_coordinator as coord

        monkeypatch.setattr(coord, '_enabled', lambda: True)
        monkeypatch.setattr(coord, '_client', lambda: _FakeRedis(exists_result=1))
        assert gen_mod.is_generation_locked(5) is True

    def test_false_when_redis_down(self, monkeypatch):
        import report_service.application.services.report_task_generator as gen_mod
        import shared.utils.distributed_coordinator as coord

        def _boom():
            raise RuntimeError('redis down')

        monkeypatch.setattr(coord, '_enabled', lambda: True)
        monkeypatch.setattr(coord, '_client', _boom)
        assert gen_mod.is_generation_locked(5) is False


class _FakeRedis:
    def __init__(self, exists_result=0):
        self._exists = exists_result

    def exists(self, key):
        return self._exists
