# -*- coding: utf-8 -*-
"""INT-1714 专项：容器溯源端点补结果级字段与源任务状态（§11-8）。

覆盖 `GET /api/v1/tasks/cherry-picks/{task_id}/source` 的服务层
（`CherryPickService.source_trace`，网关/gRPC 只做 JSON 透传）：

- `results[]` 追加 `result_type`（落库列，缺值 `default`，与候选行同源）/
  `execution_status` / `evaluated` / `case_name`（缺名 null，不裸显 UUID）/
  `device_name` / `api_name` / `result_created_at`（区别于关系行 `created_at`）
- 老字段一个不删、不改名、不改语义
- `missing=true` 的行结果级字段为 null、`evaluated=false`
- `groups[].source_task_status` 取来源任务状态
- 非容器任务口径按 INT-1706 §8.2：存活普通任务 200 + `is_cherry_pick:false` +
  空 `groups`（不再是 4xx）；任务不存在/容器已软删按 INT-1715 存活判定返 404

DB：进程级 SQLite（对齐 test_int339 口径），gRPC 依赖按需打桩以隔离外部服务。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int1714_proc.db')

from datetime import datetime

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import set_current_user_id

_TABLES = None

_SOURCE_RESULT_CREATED_AT = datetime(2026, 9, 21, 3, 0, 0)


def _ensure_tables():
    global _TABLES
    if _TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )
        _TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture()
def db():
    tables = _ensure_tables()
    _cleanup(tables)
    yield tables
    _cleanup(tables)
    set_current_user_id(None)


def _seed():
    """种子：终态源任务 + 2 结果。

    - `INT1714-C1`（设备 7 / API 101）：有 TestCase 名、result_type='asr'、
      execution_status='failed'、结果创建时间为固定的旧时间
    - `INT1714-C2`（设备 8 / API 102）：无 TestCase 行（缺名场景）、
      result_type 落库 NULL（应输出 default）、execution_status='completed'
    """
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestCase, TestResult,
    )
    session = get_db_session()
    try:
        task = Task(name='INT1714来源任务', status='completed', total_cases=2,
                    algorithm_type='asr')
        session.add(task)
        session.flush()
        session.add(TestCase(id='INT1714-C1', name='用例一', config={},
                             algorithm_type='asr'))
        for case_id, device_id, api_id in (
                ('INT1714-C1', 7, 101), ('INT1714-C2', 8, 102)):
            session.add(TaskCase(
                task_id=task.id, test_case_id=case_id,
                status='completed', execution_status='completed',
                evaluation_status='completed', device_type='physical',
                device_id=str(device_id),
            ))
        r1 = TestResult(
            task_id=task.id, test_case_id='INT1714-C1', device_id=7, api_id=101,
            algorithm_type='asr', execution_status='failed', result_type='asr',
            created_at=_SOURCE_RESULT_CREATED_AT,
        )
        r2 = TestResult(
            task_id=task.id, test_case_id='INT1714-C2', device_id=8, api_id=102,
            algorithm_type='asr', execution_status='completed', result_type=None,
            created_at=_SOURCE_RESULT_CREATED_AT,
        )
        session.add_all([r1, r2])
        session.flush()
        ids = (r1.id, r2.id)
        session.commit()
        return task.id, ids
    finally:
        remove_db_session()


@pytest.fixture()
def patched_names(monkeypatch):
    """打桩跨服务名查询（device / api_test）与评估集合，隔离外部 gRPC。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    monkeypatch.setattr(cherry_pick_service, '_fetch_device_names',
                        lambda ids: {7: '设备七', 8: '设备八'})
    monkeypatch.setattr(cherry_pick_service, '_fetch_api_names',
                        lambda ids: {101: '接口一', 102: '接口二'})
    return cherry_pick_service


def _make_container(service, result_ids):
    service.cart_add({'result_ids': list(result_ids)})
    resp = service.checkout({'action': 'merge', 'name': 'INT1714容器'})
    assert resp['success'] is True, resp.get('message')
    return resp['data']['task_id']


