# -*- coding: utf-8 -*-
"""VEGA-32 软删语义收敛 + 软删审计 测试

覆盖：
1. 全局软删过滤单一入口 —— 建任务 / 执行 / 报告 / 发布任务四条路径同口径；
2. 软删审计 —— 软删后 deleted_at 非空、恢复后清空；
3. 显式放开 —— include_deleted() / execution_options(include_deleted=True) 可读到软删行；
4. 操作人机制就位（临时口径 A）—— 有身份来源时落库、无身份来源时不伪造；
5. 执行路径软删不得静默（缺陷 D1 回归）。

运行（在 Intelligent-Audio-TEST 目录下）：
    python -m pytest backend/tests/test_soft_delete_semantics.py -v
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from backend.models.database import db
from backend.models.models import TestCase, TestCaseGroup, Tag, TestCaseTag, Task, TaskCase
from backend.models.soft_delete import bulk_soft_delete, include_deleted
from backend.controllers.task_controller import TaskController
from backend.controllers.published_task_controller import PublishedTaskController
from backend.controllers.testcase_controller import TestCaseController
from backend.services.execution.execution_engine import ExecutionEngine
from backend.services.execution.api_executor import APIExecutor

UTC8 = timezone(timedelta(hours=8))
OPERATOR_ID = 424242


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


# ---------- 5. 操作人机制就位（临时口径 A：无认证体系时落 NULL，但不伪造身份） ----------

def _raw_case_operator(case_id):
    """绕开 ORM 直接读软删痕迹 + 操作人（软删行对 ORM 查询不可见）"""
    return db.session.execute(text(
        'SELECT deleted, deleted_at, updated_by_user_id FROM test_cases WHERE id = :i'
    ), {'i': case_id}).fetchone()


def test_operator_header_lands_on_single_delete(app, client):
    """写入点① 单条删除（ORM 路径，走 before_flush）：X-User-Id 注入时操作人落库"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/testcases/{case.id}',
                         headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw_case_operator(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator == OPERATOR_ID


def test_operator_header_lands_on_batch_delete(app, client):
    """写入点② 批量删除（bulk 统一入口）：X-User-Id 注入时操作人落库"""
    group = _new_group()
    ids = [_new_case(group).id, _new_case(group).id]
    db.session.commit()

    resp = client.post('/api/v1/testcases/batch',
                       json={'action': 'delete', 'ids': ids},
                       headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    for case_id in ids:
        deleted, deleted_at, operator = _raw_case_operator(case_id)
        assert deleted is True
        assert deleted_at is not None
        assert operator == OPERATOR_ID


def test_operator_header_lands_on_tag_cascade(app, client):
    """写入点③ 删标签级联（bulk 统一入口，最易漏的一处）"""
    group = _new_group()
    case = _new_case(group)
    tag = Tag(name=f'软删测试标签-{uuid.uuid4().hex[:8]}')
    db.session.add(tag)
    db.session.flush()
    db.session.add(TestCaseTag(test_case_id=case.id, tag_id=tag.id))
    db.session.commit()

    resp = client.delete(f'/api/v1/tags/{tag.id}?cascade=true',
                         headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw_case_operator(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator == OPERATOR_ID


def test_operator_header_lands_on_group_cascade(app, client):
    """写入点④ 删分组级联（bulk 统一入口）+ 分组本体（ORM 路径），两处都要落操作人"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/groups/{group.id}?cascade=true',
                         headers={'X-User-Id': str(OPERATOR_ID)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw_case_operator(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator == OPERATOR_ID

    group_row = db.session.execute(text(
        'SELECT deleted, deleted_at, updated_by_user_id FROM test_case_groups WHERE id = :i'
    ), {'i': group.id}).fetchone()
    assert group_row[0] is True
    assert group_row[1] is not None
    assert group_row[2] == OPERATOR_ID


def test_operator_stays_null_without_identity(app, client):
    """临时口径 A：无身份来源时**不伪造**操作人，落 NULL 属预期（deleted_at 仍须非空）"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    resp = client.delete(f'/api/v1/testcases/{case.id}')
    assert resp.status_code == 200, resp.get_data(as_text=True)

    deleted, deleted_at, operator = _raw_case_operator(case.id)
    assert deleted is True
    assert deleted_at is not None
    assert operator is None


def test_deleted_at_is_utc8_wall_clock(app, client):
    """deleted_at 为东八区时间（与库内既有 created_at/updated_at 口径一致）"""
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    before = datetime.now(UTC8).replace(tzinfo=None) - timedelta(seconds=5)
    resp = client.delete(f'/api/v1/testcases/{case.id}')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    after = datetime.now(UTC8).replace(tzinfo=None) + timedelta(seconds=5)

    stored = _raw_case_operator(case.id)[1]
    assert stored is not None
    assert before <= stored <= after, f'deleted_at={stored} 不在东八区当前时间窗口内'


# ---------- 6. 执行路径：软删用例不得静默（缺陷 D1 回归） ----------

def test_api_execution_of_soft_deleted_case_marks_failed(app):
    """建任务后用例被软删 → API 执行必须显式失败并落 error_message。

    缺陷 D1：原先 `_validate_and_get_data` 取不到用例时抛异常，异常被
    `execute_api_case` 的兜底 except 吞掉，TaskCase 停在 execution_status='running'，
    任务主循环要干等到 test_case_wait_time（默认 3000 秒）超时才收敛。
    口径「软删即不可用」：显式失败 + 可见原因，不静默。
    """
    group = _new_group()
    case = _new_case(group)
    task = Task(name=f'软删执行测试任务-{uuid.uuid4().hex[:8]}', type='api',
                status='running', total_cases=1)
    db.session.add(task)
    db.session.flush()
    tc_rel = TaskCase(task_id=task.id, test_case_id=case.id, status='pending',
                      execution_status='pending', evaluation_status='pending')
    db.session.add(tc_rel)
    db.session.commit()
    task_id, tc_rel_id = task.id, tc_rel.id

    # 建任务之后软删该用例
    case.deleted = True
    db.session.commit()

    APIExecutor(ExecutionEngine()).execute_api_case(app, task_id, tc_rel_id)

    row = db.session.execute(text(
        'SELECT status, execution_status, error_message FROM task_case_relations WHERE id = :i'
    ), {'i': tc_rel_id}).fetchone()
    assert row[0] == 'failed', f'期望 status=failed，实际 {row[0]!r}'
    assert row[1] == 'failed', \
        f'期望 execution_status=failed，实际 {row[1]!r}（停在 running 会让任务无法收敛）'
    assert row[2] == '找不到测试用例', f'期望可见失败原因，实际 {row[2]!r}'


def test_api_execution_of_alive_case_regression(app):
    """回归：未软删用例不会被上面的改动误判为失败（走不到「找不到测试用例」分支）"""
    group = _new_group()
    case = _new_case(group)
    task = Task(name=f'正常执行测试任务-{uuid.uuid4().hex[:8]}', type='api',
                status='running', total_cases=1)
    db.session.add(task)
    db.session.flush()
    tc_rel = TaskCase(task_id=task.id, test_case_id=case.id, status='pending',
                      execution_status='pending', evaluation_status='pending')
    db.session.add(tc_rel)
    db.session.commit()
    tc_rel_id = tc_rel.id

    APIExecutor(ExecutionEngine()).execute_api_case(app, task.id, tc_rel_id)

    row = db.session.execute(text(
        'SELECT error_message FROM task_case_relations WHERE id = :i'
    ), {'i': tc_rel_id}).fetchone()
    # 未软删用例：不会被误报为「找不到测试用例」（后续失败原因是缺 API 配置等真实原因）
    assert row[0] != '找不到测试用例', f'未软删用例被误判: {row[0]!r}'
