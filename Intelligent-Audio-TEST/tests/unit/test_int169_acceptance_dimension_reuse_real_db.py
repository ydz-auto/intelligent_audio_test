# -*- coding: utf-8 -*-
"""INT-169 验收独立测试：幂等复用路径走真实 ORM PO + 真实 SQLite DB。

开发提测守卫（test_int169_dimension_score_id_and_eval_submit.py）的 recorder
部分基于 mock 仓储、_trd_po_to_entity 基于 SimpleNamespace 形状对象。本文件
补验收缺口：事故根因发生在「真实 ORM PO 从库里加载 → 转领域实体」一跳，
用真实 SQLAlchemy 引擎 + 真实 EvaluationDimensionRepository 复现并锁定：

1. find_score 返回的实体必须带持久化主键 id（原缺陷：实体无 id 必 AttributeError）；
2. 事故场景回放：round-0 评估响应经 per_round 覆盖已创建 round-1 TRD 行
   （completed）→ 对 round-1 重复提交 EvaluateCase → 幂等复用 + 按主键重置
   pending，不再崩，且只重置目标行；
3. 整体评估（round_number=None）重复提交：IS NULL 匹配 + 复用真实生效；
4. 无已有记录时真实 create_score_with_commit 落库返回真实主键。

数据卫生：全部写入进程内 sqlite://（StaticPool 内存库），不触共享库，
无 teardown 残留面。
"""
import os
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import evaluation_service.infrastructure.persistence.evaluation_dimension_repository as repo_mod
from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
    EvaluationDimensionRepository,
)
from evaluation_service.domain.services.evaluation_service.dimension_result_recorder import (
    DimensionResultRecorderMixin,
)
from shared.models.database import remove_db_session as _remove_db_session
from shared.utils.status_constants import EvaluationStatus

_remove_db_session()


def _trd_po_cls():
    from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
    return TestResultDimension


