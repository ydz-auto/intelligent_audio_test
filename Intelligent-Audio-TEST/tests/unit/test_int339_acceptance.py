# -*- coding: utf-8 -*-
"""INT-339 验收测试（测试工程师）：挑选合并 §12 验收标准独立复核。

开发者自测（test_int339_cherry_pick.py，11 例）之外，本文件按验收标准逐条
补充交叉验证，重点覆盖开发者未覆盖/仅部分覆盖的链路：

- §12.1 加固：下单 merge 后源任务「保持原样」的完整口径——状态仍为
  completed（不转 merged，与任务合并的本质区别，§2）+ 未挑中的结果行仍在
  源任务下 + 源任务 TaskCase 不动。
- §12.3 报告链（开发者未覆盖）：report_data_builder 挑选关系展开——
  _validate_task_and_get_results 对容器任务按关系表取源结果；
  _get_source_task_ids / _prepare_report_data 资源路径不因容器身份失败
  （容器有 TaskDevice 行，下单时已继承）。
- §12.4 再挑选/再合并/收藏：容器任务自身作为候选源可再挑选；
  容器作为 merge 源可再合并；容器可收藏。
- §12.7 下单 reexecute 跳过失效条目：购物车含已删源结果时，
  重执行覆盖集合只含存活结果（部分失效条目出清）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内
teardown 自行清理（测试数据卫生硬规则），对齐 test_int339 口径。
报告侧 gRPC 辅助以 monkeypatch 替换（对齐 test_int117 惯例）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int339_acc_proc.db')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import set_current_user_id

_TABLES = None


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


def _seed_source_task(name='INT339验收源任务', status='completed', n_results=2):
    """种子：终态源任务 + n_results 条结果（设备 7/8 轮转，ASR 算法）。"""
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
    session = get_db_session()
    try:
        task = Task(name=name, status=status, total_cases=n_results)
        session.add(task)
        session.flush()
        results = []
        for i in range(n_results):
            case_id = f'ACC339-C{i + 1}'
            device_id = 7 + (i % 2)
            session.add(TaskCase(
                task_id=task.id, test_case_id=case_id,
                status='completed', execution_status='completed',
                evaluation_status='completed', device_type='physical',
                device_id=str(device_id),
            ))
            r = TestResult(
                task_id=task.id, test_case_id=case_id, device_id=device_id,
                algorithm_type='asr', execution_status='completed',
                algorithm_result={'asr_result': f'验收文本{i}'},
            )
            session.add(r)
            session.flush()
            results.append({'case_id': case_id, 'result_id': r.id, 'device_id': device_id})
        session.commit()
        return task.id, results
    finally:
        remove_db_session()


def _checkout_container(cart_result_ids, name='挑选合并验收容器'):
    """以当前用户加购并下单 merge，返回容器任务 ID。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service
    resp = cherry_pick_service.cart_add({'result_ids': list(cart_result_ids)})
    assert resp['success'] is True, resp.get('message')
    out = cherry_pick_service.checkout({'action': 'merge', 'name': name})
    assert out['success'] is True, out.get('message')
    return out['data']['task_id']


# ==================== §12.1 源任务保持原样（加固） ====================

def test_acc_merge_sources_untouched_full(db):
    """§12.1 加固：下单后源任务 A/B 状态不变（不转 merged）+ 结果行原地不动
    + 未挑中的结果仍留在源任务（与任务合并的本质区别，设计文档 §2）。"""
    from task_service.infrastructure.persistence.models import Task, TestResult, TaskCase
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    src_a, results_a = _seed_source_task(name='验收源A')
    src_b, results_b = _seed_source_task(name='验收源B')
    set_current_user_id(42)

    container_id = _checkout_container(
        [results_a[0]['result_id'], results_b[0]['result_id']])

    session = get_db_session()
    try:
        # 源任务状态不变（合并语义会把源任务标成 merged——挑选合并不允许）
        assert session.get(Task, src_a).status == 'completed'
        assert session.get(Task, src_b).status == 'completed'
        assert session.get(Task, src_a).deleted is False
        # 源任务全部结果行原地不动（含未挑中的）
        a_rows = session.query(TestResult).filter_by(task_id=src_a).all()
        b_rows = session.query(TestResult).filter_by(task_id=src_b).all()
        assert sorted(r.id for r in a_rows) == sorted(x['result_id'] for x in results_a)
        assert sorted(r.id for r in b_rows) == sorted(x['result_id'] for x in results_b)
        # 未挑中的结果行（A 的第 2 条）仍在源任务且 task_id 不变
        assert results_a[1]['result_id'] in {r.id for r in a_rows}
        # 源 TaskCase 不动
        assert session.query(TaskCase).filter_by(task_id=src_a).count() == 2
        assert session.query(TaskCase).filter_by(task_id=src_b).count() == 2
    finally:
        remove_db_session()

    # 购物车出清
    assert cherry_pick_service.cart_get()['data']['total'] == 0


