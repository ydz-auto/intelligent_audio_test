# -*- coding: utf-8 -*-
"""INT-2285：E2E 用例未提交评估时收口评估终态，任务执行完成后必须收敛。

缺陷现场（INT-2228 设备矩阵 M4/M5）：用例 `f50b2c8c…` 配置
`rounds[0].evaluation = {enabled: false, dimensions: []}` 且无顶层 dimensions，
1 轮 2 段音频、devices 9/10/11 三行执行全部 completed 后任务长期 running：

- 轮次循环：`evaluation.enabled is False` → 不提交单轮评估；
- `_finalize_rounds`：`_has_round_dims/_has_overall_dims` 均 False → 不提交整体评估；
- `process_results` 多轮分支无条件写 `evaluation_status=pending`
  → `derive_task_case_status(completed, pending) = evaluating`
  → task_service 等待循环 `_has_evaluating_cases` 把 pending 计入活跃评估集合，
    任务永不收敛（只能人工 stop，同 SN 队列被占）。

修复：调用方按实际评估提交门控把 `evaluation_expected` 传给 `process_results`；
为 False（评测关闭 / 无维度）时评估永远不会回调，就地补写
`evaluation_status=completed`（与评估入口「无维度跳过」收尾口径一致）。
"""
import os
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

import shared.models.database as database
import e2e_test_service.application.services.e2e_executor.finalization_mixin as fin_mod
from e2e_test_service.application.services.e2e_executor.finalization_mixin import FinalizationMixin
from e2e_test_service.application.services.e2e_aggregator import E2EAggregator
from shared.models.database import Base, get_db_session
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskCaseStatus,
    FINISHED_CASE_STATUSES, ACTIVE_EVALUATION_STATUSES,
)
from shared.utils.status_utils import derive_task_case_status
from task_service.core.execution_engine.mixins.evaluation_arbiter import EvaluationArbiterMixin
from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin
from task_service.core.time_utils import utcnow
from task_service.infrastructure.persistence.models import Task, TaskCase


# ---------------- 执行链：evaluation_expected 由提交门控派生 ----------------

class _Host(FinalizationMixin):
    """最小宿主：聚合器与评估提交 mock，仅跑真实门控逻辑。"""

    def __init__(self):
        self._aggregator = MagicMock()
        self._aggregator.build_algorithm_result.return_value = {'rounds': [{'output': {}}]}
        self._aggregator.process_results.return_value = True
        self.eval_calls = []
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _handle_control(self, task_id):
        return None

    def _evaluate_result(self, **kwargs):
        self.eval_calls.append(kwargs)


_RUN_ARGS = dict(
    task_id='t1', tc_rel_id='tc1', data={}, case_name='接线测试_INT2032_C',
    algorithm_type='voice_llm', test_case_id='c1', result_ids={1: 99},
    all_round_results=[{'device_id': 1, 'round_number': 1, 'response_time': 100}],
    case_reference_params=None, last_adjusted_ref_params=None,
    device_info_list=[{'device_id': 1, 'device_sn': 'SN-A'}],
)


def _run(config):
    host = _Host()
    with patch.object(fin_mod, 'write_result_data_file', MagicMock(return_value=None)):
        host._finalize_rounds(case_config=config, execution_success=True, **_RUN_ARGS)
    assert len(host._aggregator.process_results.call_args_list) == 1
    return host._aggregator.process_results.call_args_list[0].kwargs


class TestEvaluationExpectedGate:

    def test_eval_disabled_round_no_overall_dims_not_expected(self):
        """缺陷现场配置（rounds[0].evaluation.enabled=False、无顶层维度）→ 不期待评估。"""
        kwargs = _run({'rounds': [{'round_number': 1, 'audios': [],
                                   'evaluation': {'enabled': False, 'dimensions': []}}]})
        assert kwargs['evaluation_expected'] is False

    def test_no_dims_anywhere_not_expected(self):
        kwargs = _run({'rounds': [{'round_number': 1, 'audios': []}]})
        assert kwargs['evaluation_expected'] is False

    def test_round_dims_expected(self):
        """逐轮评估维度存在 → 轮次循环会提交评估，等待评估回调。"""
        kwargs = _run({'rounds': [{'round_number': 1, 'audios': [],
                                   'evaluation': {'enabled': True, 'dimensions': [{'id': 1}]}}]})
        assert kwargs['evaluation_expected'] is True

    def test_overall_dims_expected(self):
        kwargs = _run({'rounds': [{'round_number': 1, 'audios': []}],
                       'dimensions': [{'id': 7}]})
        assert kwargs['evaluation_expected'] is True


# ---------------- 聚合器：按 evaluation_expected 写评估终态 ----------------

