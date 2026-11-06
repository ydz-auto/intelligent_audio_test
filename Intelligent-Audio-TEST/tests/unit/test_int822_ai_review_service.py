# -*- coding: utf-8 -*-
"""INT-822 专项：task_service AI 复核命令侧（发起/幂等复用/采纳/驳回/审计）。

覆盖（对齐 INT-800 契约定稿 #2 + 验收标准）：
- 发起：每对 (result_id, dimension_id) 落记录；缺省维度=结果已完成评估的 LLM 判分维度；
  异步执行骨架回写 verdict/confidence/reasoning/completed，失败置 failed 不落判定
- 幂等：非 force 且该对已有 running/completed → 复用最近一条（reused=true）；force 新建
- 采纳：复用 apply_review 落 test_result_reviews 留痕 + 统计重算 + 记录置 adopted
  （前置 status=completed 且未处置 / 终态任务 / 枚举 / comment≥1）
- 驳回：置 rejected/rejected_by/rejected_at，原判定不变
- 审计：AI 复核历史按任务/结果/维度/状态过滤（时间倒序）
- 回归：人工复核计数/历史/标记不受 AI 记录影响（review-count / review-history /
  reviewed_result_ids 结果不变）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int340 / test_int821 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int822_proc.db')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session, utc8now,
)
from shared.infrastructure.user_context import set_current_user_id
from task_service.infrastructure.persistence.models import AiReview

_TABLES = None


def _ensure_tables():
    global _TABLES
    if _TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TestCase, TestResult, TestResultReview, Log,
        )
        _TABLES = [t.__table__ for t in (
            Task, TaskCase, TestCase, TestResult, TestResultReview, AiReview, Log,
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


def _seed_task(name='INT822源任务', status='completed', case_status=None,
               exec_status='failed', eval_status='completed'):
    """种子：终态任务 + 1 用例 1 结果（执行失败 / 评估完成）。返回 (task_id, result_id, case_id)。"""
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult, TestCase
    session = get_db_session()
    try:
        task = Task(name=name, status=status, total_cases=1,
                    completed_cases=0, failed_cases=1, algorithm_type='asr')
        session.add(task)
        session.flush()
        case_id = 'INT822-C1'
        if session.query(TestCase).filter(TestCase.id == case_id).first() is None:
            session.add(TestCase(
                id=case_id, name='INT822用例', description='', config={},
                algorithm_type='asr',
            ))
        session.add(TaskCase(
            task_id=task.id, test_case_id=case_id,
            status=case_status or ('skipped' if exec_status == 'skipped' else 'failed'),
            execution_status=exec_status, evaluation_status=eval_status,
            device_type='physical', device_id='7',
        ))
        r = TestResult(
            task_id=task.id, test_case_id=case_id, device_id=7,
            algorithm_type='asr', execution_status=exec_status,
            algorithm_result={'asr_result': '文本'},
        )
        session.add(r)
        session.flush()
        session.commit()
        return task.id, r.id, case_id
    finally:
        remove_db_session()


def _seed_ai_review(result_id, task_id, test_case_id='INT822-C1', dimension_id=7,
                    status='completed', verdict='passed', confidence=0.9,
                    reasoning='AI复核理由', adopted=0, rejected=0):
    """种子：一条 AI 复核记录（可带处置标记）。返回 record dict。"""
    from task_service.infrastructure.persistence.ai_review_repository import (
        ai_review_repository,
    )
    rec = ai_review_repository.create(
        result_id=result_id, task_id=task_id, test_case_id=test_case_id,
        dimension_id=dimension_id, status=status, verdict=verdict,
        confidence=confidence, reasoning=reasoning,
    )
    if adopted or rejected:
        session = get_db_session()
        try:
            po = session.get(AiReview, rec['id'])
            if adopted:
                po.adopted = 1
                po.adopted_by_user_id = 7
                po.adopted_at = utc8now()
            if rejected:
                po.rejected = 1
                po.rejected_by_user_id = 9
                po.rejected_at = utc8now()
            session.commit()
        finally:
            remove_db_session()
    return rec


def _sync_executor(monkeypatch):
    """让发起后的异步执行同步跑（单测绕开线程时序；LLM 复检结果由用例 mock ACL）。"""
    from task_service.application.task.ai_review_executor import ai_review_executor
    monkeypatch.setattr(ai_review_executor, 'submit',
                        lambda review_id: ai_review_executor.execute_now(review_id))


def _mock_llm(monkeypatch, verdict='passed', confidence=0.92, reasoning='置信度达标'):
    """mock evaluation_service LLM 复检 gRPC 成功返回。"""
    from task_service.infrastructure.acl.evaluation_config_acl_repository import (
        evaluation_config_acl_repository,
    )
    monkeypatch.setattr(
        evaluation_config_acl_repository, 'run_ai_review_check',
        lambda **kw: {'success': True, 'message': '', 'data': {
            'verdict': verdict, 'confidence': confidence, 'reasoning': reasoning}})


def _mock_llm_fail(monkeypatch, message='LLM 端点不可达'):
    """mock LLM 复检失败（发起记录置 failed）。"""
    from task_service.infrastructure.acl.evaluation_config_acl_repository import (
        evaluation_config_acl_repository,
    )
    monkeypatch.setattr(
        evaluation_config_acl_repository, 'run_ai_review_check',
        lambda **kw: {'success': False, 'message': message, 'data': None})


def _mock_dimension_results_grpc(monkeypatch, rows_by_result_id):
    """mock evaluation_service gRPC 层（真实条目形状）→ 走真实 ACL 映射。

    rows_by_result_id: {result_id: [条目 dict, ...]}。条目对齐 evaluation_service
    get_dimension_results_with_names_by_result_ids 输出形状（含 test_result_id /
    dimension_id / evaluation_status ...）。缺省维度用例经此 mock，防「mock 形状
    与真实 ACL 输出不一致」掩盖映射缺陷（INT-822 审计 P1 回归）。
    """
    import json as _json
    from shared.clients import grpc_clients as _gc
    from shared.proto import evaluation_service_pb2 as eval_pb

    items = []
    for rid, rows in rows_by_result_id.items():
        for row in rows:
            item = {'test_result_id': rid}
            item.update(row)
            items.append(item)

    class _FakeStub:
        def GetDimensionResultsByResultIds(self, request):
            return eval_pb.EvaluationDataResponse(
                success=True, message='',
                data=_json.dumps({'items': items}),
            )

    monkeypatch.setattr(_gc, 'get_evaluation_data_service_stub',
                        lambda: _FakeStub())


def _llm_service():
    from task_service.application.task.ai_review_service import ai_review_service
    return ai_review_service


def _review_service():
    from task_service.application.task.review_service import review_service
    return review_service


# ==================== 发起 ====================

def test_initiate_creates_record_and_executes(db, monkeypatch):
    """发起：落 running 记录 → 异步执行回写 verdict/confidence/reasoning/completed。"""
    from task_service.infrastructure.persistence.ai_review_repository import (
        ai_review_repository,
    )
    task_id, result_id, _ = _seed_task()
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch)

    set_current_user_id(42)
    resp = _llm_service().initiate_review({
        'result_ids': [result_id], 'dimension_ids': [7],
    })
    assert resp['success'] is True, resp
    assert resp['data']['reused'] is False
    items = resp['data']['items']
    assert len(items) == 1
    assert items[0]['result_id'] == result_id
    assert items[0]['task_id'] == task_id
    assert items[0]['dimension_id'] == 7
    # 发起返回快照为 running；异步执行（同步 mock）写回落库状态
    assert items[0]['status'] == 'running'
    got = ai_review_repository.get(items[0]['id'])
    assert got['status'] == 'completed'
    assert got['verdict'] == 'passed'
    assert got['confidence'] == 0.92
    assert got['reasoning'] == '置信度达标'


def test_initiate_multiple_pairs(db, monkeypatch):
    """发起多结果多维度：每对 (result_id, dimension_id) 各落一条。"""
    task_id, result_id, _ = _seed_task()
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch)

    resp = _llm_service().initiate_review({
        'result_ids': [result_id], 'dimension_ids': [7, 8],
    })
    assert resp['success'] is True, resp
    items = resp['data']['items']
    assert len(items) == 2
    assert {it['dimension_id'] for it in items} == {7, 8}


def test_initiate_idempotent_reuse(db, monkeypatch):
    """幂等：非 force 且该对已有 completed → 复用最近一条（reused=true），不重复发起。"""
    from task_service.infrastructure.persistence.ai_review_repository import (
        ai_review_repository,
    )
    task_id, result_id, _ = _seed_task()
    _seed_ai_review(result_id, task_id, dimension_id=7,
                    status='completed', verdict='passed')
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch)

    resp = _llm_service().initiate_review({
        'result_ids': [result_id], 'dimension_ids': [7],
    })
    assert resp['success'] is True, resp
    assert resp['data']['reused'] is True
    assert len(resp['data']['items']) == 1
    # 复用最近一条，不新建
    assert ai_review_repository.list_by_result(result_id) == resp['data']['items']
    assert ai_review_repository.list_by_result(result_id)[0]['status'] == 'completed'


def test_initiate_reuses_running_too(db, monkeypatch):
    """幂等：running 中重复发起同样复用（不并发重复执行）。"""
    task_id, result_id, _ = _seed_task()
    _seed_ai_review(result_id, task_id, dimension_id=7, status='running')

    resp = _llm_service().initiate_review({
        'result_ids': [result_id], 'dimension_ids': [7],
    })
    assert resp['success'] is True, resp
    assert resp['data']['reused'] is True
    assert resp['data']['items'][0]['status'] == 'running'


def test_initiate_failed_not_reused(db, monkeypatch):
    """幂等不覆盖 failed：最近一条 failed 时非 force 重新发起新建记录。"""
    from task_service.infrastructure.persistence.ai_review_repository import (
        ai_review_repository,
    )
    task_id, result_id, _ = _seed_task()
    _seed_ai_review(result_id, task_id, dimension_id=7, status='failed')
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch)

    resp = _llm_service().initiate_review({
        'result_ids': [result_id], 'dimension_ids': [7],
    })
    assert resp['success'] is True, resp
    assert resp['data']['reused'] is False
    rows = ai_review_repository.list_by_result(result_id)
    assert len(rows) == 2  # 旧 failed + 新执行
    assert rows[0]['status'] == 'completed'


def test_initiate_force_new_record(db, monkeypatch):
    """force=true：绕过幂等复用，新建记录重新执行。"""
    from task_service.infrastructure.persistence.ai_review_repository import (
        ai_review_repository,
    )
    task_id, result_id, _ = _seed_task()
    first = _seed_ai_review(result_id, task_id, dimension_id=7,
                            status='completed', verdict='passed')
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch, verdict='failed', confidence=0.3, reasoning='重测失败')

    resp = _llm_service().initiate_review({
        'result_ids': [result_id], 'dimension_ids': [7], 'force': True,
    })
    assert resp['success'] is True, resp
    assert resp['data']['reused'] is False
    assert resp['data']['items'][0]['id'] != first['id']
    # 新建记录异步执行落库 verdict=failed
    rows = ai_review_repository.list_by_result(result_id)
    assert len(rows) == 2
    new_row = next(r for r in rows if r['id'] != first['id'])
    assert new_row['verdict'] == 'failed'
    assert new_row['status'] == 'completed'


def test_initiate_empty_result_ids_rejected(db):
    """发起：result_ids 为空拒绝。"""
    resp = _llm_service().initiate_review({'result_ids': []})
    assert resp['success'] is False
    assert resp['data']['code'] == 400
    assert '不能为空' in resp['message']


def test_initiate_missing_result_skipped(db, monkeypatch):
    """发起：结果不存在 → skipped，无记录不 200。"""
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch)
    resp = _llm_service().initiate_review({'result_ids': [999999]})
    assert resp['success'] is False
    assert resp['data']['code'] == 400
    assert resp['data']['skipped'][0]['message'] == '结果不存在'


def test_initiate_default_dimensions_from_completed_llm_judge(db, monkeypatch):
    """缺省维度：结果现有已完成评估的 LLM 判分维度（非 LLM / 未完成不纳入）。

    mock 在 gRPC 层（模拟 evaluation_service 真实条目形状），走真实 ACL 映射
    （INT-822 审计 P1 回归：dimension_id 透传）。
    """
    from task_service.infrastructure.acl.evaluation_config_acl_repository import (
        evaluation_config_acl_repository,
    )
    from task_service.infrastructure.persistence.ai_review_repository import (
        ai_review_repository,
    )
    _task_id, result_id, _ = _seed_task()
    _mock_dimension_results_grpc(monkeypatch, {result_id: [
        {'dimension_id': 7, 'evaluation_status': 'completed'},
        {'dimension_id': 8, 'evaluation_status': 'failed'},      # 未完成不纳入
        {'dimension_id': 9, 'evaluation_status': 'completed'},   # 非 LLM 不纳入
    ]})
    monkeypatch.setattr(evaluation_config_acl_repository, 'list_llm_judge_dimension_ids',
                        lambda: [7, 8])
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch)

    resp = _llm_service().initiate_review({'result_ids': [result_id]})
    assert resp['success'] is True, resp
    items = resp['data']['items']
    assert len(items) == 1
    assert items[0]['dimension_id'] == 7
    got = ai_review_repository.get(items[0]['id'])
    assert got['verdict'] == 'passed'
    assert got['status'] == 'completed'


def test_initiate_default_no_llm_dim_skipped(db, monkeypatch):
    """缺省维度：结果无已完成 LLM 判分维度 → 该结果不可发起。"""
    from task_service.infrastructure.acl.evaluation_config_acl_repository import (
        evaluation_config_acl_repository,
    )
    _task_id, result_id, _ = _seed_task()
    _mock_dimension_results_grpc(monkeypatch, {result_id: [
        {'dimension_id': 9, 'evaluation_status': 'completed'},
    ]})
    monkeypatch.setattr(evaluation_config_acl_repository, 'list_llm_judge_dimension_ids',
                        lambda: [7])
    _sync_executor(monkeypatch)
    _mock_llm(monkeypatch)

    resp = _llm_service().initiate_review({'result_ids': [result_id]})
    assert resp['success'] is False
    assert resp['data']['skipped'][0]['message'].startswith('结果无已完成评估的 LLM')


def test_initiate_execution_failed_marks_failed(db, monkeypatch):
    """异步执行失败：status=failed 不落判定（重试=force 再发）。"""
    from task_service.infrastructure.persistence.ai_review_repository import (
        ai_review_repository,
    )
    task_id, result_id, _ = _seed_task()
    _sync_executor(monkeypatch)
    _mock_llm_fail(monkeypatch)

    resp = _llm_service().initiate_review({
        'result_ids': [result_id], 'dimension_ids': [7],
    })
    assert resp['success'] is True, resp
    item = resp['data']['items'][0]
    assert item['status'] == 'running'  # 发起快照；执行失败写回落库状态
    got = ai_review_repository.get(item['id'])
    assert got['status'] == 'failed'
    assert got['verdict'] is None


# ==================== 采纳 ====================

def test_adopt_reuses_apply_review(db):
    """采纳：复用 apply_review 落 test_result_reviews 留痕 + TestResult 改判 + 记录置 adopted。"""
    from task_service.infrastructure.persistence.review_repository import review_repository
    from task_service.infrastructure.persistence.test_result_repository import (
        test_result_repository,
    )
    from task_service.infrastructure.persistence.task_repository import task_repository

    task_id, result_id, case_id = _seed_task(exec_status='failed', eval_status='completed')
    rec = _seed_ai_review(result_id, task_id, dimension_id=7,
                          status='completed', verdict='passed')
    set_current_user_id(42)

    resp = _llm_service().adopt_review(rec['id'], {
        'execution_status': 'completed', 'comment': '人工确认采纳 AI 结论',
    })
    assert resp['success'] is True, resp
    data = resp['data']
    assert data['applied'][0]['field_name'] == 'execution_status'
    # 记录置 adopted
    assert data['item']['adopted'] == 1
    assert data['item']['adopted_by_user_id'] == 42
    assert data['item']['adopted_at'] is not None
    assert data['item']['rejected'] == 0
    # 人工复核留痕落库（TestResult 改判 + 标记）
    result = test_result_repository.get_by_id(result_id)
    assert result['execution_status'] == 'completed'
    assert result['reviewed'] == 1
    assert result['reviewed_by_user_id'] == 42
    history = review_repository.review_history_by_task(task_id)
    assert len(history) == 1
    assert history[0]['old_value'] == 'failed'
    assert history[0]['new_value'] == 'completed'
    assert history[0]['comment'] == '人工确认采纳 AI 结论'
    # 统计重算（completed_cases/failed_cases）
    task = task_repository.get_task_dict_by_id(task_id)
    assert task['completed_cases'] == 1
    assert task['failed_cases'] == 0


def test_adopt_requires_completed_and_unhandled(db):
    """采纳前置：status=completed 且未处置，否则拒绝。"""
    task_id, result_id, _ = _seed_task()
    # running
    rec_running = _seed_ai_review(result_id, task_id, status='running')
    resp = _llm_service().adopt_review(rec_running['id'], {
        'execution_status': 'completed', 'comment': 'x'})
    assert resp['success'] is False
    assert '未完成' in resp['message']
    # 已采纳
    rec_adopted = _seed_ai_review(result_id, task_id, dimension_id=8,
                                  status='completed', adopted=1)
    resp = _llm_service().adopt_review(rec_adopted['id'], {
        'execution_status': 'completed', 'comment': 'x'})
    assert resp['success'] is False
    assert '已处置' in resp['message']
    # 已驳回
    rec_rejected = _seed_ai_review(result_id, task_id, dimension_id=9,
                                   status='completed', rejected=1)
    resp = _llm_service().adopt_review(rec_rejected['id'], {
        'execution_status': 'completed', 'comment': 'x'})
    assert resp['success'] is False
    assert '已处置' in resp['message']


def test_adopt_validation(db):
    """采纳准入：空备注 / 未设置状态 / 非法状态拒绝。"""
    task_id, result_id, _ = _seed_task()
    rec = _seed_ai_review(result_id, task_id)
    # 空备注
    resp = _llm_service().adopt_review(rec['id'], {'execution_status': 'completed', 'comment': '  '})
    assert resp['success'] is False
    assert '备注必填' in resp['message']
    # 未设置任何状态
    resp = _llm_service().adopt_review(rec['id'], {'comment': 'x'})
    assert resp['success'] is False
    assert '至少设置一项' in resp['message']
    # 非法执行状态
    resp = _llm_service().adopt_review(rec['id'], {'execution_status': 'pending', 'comment': 'x'})
    assert resp['success'] is False
    assert '不可改判' in resp['message']
    # 非法评估状态
    resp = _llm_service().adopt_review(rec['id'], {'evaluation_status': 'running', 'comment': 'x'})
    assert resp['success'] is False
    assert '不可改判' in resp['message']
    # 记录不存在
    resp = _llm_service().adopt_review(999999, {'execution_status': 'completed', 'comment': 'x'})
    assert resp['success'] is False
    assert resp['data']['code'] == 404


def test_adopt_non_terminal_task_rejected(db):
    """采纳准入：任务未到终态禁止复核。"""
    task_id, result_id, _ = _seed_task(status='running')
    rec = _seed_ai_review(result_id, task_id, status='completed')
    resp = _llm_service().adopt_review(rec['id'], {
        'execution_status': 'completed', 'comment': 'x'})
    assert resp['success'] is False
    assert '未到终态' in resp['message']


def test_adopt_evaluation_status_syncs_trd(db, monkeypatch):
    """采纳评估状态改判：本地落库 + 经 evaluation_service gRPC 联动（TRD 改判）。"""
    from task_service.infrastructure.persistence.task_repository import task_repository

    task_id, result_id, _ = _seed_task(exec_status='completed', eval_status='pending',
                                       case_status='evaluating')
    rec = _seed_ai_review(result_id, task_id, status='completed', verdict='passed')
    captured = {}
    from task_service.application.task.ai_review_service import AiReviewService
    monkeypatch.setattr(AiReviewService, '_sync_dimension_review_status',
                        staticmethod(lambda rids, eval_status: captured.update(
                            {'result_ids': rids, 'eval_status': eval_status})))

    set_current_user_id(7)
    resp = _llm_service().adopt_review(rec['id'], {
        'evaluation_status': 'completed', 'comment': '采纳 AI 评估通过'})
    assert resp['success'] is True, resp
    assert captured['result_ids'] == [result_id]
    assert captured['eval_status'] == 'completed'
    # TaskCase 评估状态联动
    tcs = task_repository.get_task_case_dicts(task_id)
    assert tcs[0]['evaluation_status'] == 'completed'
    assert tcs[0]['status'] == 'completed'


# ==================== 驳回 ====================

def test_reject_marks_rejected(db):
    """驳回：置 rejected/rejected_by/rejected_at，原判定不变。"""
    task_id, result_id, _ = _seed_task()
    rec = _seed_ai_review(result_id, task_id, verdict='passed', confidence=0.9)
    set_current_user_id(9)

    resp = _llm_service().reject_review(rec['id'])
    assert resp['success'] is True, resp
    data = resp['data']
    assert data['rejected'] == 1
    assert data['rejected_by_user_id'] == 9
    assert data['rejected_at'] is not None
    assert data['adopted'] == 0
    # 原判定不变
    assert data['verdict'] == 'passed'
    assert data['confidence'] == 0.9


def test_reject_idempotent_and_adopted_rejected(db):
    """驳回幂等：已驳回重复驳回返回现状；已采纳不可驳回。"""
    task_id, result_id, _ = _seed_task()
    rec = _seed_ai_review(result_id, task_id, rejected=1)
    resp = _llm_service().reject_review(rec['id'])
    assert resp['success'] is True
    assert resp['data']['rejected'] == 1

    rec2 = _seed_ai_review(result_id, task_id, dimension_id=8, adopted=1)
    resp = _llm_service().reject_review(rec2['id'])
    assert resp['success'] is False
    assert '已采纳' in resp['message']

    resp = _llm_service().reject_review(999999)
    assert resp['success'] is False
    assert resp['data']['code'] == 404


# ==================== 历史（审计） ====================

def test_review_history_filters(db):
    """AI 复核历史：时间倒序 + result_id/dimension_id/status 过滤。"""
    task_id, result_id, _ = _seed_task()
    r1 = _seed_ai_review(result_id, task_id, dimension_id=7, status='completed', verdict='passed')
    r2 = _seed_ai_review(result_id, task_id, dimension_id=8, status='failed', verdict=None)
    r3 = _seed_ai_review(result_id, task_id, dimension_id=9, status='completed', verdict='uncertain')

    # 全量倒序（最近优先，id 倒序）
    all_rows = _llm_service().review_history(task_id)['data']['items']
    assert [r['id'] for r in all_rows] == [r3['id'], r2['id'], r1['id']]
    assert len(all_rows) == 3
    # status 过滤
    comp = _llm_service().review_history(task_id, {'status': 'completed'})['data']['items']
    assert len(comp) == 2
    # dimension_id 过滤
    dim8 = _llm_service().review_history(task_id, {'dimension_id': 8})['data']['items']
    assert len(dim8) == 1
    assert dim8[0]['id'] == r2['id']
    # result_id 过滤（其他任务不出现）
    assert _llm_service().review_history(999999)['data']['items'] == []


# ==================== 回归：人工复核不受 AI 记录影响 ====================

def test_ai_review_does_not_affect_manual_review_counts(db, monkeypatch):
    """回归：人工复核计数/历史/标记不受 AI 记录影响（review-count/history/reviewed_result_ids 不变）。"""
    from task_service.infrastructure.persistence.review_repository import review_repository

    task_id, result_id, _ = _seed_task()
    # 人工复核 1 条（先复核）
    set_current_user_id(42)
    _review_service().submit_review({
        'result_ids': [result_id], 'execution_status': 'completed', 'comment': '人工复核'})
    # AI 复核记录若干条（含 adopted/rejected/running）
    _seed_ai_review(result_id, task_id, dimension_id=7, status='completed', verdict='passed')
    _seed_ai_review(result_id, task_id, dimension_id=8, status='completed', verdict='failed', adopted=1)
    _seed_ai_review(result_id, task_id, dimension_id=9, status='running')
    _seed_ai_review(result_id, task_id, dimension_id=10, status='failed')
    _seed_ai_review(result_id, task_id, dimension_id=11, status='completed', verdict='uncertain', rejected=1)

    # 人工复核计数/历史/标记与仅人工复核时一致
    assert _review_service().review_count(task_id)['data']['review_count'] == 1
    assert len(review_repository.review_history_by_task(task_id)) == 1
    assert review_repository.reviewed_result_ids(task_id) == {result_id}
    history = review_repository.review_history_by_result(result_id)
    assert len(history) == 1
    assert history[0]['created_by_user_id'] == 42