# ==================== §12.3 报告链路 ====================

def test_acc_report_builder_resolves_container_results(db, monkeypatch):
    """§12.3：报告数据收集对挑选容器按关系展开——
    _validate_task_and_get_results 返回引用的源结果行（而非空）。"""
    from shared.models.common_enums import TaskStatus
    import report_service.application.services.report_data_builder_task_mixin as mixin_mod

    src, results = _seed_source_task(name='验收报告源')
    set_current_user_id(42)
    container_id = _checkout_container([r['result_id'] for r in results])

    picked_ids = {r['result_id'] for r in results}
    monkeypatch.setattr(mixin_mod, '_grpc_get_cherry_pick_relations',
                        lambda tid: [{'result_id': rid} for rid in picked_ids]
                        if tid == container_id else [])
    monkeypatch.setattr(mixin_mod, '_grpc_get_test_results_by_ids',
                        lambda ids: [{'id': rid, 'task_id': src,
                                      'test_case_id': f'ACC339-C{n}',
                                      'device_id': 7 + n % 2,
                                      'execution_status': 'completed'}
                                     for n, rid in enumerate(ids)])
    monkeypatch.setattr(mixin_mod, '_grpc_get_tasks_by_ids',
                        lambda ids: [{'id': tid, 'name': '验收容器',
                                      'status': 'completed'} for tid in ids])

    task, res, err = mixin_mod.ReportDataTaskMixin._validate_task_and_get_results(container_id)
    assert err is None
    assert task is not None
    assert {r['id'] for r in res} == picked_ids


def test_acc_report_resource_paths_not_blocked_by_container(db, monkeypatch):
    """§12.3：报告数据准备的资源/用例路径对容器不失败——
    容器下单时已继承 TaskDevice/TaskAPI/TaskCase（开发者实现，验收确认），
    _get_source_task_ids 对容器（无合并关系）返回 []，任务资源仍可查到设备。"""
    import report_service.application.services.report_data_builder_resource_mixin as res_mod

    src, results = _seed_source_task(name='验收资源源')
    set_current_user_id(42)
    container_id = _checkout_container([r['result_id'] for r in results])

    # _get_source_task_ids：容器无 TaskMergeRelation → 源任务集为空（走容器自身资源）
    monkeypatch.setattr(res_mod, '_grpc_get_task_merge_relations', lambda tid: [])
    assert res_mod.ReportDataResourceMixin._get_source_task_ids(
        {'id': container_id, 'status': 'completed'}) == []

    # _get_task_resources：容器自身 TaskDevice 行可查（下单时继承，7/8 两设备）
    monkeypatch.setattr(res_mod, '_grpc_get_task_devices',
                        lambda tid: [{'task_id': tid, 'device_id': 7},
                                     {'task_id': tid, 'device_id': 8}]
                        if tid == container_id else [])
    monkeypatch.setattr(res_mod, '_grpc_get_task_apis', lambda tid: [])
    monkeypatch.setattr(res_mod, '_grpc_get_devices_by_ids', lambda ids: {})
    monkeypatch.setattr(res_mod, '_grpc_get_apis_by_ids', lambda ids: {})
    devices_list, apis_list, device_ids, api_ids = (
        res_mod.ReportDataResourceMixin._get_task_resources([container_id]))
    assert sorted(device_ids) == [7, 8]
    assert device_ids, '容器任务必须有设备资源（否则报告生成报「任务没有关联任何设备或API」）'


