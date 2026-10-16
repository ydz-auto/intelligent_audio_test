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
from backend.models.models import (
    TestCase, TestCaseGroup, Tag, TestCaseTag, Task, TaskCase, TestResult, API,
)
from backend.models.soft_delete import bulk_soft_delete, include_deleted
from backend.controllers.task_controller import TaskController
from backend.controllers.published_task_controller import PublishedTaskController
from backend.controllers.testcase_controller import TestCaseController
from backend.controllers.report_controller_task import ReportControllerTask
from backend.services.execution.execution_engine import ExecutionEngine
from backend.services.execution.api_executor import APIExecutor
from backend.utils.report.report_utils import ReportUtils

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
        group_id=group.id if group is not None else None,
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


# ---------- 7. 报告域：软删用例不得静默改归（缺陷 D2 回归） ----------

def _new_task_with_result(case, status='completed'):
    """建一个含单条 TestResult 的任务（报告生成的最小前置）

    TestResult 挂一个真实 API：报告层 `get_resource_name` 需要 api_id/device_id
    才能定位资源（两者皆空会触发该函数内既有的一处 `base_resource` 未初始化问题，
    与本卡无关，见交付评论的观察项）。
    """
    api = API(name=f'软删报告测试API-{uuid.uuid4().hex[:8]}', meta={}, api_endpoints=[])
    db.session.add(api)
    db.session.flush()
    task = Task(name=f'软删报告测试任务-{uuid.uuid4().hex[:8]}', type='api',
                status=status, total_cases=1)
    db.session.add(task)
    db.session.flush()
    db.session.add(TaskCase(task_id=task.id, test_case_id=case.id, status='completed',
                            execution_status='completed', evaluation_status='completed'))
    result = TestResult(task_id=task.id, test_case_id=case.id, api_id=api.id,
                        algorithm_type='asr', execution_status='completed')
    db.session.add(result)
    db.session.flush()
    return task, result


def test_report_generation_excludes_soft_deleted_case_result(app):
    """报告生成门禁：软删用例的执行结果不得进入 results

    缺陷 D2：`valid_case_ids` 原先取自 TaskCase（未接入软删过滤），软删用例的
    TestResult 仍留在 results 里，报告层按 id 又取不到它的元数据 → 静默归到
    default_group。上游收敛后，软删用例的结果根本不进报告，且是显式失败而非静默空报告。
    """
    group = _new_group()
    case = _new_case(group)
    task, _result = _new_task_with_result(case)
    db.session.commit()
    task_id = task.id

    # 基线：未软删时结果正常进入报告
    _task, results, error = ReportControllerTask._validate_task_and_get_results(task_id)
    assert error is None, f'基线不应报错: {error}'
    assert results is not None and len(results) == 1, f'基线应含 1 条结果，实际 {results!r}'

    # 软删用例后：结果不得再进入报告，且必须显式失败
    case.deleted = True
    db.session.commit()

    _task, results, error = ReportControllerTask._validate_task_and_get_results(task_id)
    assert not results, f'软删用例的执行结果仍进入报告: {results!r}'
    assert error is not None, '软删用例被剔除后应显式报错，不能静默产出空报告'


def test_report_aggregation_skips_soft_deleted_case_instead_of_default_group(app):
    """报告聚合：软删用例被显式跳过，不得凭空生成 default_group / default_tag 桶

    缺陷 D2 的静默错分：原实现 `if not test_case` 走 `default_group` 兜底，
    同一份数据出现在一个不存在的分组里、原分组少一个样本，全程无日志。
    """
    group = _new_group()
    case = _new_case(group)
    task, result = _new_task_with_result(case)
    db.session.commit()
    task_id, result_id = task.id, result.id

    # 基线：未软删 → 分数归在真实分组下
    alive_result = db.session.get(TestResult, result_id)
    baseline = ReportUtils.calculate_core_metrics([alive_result], [], [], tasks_map={task_id: task})
    assert group.id in baseline['case_type_stats'], '基线应归到真实分组'
    assert 'default_group' not in baseline['case_type_stats']

    # 软删该用例 → 不得凭空出现 default_group / default_tag
    case.deleted = True
    db.session.commit()
    db.session.expire_all()

    soft_deleted_result = db.session.get(TestResult, result_id)
    assert soft_deleted_result is not None, 'TestResult 本身未软删，应仍可读'
    payload = ReportUtils.calculate_core_metrics(
        [soft_deleted_result], [], [], tasks_map={task_id: task}
    )
    assert 'default_group' not in payload['case_type_stats'], \
        f"软删用例被静默归到 default_group: {payload['case_type_stats']!r}"
    assert 'default_tag' not in payload['tag_metric_data'], \
        f"软删用例被静默归到 default_tag: {payload['tag_metric_data']!r}"
    assert payload['resources'] == [], \
        f"软删用例仍被登记为报告资源: {payload['resources']!r}"


