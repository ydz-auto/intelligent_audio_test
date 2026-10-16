# -*- coding: utf-8 -*-
"""VEGA-32 软删语义收敛 + 软删审计 测试

覆盖：
1. 全局软删过滤单一入口 —— 建任务 / 执行 / 报告 / 发布任务四条路径同口径；
2. 软删审计 —— 软删后 deleted_at 非空、恢复后清空；
3. 显式放开 —— include_deleted() / execution_options(include_deleted=True) 可读到软删行。

运行（在 Intelligent-Audio-TEST 目录下）：
    python -m pytest backend/tests/test_soft_delete_semantics.py -v
"""
import uuid

import pytest
from sqlalchemy import text

from backend.models.database import db
from backend.models.models import TestCase, TestCaseGroup, Tag, TestCaseTag, Task, TaskCase
from backend.models.soft_delete import bulk_soft_delete, include_deleted
from backend.controllers.task_controller import TaskController
from backend.controllers.published_task_controller import PublishedTaskController
from backend.controllers.testcase_controller import TestCaseController


def _new_group():
    group = TestCaseGroup(id=str(uuid.uuid4()), name=f'软删测试组-{uuid.uuid4().hex[:8]}')
    db.session.add(group)
    db.session.flush()
    return group


def _new_case(group, deleted=False):
    case = TestCase(
        id=str(uuid.uuid4()),
        name=f'软删测试用例-{uuid.uuid4().hex[:8]}',
        config={'rounds': []},
        group_id=group.id,
        test_type='api',
        deleted=deleted,
    )
    db.session.add(case)
    db.session.flush()
    return case


# ---------- 1. 单一入口：全局过滤 ----------

def test_soft_deleted_case_hidden_from_all_query_styles(app):
    """软删用例对 session.get / Query.get / filter / 纯列查询 一律不可见

    注：断言前 expunge_all() 模拟"新请求拿到新 Session"（同 Session 内已加载的实例
    由 SQLAlchemy identity map 直接返回，属 ORM 通用语义，见文件末尾的显式用例）。
    """
    group = _new_group()
    case = _new_case(group)
    case.deleted = True
    db.session.commit()
    case_id = case.id

    db.session.expunge_all()
    assert db.session.get(TestCase, case_id) is None
    assert db.session.query(TestCase).filter_by(id=case_id).first() is None
    assert db.session.query(TestCase.id).filter(TestCase.id == case_id).all() == []
    assert db.session.query(TestCase).filter(TestCase.deleted == False).filter_by(id=case_id).first() is None


def test_alive_case_still_visible(app):
    """回归：未软删用例不受影响"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    db.session.expire_all()

    assert db.session.get(TestCase, case.id) is not None
    assert db.session.query(TestCase).filter_by(id=case.id).first() is not None


def test_include_deleted_opt_out(app):
    """显式放开：include_deleted() 上下文 / execution_options 均可读到软删行"""
    group = _new_group()
    case = _new_case(group)
    case.deleted = True
    db.session.commit()
    case_id = case.id
    db.session.expunge_all()

    with include_deleted():
        assert db.session.get(TestCase, case_id) is not None

    # 退出上下文后恢复过滤
    db.session.expunge_all()
    assert db.session.get(TestCase, case_id) is None

    assert db.session.query(TestCase).execution_options(
        include_deleted=True).filter_by(id=case_id).first() is not None


def test_identity_map_resident_instance_is_stale_by_design(app):
    """已知边界：同一 Session 内已加载的实例由 identity map 直接返回（ORM 通用语义）。

    四条业务路径（建任务 / 执行 / 报告 / 发布任务）均走会发出 SQL 的查询或独立 Session，
    因此不受影响；此处显式固化该边界，避免被误判为过滤失效。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    case.deleted = True
    db.session.commit()

    # 同 Session：identity map 命中，不重发查询
    assert db.session.get(TestCase, case_id) is not None
    # 换 Session（等价于新请求）：过滤生效
    db.session.expunge_all()
    assert db.session.get(TestCase, case_id) is None


