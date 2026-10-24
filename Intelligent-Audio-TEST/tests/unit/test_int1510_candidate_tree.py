# -*- coding: utf-8 -*-
"""INT-1510 专项：挑选合并阶段 2 候选树聚合端点（设计文档 §8.2）。

覆盖：
- 契约字段齐全：data = {total, task_count, meta{tasks,cases,devices,apis}, tree}；
- 计数一致：tree 各层计数求和 = total（叶节点 count = len(result_ids)）；
- result_type 缺值归缺值桶 `default`（落库 NULL/空串，§8.2.2）；
- 容器任务经 task_cherry_pick_relations 展开，命中原结果；同一行只进一个任务
  节点（直查命中优先），total / task_count 不重复计（§8.2.2 容器口径）；
- 维度过滤：device_ids / api_ids / case_ids / case_keyword / execution_status /
  evaluation_status / 时间范围（结果级，与 candidates 同语义）；
- 权限可见性（INT-423）：非 owner 非 admin 看不到他人私有任务的结果；
- 参数校验：task_ids 缺失 / 空 / >200 → 400（网关 schema + task_service 双侧）；
- 性能硬性：请求路径零 OSS 往返（storage.exists/load_bytes 调用即失败）、
  跨服务调用只剩设备名/API 名各 1 次且与行数无关（调用计数）；
- 选择口径：select-all 返回集合 = tree 各 result_type 节点 result_ids 并集。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int1496 / test_int1130 口径。评估域表在单测库内以最小 DDL 建出
（只读投影 `test_result_dimensions`，与生产共享库同语义）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int1510_proc.db')

import pytest
from sqlalchemy import text

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import (
    set_current_user_id, set_current_user_is_admin,
)

_TABLES = None

_OWNER = 42
_OTHER = 43
_ADMIN = 99

_MIN_EVAL_TABLE_DDL = (
    'CREATE TABLE IF NOT EXISTS test_result_dimensions ('
    ' id INTEGER PRIMARY KEY AUTOINCREMENT,'
    ' test_result_id INTEGER NOT NULL,'
    ' dimension_id INTEGER)'
)


def _ensure_tables():
    global _TABLES
    if _TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, Tag, TaskTag, TestCase, TestCaseGroup, TestCaseTag,
            TestResult, TaskCherryPickRelation,
        )
        _TABLES = [t.__table__ for t in (
            Task, TaskCase, Tag, TaskTag, TestCase, TestCaseGroup, TestCaseTag,
            TestResult, TaskCherryPickRelation,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
        with get_engine().begin() as conn:
            conn.execute(text(_MIN_EVAL_TABLE_DDL))
        remove_db_session()
    return _TABLES


def _cleanup(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.execute(text('DELETE FROM test_result_dimensions'))
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture()
def db(monkeypatch):
    """建表 + 清库；默认把设备/API 名 gRPC 桩成空（各用例按需覆盖）。"""
    tables = _ensure_tables()
    _cleanup(tables)
    from task_service.infrastructure.acl import device_acl_repository as device_mod
    from task_service.infrastructure.acl import report_acl_repository as report_mod
    monkeypatch.setattr(device_mod.device_acl_repository,
                        'get_device_statuses', lambda ids: [])
    monkeypatch.setattr(report_mod.api_test_acl_repository,
                        'fetch_api_names', lambda ids: {})
    yield tables
    _cleanup(tables)
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _seed_task(name, status='completed', owner=_OWNER, visibility='shared',
               deleted=False, results=()):
    """种子任务 + 结果行。

    results: [{case_id, device_id?, api_id?, result_type?, execution_status?,
               excluded?, created_at?}]，返回 (task_id, [result_id...])。
    """
    from task_service.infrastructure.persistence.models import Task, TestResult
    session = get_db_session()
    try:
        task = Task(name=name, status=status, total_cases=len(results),
                    created_by_user_id=owner, visibility=visibility,
                    deleted=deleted)
        session.add(task)
        session.flush()
        result_ids = []
        for row in results:
            result = TestResult(
                task_id=task.id,
                test_case_id=row.get('case_id'),
                device_id=row.get('device_id'),
                api_id=row.get('api_id'),
                algorithm_type=row.get('algorithm_type', 'asr'),
                execution_status=row.get('execution_status', 'completed'),
                excluded=row.get('excluded', 0),
                result_type=row.get('result_type'),
                created_at=row.get('created_at'),
            )
            session.add(result)
            session.flush()
            result_ids.append(result.id)
        session.commit()
        return task.id, result_ids
    finally:
        remove_db_session()


def _seed_case(case_id, name=None, group_id=None, group_name=None, tags=(),
               config=None, algorithm_type='asr', deleted=False):
    from task_service.infrastructure.persistence.models import (
        TestCase, TestCaseGroup, Tag,
    )
    session = get_db_session()
    try:
        if group_id and session.get(TestCaseGroup, group_id) is None:
            session.add(TestCaseGroup(id=group_id, name=group_name or group_id))
            session.flush()
        case = TestCase(id=case_id, name=name or case_id, description='',
                        group_id=group_id, config=config or {},
                        algorithm_type=algorithm_type, deleted=deleted)
        session.add(case)
        session.flush()
        for tag_name in tags:
            tag = session.query(Tag).filter(Tag.name == tag_name).first()
            if tag is None:
                tag = Tag(name=tag_name)
                session.add(tag)
                session.flush()
            case.tags.append(tag)
        session.commit()
    finally:
        remove_db_session()


def _tree(**kwargs):
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    return cherry_pick_service.candidate_tree(kwargs)


def _all_result_ids(tree):
    out = []
    for task_node in tree:
        for case_node in task_node['cases']:
            for device_node in case_node['devices']:
                for rt_node in device_node['result_types']:
                    out.extend(rt_node['result_ids'])
    return out


# ==================== 契约与计数一致性 ====================

def test_tree_contract_and_count_consistency(db):
    """契约字段齐全；四层计数求和 = total；叶 count = len(result_ids)。"""
    task_a, ids_a = _seed_task('树任务A', results=[
        {'case_id': 'C1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'C1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'C1', 'device_id': 2, 'result_type': 'real-time'},
        {'case_id': 'C2', 'device_id': 1, 'result_type': None},
    ])
    task_b, ids_b = _seed_task('树任务B', results=[
        {'case_id': 'C1', 'device_id': 7, 'api_id': 9, 'result_type': 'asr'},
    ])

    resp = _tree(task_ids=[task_a, task_b])
    assert resp['success'] is True
    data = resp['data']
    assert set(data) == {'total', 'task_count', 'meta', 'tree'}
    assert set(data['meta']) == {'tasks', 'cases', 'devices', 'apis'}
    assert data['total'] == 5
    assert data['task_count'] == 2

    # 各级计数求和一致
    assert sum(t['count'] for t in data['tree']) == data['total']
    for task_node in data['tree']:
        assert task_node['count'] == sum(c['count'] for c in task_node['cases'])
        for case_node in task_node['cases']:
            assert case_node['count'] == sum(
                d['count'] for d in case_node['devices'])
            for device_node in case_node['devices']:
                assert device_node['count'] == sum(
                    rt['count'] for rt in device_node['result_types'])
                for rt_node in device_node['result_types']:
                    assert rt_node['count'] == len(rt_node['result_ids'])

    # 命中结果 ID 不重不漏
    assert sorted(_all_result_ids(data['tree'])) == sorted(ids_a + ids_b)


def test_tree_shape_and_default_bucket(db):
    """树形：任务→用例→设备/API→result_type；result_type 缺值进 default 桶。"""
    task_id, _ids = _seed_task('形状任务', results=[
        {'case_id': 'C1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'C2', 'device_id': None, 'api_id': 5, 'result_type': ''},
    ])
    data = _tree(task_ids=[task_id])['data']
    task_node = data['tree'][0]
    assert task_node['task_id'] == task_id
    cases = {c['case_id']: c for c in task_node['cases']}
    assert set(cases) == {'C1', 'C2'}

    c1_devices = cases['C1']['devices']
    assert c1_devices[0]['device_id'] == 1 and c1_devices[0]['api_id'] is None
    assert [rt['result_type'] for rt in c1_devices[0]['result_types']] == ['final']

    c2_devices = cases['C2']['devices']
    assert c2_devices[0]['device_id'] is None and c2_devices[0]['api_id'] == 5
    # 空串与 NULL 同为缺值桶，对外值 default
    assert [rt['result_type'] for rt in c2_devices[0]['result_types']] == ['default']


def test_meta_dedup_tables(db, monkeypatch):
    """meta 为去重表：tasks/cases/devices/apis 各一条，字段口径齐全。"""
    from task_service.infrastructure.acl import device_acl_repository as device_mod

    monkeypatch.setattr(
        device_mod.device_acl_repository, 'get_device_statuses',
        lambda ids: [{'id': d, 'name': f'设备{d}'} for d in ids])

    _seed_case('MC1', name='用例一号', group_id='g1', group_name='分组一',
               tags=['标签甲'], config={'rounds': [{'roundNumber': 1}]})
    task_a, _ = _seed_task('meta任务A', results=[
        {'case_id': 'MC1', 'device_id': 1, 'result_type': 'final'},
    ])
    task_b, _ = _seed_task('meta任务B', results=[
        {'case_id': 'MC1', 'device_id': 2, 'result_type': 'final'},
    ])

    data = _tree(task_ids=[task_a, task_b])['data']
    meta = data['meta']
    assert [t['task_id'] for t in meta['tasks']] == sorted([task_a, task_b])
    assert {t['task_name'] for t in meta['tasks']} == {'meta任务A', 'meta任务B'}
    assert all(t['task_status'] == 'completed' for t in meta['tasks'])

    assert len(meta['cases']) == 1
    case_meta = meta['cases'][0]
    assert case_meta['case_id'] == 'MC1'
    assert case_meta['case_name'] == '用例一号'
    assert case_meta['tags'] == ['标签甲']
    assert case_meta['group_id'] == 'g1'
    assert case_meta['group_name'] == '分组一'
    assert case_meta['rounds'] == 1
    assert case_meta['duration'] is None  # 无音频
    assert case_meta['algorithm_type'] == 'asr'

    assert [d['device_id'] for d in meta['devices']] == [1, 2]
    assert [d['device_name'] for d in meta['devices']] == ['设备1', '设备2']
    assert meta['apis'] == []  # 无 API 归属行

    # 去重：同名结果行不重复出现在 meta
    assert len(meta['tasks']) == 2 and len(meta['devices']) == 2


# ==================== 容器任务展开（INT-657 口径） ====================

def _seed_container(name, source_task_id, result_ids):
    from task_service.infrastructure.persistence.models import (
        Task, TaskCherryPickRelation,
    )
    session = get_db_session()
    try:
        container = Task(name=name, status='completed', total_cases=len(result_ids),
                         created_by_user_id=_OWNER, visibility='shared')
        session.add(container)
        session.flush()
        for rid in result_ids:
            session.add(TaskCherryPickRelation(
                cherry_pick_task_id=container.id, result_id=rid,
                source_task_id=source_task_id, source_task_name='源任务'))
        session.commit()
        return container.id
    finally:
        remove_db_session()


def test_container_expands_and_no_double_count(db):
    """容器任务展开引用结果；容器 + 源任务同传时直查优先，total 不重复计。"""
    source_id, result_ids = _seed_task('容器源任务', results=[
        {'case_id': 'C1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'C1', 'device_id': 1, 'result_type': 'final'},
    ])
    container_id = _seed_container('挑选容器', source_id, result_ids)

    only_container = _tree(task_ids=[container_id])['data']
    assert only_container['total'] == 2
    assert only_container['task_count'] == 1
    assert only_container['tree'][0]['task_id'] == container_id
    assert only_container['meta']['tasks'][0]['task_name'] == '挑选容器'
    assert sorted(_all_result_ids(only_container['tree'])) == sorted(result_ids)

    # 容器 + 源任务同传：同一行只进一个任务节点（直查优先），不重复计
    both = _tree(task_ids=[source_id, container_id])['data']
    assert both['total'] == 2
    assert both['task_count'] == 1
    assert both['tree'][0]['task_id'] == source_id


def test_container_not_pickable_falls_back_to_direct(db):
    """容器任务非终态（已合并/已删除）不可再挑：不展开引用（与 candidates 同口径）。"""
    source_id, result_ids = _seed_task('容器源B', results=[
        {'case_id': 'C1', 'device_id': 1, 'result_type': 'final'},
    ])
    container_id = _seed_container('不可再挑容器', source_id, result_ids)
    session = get_db_session()
    try:
        from task_service.infrastructure.persistence.models import Task
        task = session.get(Task, container_id)
        task.status = 'merged'
        session.commit()
    finally:
        remove_db_session()

    data = _tree(task_ids=[container_id])['data']
    assert data['total'] == 0 and data['tree'] == []


# ==================== 维度过滤 ====================

def _seed_filter_fixture():
    for case_id, name in (('F1', '过滤用例甲'), ('F2', '过滤用例乙'),
                          ('F3', '过滤用例丙')):
        _seed_case(case_id, name=name)
    task_id, _ = _seed_task('过滤任务', results=[
        {'case_id': 'F1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'F2', 'device_id': 2, 'api_id': 7, 'result_type': 'asr'},
        {'case_id': 'F3', 'device_id': 1, 'result_type': 'final',
         'execution_status': 'failed'},
    ])
    return task_id


def test_filter_by_device_api_case(db):
    task_id = _seed_filter_fixture()
    assert _tree(task_ids=[task_id], device_ids=[1])['data']['total'] == 2
    assert _tree(task_ids=[task_id], device_ids=[2])['data']['total'] == 1
    assert _tree(task_ids=[task_id], api_ids=[7])['data']['total'] == 1
    assert _tree(task_ids=[task_id], case_ids=['F2'])['data']['total'] == 1
    assert _tree(task_ids=[task_id], case_ids=['F1', 'F3'])['data']['total'] == 2
    assert _tree(task_ids=[task_id], case_keyword='F3')['data']['total'] == 1


def test_filter_by_execution_status_and_date(db):
    from datetime import datetime

    task_id = _seed_filter_fixture()
    data = _tree(task_ids=[task_id], execution_status='failed')['data']
    assert data['total'] == 1
    assert data['tree'][0]['cases'][0]['case_id'] == 'F3'

    future = datetime(2099, 1, 1).isoformat()
    assert _tree(task_ids=[task_id], start_date=future)['data']['total'] == 0
    past = datetime(2000, 1, 1).isoformat()
    assert _tree(task_ids=[task_id], end_date=past)['data']['total'] == 0
    assert _tree(task_ids=[task_id], start_date=past)['data']['total'] == 3


def test_filter_by_evaluation_status(db):
    """evaluation_status 走评估域存在性投影（子查询，不回传结果 ID 列表）。"""
    task_id, result_ids = _seed_task('评估过滤任务', results=[
        {'case_id': 'E1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'E2', 'device_id': 1, 'result_type': 'final'},
    ])
    session = get_db_session()
    try:
        session.execute(
            text('INSERT INTO test_result_dimensions (test_result_id, dimension_id) '
                 'VALUES (:rid, 1)'), {'rid': result_ids[0]})
        session.commit()
    finally:
        remove_db_session()

    evaluated = _tree(task_ids=[task_id], evaluation_status='evaluated')['data']
    assert evaluated['total'] == 1
    assert _all_result_ids(evaluated['tree']) == [result_ids[0]]

    pending = _tree(task_ids=[task_id], evaluation_status='pending')['data']
    assert pending['total'] == 1
    assert _all_result_ids(pending['tree']) == [result_ids[1]]

    bad = _tree(task_ids=[task_id], evaluation_status='unknown')
    assert bad['success'] is False


def test_excluded_and_non_finished_scope(db):
    """excluded=1 行剔除；非终态 / 已删任务不入树（§10 可挑选口径）。"""
    ok_id, _ = _seed_task('终态任务', results=[
        {'case_id': 'S1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'S1', 'device_id': 1, 'result_type': 'final', 'excluded': 1},
    ])
    running_id, _ = _seed_task('执行中任务', status='running', results=[
        {'case_id': 'S2', 'device_id': 1, 'result_type': 'final'},
    ])
    deleted_id, _ = _seed_task('已删任务', deleted=True, results=[
        {'case_id': 'S3', 'device_id': 1, 'result_type': 'final'},
    ])

    data = _tree(task_ids=[ok_id, running_id, deleted_id])['data']
    assert data['total'] == 1
    assert [t['task_id'] for t in data['tree']] == [ok_id]


# ==================== 可见性（INT-423） ====================

def test_visibility_private_task_hidden_from_others(db):
    shared_id, _ = _seed_task('共享任务', owner=_OTHER, visibility='shared', results=[
        {'case_id': 'V1', 'device_id': 1, 'result_type': 'final'},
    ])
    own_private_id, _ = _seed_task('我的私有任务', owner=_OWNER, visibility='private',
                                   results=[
        {'case_id': 'V2', 'device_id': 1, 'result_type': 'final'},
    ])
    other_private_id, _ = _seed_task('他人私有任务', owner=_OTHER, visibility='private',
                                     results=[
        {'case_id': 'V3', 'device_id': 1, 'result_type': 'final'},
    ])
    task_ids = [shared_id, own_private_id, other_private_id]

    set_current_user_id(_OWNER)
    set_current_user_is_admin(False)
    data = _tree(task_ids=task_ids)['data']
    assert data['total'] == 2
    assert set(t['task_id'] for t in data['tree']) == {shared_id, own_private_id}

    # 他人私有任务及其实体结果都不可见（即便显式传任务 ID）
    assert _tree(task_ids=[other_private_id])['data']['total'] == 0

    set_current_user_id(_ADMIN)
    set_current_user_is_admin(True)
    assert _tree(task_ids=task_ids)['data']['total'] == 3


# ==================== 选择口径：select-all 与树并集一致 ====================

def test_select_all_matches_tree_result_ids(db):
    task_id, result_ids = _seed_task('全选任务', results=[
        {'case_id': 'A1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'A1', 'device_id': 1, 'result_type': 'real-time'},
        {'case_id': 'A2', 'device_id': 2, 'result_type': None},
    ])
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    tree_data = _tree(task_ids=[task_id])['data']
    tree_ids = set(_all_result_ids(tree_data['tree']))
    assert tree_ids == set(result_ids)

    select_all = cherry_pick_service.list_candidates({
        'task_ids': [task_id], 'select_all': True})
    assert select_all['success'] is True
    assert set(select_all['data']['result_ids']) == tree_ids
    # 与 tree.total 同口径
    assert select_all['data']['result_ids'].__len__() == tree_data['total']


def test_leaf_detail_pagination_no_overlap(db):
    """tree 只给节点计数与 result_id 集；叶明细走 candidates 分页，逐页不重不漏。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    results = [{'case_id': f'P{i}', 'device_id': 1, 'result_type': 'final'}
               for i in range(5)]
    task_id, result_ids = _seed_task('叶分页任务', results=results)

    data = _tree(task_ids=[task_id])['data']
    # 叶节点只含 result_type/count/result_ids，不下发结果行明细
    for task_node in data['tree']:
        for case_node in task_node['cases']:
            for device_node in case_node['devices']:
                for rt_node in device_node['result_types']:
                    assert set(rt_node) == {'result_type', 'count', 'result_ids'}

    seen = []
    page = 1
    while True:
        resp = cherry_pick_service.list_candidates(
            {'task_ids': [task_id], 'page': page, 'per_page': 2})
        items = resp['data']['items']
        if not items:
            break
        seen.extend(item['result_id'] for item in items)
        page += 1
    assert sorted(seen) == sorted(result_ids)
    assert len(seen) == len(set(seen))
    assert sorted(_all_result_ids(data['tree'])) == sorted(result_ids)


