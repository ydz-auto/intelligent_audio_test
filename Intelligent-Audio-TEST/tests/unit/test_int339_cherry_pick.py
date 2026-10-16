# -*- coding: utf-8 -*-
"""INT-339 专项：任务结果挑选合并（购物车/容器关系/读链路引用解析/下单）。

覆盖（对齐设计文档 §3/§5.1/§5.4/§8/§10/§12）：
- S1 购物车：加购幂等/溯源快照提取/移除/清空/失效标注/挑选集另存与恢复
- S3 容器任务：创建即 completed + 关系表引用（禁止搬家语义——源结果
  task_id 不变）+ 读链路引用解析（get_case_results/detail 按关系展开）
- S3 列表过滤：cherry_pick=true 仅命中容器任务（§5.4 存在性判定）
- S2 候选查询：多条件 AND（设备+用例点名维度）/仅终态任务（§10）
- 下单三出口 action 校验（枚举拒绝魔法字符串）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int298 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int339_proc.db')

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
            Tag, TaskTag, TestCase, TestResult,
            CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestResult,
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
    set_current_user_id(None)


def _seed_source_task(name='INT339源任务', status='completed'):
    """种子：终态源任务 + 2 用例 2 结果（设备 7/8 各一）。返回 (task_id, [(case_id, result_id, device_id)...])"""
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
    session = get_db_session()
    try:
        task = Task(name=name, status=status, total_cases=2)
        session.add(task)
        session.flush()
        results = []
        for i, (case_id, device_id) in enumerate([('INT339-C1', 7), ('INT339-C2', 8)]):
            session.add(TaskCase(
                task_id=task.id, test_case_id=case_id,
                status='completed', execution_status='completed',
                evaluation_status='completed', device_type='physical',
                device_id=str(device_id),
            ))
            r = TestResult(
                task_id=task.id, test_case_id=case_id, device_id=device_id,
                algorithm_type='asr', execution_status='completed',
                algorithm_result={'asr_result': f'文本{i}'},
            )
            session.add(r)
            session.flush()
            results.append((case_id, r.id, device_id))
        session.commit()
        return task.id, results
    finally:
        remove_db_session()


# ==================== S1 购物车 ====================

def test_cart_add_snapshot_and_idempotent(db):
    """加购提取溯源快照（防伪造）；重复加购幂等跳过；失效结果标注 missing。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    task_id, results = _seed_source_task()
    set_current_user_id(42)

    resp = cherry_pick_service.cart_add({'result_ids': [results[0][1], results[1][1]]})
    assert resp['success'] is True
    assert resp['data']['added'] == [results[0][1], results[1][1]]

    # 幂等：重复加购全部跳过
    resp2 = cherry_pick_service.cart_add({'result_ids': [results[0][1]]})
    assert resp2['success'] is True
    assert resp2['data']['duplicated'] == [results[0][1]]

    # 溯源快照正确（仓储从源行提取，客户端无伪造面）
    cart = cherry_pick_service.cart_get()
    assert cart['success'] is True
    assert cart['data']['total'] == 2
    group = cart['data']['groups'][0]
    assert group['source_task_id'] == task_id
    assert group['source_task_name'] == 'INT339源任务'
    item = group['items'][0]
    assert item['source_case_id'] in ('INT339-C1', 'INT339-C2')
    assert item['source_device_id'] in (7, 8)
    assert item['invalid'] is False

    # 失效标注：直接删源结果行后 invalid=True（§10）
    from task_service.infrastructure.persistence.models import TestResult
    session = get_db_session()
    try:
        session.query(TestResult).filter(TestResult.id == results[0][1]).delete()
        session.commit()
    finally:
        remove_db_session()
    cart2 = cherry_pick_service.cart_get()
    assert results[0][1] in cart2['data']['invalid_item_ids']