def test_relationship_load_filters_soft_deleted(app):
    """关系加载同口径：task.cases 不返回软删用例"""
    group = _new_group()
    alive = _new_case(group)
    doomed = _new_case(group)
    task = Task(name='软删关系测试任务', type='api', status='pending', total_cases=2)
    db.session.add(task)
    db.session.flush()
    for c in (alive, doomed):
        db.session.add(TaskCase(task_id=task.id, test_case_id=c.id, status='pending',
                                execution_status='pending', evaluation_status='pending'))
    db.session.flush()

    doomed.deleted = True
    db.session.commit()
    db.session.expire_all()

    task = db.session.get(Task, task.id)
    loaded_ids = {c.id for c in task.cases}
    assert alive.id in loaded_ids
    assert doomed.id not in loaded_ids


# ---------- 2. 四条路径同口径 ----------

def test_create_task_rejects_soft_deleted_case(app):
    """建任务路径：软删用例被拒绝，且错误信息可见（不静默）"""
    group = _new_group()
    case = _new_case(group)
    case.deleted = True
    db.session.commit()

    unusable = TaskController._find_unusable_case_ids([case.id])
    assert unusable == [case.id]


def test_create_task_accepts_alive_case(app):
    """回归：未软删用例可正常建任务"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    assert TaskController._find_unusable_case_ids([case.id]) == []


def test_create_task_rejects_unknown_case(app):
    """建任务路径：不存在的用例同样被拒绝"""
    missing_id = str(uuid.uuid4())
    assert TaskController._find_unusable_case_ids([missing_id]) == [missing_id]


def test_published_task_snapshot_filters_soft_deleted(app):
    """发布任务路径：docstring 所述「已删除的用例 ID 自动过滤」与代码一致"""
    group = _new_group()
    alive = _new_case(group)
    doomed = _new_case(group)
    doomed.deleted = True
    db.session.commit()

    snapshot = {'caseIds': [doomed.id, alive.id]}
    valid, err = PublishedTaskController._validate_snapshot(snapshot)
    assert err is None
    assert valid == [alive.id]


def test_published_task_snapshot_all_deleted_rejected(app):
    """发布任务路径：快照用例全被软删时明确拒绝"""
    group = _new_group()
    doomed = _new_case(group)
    doomed.deleted = True
    db.session.commit()

    valid, err = PublishedTaskController._validate_snapshot({'caseIds': [doomed.id]})
    assert valid is None
    assert err is not None


def test_report_path_excludes_soft_deleted_case(app):
    """报告路径：用例快照批量加载不再返回软删用例（report_utils / report_controller_base 同口径）"""
    group = _new_group()
    alive = _new_case(group)
    doomed = _new_case(group)
    doomed.deleted = True
    db.session.commit()

    loaded = TestCase.query.filter(TestCase.id.in_([alive.id, doomed.id])).all()
    loaded_ids = {c.id for c in loaded}
    assert alive.id in loaded_ids
    assert doomed.id not in loaded_ids


# ---------- 3. 软删审计 ----------

def test_soft_delete_writes_deleted_at(app):
    """软删后 deleted_at 非空（东八区时间），并留下可追溯痕迹"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id
    assert case.deleted_at is None

    case.deleted = True
    db.session.commit()

    row = db.session.execute(text(
        'SELECT deleted, deleted_at FROM test_cases WHERE id = :i'
    ), {'i': case_id}).fetchone()
    assert row[0] is True
    assert row[1] is not None


def test_restore_clears_deleted_at(app):
    """恢复（deleted true→false）时清空 deleted_at"""
    group = _new_group()
    case = _new_case(group)
    case.deleted = True
    db.session.commit()
    case_id = case.id

    with include_deleted():
        row = db.session.get(TestCase, case_id)
    row.deleted = False
    db.session.commit()

    stored = db.session.execute(text(
        'SELECT deleted, deleted_at FROM test_cases WHERE id = :i'
    ), {'i': case_id}).fetchone()
    assert stored[0] is False
    assert stored[1] is None