def test_alive_ungrouped_case_still_uses_default_group(app):
    """回归：用例**存在**但确实没有分组/标签时，default_group / default_tag 仍照旧

    区分两种「取不到 test_case」：软删（跳过）vs 用例本就没有分组（合法桶，保留）。
    """
    case = _new_case(None)
    task, result = _new_task_with_result(case)
    db.session.commit()

    payload = ReportUtils.calculate_core_metrics(
        [db.session.get(TestResult, result.id)], [], [], tasks_map={task.id: task}
    )
    assert 'default_group' in payload['case_type_stats'], \
        '无分组用例应仍归到 default_group（合法桶，不能被本次改动误伤）'
    assert 'default_tag' in payload['tag_metric_data']


# ---------- 8. 统一入口的幂等守卫（M3） ----------

def test_bulk_soft_delete_is_idempotent(app):
    """M3：重复软删不得覆盖首次的 deleted_at / 操作人（守卫内聚在统一入口）

    标签级联删除的 case_ids 取自关联表（含已软删用例）→ 必然发生重复软删；
    原实现会覆盖首次痕迹。守卫收敛进 `bulk_soft_delete` 后，调用方无需各自记得加。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()
    case_id = case.id

    affected = bulk_soft_delete(TestCase.query.filter(TestCase.id == case_id),
                                operator_user_id=111111)
    db.session.commit()
    assert affected == 1, f'首次软删应命中 1 行，实际 {affected}'
    first = _raw_case_operator(case_id)

    affected_again = bulk_soft_delete(TestCase.query.filter(TestCase.id == case_id),
                                      operator_user_id=222222)
    db.session.commit()
    assert affected_again == 0, f'重复软删不应再命中已软删行，实际 {affected_again}'
    second = _raw_case_operator(case_id)

    assert second[1] == first[1], f'deleted_at 被重复软删覆盖: {first[1]!r} → {second[1]!r}'
    assert second[2] == first[2], f'操作人被重复软删覆盖: {first[2]!r} → {second[2]!r}'


def test_tag_cascade_does_not_overwrite_existing_deleted_at(app, client):
    """M3 真实路径：用例已软删后，删其标签的级联不得覆盖该用例的首次软删痕迹"""
    group = _new_group()
    case = _new_case(group)
    tag = Tag(name=f'幂等守卫标签-{uuid.uuid4().hex[:8]}')
    db.session.add(tag)
    db.session.flush()
    db.session.add(TestCaseTag(test_case_id=case.id, tag_id=tag.id))
    db.session.commit()
    case_id, tag_id = case.id, tag.id

    # 先由单条删除接口软删该用例（留下首次痕迹）
    resp = client.delete(f'/api/v1/testcases/{case_id}',
                         headers={'X-User-Id': '111111'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    first = _raw_case_operator(case_id)
    assert first[1] is not None and first[2] == 111111

    # 再删标签触发级联：关联表里仍留着该已软删用例的 id
    resp = client.delete(f'/api/v1/tags/{tag_id}?cascade=true',
                         headers={'X-User-Id': '222222'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    second = _raw_case_operator(case_id)

    assert second[1] == first[1], f'级联重复软删覆盖了 deleted_at: {first[1]!r} → {second[1]!r}'
    assert second[2] == 111111, f'级联重复软删覆盖了操作人: {second[2]!r}'


# ---------- 9. 操作人过渡期开关（M4） ----------

def test_operator_header_ignored_when_auth_enabled(app, client):
    """M4：认证落地（AUTH_ENABLED=true）后不再信任客户端自带的 X-User-Id

    否则任何客户端都能伪造审计操作人——被污染的审计字段比 NULL 更坏。
    """
    group = _new_group()
    case = _new_case(group)
    db.session.commit()

    original = app.config.get('AUTH_ENABLED', False)
    app.config['AUTH_ENABLED'] = True
    try:
        resp = client.delete(f'/api/v1/testcases/{case.id}',
                             headers={'X-User-Id': str(OPERATOR_ID)})
        assert resp.status_code == 200, resp.get_data(as_text=True)
    finally:
        app.config['AUTH_ENABLED'] = original

    deleted, deleted_at, operator = _raw_case_operator(case.id)
    assert deleted is True
    assert deleted_at is not None, '即使不认请求头，软删审计（deleted_at）仍须写入'
    assert operator is None, f'认证落地后不应采信客户端自带的 X-User-Id，实际 {operator!r}'
