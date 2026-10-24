# -*- coding: utf-8 -*-
"""INT-1693 专项：购物车行补用例分组/标签（tags/group_id/group_name，§11-7）。

购物车用例视图 = 任务 → 分组/标签 组织（负责人 2026-10-24 于 INT-1499 定口径），
数据源要求与 INT-1130 候选行完全一致（同表同源、批量一次 join、无 N+1）。

覆盖（对齐卡验收 ③④）：
- 真实分组/标签用例返回真实值（标签去重保序）；
- 无分组/无标签用例落缺省 []/null/null；
- 用例已软删或查不到（用例不存在）落缺省；
- 空购物车响应结构不变（groups []/total 0/invalid_item_ids []）；
- 容器（cherry-pick 容器任务引用）来源结果行同样装饰；
- **SQL 语句数与行数无关**：1 条用例与 N 条用例购物车的语句数相同（证明无 N+1）；
- 购物车不触发 audio_service 时长查询（with_duration=False，不走候选慢路径）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int1130_cherry_pick_case_meta.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int1693_proc.db')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import set_current_user_id

_TASK_TABLES = None


def _ensure_tables():
    global _TASK_TABLES
    if _TASK_TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestCaseGroup, TestCaseTag, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestCaseGroup, TestCaseTag, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
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
    tables = _ensure_tables()
    _cleanup(tables)
    yield tables
    _cleanup(tables)


@pytest.fixture(autouse=True)
def _no_gateway_calls(monkeypatch):
    """隔离跨服务 gRPC：设备名/时长查询只允许走批量口径，不允许真的连服务。"""
    from task_service.infrastructure.acl import device_acl_repository as device_acl_mod
    monkeypatch.setattr(
        device_acl_mod.device_acl_repository, 'get_device_statuses',
        lambda device_ids: [{'id': i, 'name': f'设备{i}'} for i in device_ids])

    from task_service.infrastructure.acl import audio_acl_repository as audio_acl_mod

    def _forbidden(*_a, **_kw):
        raise AssertionError('购物车不应触发 audio 时长查询（INT-1693 裁定②）')

    monkeypatch.setattr(
        audio_acl_mod.audio_acl_repository, 'get_audio_durations', _forbidden)


def _seed_cases(cases):
    """按 [(case_id, name, group_id|None, [tag_name...]), ...] 播种用例 + 结果。

    返回 (task_id, {case_id: result_id})。
    """
    from task_service.infrastructure.persistence.models import (
        Task, TestCase, TestCaseGroup, Tag, TestResult,
    )
    session = get_db_session()
    try:
        group_ids = {g for _c, _n, g, _t in cases if g}
        for gid in group_ids:
            session.add(TestCaseGroup(id=gid, name=f'INT1693分组{gid}'))
        session.flush()
        for case_id, name, group_id, tag_names in cases:
            tc = TestCase(id=case_id, name=name, description='',
                          group_id=group_id, config={})
            tags = []
            for tag_name in tag_names:
                tag = Tag(name=tag_name)
                session.add(tag)
                tags.append(tag)
            session.flush()
            tc.tags = tags
            session.add(tc)
        task = Task(name='INT1693源任务', status='completed', total_cases=len(cases),
                    algorithm_type='asr')
        session.add(task)
        session.flush()
        result_ids = {}
        for i, (case_id, _n, _g, _t) in enumerate(cases):
            r = TestResult(task_id=task.id, test_case_id=case_id, device_id=7 + i,
                           algorithm_type='asr', execution_status='completed',
                           algorithm_result={'asr_result': f'文本{i}'})
            session.add(r)
            session.flush()
            result_ids[case_id] = r.id
        session.commit()
        return task.id, result_ids
    finally:
        remove_db_session()


def _cart_rows(resp):
    assert resp['success'] is True, resp
    rows = [it for g in resp['data']['groups'] for it in g['items']]
    return {it['source_case_id']: it for it in rows}


def test_cart_rows_case_group_tags(db):
    """§11-7：购物车行补 tags/group_id/group_name（含去重保序与缺省兜底）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    _task_id, result_ids = _seed_cases([
        ('INT1693-C1', '带分组标签用例', 'g1',
         ['INT1693标签1', 'INT1693标签2', 'INT1693标签1']),  # 同名去重
        ('INT1693-C2', '无分组标签用例', None, []),
    ])
    set_current_user_id(1693)
    add = cherry_pick_service.cart_add(
        {'result_ids': [result_ids['INT1693-C1'], result_ids['INT1693-C2']]})
    assert add['success'] is True

    resp = cherry_pick_service.cart_get()
    assert resp['success'] is True
    rows = _cart_rows(resp)
    assert len(rows) == 2

    c1 = rows['INT1693-C1']
    assert c1['tags'] == ['INT1693标签1', 'INT1693标签2']
    assert c1['group_id'] == 'g1'
    assert c1['group_name'] == 'INT1693分组g1'
    # 既有字段不回归（INT-577 §11-5）
    assert c1['source_case_name'] == '带分组标签用例'
    assert c1['source_device_name'] == '设备7'
    assert c1['invalid'] is False

    c2 = rows['INT1693-C2']
    assert c2['tags'] == []
    assert c2['group_id'] is None
    assert c2['group_name'] is None

    # 顶层结构与语义不变
    assert resp['data']['total'] == 2
    assert resp['data']['invalid_item_ids'] == []