def test_soft_delete_audit_covers_other_models(app):
    """审计入口覆盖所有继承 SoftDeleteMixin 的模型（用例分组 / 音频 / 任务）"""
    group = _new_group()
    db.session.commit()

    group.deleted = True
    db.session.commit()

    stored = db.session.execute(text(
        'SELECT deleted_at FROM test_case_groups WHERE id = :i'
    ), {'i': group.id}).fetchone()
    assert stored is not None and stored[0] is not None


# ---------- 4. 批量 / 级联软删的审计（bulk update 不走 ORM before_flush） ----------

def _raw_case_audit(case_id):
    """绕开 ORM 直接读软删痕迹（软删行对 ORM 查询不可见）"""
    return db.session.execute(text(
        'SELECT deleted, deleted_at FROM test_cases WHERE id = :i'
    ), {'i': case_id}).fetchone()


def test_raw_bulk_update_bypasses_audit_hook(app):
    """边界（为什么必须走 bulk_soft_delete）：裸 bulk update 绕过 before_flush，不写 deleted_at。

    这是 ORM 语义而非缺陷——正因如此，批量删除与级联删除必须显式改调统一入口，
    否则它们会成为审计盲区。本用例把该边界固化下来。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    TestCase.query.filter(TestCase.id == case.id).update(
        {"deleted": True}, synchronize_session=False)

    row = _raw_case_audit(case.id)
    assert row[0] is True
    assert row[1] is None


def test_bulk_soft_delete_writes_deleted_at(app):
    """批量软删统一入口：bulk update 同样写 deleted_at（before_flush 拦不到 bulk）"""
    group = _new_group()
    case_ids = [_new_case(group).id, _new_case(group).id]
    db.session.commit()

    affected = bulk_soft_delete(TestCase.query.filter(TestCase.id.in_(case_ids)))
    assert affected == len(case_ids)

    for case_id in case_ids:
        row = _raw_case_audit(case_id)
        assert row[0] is True
        assert row[1] is not None


def test_batch_delete_controller_writes_deleted_at(app):
    """软删写入点②（批量删除接口）：走统一入口后 deleted_at 非空"""
    group = _new_group()
    case_ids = [_new_case(group).id, _new_case(group).id]
    db.session.commit()

    class _Req:
        pass

    req = _Req()
    req.ids = case_ids
    assert '2' in TestCaseController._batch_delete(req)

    for case_id in case_ids:
        row = _raw_case_audit(case_id)
        assert row[0] is True
        assert row[1] is not None


def test_tag_cascade_soft_delete_writes_deleted_at(app, client):
    """软删写入点③（删标签级联）：级联软删的用例 deleted_at 非空"""
    group = _new_group()
    case = _new_case(group)
    tag = Tag(name=f'软删测试标签-{uuid.uuid4().hex[:8]}')
    db.session.add(tag)
    db.session.flush()
    db.session.add(TestCaseTag(test_case_id=case.id, tag_id=tag.id))
    db.session.commit()

    resp = client.delete(f'/api/v1/tags/{tag.id}?cascade=true')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    row = _raw_case_audit(case.id)
    assert row[0] is True
    assert row[1] is not None


def test_group_cascade_soft_delete_writes_deleted_at(app, client):
    """软删写入点④（删分组级联）：分组与其下用例 deleted_at 均非空"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/groups/{group.id}?cascade=true')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    case_row = _raw_case_audit(case.id)
    assert case_row[0] is True
    assert case_row[1] is not None

    group_row = db.session.execute(text(
        'SELECT deleted, deleted_at FROM test_case_groups WHERE id = :i'
    ), {'i': group.id}).fetchone()
    assert group_row[0] is True
    assert group_row[1] is not None
