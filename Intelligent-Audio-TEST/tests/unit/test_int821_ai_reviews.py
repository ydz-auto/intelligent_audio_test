# -*- coding: utf-8 -*-
"""INT-821 专项：ai_reviews 数据模型 + AiReviewRepository CRUD。

覆盖（对齐契约定稿 + INT-800 幂等复用语义）：
- create：发起一条 AI 复核记录，默认 status='pending' / adopted=0 / rejected=0
- get / list_by_task / list_by_result / latest_by_result_dimension 读
  （latest 区分整体评估 dimension_id=NULL 与维度级，幂等复用最近一次结论）
- update_status / update_verdict：复核任务状态与 AI 判定结论落库
- adopt / reject：人工采纳 / 驳回标记（字段级落库，业务编排在 #2）
- delete：物理删除

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int340 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from task_service.infrastructure.persistence.models import AiReview
from task_service.infrastructure.persistence.ai_review_repository import (
    ai_review_repository,
)

_TABLES = None


def _ensure_tables():
    global _TABLES
    if _TABLES is None:
        init_db(pool_size=2)
        _TABLES = [AiReview.__table__]
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


def _seed(result_id=101, task_id=201, test_case_id='INT821-C1',
          dimension_id=None, status='pending', verdict=None,
          confidence=None, reasoning=None):
    """种子：发起一条 AI 复核记录，返回 record dict（含 id）。"""
    return ai_review_repository.create(
        result_id=result_id, task_id=task_id, test_case_id=test_case_id,
        dimension_id=dimension_id, status=status, verdict=verdict,
        confidence=confidence, reasoning=reasoning,
    )


# ==================== create ====================

def test_create_defaults(db):
    """发起默认记录：status=pending、adopted/rejected=0、verdict/confidence 为空。"""
    rec = _seed()
    assert rec['id'] > 0
    assert rec['result_id'] == 101
    assert rec['task_id'] == 201
    assert rec['test_case_id'] == 'INT821-C1'
    assert rec['dimension_id'] is None
    assert rec['status'] == 'pending'
    assert rec['verdict'] is None
    assert rec['confidence'] is None
    assert rec['adopted'] == 0
    assert rec['rejected'] == 0
    assert rec['created_at'] is not None
    # 契约 updated_at 列允许 NULL；ORM 侧随 default/onupdate 维护时间戳
    assert rec['updated_at'] is not None


def test_create_with_full_fields(db):
    """发起带 AI 判定结论：verdict/confidence/reasoning/dimension_id 落库。"""
    rec = _seed(dimension_id=7, status='completed', verdict='passed',
                confidence=0.92, reasoning='置信度达标')
    assert rec['dimension_id'] == 7
    assert rec['status'] == 'completed'
    assert rec['verdict'] == 'passed'
    assert rec['confidence'] == 0.92
    assert rec['reasoning'] == '置信度达标'


# ==================== read ====================

def test_get_and_get_missing(db):
    """get 读单条；不存在返回 None。"""
    rec = _seed()
    got = ai_review_repository.get(rec['id'])
    assert got == rec
    assert ai_review_repository.get(999999) is None


def test_list_by_task(db):
    """按任务读：仅返回该任务记录，倒序最近优先。"""
    r1 = _seed(result_id=1, task_id=201)
    r2 = _seed(result_id=2, task_id=201)
    _seed(result_id=3, task_id=202)  # 其他任务
    rows = ai_review_repository.list_by_task(201)
    assert len(rows) == 2
    # created_at 同秒时按 id 倒序
    assert [r['id'] for r in rows] == [r2['id'], r1['id']]


def test_list_by_result(db):
    """按结果读：多次发起追加历史不覆盖。"""
    _seed(result_id=301, task_id=201)
    _seed(result_id=301, task_id=201)
    _seed(result_id=302, task_id=201)
    rows = ai_review_repository.list_by_result(301)
    assert len(rows) == 2
    assert {r['result_id'] for r in rows} == {301}


def test_latest_by_result_dimension(db):
    """幂等复用查询：同结果同维度取最近一次；整体评估与维度级互不视为重复。"""
    _seed(result_id=401, task_id=201, verdict='failed')                    # 整体评估 1
    _seed(result_id=401, task_id=201, verdict='passed', confidence=0.9)    # 整体评估 2（最近）
    _seed(result_id=401, task_id=201, dimension_id=7, verdict='uncertain')  # 维度级 1
    _seed(result_id=401, task_id=201, dimension_id=7, verdict='passed')    # 维度级 2（最近）

    whole = ai_review_repository.latest_by_result_dimension(401, None)
    assert whole['verdict'] == 'passed'
    assert whole['dimension_id'] is None

    dim = ai_review_repository.latest_by_result_dimension(401, 7)
    assert dim['verdict'] == 'passed'
    assert dim['dimension_id'] == 7

    assert ai_review_repository.latest_by_result_dimension(999, None) is None
    assert ai_review_repository.latest_by_result_dimension(999, 7) is None


# ==================== update ====================

def test_update_status(db):
    """复核任务状态流转：pending → running → completed。"""
    rec = _seed()
    assert ai_review_repository.update_status(rec['id'], 'running') is True
    assert ai_review_repository.update_status(rec['id'], 'completed') is True
    got = ai_review_repository.get(rec['id'])
    assert got['status'] == 'completed'
    assert got['updated_at'] is not None  # 更新时落 updated_at
    assert ai_review_repository.update_status(999999, 'running') is False


def test_update_verdict(db):
    """落 AI 判定结论：verdict + confidence + reasoning。"""
    rec = _seed()
    assert ai_review_repository.update_verdict(
        rec['id'], 'failed', confidence=0.35, reasoning='置信度不足') is True
    got = ai_review_repository.get(rec['id'])
    assert got['verdict'] == 'failed'
    assert got['confidence'] == 0.35
    assert got['reasoning'] == '置信度不足'
    assert got['updated_at'] is not None
    assert ai_review_repository.update_verdict(999999, 'failed') is False


def test_adopt(db):
    """采纳标记：adopted=1 + 操作人 + 采纳时间。"""
    rec = _seed()
    assert ai_review_repository.adopt(rec['id'], 42) is True
    got = ai_review_repository.get(rec['id'])
    assert got['adopted'] == 1
    assert got['adopted_by_user_id'] == 42
    assert got['adopted_at'] is not None
    assert got['rejected'] == 0
    assert ai_review_repository.adopt(999999, 42) is False


def test_reject(db):
    """驳回标记：rejected=1 + 操作人 + 驳回时间，原判定不变。"""
    rec = _seed(verdict='passed', confidence=0.8)
    assert ai_review_repository.reject(rec['id'], 7) is True
    got = ai_review_repository.get(rec['id'])
    assert got['rejected'] == 1
    assert got['rejected_by_user_id'] == 7
    assert got['rejected_at'] is not None
    assert got['verdict'] == 'passed'  # 驳回不改判定
    assert ai_review_repository.reject(999999, 7) is False


# ==================== delete ====================

def test_delete(db):
    """删除记录；不存在返回 False。"""
    rec = _seed()
    assert ai_review_repository.delete(rec['id']) is True
    assert ai_review_repository.get(rec['id']) is None
    assert ai_review_repository.delete(rec['id']) is False