# ==================== 性能硬性：零 OSS / 跨服务调用计数 ====================
def test_tree_request_zero_oss_roundtrip(db, monkeypatch):
    """tree 请求路径零 OSS 往返（result_type 取落库列，不回源结果文件）。"""
    from shared.infrastructure import storage as storage_mod

    def _boom(*args, **kwargs):
        raise AssertionError('tree 请求路径不得回源对象存储（§8.2.3 第 1 条）')

    monkeypatch.setattr(storage_mod.storage, 'exists', _boom)
    monkeypatch.setattr(storage_mod.storage, 'load_bytes', _boom)

    task_id, result_ids = _seed_task('零OSS任务', results=[
        {'case_id': 'O1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'O1', 'device_id': 1, 'result_type': None},
    ])
    data = _tree(task_ids=[task_id])['data']
    assert data['total'] == 2
    assert sorted(_all_result_ids(data['tree'])) == sorted(result_ids)


def test_cross_service_calls_bounded_and_row_independent(db, monkeypatch):
    """跨服务调用 = 设备名 1 次 + API 名 1 次，与结果行数/节点数无关。"""
    from task_service.infrastructure.acl import device_acl_repository as device_mod
    from task_service.infrastructure.acl import report_acl_repository as report_mod

    calls = {'device': 0, 'api': 0}

    def _device_statuses(ids):
        calls['device'] += 1
        calls['device_ids'] = list(ids)
        return [{'id': d, 'name': f'设备{d}'} for d in ids]

    def _api_names(ids):
        calls['api'] += 1
        calls['api_ids'] = list(ids)
        return {int(a): f'API{a}' for a in ids}

    monkeypatch.setattr(device_mod.device_acl_repository,
                        'get_device_statuses', _device_statuses)
    monkeypatch.setattr(report_mod.api_test_acl_repository,
                        'fetch_api_names', _api_names)

    small_id, _ = _seed_task('少量行任务', results=[
        {'case_id': 'X1', 'device_id': 1, 'api_id': 3, 'result_type': 'final'},
    ])
    big_rows = []
    for i in range(40):
        big_rows.append({'case_id': f'B{i % 7}', 'device_id': (i % 5) + 1,
                         'api_id': 100 + (i % 3), 'result_type': 'final'})
    big_id, _ = _seed_task('多行任务', results=big_rows)

    _tree(task_ids=[small_id])
    assert calls['device'] == 1 and calls['api'] == 1

    calls['device'] = calls['api'] = 0
    data = _tree(task_ids=[big_id])['data']
    assert data['total'] == 40
    # 行数 / 节点数放大不放大跨服务调用
    assert calls['device'] == 1 and calls['api'] == 1
    assert sorted(calls['device_ids']) == [1, 2, 3, 4, 5]
    assert sorted(calls['api_ids']) == [100, 101, 102]


def test_no_cross_service_call_without_device_or_api(db, monkeypatch):
    """无设备/API 归属的结果行不触发任何跨服务调用。"""
    calls = {'device': 0, 'api': 0}
    from task_service.infrastructure.acl import device_acl_repository as device_mod
    from task_service.infrastructure.acl import report_acl_repository as report_mod
    monkeypatch.setattr(
        report_mod.api_test_acl_repository, 'fetch_api_names',
        lambda ids: calls.__setitem__('api', calls['api'] + 1) or {})
    monkeypatch.setattr(
        device_mod.device_acl_repository, 'get_device_statuses',
        lambda ids: calls.__setitem__('device', calls['device'] + 1) or [])

    task_id, _ = _seed_task('无归属任务', results=[
        {'case_id': 'N1', 'device_id': None, 'api_id': None, 'result_type': 'final'},
    ])
    assert _tree(task_ids=[task_id])['data']['total'] == 1
    assert calls == {'device': 0, 'api': 0}


# ==================== 参数校验（网关 schema 400 / task_service 兜底） ====================

class _FakeRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


class _FakeAcl:
    def __init__(self):
        self.calls = []

    def list_candidate_tree(self, query):
        self.calls.append(query)
        from api_gateway.domain.dto import CommandResultDTO
        return CommandResultDTO(success=True, data={
            'total': 0, 'task_count': 0,
            'meta': {'tasks': [], 'cases': [], 'devices': [], 'apis': []},
            'tree': []})


@pytest.fixture()
def gateway(monkeypatch):
    from api_gateway.infrastructure import request_adapter
    from api_gateway.application.services.task import cherry_pick_service as svc_mod

    fake = _FakeAcl()
    monkeypatch.setattr(svc_mod, '_cherry_pick_acl', fake)
    request_adapter.set_current_request(_FakeRequest())
    yield fake, request_adapter
    request_adapter.set_current_request(None)


def _gw_tree():
    from api_gateway.application.services.task.cherry_pick_service import CherryPickService
    return CherryPickService.list_candidate_tree()


@pytest.mark.parametrize('params', [
    {},                                  # 缺失
    {'task_ids': ''},                    # 空
    {'task_ids': ' , , '},               # 全是空 token
    {'task_ids': '1,abc'},               # 非整数
    {'task_ids': ','.join(str(i) for i in range(1, 202))},  # 201 个，越界
])
def test_gateway_rejects_invalid_task_ids(gateway, params):
    fake, adapter = gateway
    adapter.set_current_request(_FakeRequest(params))
    _body, code = _gw_tree()
    assert code == 400
    assert fake.calls == []  # 校验失败不下发 gRPC


def test_gateway_passes_task_ids_and_filters(gateway):
    fake, adapter = gateway
    adapter.set_current_request(_FakeRequest({
        'task_ids': '11, 22', 'device_ids': '3', 'api_ids': '4,5',
        'case_ids': 'C1,C2', 'case_keyword': ' 语音 ',
        'execution_status': 'failed', 'evaluation_status': 'evaluated',
        'start_date': '2026-10-01T00:00:00', 'end_date': '2026-10-31T23:59:59',
    }))
    _body, code = _gw_tree()
    assert code == 200
    assert fake.calls == [{
        'task_ids': [11, 22], 'device_ids': [3], 'api_ids': [4, 5],
        'case_ids': ['C1', 'C2'], 'case_keyword': '语音',
        'execution_status': 'failed', 'evaluation_status': 'evaluated',
        'start_date': '2026-10-01T00:00:00', 'end_date': '2026-10-31T23:59:59',
    }]


def test_gateway_accepts_200_task_ids(gateway):
    fake, adapter = gateway
    adapter.set_current_request(_FakeRequest(
        {'task_ids': ','.join(str(i) for i in range(1, 201))}))
    _body, code = _gw_tree()
    assert code == 200
    assert len(fake.calls[0]['task_ids']) == 200


@pytest.mark.parametrize('task_ids', [[], list(range(1, 202))])
def test_task_service_rejects_invalid_task_ids(db, task_ids):
    """task_service 侧兜底校验（网关已挡，但契约不可只依赖网关）。"""
    resp = _tree(task_ids=task_ids)
    assert resp['success'] is False
    assert resp.get('code') == 400


# ==================== gRPC 契约（servicer 序列化） ====================

def test_grpc_servicer_roundtrip(db):
    """新增 rpc 的 servicer 方法：请求 data JSON → 应用层 → TaskConfigResponse。"""
    import json as _json

    from shared.proto import task_service_pb2 as task_pb
    from task_service.interfaces.grpc.cherry_pick import CherryPickServiceServicer

    task_id, result_ids = _seed_task('servicer任务', results=[
        {'case_id': 'G1', 'device_id': 1, 'result_type': 'final'},
        {'case_id': 'G1', 'device_id': 1, 'result_type': None},
    ])
    # proto 契约：请求/响应消息已生成（两服务共用同一份 pb2）
    assert task_pb.CherryPickCandidateTreeRequest(data='{}').data == '{}'
    assert hasattr(task_pb, 'TaskConfigResponse')

    request = task_pb.CherryPickCandidateTreeRequest(
        data=_json.dumps({'task_ids': [task_id]}))
    response = CherryPickServiceServicer().ListCherryPickCandidateTree(request, None)
    assert response.success is True
    payload = _json.loads(response.data)
    assert payload['total'] == 2
    assert payload['task_count'] == 1
    found = set(_all_result_ids(payload['tree']))
    assert found == set(result_ids)
    # 缺值桶对外值 default
    rts = {rt['result_type'] for c in payload['tree'][0]['cases']
           for d in c['devices'] for rt in d['result_types']}
    assert rts == {'final', 'default'}