@pytest.fixture()
def real_trd_db(monkeypatch):
    """真实内存 SQLite 引擎 + 仅建 test_result_dimensions 表，get_db_session 指向它。

    SQLite 仅对 INTEGER PRIMARY KEY 做行ID别名自增（生产库 BIGINT 无此约束），
    故按表定义编译 DDL 后仅将 id 列替换为 INTEGER，其余列保持原样。
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.schema import CreateTable
    from shared.models.database import Base

    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    ddl = str(CreateTable(_trd_po_cls().__table__).compile(engine))
    ddl = ddl.replace('id BIGINT NOT NULL', 'id INTEGER NOT NULL', 1)
    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(repo_mod, 'get_db_session', factory)
    return factory


def _insert_trd(factory, **kwargs):
    TestResultDimension = _trd_po_cls()
    session = factory()
    try:
        po = TestResultDimension(**kwargs)
        session.add(po)
        session.commit()
        return po.id
    finally:
        session.close()


def _get_trd(factory, trd_id):
    TestResultDimension = _trd_po_cls()
    session = factory()
    try:
        po = session.get(TestResultDimension, trd_id)
        session.expunge(po)
        return po
    finally:
        session.close()


class _RecorderHost(DimensionResultRecorderMixin):
    """真实仓储注入的 recorder 宿主（algorithm_type 非 translation，不触 ACL）。"""

    def __init__(self):
        self._evaluation_dimension_repo = EvaluationDimensionRepository()
        self._task_acl_repo = MagicMock()
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


def _run_create(host, dim_id=7, result_id=99, round_number=1):
    return host._create_dimension_results(
        [{'id': dim_id, 'name': 'dim-a'}], result_id=result_id,
        task_id='t1', test_case_id='c1', algorithm_type='voice_llm',
        kwargs={'round_number': round_number},
    )


class TestFindScoreEntityCarriesPrimaryKey:
    """根因点：真实 PO → 实体转换必须回填 id。"""

    def test_find_score_returns_entity_with_id(self, real_trd_db):
        trd_id = _insert_trd(
            real_trd_db, test_result_id=99, dimension_id=7,
            algorithm_type='voice_llm', round_number=1,
            evaluation_status=EvaluationStatus.COMPLETED, score=0.85)
        repo = EvaluationDimensionRepository()

        entity = repo.find_score(99, 7, 1)

        assert entity is not None
        assert entity.id == trd_id
        assert entity.test_result_id == 99
        assert entity.dimension_id == 7
        assert entity.round_number == 1
        assert entity.evaluation_status == EvaluationStatus.COMPLETED

    def test_find_score_overall_round_matches_null(self, real_trd_db):
        """round_number=None 查询匹配 IS NULL（整体评估行）。"""
        trd_id = _insert_trd(
            real_trd_db, test_result_id=99, dimension_id=7,
            algorithm_type='voice_llm', round_number=None,
            evaluation_status=EvaluationStatus.FAILED, error_message='boom')
        repo = EvaluationDimensionRepository()

        entity = repo.find_score(99, 7, None)

        assert entity is not None
        assert entity.id == trd_id
        assert entity.round_number is None


class TestIncidentReplayRoundOneReuse:
    """INT-95 第 8 轮事故回放（真实 DB）：重复 EvaluateCase 不再 AttributeError。"""

    def test_round1_existing_completed_row_reused_and_reset(self, real_trd_db):
        # 事故前置态：round-0 评估响应经 per_round 覆盖已创建 round-1 行（completed）
        trd_id = _insert_trd(
            real_trd_db, test_result_id=99, dimension_id=7,
            algorithm_type='voice_llm', round_number=1,
            evaluation_status=EvaluationStatus.COMPLETED, score=0.85)

        host = _RecorderHost()
        result_map = _run_create(host, round_number=1)

        assert result_map == {7: trd_id}
        row = _get_trd(real_trd_db, trd_id)
        assert row.evaluation_status == EvaluationStatus.PENDING
        assert row.score is None
        assert row.error_message is None

    def test_repeat_submission_idempotent(self, real_trd_db):
        """同一 result 重复提交第二次：已 pending 行直接复用，主键不变。"""
        trd_id = _insert_trd(
            real_trd_db, test_result_id=99, dimension_id=7,
            algorithm_type='voice_llm', round_number=1,
            evaluation_status=EvaluationStatus.COMPLETED, score=0.85)
        host = _RecorderHost()

        first = _run_create(host, round_number=1)
        second = _run_create(host, round_number=1)

        assert first == second == {7: trd_id}
        row = _get_trd(real_trd_db, trd_id)
        assert row.evaluation_status == EvaluationStatus.PENDING

    def test_reset_only_touches_target_row(self, real_trd_db):
        """按主键重置不波及同 result 其他行（round-0 的既有分数必须保留）。"""
        round0_id = _insert_trd(
            real_trd_db, test_result_id=99, dimension_id=7,
            algorithm_type='voice_llm', round_number=0,
            evaluation_status=EvaluationStatus.COMPLETED, score=0.9)
        round1_id = _insert_trd(
            real_trd_db, test_result_id=99, dimension_id=7,
            algorithm_type='voice_llm', round_number=1,
            evaluation_status=EvaluationStatus.COMPLETED, score=0.85)

        host = _RecorderHost()
        result_map = _run_create(host, round_number=1)

        assert result_map == {7: round1_id}
        assert _get_trd(real_trd_db, round0_id).evaluation_status == EvaluationStatus.COMPLETED
        assert _get_trd(real_trd_db, round0_id).score == 0.9
        assert _get_trd(real_trd_db, round1_id).evaluation_status == EvaluationStatus.PENDING

    def test_overall_duplicate_submission_reused(self, real_trd_db):
        """整体评估（round_number=None）重复提交：复用整体行并重置。"""
        overall_id = _insert_trd(
            real_trd_db, test_result_id=99, dimension_id=12,
            algorithm_type='voice_llm', round_number=None,
            evaluation_status=EvaluationStatus.FAILED, error_message='boom')

        host = _RecorderHost()
        result_map = _run_create(host, dim_id=12, round_number=None)

        assert result_map == {12: overall_id}
        row = _get_trd(real_trd_db, overall_id)
        assert row.evaluation_status == EvaluationStatus.PENDING
        assert row.error_message is None


class TestFreshCreateRealPath:

    def test_no_existing_row_creates_with_real_id(self, real_trd_db):
        """无已有记录：真实 create_score_with_commit 落库，返回真实主键。"""
        host = _RecorderHost()

        result_map = _run_create(host, dim_id=8, round_number=1)

        new_id = result_map[8]
        row = _get_trd(real_trd_db, new_id)
        assert row.test_result_id == 99
        assert row.dimension_id == 8
        assert row.round_number == 1
        assert row.algorithm_type == 'voice_llm'
        assert row.evaluation_status == EvaluationStatus.PENDING