def test_cart_requires_user(db):
    """未认证（user_id=None）拒绝写入（红线：0/None 不充当真实用户）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    resp = cherry_pick_service.cart_add({'result_ids': [1]})
    assert resp['success'] is False and resp['code'] == 401


def test_cart_save_as_set_and_restore(db):
    """购物车另存挑选集 → 清空 → 挑选集恢复进购物车（另存/恢复两向，§3）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    _task_id, results = _seed_source_task(name='INT339挑选集源')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [results[0][1], results[1][1]]})

    saved = cherry_pick_service.cart_save_as_set({'name': '回归挑选集'})
    assert saved['success'] is True and saved['data']['item_count'] == 2

    cherry_pick_service.cart_clear()
    assert cherry_pick_service.cart_get()['data']['total'] == 0

    restored = cherry_pick_service.set_to_cart(saved['data']['set_id'])
    assert restored['success'] is True
    assert cherry_pick_service.cart_get()['data']['total'] == 2


# ==================== S2 候选查询 ====================

def test_candidates_terminal_tasks_only_and_filters(db):
    """候选查询仅终态任务（§10 显式集合）+ 设备/用例 AND 过滤（点名维度）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    task_id, results = _seed_source_task(name='INT339终态源')
    running_task_id, _running_results = _seed_source_task(
        name='INT339执行中源', status='running')

    set_current_user_id(None)  # 查询侧不要求用户
    # 无过滤：仅终态任务结果命中（执行中任务被排除）
    resp = cherry_pick_service.list_candidates({})
    assert resp['success'] is True
    assert all(item['task_id'] != running_task_id for item in resp['data']['items'])
    assert {item['result_id'] for item in resp['data']['items']} == {results[0][1], results[1][1]}

    # 设备过滤（点名维度 1）
    by_device = cherry_pick_service.list_candidates({'device_ids': [7]})
    assert [i['result_id'] for i in by_device['data']['items']] == [results[0][1]]

    # 用例过滤（点名维度 2）
    by_case = cherry_pick_service.list_candidates({'case_ids': ['INT339-C2']})
    assert [i['result_id'] for i in by_case['data']['items']] == [results[1][1]]

    # 组合 AND：设备 8 + 用例 C1 = 空集
    empty = cherry_pick_service.list_candidates({'device_ids': [8], 'case_ids': ['INT339-C1']})
    assert empty['data']['items'] == []

    # 执行状态过滤
    by_status = cherry_pick_service.list_candidates({'execution_status': 'failed'})
    assert by_status['data']['items'] == []


# ==================== S3 容器任务 / 读链路引用解析 ====================

def test_checkout_merge_container_and_reference_resolution(db):
    """下单 merge：容器创建即 completed + 关系引用（源行不动）+ 读链路按关系解析。

    红线断言：源结果 task_id 不变（禁止搬家语义，§5.1）。
    """
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import Task, TestResult
    from task_service.infrastructure.read_models.task_read_model import task_read_model
    from task_service.infrastructure.read_models.task_read_model_case_results import (
        TaskCaseResultsMixin,
    )

    src_a_id, results_a = _seed_source_task(name='INT339来源A')
    src_b_id, results_b = _seed_source_task(name='INT339来源B')
    set_current_user_id(42)

    # 跨任务加购：A 的用例 C1 结果 + B 的用例 C2 结果
    cherry_pick_service.cart_add({'result_ids': [results_a[0][1], results_b[1][1]]})

    resp = cherry_pick_service.checkout({'action': 'merge', 'name': '挑选合并容器'})
    assert resp['success'] is True, resp.get('message')
    container_id = resp['data']['task_id']

    # 容器任务创建即 completed（§5.3）
    session = get_db_session()
    try:
        container = session.get(Task, container_id)
        assert container.status == 'completed'
        assert container.total_cases == 2
        # 红线：源结果 task_id 保持原任务（未搬家）
        ra = session.get(TestResult, results_a[0][1])
        rb = session.get(TestResult, results_b[1][1])
        assert ra.task_id == src_a_id and rb.task_id == src_b_id
    finally:
        remove_db_session()

    # 下单成功购物车出清（§3）
    assert cherry_pick_service.cart_get()['data']['total'] == 0

    # cherry_pick=true 列表过滤仅命中容器（§5.4 存在性判定）
    listed = task_read_model.search_tasks(page=1, per_page=50, cherry_pick=True)
    assert [i['id'] for i in listed['items']] == [container_id]
    assert listed['items'][0]['is_cherry_pick'] is True
    plain = task_read_model.search_tasks(page=1, per_page=50)
    assert src_a_id in {i['id'] for i in plain['items']}
    plain_row = next(i for i in plain['items'] if i['id'] == src_a_id)
    assert plain_row['is_cherry_pick'] is False

    # 读链路引用解析：get_case_results 按关系返回源结果（容器自身无 test_results 行）
    case_b = results_b[1][0]  # INT339-C2（来自来源B）
    resolved = TaskCaseResultsMixin().get_case_results(container_id, case_b)
    assert resolved is not None
    assert [r['id'] for r in resolved['results']] == [results_b[1][1]]
    # 验收 §12.2：每条结果可溯源到来源任务
    assert resolved['results'][0]['source_task_id'] == src_b_id
    assert resolved['results'][0]['source_task_name'] == 'INT339来源B'

    # 溯源查询接口（§8 source）
    trace = cherry_pick_service.source_trace(container_id)
    assert trace['success'] is True
    assert trace['data']['total'] == 2
    grouped_srcs = {g['source_task_id'] for g in trace['data']['groups']}
    assert grouped_srcs == {src_a_id, src_b_id}

    # 普通任务溯源查询 404
    assert cherry_pick_service.source_trace(src_a_id)['code'] == 404


def test_checkout_merge_case_status_inherit_and_counts(db):
    """容器 TaskCase 状态继承源结果（避免详情全显示待执行）+ 计数自洽。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import Task, TaskCase

    _src, results = _seed_source_task(name='INT339状态继承源')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})

    resp = cherry_pick_service.checkout({'action': 'merge', 'name': '状态继承容器'})
    container_id = resp['data']['task_id']

    session = get_db_session()
    try:
        container = session.get(Task, container_id)
        assert container.completed_cases == 2 and container.failed_cases == 0
        tc_rows = session.query(TaskCase).filter_by(task_id=container_id).all()
        assert len(tc_rows) == 2
        for tc in tc_rows:
            assert tc.execution_status == 'completed'
            assert tc.evaluation_status == 'completed'
            assert tc.device_type == 'physical'
    finally:
        remove_db_session()