def test_cart_case_missing_falls_back_to_defaults(db):
    """用例查不到（含已软删）时落缺省 []/null/null，与 _case_meta_map 吞异常口径一致。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import Task, TestResult

    session = get_db_session()
    try:
        task = Task(name='INT1693孤儿用例任务', status='completed', total_cases=1,
                    algorithm_type='asr')
        session.add(task)
        session.flush()
        r = TestResult(task_id=task.id, test_case_id='INT1693-GONE', device_id=9,
                       algorithm_type='asr', execution_status='completed',
                       algorithm_result={'a': 1})
        session.add(r)
        session.commit()
        result_id = r.id
    finally:
        remove_db_session()

    set_current_user_id(1694)
    assert cherry_pick_service.cart_add({'result_ids': [result_id]})['success'] is True
    rows = _cart_rows(cherry_pick_service.cart_get())
    gone = rows['INT1693-GONE']
    assert gone['tags'] == []
    assert gone['group_id'] is None
    assert gone['group_name'] is None


def test_cart_soft_deleted_case_falls_back_to_defaults(db):
    """用例已软删（deleted=true）→ 落缺省 []/null/null，与用例管理页口径一致。

    返工项（测试工程师 2026-10-24 P2）：原实现只按 id 批量取用例，软删用例仍
    返回原分组/标签，购物车会按「用例管理页已看不到」的分组组织。
    """
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import (
        Task, TestCase, TestCaseGroup, Tag, TestResult,
    )

    session = get_db_session()
    try:
        session.add(TestCaseGroup(id='gDel', name='INT1693已删分组'))
        session.flush()
        tag = Tag(name='INT1693已删标签')
        session.add(tag)
        session.flush()
        deleted_case = TestCase(id='INT1693-DEL', name='已软删用例',
                                group_id='gDel', config={}, deleted=True)
        deleted_case.tags = [tag]
        session.add(deleted_case)
        # 对照组：存活用例，同分组同标签，必须仍返回真实值
        alive_case = TestCase(id='INT1693-ALIVE', name='存活用例',
                              group_id='gDel', config={})
        alive_case.tags = [tag]
        session.add(alive_case)
        task = Task(name='INT1693软删源任务', status='completed', total_cases=2,
                    algorithm_type='asr')
        session.add(task)
        session.flush()
        deleted_rid = TestResult(task_id=task.id, test_case_id='INT1693-DEL',
                                 device_id=11, algorithm_type='asr',
                                 execution_status='completed',
                                 algorithm_result={'a': 1})
        alive_rid = TestResult(task_id=task.id, test_case_id='INT1693-ALIVE',
                               device_id=12, algorithm_type='asr',
                               execution_status='completed',
                               algorithm_result={'a': 2})
        session.add_all([deleted_rid, alive_rid])
        session.commit()
        deleted_result_id, alive_result_id = deleted_rid.id, alive_rid.id
    finally:
        remove_db_session()

    set_current_user_id(1698)
    assert cherry_pick_service.cart_add(
        {'result_ids': [deleted_result_id, alive_result_id]})['success'] is True
    rows = _cart_rows(cherry_pick_service.cart_get())

    deleted = rows['INT1693-DEL']
    assert deleted['tags'] == []
    assert deleted['group_id'] is None
    assert deleted['group_name'] is None

    alive = rows['INT1693-ALIVE']
    assert alive['tags'] == ['INT1693已删标签']
    assert alive['group_id'] == 'gDel'
    assert alive['group_name'] == 'INT1693已删分组'


def test_cart_empty_structure_unchanged(db):
    """空购物车响应结构不变（分组/总数/失效集合语义不动）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    set_current_user_id(1695)
    resp = cherry_pick_service.cart_get()
    assert resp['success'] is True
    assert resp['data'] == {'groups': [], 'total': 0, 'invalid_item_ids': []}


