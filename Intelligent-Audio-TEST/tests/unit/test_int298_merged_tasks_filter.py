# -*- coding: utf-8 -*-
"""INT-298 专项：合并容器任务过滤（GET /tasks?merged=true）。

覆盖（对齐 V9.7.10 合并页签数据源语义）：
- task.type 已废弃，合并容器以 TaskMergeRelation 存在性判定；
- merged=true 仅命中合并容器任务（有 TaskMergeRelation.merged_task_id 行）；
  普通任务 / 已被合并的源任务（status=merged 但非容器）不命中；
- merged=true 与 status 组合过滤正常（合并视图状态筛选：completed/merged）；
- 回归：merged 缺省（False）不改变日常列表结果集。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int141 / test_int301 口径。
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


def _seed_merged_chain():
    """种子：源任务A/B（status=merged）→ 合并容器M（status=completed）→ 普通任务P。

    返回 (source_a_id, source_b_id, merged_id, plain_id)。
    """
    from task_service.infrastructure.persistence.models import Task, TaskMergeRelation
    session = get_db_session()
    try:
        a = Task(name='INT298源任务A', status='merged', total_cases=1)
        b = Task(name='INT298源任务B', status='merged', total_cases=1)
        m = Task(name='INT298合并容器', status='completed', total_cases=2)
        p = Task(name='INT298普通任务', status='completed', total_cases=1)
        session.add_all([a, b, m, p])
        session.flush()
        session.add(TaskMergeRelation(merged_task_id=m.id, source_task_id=a.id))
        session.add(TaskMergeRelation(merged_task_id=m.id, source_task_id=b.id))
        session.commit()
        ids = (a.id, b.id, m.id, p.id)
    finally:
        remove_db_session()
    return ids


def test_search_tasks_merged_filter_hits_containers_only(db):
    """merged=true 仅命中合并容器；源任务（status=merged 非容器）与普通任务不命中。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    src_a, src_b, merged_id, plain_id = _seed_merged_chain()

    result = task_read_model.search_tasks(page=1, per_page=50, merged=True)
    ids = {i['id'] for i in result['items']}
    assert merged_id in ids
    assert src_a not in ids and src_b not in ids and plain_id not in ids
    # 容器行携带 source_tasks（既有行为不回归）
    container = next(i for i in result['items'] if i['id'] == merged_id)
    assert {s['id'] for s in container['source_tasks']} == {src_a, src_b}


def test_search_tasks_merged_filter_combines_status(db):
    """merged=true 与 status 组合过滤正常（合并视图状态筛选）。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _src_a, _src_b, merged_id, plain_id = _seed_merged_chain()

    completed = task_read_model.search_tasks(page=1, per_page=50, merged=True,
                                             status='completed')
    assert {i['id'] for i in completed['items']} == {merged_id}

    # status=merged 命中的是源任务（执行侧状态），不含容器——两过滤语义正交
    merged_status = task_read_model.search_tasks(page=1, per_page=50,
                                                 status='merged')
    assert merged_id not in {i['id'] for i in merged_status['items']}


def test_search_tasks_default_includes_all_active(db):
    """回归：merged 缺省（False）不改变日常列表结果集（四类任务全部可见）。"""
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    src_a, src_b, merged_id, plain_id = _seed_merged_chain()

    result = task_read_model.search_tasks(page=1, per_page=50)
    ids = {i['id'] for i in result['items']}
    assert {src_a, src_b, merged_id, plain_id} <= ids