class TestProcessResultsNoEvaluationConvergence:

    def _aggregator(self):
        executor = MagicMock()
        executor._log = MagicMock()
        agg = E2EAggregator(executor)
        agg._task_data_repo = MagicMock()
        agg._task_data_repo.get_task_case_by_ids.return_value = [MagicMock()]
        return agg

    def _process(self, **kwargs):
        agg = self._aggregator()
        with patch('shared.utils.redis_pubsub.EventBus'):
            agg.process_results(
                't1', '接线测试_INT2032_C', 101, 'c1',
                [{'device_id': 1, 'round_number': 1,
                  'raw_results': {'success': True, 'device_id': 1}}],
                precreated_result_id=11, precomputed_execution_success=True,
                **kwargs,
            )
        return agg._task_data_repo.update_task_case_status.call_args_list[-1].kwargs

    def test_no_evaluation_writes_terminal_evaluation_status(self):
        """评测关闭 / 无维度：多轮收口就地写 evaluation_status=completed、status=completed。"""
        written = self._process(evaluation_expected=False)
        assert written['execution_status'] == ExecutionStatus.COMPLETED
        assert written['evaluation_status'] == EvaluationStatus.COMPLETED
        assert written['status'] == TaskCaseStatus.COMPLETED

    def test_terminal_values_satisfy_task_convergence(self):
        """写入值必须同时满足 task_service 收敛判定：终态 status 且不在活跃评估集合。"""
        written = self._process(evaluation_expected=False)
        assert written['status'] in FINISHED_CASE_STATUSES
        assert written['evaluation_status'] not in ACTIVE_EVALUATION_STATUSES

    def test_evaluation_expected_keeps_pending(self):
        """评估会提交（默认口径）：维持 pending，等评估服务回调收口。"""
        written = self._process()
        assert written['evaluation_status'] == EvaluationStatus.PENDING
        assert written['status'] == TaskCaseStatus.EVALUATING

    def test_execution_failure_unaffected(self):
        """执行失败分支不变：评估状态写 failed，不因新参数改变。"""
        agg = self._aggregator()
        with patch('shared.utils.redis_pubsub.EventBus'):
            agg.process_results(
                't1', 'c', 101, 'c1',
                [{'device_id': 1, 'round_number': 1,
                  'raw_results': {'success': False, 'device_id': 1}}],
                precreated_result_id=11, precomputed_execution_success=False,
                evaluation_expected=False,
            )
        written = agg._task_data_repo.update_task_case_status.call_args_list[-1].kwargs
        assert written['execution_status'] == ExecutionStatus.FAILED
        assert written['evaluation_status'] == EvaluationStatus.FAILED


# ---------------- task_service 收敛判定：真实引擎方法 + sqlite ----------------

_TABLES = [Task.__table__, TaskCase.__table__]


class _WaitHost(TaskFinalizeMixin, EvaluationArbiterMixin):
    """等待循环所需的最小引擎属性面（与 ExecutionEngine 同构，只跑收敛判定）。"""

    def __init__(self):
        self.test_case_wait_time = 3600       # 收敛路径不应触发超时
        self.wait_initial_interval = 0.1
        self.wait_max_interval = 0.2
        self.evaluation_hang_timeout = 3600   # 收敛路径不应触发仲裁
        self.task_wait_states = {}
        self.task_completion_events = {}
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _emit_progress(self, task=None):
        pass

    def _emit_alert(self, task_id, message, level='error'):
        pass

    def refresh_task_counts_atomic(self, task_id):
        pass


def _seed(task_id, exec_status, eval_status):
    session = get_db_session()
    try:
        session.add(Task(id=task_id, name=f'接线测试_{task_id}', status='running',
                         deleted=False, started_at=utcnow()))
        for device_id in (9, 10, 11):
            session.add(TaskCase(
                task_id=task_id, test_case_id='f50b2c8c', device_type='physical',
                device_id=str(device_id),
                execution_status=exec_status,
                evaluation_status=eval_status,
                status=derive_task_case_status(exec_status, eval_status),
            ))
        session.commit()
    finally:
        session.close()


def _db_task_status(task_id):
    session = get_db_session()
    try:
        return session.get(Task, task_id).status
    finally:
        session.close()


@pytest.fixture()
def task_db(monkeypatch):
    """独立 sqlite 库 + 会话工厂（对齐 test_int2231 口径，测试后还原不污染他例）。"""
    dbfile = os.path.join(tempfile.mkdtemp(prefix='int2285_'), 'int2285.db')
    engine = create_engine(f'sqlite:///{dbfile}')
    Base.metadata.create_all(bind=engine, tables=_TABLES)
    factory = sessionmaker(bind=engine)
    scoped = scoped_session(factory, scopefunc=threading.get_ident)
    monkeypatch.setattr(database, '_SessionFactory', factory)
    monkeypatch.setattr(database, '_scoped_session', scoped)

    created = []
    yield created

    scoped.close()
    engine.dispose()


class TestTaskConvergencePredicate:
    """引擎侧收敛判定与聚合器写入值对齐（缺陷方向 / 修复方向各一条）。"""

    def test_evaluation_pending_keeps_task_running(self, task_db):
        """缺陷现场：exec=completed 但 eval=pending → status=evaluating，任务不收敛。"""
        task_id = 2285001
        task_db.append(task_id)
        _seed(task_id, ExecutionStatus.COMPLETED, EvaluationStatus.PENDING)

        host = _WaitHost()
        host._update_post_loop_status(task_id)
        assert _db_task_status(task_id) == 'running'

        host.test_case_wait_time = 1.5      # 等待超时上限压到 1.5s
        started = time.time()
        host._wait_for_cases_completion(task_id, None, threading.Event())
        assert time.time() - started >= 1.5
        assert _db_task_status(task_id) == 'running', '修复前：等待循环超时退出，任务仍 running'

    def test_evaluation_completed_converges_task(self, task_db):
        """修复后写入 completed/completed → 任务立即收敛 completed，不再空转等待。"""
        task_id = 2285002
        task_db.append(task_id)
        _seed(task_id, ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED)

        host = _WaitHost()
        host._update_post_loop_status(task_id)
        assert _db_task_status(task_id) == 'completed'

        started = time.time()
        host._wait_for_cases_completion(task_id, None, threading.Event())
        assert time.time() - started < 1.0, '已收敛任务不得再进入等待循环'
        assert not any('超时' in str(item.get('content', '')) for item in host.logs)
