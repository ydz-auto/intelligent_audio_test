# -*- coding: utf-8 -*-
"""INT-1776 专项：报告列表 / 详情 / HTML 导出补 task_name（任务名恒空修复）。

覆盖：
- 整页一次批量补名：task_id 去重、对比报告（task_id 空）→ ''
- 查不到任务 → ''
- RPC 异常 / 超时 → 全 ''，不抛异常（读路径不因补名失败而失败）
- 三个出口接线：ListReports / GetReportDetail / HTML 导出数据含 task_name

gRPC 批量取任务以 monkeypatch 替身注入（不依赖 task_service / 数据库）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json
import time
from types import SimpleNamespace

import pytest

import report_service.infrastructure.clients.grpc_clients as grpc_clients_mod
from report_service.application.services.report_task_name_enricher import (
    enrich_task_names,
)


def _fake_tasks_by_ids(records=None, calls=None, error=None, delay=None):
    """构造 _grpc_get_tasks_by_ids 替身。"""
    def _fake(task_ids):
        if calls is not None:
            calls.append(list(task_ids))
        if delay is not None:
            time.sleep(delay)
        if error is not None:
            raise error
        wanted = set(task_ids)
        return [t for t in (records or []) if t.get('id') in wanted]
    return _fake


class TestEnrichTaskNames:
    """enrich_task_names 批量补名与降级。"""

    def test_batch_fills_names_with_one_call(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            grpc_clients_mod, '_grpc_get_tasks_by_ids',
            _fake_tasks_by_ids(
                [{'id': 398, 'name': '声纹识别回归'}, {'id': 413, 'name': '噪声场景'}],
                calls=calls))
        items = [
            {'id': 1, 'task_id': 398},
            {'id': 2, 'task_id': 413},
            {'id': 3, 'task_id': 413},
            {'id': 4, 'task_id': 0},  # 对比 / 二次对比报告
        ]
        enrich_task_names(items, timeout_seconds=5)

        assert calls == [[398, 413]]  # 整页仅一次调用且 task_id 去重
        assert [it['task_name'] for it in items] == ['声纹识别回归', '噪声场景', '噪声场景', '']

    def test_missing_task_degrades_to_empty(self, monkeypatch):
        monkeypatch.setattr(
            grpc_clients_mod, '_grpc_get_tasks_by_ids', _fake_tasks_by_ids([]))
        items = [{'id': 1, 'task_id': 527}]
        enrich_task_names(items, timeout_seconds=5)
        assert items[0]['task_name'] == ''

    def test_rpc_error_degrades_to_empty(self, monkeypatch):
        monkeypatch.setattr(
            grpc_clients_mod, '_grpc_get_tasks_by_ids',
            _fake_tasks_by_ids(error=RuntimeError('task_service 不可达')))
        items = [{'id': 1, 'task_id': 398}, {'id': 2, 'task_id': 413}]
        enrich_task_names(items, timeout_seconds=5)  # 不抛异常
        assert [it['task_name'] for it in items] == ['', '']

    def test_timeout_degrades_to_empty(self, monkeypatch):
        monkeypatch.setattr(
            grpc_clients_mod, '_grpc_get_tasks_by_ids',
            _fake_tasks_by_ids([{'id': 398, 'name': 'x'}], delay=1.0))
        items = [{'id': 1, 'task_id': 398}]
        enrich_task_names(items, timeout_seconds=0.05)
        assert items[0]['task_name'] == ''

    def test_keeps_existing_name_when_lookup_empty(self, monkeypatch):
        """查不到时保留已有值（HTML 导出 config 兜底口径）。"""
        monkeypatch.setattr(
            grpc_clients_mod, '_grpc_get_tasks_by_ids', _fake_tasks_by_ids([]))
        items = [{'id': 1, 'task_id': 398, 'task_name': '历史快照名'}]
        enrich_task_names(items, timeout_seconds=5)
        assert items[0]['task_name'] == '历史快照名'

    def test_empty_items_no_rpc(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            grpc_clients_mod, '_grpc_get_tasks_by_ids',
            _fake_tasks_by_ids([], calls=calls))
        assert enrich_task_names([], timeout_seconds=5) == []
        assert enrich_task_names(None, timeout_seconds=5) is None
        assert calls == []


# ----------------------------------------------------------------------
# 出口接线：servicer / HTML 导出
# ----------------------------------------------------------------------

class _FakeAggregate:
    """_aggregate_to_dict 所需的最小聚合根替身。"""

    def __init__(self, report_id, task_id, name='报告'):
        self.id = report_id
        self.task_id = task_id
        self.name = name
        self.report_type = 'standard'
        self.status = 'published'
        self.config = {}
        self.created_at = None
        self.visibility = 'shared'
        self.created_by_user_id = None
        self.deleted = False
        self.deleted_at = None
        self.deleted_by_user_id = None
        self.full_summary = None
        self.summaries = []
        self.cases = []
        self.metric_stats = []
        self.raw_data = []

    def flat_summary(self):
        return {}


class _FakeQueryHandler:
    def __init__(self, aggregates):
        self._aggregates = aggregates

    def handle_list(self, query):
        return self._aggregates

    def handle_count_reports(self, query):
        return len(self._aggregates)

    def handle_get(self, query):
        return self._aggregates[0] if self._aggregates else None

    def handle_get_by_task(self, query):
        return self._aggregates[0] if self._aggregates else None


def _servicer(aggregates):
    from report_service.interfaces.grpc.servicers import ReportServicer

    servicer = ReportServicer()
    servicer._query_handler = _FakeQueryHandler(aggregates)
    return servicer


def test_list_reports_includes_task_name(monkeypatch):
    monkeypatch.setattr(
        grpc_clients_mod, '_grpc_get_tasks_by_ids',
        _fake_tasks_by_ids([{'id': 398, 'name': '声纹识别回归'}]))
    servicer = _servicer([_FakeAggregate(11, 398)])
    request = SimpleNamespace(
        status='', report_type='', task_id=0, page=1, per_page=20,
        favorite=False, deleted=False)

    resp = servicer.ListReports(request, context=None)

    assert resp.success
    data = json.loads(resp.data)
    assert data['items'][0]['task_name'] == '声纹识别回归'


def test_get_report_detail_includes_task_name(monkeypatch):
    monkeypatch.setattr(
        grpc_clients_mod, '_grpc_get_tasks_by_ids',
        _fake_tasks_by_ids([{'id': 413, 'name': '噪声场景'}]))
    servicer = _servicer([_FakeAggregate(12, 413)])
    request = SimpleNamespace(report_id=12)

    resp = servicer.GetReportDetail(request, context=None)

    assert resp.success
    assert json.loads(resp.data)['task_name'] == '噪声场景'


def test_get_report_by_task_includes_task_name(monkeypatch):
    monkeypatch.setattr(
        grpc_clients_mod, '_grpc_get_tasks_by_ids',
        _fake_tasks_by_ids([{'id': 418, 'name': '豆包拒识E2E测试任务'}]))
    servicer = _servicer([_FakeAggregate(14, 418)])
    request = SimpleNamespace(task_id=418)

    resp = servicer.GetReportByTask(request, context=None)

    assert resp.success
    assert json.loads(resp.data)['task_name'] == '豆包拒识E2E测试任务'


def test_html_export_data_includes_task_name(monkeypatch):
    from report_service.application.handlers._report_cases_query_mixin import (
        ReportCasesQueryMixin,
    )

    monkeypatch.setattr(
        grpc_clients_mod, '_grpc_get_tasks_by_ids',
        _fake_tasks_by_ids([{'id': 398, 'name': '声纹识别回归'}]))
    aggregate = _FakeAggregate(11, 398)
    data = ReportCasesQueryMixin._assemble_html_report_data(aggregate, {'cases': []})
    assert data['task_name'] == '声纹识别回归'


@pytest.mark.parametrize('task_id', [0, None])
def test_compare_report_task_name_empty(monkeypatch, task_id):
    calls = []
    monkeypatch.setattr(
        grpc_clients_mod, '_grpc_get_tasks_by_ids',
        _fake_tasks_by_ids([], calls=calls))
    servicer = _servicer([_FakeAggregate(13, task_id)])
    request = SimpleNamespace(report_id=13)

    resp = servicer.GetReportDetail(request, context=None)

    assert resp.success
    assert json.loads(resp.data)['task_name'] == ''
    assert calls == []  # 无 task_id 不触发补名 RPC