def test_cart_container_source_row(db):
    """容器（cherry-pick 容器任务引用）来源结果行同样按 source_case_id 装饰。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    _task_id, result_ids = _seed_cases([
        ('INT1693-CT', '容器引用用例', 'g2', ['INT1693容器标签']),
    ])
    set_current_user_id(1696)
    assert cherry_pick_service.cart_add(
        {'result_ids': [result_ids['INT1693-CT']]})['success'] is True
    checkout = cherry_pick_service.checkout_merge({'name': 'INT1693容器'})
    assert checkout['success'] is True, checkout
    container_id = checkout['data']['task_id']
    assert container_id

    # 容器任务已建立引用关系；同一结果重新入购物车，行字段口径不变
    assert cherry_pick_service.cart_add(
        {'result_ids': [result_ids['INT1693-CT']]})['success'] is True
    rows = _cart_rows(cherry_pick_service.cart_get())
    row = rows['INT1693-CT']
    assert row['tags'] == ['INT1693容器标签']
    assert row['group_id'] == 'g2'
    assert row['group_name'] == 'INT1693分组g2'


def _count_sql(fn):
    """统计 fn 执行期间的 SQL 语句数（SQLAlchemy before_cursor_execute）。"""
    from sqlalchemy import event

    engine = get_engine()
    statements = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', _before)
    try:
        resp = fn()
    finally:
        event.remove(engine, 'before_cursor_execute', _before)
    assert resp['success'] is True, resp
    return len(statements), resp


def test_cart_sql_count_independent_of_row_count(db):
    """批量口径：1 条用例与 N 条用例的购物车 SQL 语句数相同（无 N+1）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    cases = [(f'INT1693-N{i}', f'批量用例{i}', f'gN{i}', [f'INT1693批量标签{i}'])
             for i in range(1, 5)]
    _task_id, result_ids = _seed_cases(cases)
    all_ids = [result_ids[c[0]] for c in cases]

    set_current_user_id(1697)
    assert cherry_pick_service.cart_add({'result_ids': [all_ids[0]]})['success'] is True
    one_count, one_resp = _count_sql(cherry_pick_service.cart_get)
    assert one_resp['data']['total'] == 1

    assert cherry_pick_service.cart_clear()['success'] is True
    assert cherry_pick_service.cart_add({'result_ids': all_ids})['success'] is True
    many_count, many_resp = _count_sql(cherry_pick_service.cart_get)
    assert many_resp['data']['total'] == len(cases)

    assert one_count == many_count, (
        f'SQL 语句数随行数增长（{one_count} → {many_count}），存在 N+1')