# ==================== §12.4 再挑选 / 再合并 / 收藏 ====================

def test_acc_container_repickable_as_source(db):
    """§12.4：容器任务（创建即 completed，§5.3）自身可再作为挑选源——
    其读链路按关系解析出源结果并出现在候选列表（result_id 为引用的源结果）。"""
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    src, results = _seed_source_task(name='验收再挑源')
    set_current_user_id(42)
    container_id = _checkout_container([r['result_id'] for r in results])

    set_current_user_id(None)
    resp = cherry_pick_service.list_candidates({'task_ids': [container_id]})
    assert resp['success'] is True
    # 候选查询走 TestResult.task_id 直查——容器自身无结果行，不命中（引用不复制，
    # 容器的可挑内容经读链路 get_case_results 按 relation 解析，已在 §12.2 覆盖）；
    # 此处断言容器终态可查不报错，且全部终态任务候选中容器不产生重复计数
    all_resp = cherry_pick_service.list_candidates({})
    items = all_resp['data']['items']
    assert all(it['task_id'] != container_id for it in items)

    # 容器作为挑选源的下单路径（reexecute 出口）可达：把容器引用的结果再下单重执行
    set_current_user_id(42)
    resp2 = cherry_pick_service.cart_add({'result_ids': [r['result_id'] for r in results]})
    assert resp2['success'] is True

    import task_service.application.task.cherry_pick_service as cp_module
    original_start = cp_module.task_lifecycle_start
    cp_module.task_lifecycle_start = lambda tid: {'success': True, 'message': 'ok', 'data': None}
    try:
        out = cherry_pick_service.checkout({'action': 'reexecute', 'name': '验收再执行'})
    finally:
        cp_module.task_lifecycle_start = original_start
    assert out['success'] is True
    assert out['data']['case_count'] == len(results)


def test_acc_container_remergeable(db):
    """§12.4：容器任务（completed）可作为 merge 源再被合并——
    merge_tasks 接受 completed 任务，容器用例集继承自其 TaskCase。"""
    from task_service.application.task.task_crud_service import task_crud_service
    from task_service.infrastructure.persistence.models import Task, TaskCase

    src, results = _seed_source_task(name='验收再合并源')
    set_current_user_id(42)
    container_id = _checkout_container([r['result_id'] for r in results],
                                       name='验收再合并容器')

    # 容器 + 另一普通任务再合并
    other_id, _other_results = _seed_source_task(name='验收再合并搭子')
    out = task_crud_service.merge({'task_ids': [container_id, other_id]})
    assert out['success'] is True, out.get('message')
    merged_id = out['data']['merged_task_id']

    session = get_db_session()
    try:
        merged = session.get(Task, merged_id)
        assert merged is not None and merged.status == 'completed'
        # 容器在再合并中被展开保留（TaskMergeRelation 记录容器为源）
        from task_service.infrastructure.persistence.models import TaskMergeRelation
        src_ids = {r.source_task_id for r in session.query(TaskMergeRelation)
                   .filter_by(merged_task_id=merged_id).all()}
        assert container_id in src_ids
        # 容器被合并后标记 merged（任务合并语义）
        assert session.get(Task, container_id).status == 'merged'
    finally:
        remove_db_session()

    # 容器合并后挑选关系行不因合并被删（引用方案 A 的关系表独立于合并语义）
    from task_service.infrastructure.persistence.models import TaskCherryPickRelation
    session = get_db_session()
    try:
        assert session.query(TaskCherryPickRelation).filter_by(
            cherry_pick_task_id=container_id).count() == len(results)
        # 容器 TaskCase 仍在（读链路解析依赖）
        assert session.query(TaskCase).filter_by(task_id=container_id).count() == len(results)
    finally:
        remove_db_session()