def test_checkout_reexecute_covers_case_device_set(db):
    """下单 reexecute：新任务覆盖所选结果的用例×设备集合（验收 §12.7）。

    start 链路依赖执行引擎，本用例仅断言任务创建/用例路由，不触 start。
    """
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import Task, TaskCase

    _src, results = _seed_source_task(name='INT339重执行源')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})

    # monkeypatch start：执行引擎不可用于单测，重执行任务创建成功即可
    import task_service.application.task.cherry_pick_service as cp_module
    original_start = cp_module.task_lifecycle_start
    cp_module.task_lifecycle_start = lambda tid: {'success': True, 'message': 'ok', 'data': None}
    try:
        resp = cherry_pick_service.checkout({'action': 'reexecute'})
    finally:
        cp_module.task_lifecycle_start = original_start

    assert resp['success'] is True
    new_task_id = resp['data']['task_id']
    session = get_db_session()
    try:
        new_task = session.get(Task, new_task_id)
        assert new_task is not None
        tc_rows = session.query(TaskCase).filter_by(task_id=new_task_id).all()
        assert sorted(tc.test_case_id for tc in tc_rows) == ['INT339-C1', 'INT339-C2']
        for tc in tc_rows:
            # 用例级路由继承源任务（执行路由唯一依据）
            assert tc.device_id in ('7', '8')
            assert tc.device_type == 'physical'
    finally:
        remove_db_session()
    # 下单成功购物车出清
    assert cherry_pick_service.cart_get()['data']['total'] == 0


