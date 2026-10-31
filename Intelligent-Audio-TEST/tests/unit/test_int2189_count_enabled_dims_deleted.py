# -*- coding: utf-8 -*-
"""INT-2189 返工回归：预期维度数必须与评估链路加载器同口径（排除软删维度）。

缺陷链路（测试工程师用事故同批数据复现）：
- 用例 config 的 `rounds[].evaluation.dimensions` 引用维度 [133,134,135]；
- 134/135 已软删（deleted=t，status 仍为 t）；
- 加载器 `list_active_dimensions_by_ids` 过滤 deleted+status → 只加载 [133]，
  只产 1 条 TestResultDimension；
- 但收口侧的 `_count_enabled_dimensions` 只过滤 status、不过滤 deleted → 预期 3；
- 于是永久停在「维度未全 (1/3)，继续等待」，且该结果不会再有第二次触发，
  TaskCase 卡 evaluating、任务忙等到超时判 failed。

本文件守的不变量：
1. `_count_enabled_dimensions` 与加载器 `list_active_dimensions_by_ids` 对同一
   ID 集合给出相同数量（软删/禁用都不计入）；
2. `_get_expected_dim_count` 对「config 引用但被加载器过滤」的维度不计入预期；
3. 修复后收口检查不再误判「维度未全」，用例可按已加载维度正常收敛。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2189dims_') + '/dims.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace  # noqa: E402
from unittest import mock  # noqa: E402

import pytest  # noqa: E402

from shared.models.database import Base, get_engine, get_db_session, init_db, remove_db_session  # noqa: E402

# 事故数据的等价 ID（用高段避免与同进程其它用例的自增主键撞号）
DIM_ACTIVE = 9133
DIM_DELETED_A = 9134
DIM_DELETED_B = 9135
DIM_DISABLED = 9136


def _current_session():
    return get_db_session()()


@pytest.fixture(scope='module', autouse=True)
def _schema():
    init_db()
    from evaluation_service.infrastructure.persistence.orm_models import (
        Category, Dimension, TestResultDimension,
    )
    Base.metadata.create_all(get_engine(), tables=[
        Category.__table__, Dimension.__table__, TestResultDimension.__table__,
    ])
    yield


@pytest.fixture(autouse=True)
def _clean_session():
    remove_db_session()
    yield
    sess = _current_session()
    try:
        sess.rollback()
    finally:
        remove_db_session()


def _seed_dimensions():
    """插入 1 条启用维度 + 2 条软删维度 + 1 条禁用维度（status 与 deleted 正交）。

    幂等：同文件内多个用例都会调用，按显式主键 merge。
    """
    from evaluation_service.infrastructure.persistence.orm_models import Dimension
    sess = _current_session()
    rows = [
        dict(id=DIM_ACTIVE, name='接线测试_启用维度', status=True, deleted=False),
        dict(id=DIM_DELETED_A, name='接线测试_软删维度A', status=True, deleted=True),
        dict(id=DIM_DELETED_B, name='接线测试_软删维度B', status=True, deleted=True),
        dict(id=DIM_DISABLED, name='接线测试_禁用维度', status=False, deleted=False),
    ]
    for row in rows:
        sess.merge(Dimension(
            id=row['id'], name=row['name'], type='auto', result_type=1,
            visibility='shared', status=row['status'], deleted=row['deleted'],
        ))
    sess.commit()


def _make_processor():
    from evaluation_service.domain.services.evaluation_logger import EvaluationLoggerMixin
    from evaluation_service.infrastructure.persistence._result_status_mixin import (
        ResultStatusMixin,
    )

    class _Proc(EvaluationLoggerMixin, ResultStatusMixin):
        pass

    return _Proc()


class TestCountEnabledDimensions:
    def test_excludes_soft_deleted_and_disabled(self):
        """[133,134,135] → 只有 1（134/135 已软删），再叠加禁用维度仍是 1。"""
        _seed_dimensions()
        proc = _make_processor()

        assert proc._count_enabled_dimensions([DIM_ACTIVE, DIM_DELETED_A, DIM_DELETED_B]) == 1
        assert proc._count_enabled_dimensions(
            [DIM_ACTIVE, DIM_DELETED_A, DIM_DELETED_B, DIM_DISABLED]) == 1

    def test_matches_loader_active_dimensions(self):
        """与评估链路加载器同口径：同一 ID 集合上数量完全一致。"""
        from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
            EvaluationDimensionRepository,
        )

        _seed_dimensions()
        ids = [DIM_ACTIVE, DIM_DELETED_A, DIM_DELETED_B, DIM_DISABLED]

        expected = _make_processor()._count_enabled_dimensions(ids)
        loaded = len(EvaluationDimensionRepository().list_active_dimensions_by_ids(ids))

        assert expected == loaded == 1


class TestExpectedDimCount:
    def test_config_refs_to_deleted_dims_are_not_counted(self):
        """config 引用 [133,134,135]、其中两条软删 → 预期维度数 = 1 而非 3。"""
        from evaluation_service.infrastructure.persistence import (
            _result_status_mixin as m,
        )

        _seed_dimensions()
        config = {
            'rounds': [{
                'evaluation': {'dimensions': [
                    {'id': DIM_ACTIVE}, {'id': DIM_DELETED_A}, {'id': DIM_DELETED_B},
                ]},
            }],
        }
        with mock.patch.object(m, 'task_acl_repository') as repo:
            repo.get_test_case_detail.return_value = SimpleNamespace(config=config)
            assert _make_processor()._get_expected_dim_count('case-1') == 1


class TestConvergesAfterDeletedExcluded:
    def test_case_finishes_when_loaded_dims_match_expected(self):
        """加载器只产 1 条维度行、预期也为 1 → 不再卡「维度未全」，用例收敛。"""
        from evaluation_service.infrastructure.persistence.orm_models import (
            TestResultDimension,
        )

        _seed_dimensions()
        result_id = 9189
        sess = _current_session()
        sess.query(TestResultDimension).filter(
            TestResultDimension.test_result_id == result_id).delete(
            synchronize_session=False)
        sess.add(TestResultDimension(
            id=9189001,  # sqlite 下 BigInteger 主键不自增，显式给值
            test_result_id=result_id,
            dimension_id=DIM_ACTIVE,
            evaluation_status='completed',
            status='passed',
        ))
        sess.commit()

        proc = _make_processor()
        expected = proc._count_enabled_dimensions(
            [DIM_ACTIVE, DIM_DELETED_A, DIM_DELETED_B])
        case_all_finished, case_any_failed, failed_reasons = \
            proc._check_all_results_completed_by_count(
                task_id=1, test_case_id='case-1', expected_count=1,
                expected_dim_count=expected,
                all_results=[SimpleNamespace(id=result_id)],
            )

        assert case_all_finished is True
        assert case_any_failed is False
        assert failed_reasons == []

        # 收尾：清掉本用例写入的行
        sess = _current_session()
        sess.query(TestResultDimension).filter(
            TestResultDimension.test_result_id == result_id).delete(
            synchronize_session=False)
        sess.commit()