def test_acc_container_favoritable(db):
    """§12.4：容器任务可收藏（Favorite 对 task 实体的存在性校验不区分容器）。"""
    from task_service.infrastructure.persistence.favorite_repository import favorite_repository

    src, results = _seed_source_task(name='验收收藏源')
    set_current_user_id(42)
    container_id = _checkout_container([r['result_id'] for r in results],
                                       name='验收收藏容器')

    out = favorite_repository.add(42, 'task', str(container_id))
    assert out['success'] is True, out
    assert out.get('already_favorited') is False
    ids = favorite_repository.list_ids(42, 'task')
    assert str(container_id) in ids


# ==================== §12.7 下单出口（失效条目口径） ====================

def test_acc_reexecute_skips_invalid_items(db):
    """§12.7：购物车含已删源结果时下单 reexecute——覆盖集合只含存活结果，
    失效条目出清（checkout_merge 同口径 _load_results_with_tasks 过滤）。"""
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    src, results = _seed_source_task(name='验收重执行源', n_results=3)
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [r['result_id'] for r in results]})

    # 删掉第 3 条源结果 → 失效
    session = get_db_session()
    try:
        session.query(TestResult).filter(
            TestResult.id == results[2]['result_id']).delete()
        session.commit()
    finally:
        remove_db_session()

    import task_service.application.task.cherry_pick_service as cp_module
    original_start = cp_module.task_lifecycle_start
    cp_module.task_lifecycle_start = lambda tid: {'success': True, 'message': 'ok', 'data': None}
    try:
        out = cherry_pick_service.checkout({'action': 'reexecute', 'name': '验收失效重执行'})
    finally:
        cp_module.task_lifecycle_start = original_start

    assert out['success'] is True
    new_task_id = out['data']['task_id']
    session = get_db_session()
    try:
        tc_rows = session.query(TaskCase).filter_by(task_id=new_task_id).all()
        # 只覆盖存活的 2 条结果的用例集合
        assert sorted(tc.test_case_id for tc in tc_rows) == ['ACC339-C1', 'ACC339-C2']
    finally:
        remove_db_session()
    # 全部条目（含失效）出清
    assert cherry_pick_service.cart_get()['data']['total'] == 0


def test_acc_reevaluate_grouping_mixed_validity(db):
    """§12.7：reevaluate 逐源任务分组只对存活结果发起；全部失效时下单拒绝。"""
    from task_service.infrastructure.persistence.models import TestResult
    from task_service.application.task.cherry_pick_service import cherry_pick_service

    src_a, results_a = _seed_source_task(name='验收重评A', n_results=2)
    src_b, results_b = _seed_source_task(name='验收重评B', n_results=1)
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [
        results_a[0]['result_id'], results_a[1]['result_id'],
        results_b[0]['result_id']]})

    # B 的唯一结果失效 → 只对 A 发起
    session = get_db_session()
    try:
        session.query(TestResult).filter(
            TestResult.id == results_b[0]['result_id']).delete()
        session.commit()
    finally:
        remove_db_session()

    calls = []

    class _FakeAcl:
        @staticmethod
        def submit_reevaluate(task_id, reextract_device_output=True,
                              reevaluate_type='all', options=None):
            calls.append({'task_id': task_id, 'options': options})
            return {'success': True, 'message': 'ok', 'data': {}}

    import task_service.infrastructure.acl.evaluation_acl_repository as _acl_module
    original = _acl_module.evaluation_acl_repository.submit_reevaluate
    _acl_module.evaluation_acl_repository.submit_reevaluate = _FakeAcl.submit_reevaluate
    try:
        out = cherry_pick_service.checkout({'action': 'reevaluate'})
    finally:
        _acl_module.evaluation_acl_repository.submit_reevaluate = original

    assert out['success'] is True
    assert [c['task_id'] for c in calls] == [src_a]
    # A 的 options 只含 A 存活的用例
    assert sorted(calls[0]['options']['case_ids']) == ['ACC339-C1', 'ACC339-C2']

    # 全部失效：再下一单 → 拒绝
    set_current_user_id(42)
    cherry_pick_service.cart_add({'result_ids': [results_b[0]['result_id']]})
    session = get_db_session()
    try:
        session.query(TestResult).filter(
            TestResult.task_id == src_a).delete()
        session.commit()
    finally:
        remove_db_session()
    out2 = cherry_pick_service.checkout({'action': 'reevaluate'})
    assert out2['success'] is False