def test_checkout_invalid_action_rejected(db):
    """下单出口枚举校验（拒绝魔法字符串，非法 action 400）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    set_current_user_id(42)
    resp = cherry_pick_service.checkout({'action': 'teleport'})
    assert resp['success'] is False and resp['code'] == 400


def test_preview_counts_and_invalid_marking(db):
    """合并预览：统计（来源任务/设备/用例/状态分布）+ 失效标注（§10）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import TestResult

    src_a, results_a = _seed_source_task(name='INT339预览A')
    src_b, results_b = _seed_source_task(name='INT339预览B')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [results_a[0][1], results_b[0][1]]})

    # 删除 B 的源结果制造失效条目
    session = get_db_session()
    try:
        session.query(TestResult).filter(TestResult.id == results_b[0][1]).delete()
        session.commit()
    finally:
        remove_db_session()

    resp = cherry_pick_service.preview()
    assert resp['success'] is True
    data = resp['data']
    assert data['total_results'] == 1
    assert data['invalid_result_ids'] == [results_b[0][1]]
    assert data['source_task_count'] == 1
    assert 7 in data['device_ids']


def test_reevaluate_submits_per_source_task(db):
    """下单 reevaluate：逐源任务发起（裁定 4，mode=selected）——ACL 调用按源任务分组。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    src_a, results_a = _seed_source_task(name='INT339重评A')
    src_b, results_b = _seed_source_task(name='INT339重评B')
    set_current_user_id(42)
    cherry_pick_service.cart_add({
        'result_ids': [results_a[0][1], results_a[1][1], results_b[0][1]]})

    calls = []

    class _FakeAcl:
        @staticmethod
        def submit_reevaluate(task_id, reextract_device_output=True,
                              reevaluate_type='all', options=None):
            calls.append({'task_id': task_id, 'options': options})
            return {'success': True, 'message': 'ok', 'data': {}}

    # 服务内为函数级 import，替换 ACL 单例方法（直接打实例补丁，避免类属性绑定语义）
    import task_service.infrastructure.acl.evaluation_acl_repository as _acl_module
    original_submit = _acl_module.evaluation_acl_repository.submit_reevaluate
    _acl_module.evaluation_acl_repository.submit_reevaluate = _FakeAcl.submit_reevaluate
    try:
        resp = cherry_pick_service.checkout({'action': 'reevaluate'})
    finally:
        _acl_module.evaluation_acl_repository.submit_reevaluate = original_submit

    assert resp['success'] is True
    assert sorted(c['task_id'] for c in calls) == sorted([src_a, src_b])
    by_task = {c['task_id']: c['options'] for c in calls}
    assert by_task[src_a]['mode'] == 'selected'
    assert sorted(by_task[src_a]['case_ids']) == ['INT339-C1', 'INT339-C2']
    assert by_task[src_b]['case_ids'] == ['INT339-C1']
    # 全部成功购物车出清
    assert cherry_pick_service.cart_get()['data']['total'] == 0


def test_reevaluate_partial_failure_keeps_cart(db):
    """下单 reevaluate 部分失败：条目保留（便于重试，§3 口径延伸）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    src_a, results_a = _seed_source_task(name='INT339重评失败')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [results_a[0][1]]})

    class _FakeAcl:
        @staticmethod
        def submit_reevaluate(task_id, reextract_device_output=True,
                              reevaluate_type='all', options=None):
            return {'success': False, 'message': '任务正在重新评估中', 'data': {}}

    import task_service.infrastructure.acl.evaluation_acl_repository as _acl_module
    original_submit = _acl_module.evaluation_acl_repository.submit_reevaluate
    _acl_module.evaluation_acl_repository.submit_reevaluate = _FakeAcl.submit_reevaluate
    try:
        resp = cherry_pick_service.checkout({'action': 'reevaluate'})
    finally:
        _acl_module.evaluation_acl_repository.submit_reevaluate = original_submit

    assert resp['success'] is False
    assert cherry_pick_service.cart_get()['data']['total'] == 1