def test_source_trace_appends_result_level_fields(db, patched_names, monkeypatch):
    """容器溯源：7 个追加字段有值，老字段与结构不变。"""
    service = patched_names
    src_task_id, result_ids = _seed()
    # 只有第二条结果已评估（有差异才可验）
    monkeypatch.setattr(service, '_evaluated_result_ids',
                        lambda ids, session=None: {result_ids[1]})
    set_current_user_id(42)
    container_id = _make_container(service, result_ids)

    resp = service.source_trace(container_id)
    assert resp['success'] is True, resp.get('message')
    data = resp['data']
    assert data['task_id'] == container_id
    assert data['is_cherry_pick'] is True
    assert data['total'] == 2
    assert len(data['groups']) == 1
    group = data['groups'][0]
    assert group['source_task_id'] == src_task_id
    assert group['source_task_name'] == 'INT1714来源任务'
    # 来源任务状态（列表 DTO TaskSourceBriefDto 同口径）
    assert group['source_task_status'] == 'completed'

    by_id = {r['result_id']: r for r in group['results']}
    first, second = by_id[result_ids[0]], by_id[result_ids[1]]

    # ---- 老字段：不删 / 不改名 / 不改语义 ----
    old_keys = {'id', 'result_id', 'source_task_id', 'source_task_name',
                'source_case_id', 'source_device_id', 'source_api_id',
                'created_at', 'missing'}
    for row in (first, second):
        assert old_keys <= set(row)
        assert row['missing'] is False
        assert row['source_task_id'] == src_task_id
    assert first['source_case_id'] == 'INT1714-C1'
    assert first['source_device_id'] == 7
    assert first['source_api_id'] == 101
    # 关系行 created_at 语义不变（ISO 字符串，非结果创建时间）
    assert isinstance(first['created_at'], str)

    # ---- 追加字段 ----
    assert first['result_type'] == 'asr'
    assert first['execution_status'] == 'failed'
    assert first['evaluated'] is False
    assert first['case_name'] == '用例一'
    assert first['device_name'] == '设备七'
    assert first['api_name'] == '接口一'
    assert first['result_created_at'] == _SOURCE_RESULT_CREATED_AT.isoformat()
    # 结果时间与关系行时间确实不同（字段名不能复用 created_at 的原因）
    assert first['result_created_at'] != first['created_at']

    assert second['result_type'] == 'default'  # 落库 NULL → 待补充桶
    assert second['execution_status'] == 'completed'
    assert second['evaluated'] is True
    # 缺名返回 null（「未知用例」是前端文案，不裸显 UUID）
    assert second['case_name'] is None
    assert second['device_name'] == '设备八'
    assert second['api_name'] == '接口二'

    set_current_user_id(None)


def test_source_trace_missing_rows_null_result_fields(db, patched_names, monkeypatch):
    """源结果物理删除后：missing=true 且结果级字段 null、evaluated=false。"""
    from task_service.infrastructure.persistence.models import TestResult

    service = patched_names
    _src_task_id, result_ids = _seed()
    monkeypatch.setattr(service, '_evaluated_result_ids',
                        lambda ids, session=None: set(ids))
    set_current_user_id(42)
    container_id = _make_container(service, result_ids)

    session = get_db_session()
    try:
        session.query(TestResult).filter(TestResult.id == result_ids[0]).delete()
        session.commit()
    finally:
        remove_db_session()

    trace = service.source_trace(container_id)
    assert trace['success'] is True, trace.get('message')
    assert trace['data']['total'] == 2, '关系行应保留（引用不随源结果删除）'
    by_id = {r['result_id']: r for g in trace['data']['groups'] for r in g['results']}
    missing = by_id[result_ids[0]]
    assert missing['missing'] is True
    assert missing['result_type'] is None
    assert missing['execution_status'] is None
    assert missing['evaluated'] is False
    assert missing['case_name'] is None
    assert missing['device_name'] is None
    assert missing['api_name'] is None
    assert missing['result_created_at'] is None
    # 老字段仍在（关系行快照不依赖结果行）
    assert missing['source_case_id'] == 'INT1714-C1'
    assert missing['source_task_id'] == trace['data']['groups'][0]['source_task_id']

    set_current_user_id(None)


def test_source_trace_non_container_unchanged(db, patched_names):
    """非容器任务口径：存活普通任务按 INT-1706 §8.2 返 200 + 空 groups。

    合入适配（INT-1742）：本用例原断言的 404 是 INT-1706 之前的口径；INT-1706
    把「不是容器」改成正常查询结果（200 + `is_cherry_pick:false` + `groups: []`），
    本卡追加的结果级字段不改变这一口径。任务不存在/容器已软删的 404 由
    INT-1715 的存活判定负责（见 test_int339 的对应断言）。
    """
    service = patched_names
    src_task_id, _ = _seed()
    set_current_user_id(42)

    resp = service.source_trace(src_task_id)
    assert resp['success'] is True
    assert resp['data']['is_cherry_pick'] is False
    assert resp['data']['groups'] == []

    set_current_user_id(None)
