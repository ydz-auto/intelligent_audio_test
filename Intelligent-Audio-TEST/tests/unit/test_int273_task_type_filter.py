# -*- coding: utf-8 -*-
"""INT-273 专项：任务类型筛选（GET /tasks?task_type=api|e2e|mixed）。

派生口径（与 /tasks/stats type_counts 一致，task.type 列已废弃删除）：
- api   = 无物理设备用例（含无 device_type 行与未知类型行 → api）
- e2e   = 含物理设备用例且无 API 设备用例（http_api/websocket_api）
- mixed = 物理设备用例与 API 设备用例兼有

覆盖：
- task_type=api 命中纯 API 任务（含无用例任务，对齐统计口径）
- task_type=e2e 仅命中纯物理任务，mixed 任务不落入 e2e
- task_type=mixed 命中物理+API 兼有任务
- task_type 与 status 组合过滤正常
- 回归：task_type 缺省（None）不改变日常列表结果集

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int298 / test_int141 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_TASK_TABLES = None


def _ensure_task_tables():
    global _TASK_TABLES
    if _TASK_TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TASK_TABLES)
    return _TASK_TABLES


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
    tables = _ensure_task_tables()
    _cleanup(tables)
    yield tables
    _cleanup(tables)


def _seed_type_chain():
    """种子：纯 API 任务 / 纯物理(e2e)任务 / 混合任务 / 无用例任务。

    返回 (api_id, e2e_id, mixed_id, no_case_id)。
    """
    from task_service.infrastructure.persistence.models import Task, TaskCase
    from shared.models.common_enums import DeviceType
    session = get_db_session()
    try:
        api_t = Task(name='INT273纯API任务', status='completed', total_cases=1)
        e2e_t = Task(name='INT273纯物理任务', status='completed', total_cases=1)
        mixed_t = Task(name='INT273混合任务', status='completed', total_cases=2)
        no_case_t = Task(name='INT273无用例任务', status='pending', total_cases=0)
        session.add_all([api_t, e2e_t, mixed_t, no_case_t])
        session.flush()
        # 纯 API：两行均为 http_api / websocket_api
        session.add_all([
            TaskCase(task_id=api_t.id, test_case_id='c-api-1',
                     device_type=DeviceType.HTTP_API.value),
            TaskCase(task_id=api_t.id, test_case_id='c-api-2',
                     device_type=DeviceType.WEBSOCKET_API.value),
            # 纯物理：仅 physical
            TaskCase(task_id=e2e_t.id, test_case_id='c-e2e-1',
                     device_type=DeviceType.PHYSICAL.value),
            # 混合：physical + http_api 兼有
            TaskCase(task_id=mixed_t.id, test_case_id='c-mix-1',
                     device_type=DeviceType.PHYSICAL.value),
            TaskCase(task_id=mixed_t.id, test_case_id='c-mix-2',
                     device_type=DeviceType.HTTP_API.value),
        ])
        session.commit()
        ids = (api_t.id, e2e_t.id, mixed_t.id, no_case_t.id)
    finally:
        remove_db_session()
    return ids


def test_task_type_api_filter_hits_api_and_no_case_tasks(db):
    """task_type=api 命中纯 API 任务；无用例任务按派生口径计入 api。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    api_id, e2e_id, mixed_id, no_case_id = _seed_type_chain()

    result = task_read_model.search_tasks(page=1, per_page=50, task_type='api')
    ids = {i['id'] for i in result['items']}
    assert api_id in ids
    assert no_case_id in ids
    assert e2e_id not in ids and mixed_id not in ids


def test_task_type_e2e_filter_hits_physical_only(db):
    """task_type=e2e 仅命中纯物理任务；混合任务不落入 e2e。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    api_id, e2e_id, mixed_id, _no_case_id = _seed_type_chain()

    result = task_read_model.search_tasks(page=1, per_page=50, task_type='e2e')
    ids = {i['id'] for i in result['items']}
    assert e2e_id in ids
    assert api_id not in ids and mixed_id not in ids


def test_task_type_mixed_filter_hits_both_device_kinds(db):
    """task_type=mixed 仅命中物理 + API 设备用例兼有的任务。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    api_id, e2e_id, mixed_id, _no_case_id = _seed_type_chain()

    result = task_read_model.search_tasks(page=1, per_page=50, task_type='mixed')
    ids = {i['id'] for i in result['items']}
    assert mixed_id in ids
    assert api_id not in ids and e2e_id not in ids


def test_task_type_combines_with_status(db):
    """task_type 与 status 组合过滤正常（AND 语义）。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    api_id, _e2e_id, _mixed_id, no_case_id = _seed_type_chain()

    result = task_read_model.search_tasks(page=1, per_page=50, task_type='api',
                                          status='completed')
    ids = {i['id'] for i in result['items']}
    assert api_id in ids
    assert no_case_id not in ids  # pending 行被 status 过滤剔除


def test_task_type_default_does_not_change_result_set(db):
    """回归：task_type 缺省（None）不改变日常列表结果集（四类任务全部可见）。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    api_id, e2e_id, mixed_id, no_case_id = _seed_type_chain()

    result = task_read_model.search_tasks(page=1, per_page=50)
    ids = {i['id'] for i in result['items']}
    assert {api_id, e2e_id, mixed_id, no_case_id} <= ids


def test_task_type_invalid_value_ignored(db):
    """回归：非法 task_type 值被忽略（不报错、不改变结果集）。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    api_id, e2e_id, mixed_id, no_case_id = _seed_type_chain()

    result = task_read_model.search_tasks(page=1, per_page=50, task_type='bogus')
    ids = {i['id'] for i in result['items']}
    assert {api_id, e2e_id, mixed_id, no_case_id} <= ids
