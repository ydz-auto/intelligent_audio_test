# -*- coding: utf-8 -*-
"""INT-1462 专项：任务列表页级批量组装（报告/设备/API N+1 消解）。

背景：GET /tasks 组装一页任务时逐任务串行调用——
- report_service.ListReports（每任务 1 次跨服务 RPC）
- TaskDevice / TaskAPI 各 1 次 DB 查询（每任务 2 次）
- device_service.GetDeviceStatuses / api_test_service.GetAPIConfig（每任务各 1 次 RPC）
并发下 gRPC 排队，延迟随并发线性恶化。

本文件锁定改后的页级批量口径：
- report_service 仓储 list_report_briefs_by_task_ids：按任务分组、软删过滤、
  每任务条数上限生效
- report_service gRPC ListReportsByTaskIds：信封 {'items_by_task': {任务ID: [...]}}
- task_service search_tasks 组装一页：报告批量 RPC / 设备批量 RPC / API 批量
  RPC 各只调 1 次，且每个任务仍拿到自己的报告/设备/API（分页不串数据）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int273 / test_int297 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import datetime

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.grpc_json import loads as grpc_loads

_TABLES = None


def _ensure_tables():
    global _TABLES
    if _TABLES is None:
        init_db(pool_size=2)
        from report_service.infrastructure.persistence.models import Report
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag,
        )
        from task_service.infrastructure.persistence.models import TaskCherryPickRelation
        _TABLES = [t.__table__ for t in (
            Report, Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI,
            Favorite, TaskCherryPickRelation, Tag, TaskTag,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup():
    session = get_db_session()
    try:
        for table in reversed(_TABLES):
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture()
def db():
    tables = _ensure_tables()
    _cleanup()
    yield tables
    _cleanup()


# =====================================================================
# report_service：仓储与 gRPC 的页级批量接口
# =====================================================================

def _seed_reports():
    """3 条活跃报告 + 1 条软删报告；返回 {task_id: [report_id...]}。"""
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    rows = [
        Report(name='R101a', type='task', status='completed', task_id=101,
               created_at=datetime(2026, 1, 1, 10, 0, 0)),
        Report(name='R101b', type='task', status='completed', task_id=101,
               created_at=datetime(2026, 1, 2, 10, 0, 0)),
        Report(name='R202a', type='task', status='completed', task_id=202,
               created_at=datetime(2026, 1, 3, 10, 0, 0)),
        Report(name='R202del', type='task', status='completed', task_id=202,
               deleted=True, created_at=datetime(2026, 1, 4, 10, 0, 0)),
        # 报告名历史约定：PO.name 为空时回退 analysis(JSON).name
        Report(name='', type='task', status='completed', task_id=303,
               analysis='{"name": "R303-from-config"}',
               created_at=datetime(2026, 1, 5, 10, 0, 0)),
    ]
    session.add_all(rows)
    session.commit()
    return {101: [rows[0].id, rows[1].id], 202: [rows[2].id, rows[3].id],
            303: [rows[4].id]}


def test_repo_groups_briefs_by_task(db):
    """仓储一次查询按任务分组，软删行不计入，按 created_at 倒序。"""
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )
    ids = _seed_reports()

    briefs = report_repository.list_report_briefs_by_task_ids([101, 202, 303, 404])

    assert set(briefs) == {101, 202, 303}, '无报告的任务不应出现在结果中'
    assert [b['id'] for b in briefs[101]] == [ids[101][1], ids[101][0]]
    assert [b['id'] for b in briefs[202]] == [ids[202][0]], '软删报告不得计入'
    assert briefs[101][0]['name'] == 'R101b'
    assert briefs[101][0]['type'] == 'task'
    assert briefs[101][0]['status'] == 'completed'
    # created_at 与逐任务 ListReports 的 str(datetime) 口径一致
    assert briefs[101][0]['created_at'] == '2026-01-02 10:00:00'
    # PO.name 为空时回退 analysis(JSON).name（与列表聚合根同口径）
    assert briefs[303][0]['name'] == 'R303-from-config'


def test_repo_briefs_respects_per_task_limit(db):
    """每任务条数上限生效（列表页报告徽标历史上限 100）。"""
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )
    _seed_reports()

    briefs = report_repository.list_report_briefs_by_task_ids([101], per_task_limit=1)

    assert len(briefs[101]) == 1
    assert briefs[101][0]['name'] == 'R101b'


def test_repo_briefs_empty_input(db):
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )
    _ensure_tables()
    assert report_repository.list_report_briefs_by_task_ids([]) == {}


def test_grpc_list_reports_by_task_ids_envelope(db):
    """gRPC 信封 {'items_by_task': {'<task_id>': [摘要...]}}，键为字符串任务 ID。"""
    from report_service.interfaces.grpc.servicers import ReportServicer
    from shared.proto import report_service_pb2 as report_pb

    ids = _seed_reports()
    resp = ReportServicer().ListReportsByTaskIds(
        report_pb.ListReportsByTaskIdsRequest(task_ids=[101, 202], per_task_limit=100))

    assert resp.success, resp.message
    payload = grpc_loads(resp.data, {})
    assert set(payload['items_by_task']) == {'101', '202'}
    got_101 = payload['items_by_task']['101']
    assert [r['id'] for r in got_101] == [ids[101][1], ids[101][0]]
    assert set(got_101[0]) >= {'id', 'name', 'status', 'type', 'created_at'}

    empty = ReportServicer().ListReportsByTaskIds(
        report_pb.ListReportsByTaskIdsRequest())
    assert empty.success and grpc_loads(empty.data, {}) == {'items_by_task': {}}


# =====================================================================
# task_service：列表组装改为页级批量
# =====================================================================

def _seed_tasks_with_relations():
    """3 个任务：A 关联 2 设备 + 1 API，B 关联 1 设备，C 无关联。"""
    from task_service.infrastructure.persistence.models import (
        Task, TaskDevice, TaskAPI,
    )
    session = get_db_session()
    tasks = [
        Task(name='INT1462A', status='completed', total_cases=1,
             created_at=datetime(2026, 1, 3, 10, 0, 0)),
        Task(name='INT1462B', status='completed', total_cases=1,
             created_at=datetime(2026, 1, 2, 10, 0, 0)),
        Task(name='INT1462C', status='pending', total_cases=0,
             created_at=datetime(2026, 1, 1, 10, 0, 0)),
    ]
    session.add_all(tasks)
    session.flush()
    a, b, c = tasks
    session.add_all([
        TaskDevice(task_id=a.id, device_id=11),
        TaskDevice(task_id=a.id, device_id=12),
        TaskDevice(task_id=b.id, device_id=13),
        TaskAPI(task_id=a.id, api_id=21),
    ])
    session.commit()
    return a.id, b.id, c.id


def test_search_tasks_batches_cross_service_calls(db, monkeypatch):
    """一页 3 个任务：报告/设备/API 各 1 次批量调用，且逐任务数据正确。"""
    from task_service.infrastructure.acl.report_acl_repository import (
        api_test_acl_repository,
        report_acl_repository,
    )
    from task_service.infrastructure.acl.device_acl_repository import (
        device_acl_repository,
    )
    from task_service.infrastructure.read_models.task_read_model import TaskReadModel

    a_id, b_id, c_id = _seed_tasks_with_relations()
    calls = {'reports': [], 'devices': [], 'apis': []}

    def _fake_reports(task_ids):
        calls['reports'].append(list(task_ids))
        return {int(t): [{
            'id': int(t) * 10, 'name': f'R{t}', 'status': 'completed',
            'type': 'task', 'created_at': '2026-01-02 10:00:00',
        }] for t in task_ids}

    def _fake_device_statuses(device_ids):
        calls['devices'].append(list(device_ids))
        return [{'id': i, 'name': f'D{i}', 'status': 'online'} for i in device_ids]

    def _fake_api_list(api_ids):
        calls['apis'].append(list(api_ids))
        return [{'id': i, 'name': f'A{i}', 'status': 'active'} for i in api_ids]

    monkeypatch.setattr(report_acl_repository, 'list_reports_by_task_ids', _fake_reports)
    monkeypatch.setattr(device_acl_repository, 'get_device_statuses', _fake_device_statuses)
    monkeypatch.setattr(api_test_acl_repository, 'fetch_api_list', _fake_api_list)

    result = TaskReadModel().search_tasks(page=1, per_page=10)

    assert result['total'] == 3
    assert len(calls['reports']) == 1, f'报告应一次批量 RPC，实际 {calls["reports"]}'
    assert sorted(calls['reports'][0]) == sorted([a_id, b_id, c_id])
    assert len(calls['devices']) == 1, f'设备应一次批量 RPC，实际 {calls["devices"]}'
    assert sorted(calls['devices'][0]) == [11, 12, 13]
    assert len(calls['apis']) == 1, f'API 应一次批量 RPC，实际 {calls["apis"]}'
    assert calls['apis'][0] == [21]

    by_id = {item['id']: item for item in result['items']}
    a, b, c = by_id[a_id], by_id[b_id], by_id[c_id]
    # 报告按任务归位（不串页）
    assert a['reports']['count'] == 1
    assert a['reports']['reports'][0]['id'] == a_id * 10
    assert b['reports']['reports'][0]['id'] == b_id * 10
    assert c['reports']['count'] == 1
    # 设备/API 按任务归位
    assert [d['id'] for d in a['devices']] == [11, 12]
    assert a['device_count'] == 2
    assert [d['id'] for d in b['devices']] == [13]
    assert c['devices'] == []
    assert [x['id'] for x in a['apis']] == [21]
    assert b['apis'] == [] and c['apis'] == []


def test_search_tasks_deleted_page_skips_batch_calls(db, monkeypatch):
    """回收站模式只输出轻量字段，不触发报告/设备/API 批量调用。"""
    from task_service.infrastructure.acl.report_acl_repository import (
        report_acl_repository,
    )
    from task_service.infrastructure.read_models.task_read_model import TaskReadModel
    from task_service.infrastructure.persistence.models import Task

    _ensure_tables()
    session = get_db_session()
    session.add(Task(name='INT1462Deleted', status='completed', deleted=True))
    session.commit()

    calls = []
    monkeypatch.setattr(
        report_acl_repository, 'list_reports_by_task_ids',
        lambda task_ids: calls.append(list(task_ids)) or {})

    result = TaskReadModel().search_tasks(page=1, per_page=10, deleted=True)

    assert result['total'] == 1
    assert calls == [], '回收站模式不应发起报告批量 RPC'
    assert 'reports' not in result['items'][0]
