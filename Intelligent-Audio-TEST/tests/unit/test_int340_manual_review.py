# -*- coding: utf-8 -*-
"""INT-340 专项：测试结果人工复核（终态改判留痕 + 双状态联动 + 覆盖提醒计数）。

覆盖（对齐设计文档 §2/§3/§4/§5 + 负责人 2026-10-15 拍板）：
- 终态任务单条/批量复核：执行状态改判（completed/failed/stopped/skipped 全集）
  + 评估状态（completed/failed 双状态口径）+ 复核备注必填
- 留痕不覆盖：多次复核追加历史；TestResult reviewed 标记列 + 操作人/时间/原值/新值
- TaskCase 双状态联动 + 任务统计重算（completed_cases/failed_cases/total_cases）
- 覆盖提醒计数（review_count）与复核历史查询
- 非终态/非法状态/空备注拒绝

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int339 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./TEMP/int340_proc.db')

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
            Tag, TaskTag, TestCase, TestResult, TestResultReview, Log,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase, TestResult, TestResultReview, Log,
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


def _seed_task(name='INT340源任务', status='completed', case_status=None,
               exec_status='failed', eval_status='completed'):
    """种子：终态任务 + 1 用例 1 结果（执行失败 / 评估完成）。返回 (task_id, result_id, case_id)。"""
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult, TestCase
    session = get_db_session()
    try:
        task = Task(name=name, status=status, total_cases=1,
                    completed_cases=0, failed_cases=1, algorithm_type='asr')
        session.add(task)
        session.flush()
        case_id = 'INT340-C1'
        if session.query(TestCase).filter(TestCase.id == case_id).first() is None:
            session.add(TestCase(
                id=case_id, name='INT340用例', description='', config={},
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


# ==================== 执行状态改判 ====================

def test_review_execution_status_terminal(db):
    """终态任务执行状态改判 completed：TestResult/TaskCase/留痕/统计联动。"""
    from task_service.application.task.review_service import review_service
    from task_service.infrastructure.persistence.review_repository import review_repository
    from task_service.infrastructure.persistence.test_result_repository import test_result_repository

    task_id, result_id, case_id = _seed_task()
    set_current_user_id(42)

    resp = review_service.submit_review({
        'result_ids': [result_id],
        'execution_status': 'completed',
        'comment': '人工复核通过',
    })
    assert resp['success'] is True, resp
    assert resp['data']['reviewed'][0]['applied'][0] == {
        'field_name': 'execution_status', 'old_value': 'failed', 'new_value': 'completed'}

    # TestResult 状态与标记
    result = test_result_repository.get_by_id(result_id)
    assert result['execution_status'] == 'completed'
    assert result['reviewed'] == 1
    assert result['reviewed_by_user_id'] == 42
    assert result['last_review_comment'] == '人工复核通过'
    assert result['last_review_action'] == 'execution_status:failed→completed'

    # TaskCase 双状态联动（status 由 derive 重推）
    from task_service.infrastructure.persistence.task_repository import task_repository
    tcs = task_repository.get_task_case_dicts(task_id)
    assert tcs[0]['execution_status'] == 'completed'
    assert tcs[0]['status'] == 'completed'

    # 任务统计按复核后判定重算
    task = task_repository.get_task_dict_by_id(task_id)
    assert task['completed_cases'] == 1
    assert task['failed_cases'] == 0

    # 覆盖提醒计数
    count = review_service.review_count(task_id)
    assert count['data']['review_count'] == 1

    # 复核历史（留痕原值/新值/操作人）
    history = review_service.review_history(task_id)
    assert history['data']['items'][0]['old_value'] == 'failed'
    assert history['data']['items'][0]['new_value'] == 'completed'
    assert history['data']['items'][0]['created_by_user_id'] == 42
    assert history['data']['items'][0]['field_name'] == 'execution_status'


def test_review_skipped_execution_status(db):
    """执行状态改判 skipped（拍板全集）：TaskCase.status 落 skipped。"""
    from task_service.application.task.review_service import review_service
    from task_service.infrastructure.persistence.task_repository import task_repository

    task_id, result_id, case_id = _seed_task(exec_status='failed', eval_status='completed')
    set_current_user_id(1)

    resp = review_service.submit_review({
        'result_ids': [result_id],
        'execution_status': 'skipped',
        'comment': '用例跳过',
    })
    assert resp['success'] is True, resp
    tcs = task_repository.get_task_case_dicts(task_id)
    assert tcs[0]['execution_status'] == 'skipped'
    assert tcs[0]['status'] == 'skipped'
    # 统计：skipped 不计入 completed/failed
    task = task_repository.get_task_dict_by_id(task_id)
    assert task['completed_cases'] == 0
    assert task['failed_cases'] == 0


def test_review_rejects_non_terminal_task(db):
    """非终态任务禁止复核（执行中/评估中不允许）。"""
    from task_service.application.task.review_service import review_service

    task_id, result_id, _ = _seed_task(status='running')
    set_current_user_id(1)
    resp = review_service.submit_review({
        'result_ids': [result_id], 'execution_status': 'completed', 'comment': 'x'})
    assert resp['success'] is False
    assert '未到终态' in resp['message']


def test_review_rejects_invalid_status_and_empty_comment(db):
    """非法改判状态 / 空备注 / 未设置状态拒绝。"""
    from task_service.application.task.review_service import review_service

    _task_id, result_id, _ = _seed_task()
    set_current_user_id(1)
    # 非法执行状态（pending 禁止）
    assert review_service.submit_review({
        'result_ids': [result_id], 'execution_status': 'pending', 'comment': 'x'})['success'] is False
    # 空备注
    assert review_service.submit_review({
        'result_ids': [result_id], 'execution_status': 'completed', 'comment': '  '})['success'] is False
    # 未设置任何状态
    assert review_service.submit_review({
        'result_ids': [result_id], 'comment': 'x'})['success'] is False
    # 非法评估状态
    assert review_service.submit_review({
        'result_ids': [result_id], 'evaluation_status': 'running', 'comment': 'x'})['success'] is False


def test_review_appends_history_no_overwrite(db):
    """多次复核追加历史不覆盖（第二次改判后历史含两条，原值=第一次新值）。"""
    from task_service.application.task.review_service import review_service

    task_id, result_id, _ = _seed_task()
    set_current_user_id(42)
    review_service.submit_review({
        'result_ids': [result_id], 'execution_status': 'completed', 'comment': '第一次'})
    resp2 = review_service.submit_review({
        'result_ids': [result_id], 'execution_status': 'stopped', 'comment': '第二次改判'})
    assert resp2['success'] is True

    history = review_service.review_history(task_id)
    items = history['data']['items']
    assert len(items) == 2
    assert items[0]['old_value'] == 'failed'
    assert items[0]['new_value'] == 'completed'
    assert items[1]['old_value'] == 'completed'
    assert items[1]['new_value'] == 'stopped'


def test_review_batch_multiple_results(db):
    """批量复核：逐条留痕，任务统计合并重算。"""
    from task_service.application.task.review_service import review_service
    from task_service.infrastructure.persistence.task_repository import task_repository

    task_id, result_id1, _ = _seed_task()
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult, TestCase
    session = get_db_session()
    try:
        case_id2 = 'INT340-C2'
        if session.query(TestCase).filter(TestCase.id == case_id2).first() is None:
            session.add(TestCase(id=case_id2, name='INT340用例2', description='', config={}, algorithm_type='asr'))
        session.add(TaskCase(
            task_id=task_id, test_case_id=case_id2,
            status='failed', execution_status='failed', evaluation_status='completed',
            device_type='physical', device_id='8',
        ))
        r2 = TestResult(task_id=task_id, test_case_id=case_id2, device_id=8,
                        algorithm_type='asr', execution_status='failed',
                        algorithm_result={'asr_result': '文本2'})
        session.add(r2)
        session.flush()
        result_id2 = r2.id
        session.commit()
    finally:
        remove_db_session()

    set_current_user_id(7)
    resp = review_service.submit_review({
        'result_ids': [result_id1, result_id2],
        'execution_status': 'completed',
        'comment': '批量复核',
    })
    assert resp['success'] is True, resp
    assert resp['data']['review_count'] == 2
    task = task_repository.get_task_dict_by_id(task_id)
    assert task['completed_cases'] == 2
    assert task['failed_cases'] == 0


def test_review_evaluation_status_calls_evaluation_side(db, monkeypatch):
    """评估状态改判：本地落库 + 经 evaluation_service gRPC 联动（TRD 改判）。"""
    from task_service.application.task.review_service import review_service
    from task_service.infrastructure.persistence.task_repository import task_repository

    task_id, result_id, _ = _seed_task(exec_status='completed', eval_status='pending', case_status='evaluating')

    # 记录 gRPC 调用入参（monkeypatch ACL，对齐 test_int339 惯例）
    captured = {}
    def _fake_sync(result_ids, eval_status):
        captured['result_ids'] = result_ids
        captured['eval_status'] = eval_status
    monkeypatch.setattr('task_service.application.task.review_service.ReviewService._sync_dimension_review_status',
                        staticmethod(_fake_sync))

    set_current_user_id(42)
    resp = review_service.submit_review({
        'result_ids': [result_id],
        'evaluation_status': 'completed',
        'comment': '评估通过',
    })
    assert resp['success'] is True, resp
    assert captured['result_ids'] == [result_id]
    assert captured['eval_status'] == 'completed'

    # TaskCase 评估状态联动 + status 派生 completed
    tcs = task_repository.get_task_case_dicts(task_id)
    assert tcs[0]['evaluation_status'] == 'completed'
    assert tcs[0]['status'] == 'completed'


def test_review_no_change_same_value(db):
    """同值复核（状态无变化）拒绝：仅允许补备注不生效。"""
    from task_service.application.task.review_service import review_service

    task_id, result_id, _ = _seed_task(exec_status='failed', eval_status='completed')
    set_current_user_id(42)
    resp = review_service.submit_review({
        'result_ids': [result_id],
        'execution_status': 'failed',  # 与现值相同
        'comment': '补备注',
    })
    assert resp['success'] is False
    assert '无变化' in resp['message']
    # 复核计数仍为 0（未产生留痕）
    assert review_service.review_count(task_id)['data']['review_count'] == 0


def test_review_count_excludes_removed_results(db):
    """被删用例（excluded）的复核结果不计入覆盖提醒计数。"""
    from task_service.application.task.review_service import review_service
    from task_service.infrastructure.persistence.models import TestResult
    from shared.models.database import get_db_session

    task_id, result_id, _ = _seed_task()
    set_current_user_id(42)
    review_service.submit_review({
        'result_ids': [result_id], 'execution_status': 'completed', 'comment': '复核'})
    assert review_service.review_count(task_id)['data']['review_count'] == 1

    # 结果被删用例排除（INT-305）
    session = get_db_session()
    try:
        session.query(TestResult).filter(TestResult.id == result_id).update(
            {'excluded': 1}, synchronize_session=False)
        session.commit()
    finally:
        remove_db_session()
    assert review_service.review_count(task_id)['data']['review_count'] == 0


def test_gateway_get_one_passes_review_fields(db, monkeypatch):
    """网关任务详情 DTO 透传 review_count 与用例级 reviewed（P1-2 回归）。

    原缺陷：task_read_model_detail 已计算复核标记，但网关 TaskQueryService.get_one
    组装 TaskDetailData / TaskCaseBrief 时漏透传 → 覆盖提醒计数恒 0、用例「人工复核」
    标记不显示。本测试直测服务层 DTO 组装，防回归。
    """
    import api_gateway.application.services.task.task_query_service as tqs
    from api_gateway.application.services.task.task_query_service import TaskQueryService

    detail = {
        'id': 1,
        'name': 'INT340任务',
        'status': 'completed',
        'completed_cases': 0,
        'failed_cases': 1,
        'review_count': 2,
        'cases': [{
            'case_id': 'C1',
            'name': '用例1',
            'status': 'failed',
            'execution_status': 'failed',
            'evaluation_status': 'completed',
            'reviewed': True,
        }, {
            'case_id': 'C2',
            'name': '用例2',
            'status': 'completed',
            'execution_status': 'completed',
            'evaluation_status': 'completed',
            'reviewed': False,
        }],
    }
    monkeypatch.setattr(tqs._task_acl, 'get_task_detail', lambda task_id: {
        'success': True, 'data': detail})

    payload, http_code = TaskQueryService.get_one(1)
    assert http_code == 200
    data = payload['data']
    # 任务级复核计数透传（覆盖提醒）
    assert data['review_count'] == 2
    # 用例级复核标记透传（任务详情「人工复核」标记）
    assert data['cases'][0]['reviewed'] is True
    assert data['cases'][1]['reviewed'] is False


def test_gateway_get_one_null_review_fields_defaults(db, monkeypatch):
    """网关任务详情 DTO 对上游 null 复核字段容错（INT-734 回归）。

    原缺陷：DB 复核表无记录时上游透传 reviewed/review_count 为 null，
    网关非空 bool/int schema 校验失败 → GET /api/v1/tasks/{id} 全量 422。
    修复后：schema 放宽为 Optional，服务组装时缺省归一 False/0，
    响应恒为 bool/int（「未复核」语义），不再触发校验错误。
    """
    import api_gateway.application.services.task.task_query_service as tqs
    from api_gateway.application.services.task.task_query_service import TaskQueryService

    detail = {
        'id': 1,
        'name': 'INT734任务',
        'status': 'completed',
        'completed_cases': 0,
        'failed_cases': 1,
        'review_count': None,  # 复核表无记录 → 上游 null
        'cases': [{
            'case_id': 'C1',
            'name': '用例1',
            'status': 'failed',
            'execution_status': 'failed',
            'evaluation_status': 'completed',
            'reviewed': None,  # 复核表无记录 → 上游 null
        }],
    }
    monkeypatch.setattr(tqs._task_acl, 'get_task_detail', lambda task_id: {
        'success': True, 'data': detail})

    payload, http_code = TaskQueryService.get_one(1)
    assert http_code == 200
    data = payload['data']
    # 归一：review_count 恒为整数 0（验收：review_count 为整数）
    assert data['review_count'] == 0
    # 归一：用例级 reviewed 恒为 bool False（验收：reviewed 为 bool 或 null）
    assert data['cases'][0]['reviewed'] is False


def test_gateway_get_one_reviewed_none_ok(db, monkeypatch):
    """INT-755 回归：历史任务（reviewed 字段落地前创建）上游缺省/None 不得 422。

    常驻后端任务详情曾对全量任务返回 422
    （`reviewed: Input should be a valid boolean`）：
    TaskCaseBrief.reviewed 显式 bool 拒绝 None。修复后 schema 容错 Optional、
    网关归一 False，本测试直测服务层 DTO 组装，防回归。
    """
    import api_gateway.application.services.task.task_query_service as tqs
    from api_gateway.application.services.task.task_query_service import TaskQueryService

    detail = {
        'id': 1,
        'name': 'INT755任务',
        'status': 'completed',
        'completed_cases': 0,
        'failed_cases': 0,
        'review_count': 0,
        'cases': [{
            'case_id': 'C1',
            'name': '历史用例1',
            'status': 'completed',
            'execution_status': 'completed',
            'evaluation_status': 'completed',
            # reviewed 键缺失（字段落地前创建）——c.get('reviewed') → None
        }, {
            'case_id': 'C2',
            'name': '历史用例2',
            'status': 'failed',
            'execution_status': 'failed',
            'evaluation_status': 'completed',
            'reviewed': None,
        }],
    }
    monkeypatch.setattr(tqs._task_acl, 'get_task_detail', lambda task_id: {
        'success': True, 'data': detail})

    payload, http_code = TaskQueryService.get_one(1)
    assert http_code == 200
    data = payload['data']
    # 缺省/None 均归一 False，响应恒为 bool（不向前端泄漏 null）
    assert data['cases'][0]['reviewed'] is False
    assert data['cases'][1]['reviewed'] is False


def test_gateway_schemas_accept_null_review_fields():
    """网关响应 schema 对 null 复核字段不抛校验错误（INT-734 回归，schema 层直测）。

    原 422 的触发点：上游 null 传入非空 bool/int 字段 → ValidationError。
    放宽为 Optional 后 null 合法通过；字段缺省（未复核）时为 False/0。
    """
    from api_gateway.schemas.task import TaskCaseBrief, TaskDetailData

    # 显式 null 不抛校验错误（网关不再 422）
    case = TaskCaseBrief(case_id='C1', name='用例1', reviewed=None)
    assert case.reviewed is None
    detail = TaskDetailData(id=1, name='任务', status='completed', review_count=None)
    assert detail.review_count is None
    # 字段缺省（上游完全未提供）→ 缺省 False/0（未复核语义）
    assert TaskCaseBrief(case_id='C2', name='用例2').reviewed is False
    assert TaskDetailData(id=2, name='任务2', status='completed').review_count == 0