def test_purge_container_task_cleans_cherry_relations(db):
    """purge 容器任务须先清 task_cherry_pick_relations（INT-401 返工）。

    回归：cherry_pick_task_id REFERENCES test_tasks(id)，purge_tasks 若不清
    专有关系，PG 上 DELETE test_tasks 触发 FK 违约 500，容器任务不可彻底删除。
    """
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.trash_repository import trash_repository
    from task_service.infrastructure.persistence.models import (
        Task, TaskCherryPickRelation, Log,
    )
    # purge_tasks 级联需 test_result_dimensions / logs 表（INT-337 口径；本文件
    # _ensure_tables 未含，补建缺失表，create_all 幂等）
    from evaluation_service.infrastructure.persistence.models import TestResultDimension
    Base.metadata.create_all(bind=get_engine(),
                             tables=[Log.__table__, TestResultDimension.__table__])

    _src, results = _seed_source_task(name='INT339溯源清理源')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})
    resp = cherry_pick_service.checkout({'action': 'merge', 'name': '待purge容器'})
    assert resp['success'] is True, resp.get('message')
    container_id = resp['data']['task_id']

    session = get_db_session()
    try:
        rel_count = session.query(TaskCherryPickRelation).filter_by(
            cherry_pick_task_id=container_id).count()
        assert rel_count == 2, f'容器任务应有 2 条关系引用：实际 {rel_count}'
        # 软删（deleted=TRUE）→ purge 前置条件（活跃行 purge 会跳过）
        container = session.get(Task, container_id)
        container.deleted = True
        container.deleted_by_user_id = 42
        session.commit()
    finally:
        remove_db_session()

    # owner（创建人=删除人=42）purge → 返回 1 行，容器与关系表同清
    assert trash_repository.purge_tasks([container_id], user_id=42, is_admin=False) == 1
    session = get_db_session()
    try:
        assert session.get(Task, container_id) is None
        assert session.query(TaskCherryPickRelation).filter_by(
            cherry_pick_task_id=container_id).count() == 0
    finally:
        remove_db_session()

    # 源任务侧引用保留（容器对已删源结果的「缺失」标注依赖 relation 行）：
    # purge 源任务不应连带删其它容器对它的引用
    src_b, results_b = _seed_source_task(name='INT339另一源')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [results_b[0][1]]})
    resp_b = cherry_pick_service.checkout({'action': 'merge', 'name': '引用源B容器'})
    container_b = resp_b['data']['task_id']
    session = get_db_session()
    try:
        src_row = session.get(Task, src_b)
        src_row.deleted = True
        src_row.deleted_by_user_id = 42
        session.commit()
    finally:
        remove_db_session()

    assert trash_repository.purge_tasks([src_b], user_id=42, is_admin=False) == 1
    session = get_db_session()
    try:
        assert session.query(TaskCherryPickRelation).filter_by(
            cherry_pick_task_id=container_b).count() == 1
    finally:
        remove_db_session()



def test_source_trace_marks_deleted_results_missing(db):
    """溯源查询：源结果物理删除后 source_trace 逐条标注 missing（§10 引用方案 A）。

    INT-401 复验：P1-2 溯源展开的缺失标注链路——后端 source_trace 对已删
    test_results 行仍返回引用并置 missing=true（容器对已删源结果的「源结果
    已缺失」标注依赖 relation 行保留 + 此标记；前端 missing-badge 渲染由
    cherryPickPanel.sourceToggle.spec 覆盖）。本测试锁后端行为。
    """
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    from task_service.infrastructure.persistence.models import TestResult

    src_id, results = _seed_source_task(name='INT339缺失标注源')
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [r[1] for r in results]})
    resp = cherry_pick_service.checkout({'action': 'merge', 'name': '缺失标注容器'})
    assert resp['success'] is True, resp.get('message')
    container_id = resp['data']['task_id']

    # 物理删除其中一条源结果（missing 场景构造：引用方案 A 的源结果被删）
    deleted_result_id = results[0][1]
    session = get_db_session()
    try:
        session.query(TestResult).filter(TestResult.id == deleted_result_id).delete()
        session.commit()
    finally:
        remove_db_session()

    trace = cherry_pick_service.source_trace(container_id)
    assert trace['success'] is True, trace.get('message')
    assert trace['data']['total'] == 2, '关系行应保留（引用不随源结果删除）'
    by_id = {r['result_id']: r for g in trace['data']['groups'] for r in g['results']}
    assert by_id[deleted_result_id]['missing'] is True, \
        f'已删源结果应标 missing：实际 {by_id[deleted_result_id]}'
    assert by_id[results[1][1]]['missing'] is False, \
        '未删源结果不应标 missing'
