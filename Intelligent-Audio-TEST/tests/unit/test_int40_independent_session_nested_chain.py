# -*- coding: utf-8 -*-
"""INT-40 守卫：引擎嵌套执行链路必须用独立 Session，不得 close 线程共享 scoped_session。

原缺陷：SQLAlchemy 线程级 scoped_session 在同一线程内共享同一个 Session。
引擎主循环经 get_db_session() 加载 Task ORM 对象后，嵌套调用链
_execute_api_case 内部再次 get_db_session() 拿到同一个 session 并在 finally
中 close()——Session.close() 会 expunge 全部实例，主循环仍持有的 Task 对象
就此脱管；该对象已被链路中的 commit 过期（expire_on_commit=True），后续
_emit_progress(task) 访问 task.id 即抛 DetachedInstanceError → 引擎线程
异常退出 → 任务异常终态 failed。

修复：shared.models.database 新增 create_db_session()（sessionmaker 新实例，
非线程 scoped_session），嵌套链路 close 自己的会话不影响外层；同模式隐患点
一并治理：
- case_execution._execute_api_case 两个 DB 块 → 独立 Session（主链路根因）；
- task_control._check_queue → 独立 Session（被 control_task 嵌套调用，
  外层持有 Task 对象）；
- scheduler._schedule_pending_tasks → 循环抽取 (id, type) 纯数据，
  不跨 start_task（内部会 close 共享 session 并 commit）持有 ORM 对象。

本文件覆盖（真实 SQLAlchemy session 语义 + sqlite 文件库，不触 gRPC/Postgres）：
- 机制锁：_execute_api_case 不得调用 get_db_session（任何调用即回归），
  独立 Session 用后必须 close。
- 行为锁：外层 scoped session 持有并已过期的 Task，经 _execute_api_case
  嵌套调用后仍 attached、属性可刷新（缺陷版本此处必抛 DetachedInstanceError）。
- 行为锁：_check_queue 嵌套调用不 expunge 外层会话上的对象。
- 行为锁：_schedule_pending_tasks 在 start_task 关闭共享 session 的情形下
  仍能完成整轮调度（不再持有 ORM 对象跨调用）。

真实 Postgres + 进程内 gRPC 的端到端验证由
tests/integration/test_task_execute_real_chain.py 覆盖（INT-40 隔离守卫已随
本修复移除，回归由产品代码本身承载）。
"""
import os
import tempfile
import threading
from collections import deque
from datetime import datetime, timezone, timedelta

# BaseConfig 在 import 时校验环境变量（本文件自建 sqlite 库，与仓库既有测试同款兜底）
_TMP_DIR = tempfile.mkdtemp(prefix='int40_guard_')
os.environ.setdefault('DATABASE_URL', f'sqlite:///{_TMP_DIR}/int40_guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

import shared.clients.grpc_clients as shared_grpc_clients
import shared.models.database as database
from shared.models.database import Base, utc8now
from shared.utils.status_constants import TaskStatus
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI
from task_service.core.execution_engine.mixins.case_execution import CaseExecutionMixin
from task_service.core.execution_engine.mixins.task_control import TaskControlMixin
from task_service.core.execution_engine.mixins.scheduler import SchedulerMixin


def _utc8():
    return timezone(timedelta(hours=8))


class _CaseEngine(CaseExecutionMixin):
    """与 ExecutionEngine 同构的最小组合（仅 CaseExecutionMixin）。"""

    def __init__(self):
        self.utc_plus_8 = _utc8()
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


class _ControlEngine(TaskControlMixin):
    """_check_queue 所需的最小属性面（队列为空路径）。"""

    def __init__(self):
        self.queue_lock = threading.Lock()
        self.task_queue = deque()

    def _log(self, **kwargs):
        pass


class _SchedulerEngine(SchedulerMixin):
    """_schedule_pending_tasks 所需的最小属性面。"""

    def __init__(self):
        self.scheduler_stop_event = threading.Event()
        self.workers = {}
        self.queue_lock = threading.Lock()
        self.task_queue = deque()
        self.running_e2e = False
        self.running_apis = set()
        self.started = []

    def _log(self, **kwargs):
        pass

    def _adopt_orphan_tasks(self, local_db_session):
        pass


_DB_SEQ = iter(range(10000))


@pytest.fixture()
def sqlite_db(monkeypatch):
    """独立 sqlite 库 + 会话工厂：进程内替换 shared.models.database 的
    _SessionFactory / _scoped_session（测试后还原，不污染其他用例）。"""
    dbfile = os.path.join(_TMP_DIR, f'int40_{next(_DB_SEQ)}.db')
    engine = create_engine(f'sqlite:///{dbfile}')
    Base.metadata.create_all(
        engine, tables=[Task.__table__, TaskCase.__table__, TaskAPI.__table__])

    factory = sessionmaker(bind=engine)
    scoped = scoped_session(factory, scopefunc=threading.get_ident)
    monkeypatch.setattr(database, '_SessionFactory', factory)
    monkeypatch.setattr(database, '_scoped_session', scoped)

    yield engine

    scoped.close()
    engine.dispose()


def _seed_task_with_case():
    """播种一个 running 任务 + 一条 queued 用例，返回 (task_id, tc_rel_id)。"""
    s = database.get_db_session()
    try:
        task = Task(id=1, name='INT-40 守卫任务', status=TaskStatus.RUNNING, deleted=False)
        tc_rel = TaskCase(id=11, task_id=1, test_case_id='case-1',
                          execution_status='queued', evaluation_status='pending',
                          status='running')
        s.add(task)
        s.add(tc_rel)
        s.commit()
        return task.id, tc_rel.id
    finally:
        s.close()


def _success_stub():
    # INT-71：分发收敛到 StartAPITest 通道（经 ACL 仓储出站）
    return SimpleNamespace(StartAPITest=lambda req: SimpleNamespace(
        success=True, message='ok'))


@pytest.fixture()
def grpc_success(monkeypatch):
    monkeypatch.setattr(shared_grpc_clients, 'get_api_test_service_stub',
                        lambda: _success_stub())


class TestExecuteApiCaseUsesIndependentSession:
    """机制锁：嵌套链路不得触碰线程共享 scoped_session，独立会话用后即关。"""

    def test_get_db_session_must_not_be_called(self, monkeypatch, grpc_success):
        import task_service.core.execution_engine.mixins.case_execution as mod

        calls = []
        monkeypatch.setattr(
            database, 'get_db_session',
            lambda: (_ for _ in ()).throw(
                AssertionError('INT-40 回归：嵌套链路不得使用线程共享 scoped_session')))
        fake_session = MagicMock()
        monkeypatch.setattr(mod, 'create_db_session',
                            lambda: calls.append('create') or fake_session)

        ok = _CaseEngine()._execute_api_case(1, 11)

        assert ok is True
        assert calls == ['create'], '嵌套链路应经由 create_db_session 取独立会话'

    def test_independent_session_is_closed(self, monkeypatch, grpc_success):
        import task_service.core.execution_engine.mixins.case_execution as mod

        fake_session = MagicMock()
        monkeypatch.setattr(mod, 'create_db_session', lambda: fake_session)

        _CaseEngine()._execute_api_case(1, 11)

        fake_session.close.assert_called_once()


class TestNestedChainDoesNotDetachOuterTask:
    """行为锁：外层 scoped session 持有的已过期 Task，经嵌套链路后仍可用。

    复现语义：主循环在 scoped session 上加载 Task 并 commit（对象过期，
    等价于 _claim_case 提交后的状态），随后嵌套调用 _execute_api_case。
    缺陷版本（嵌套 close 共享 session）会把 Task expunge 成
    「脱管 + 过期」，task.id 必抛 DetachedInstanceError。
    """

    def test_outer_task_survives_nested_close(self, sqlite_db, grpc_success):
        task_id, tc_rel_id = _seed_task_with_case()

        scoped = database.get_db_session()
        try:
            task = scoped.get(Task, task_id)
            assert task is not None
            scoped.commit()  # 模拟主循环 claim 提交后的过期状态

            ok = _CaseEngine()._execute_api_case(task_id, tc_rel_id)

            assert ok is True
            # 修复前：对象已被嵌套 close expunge 且属性过期 → DetachedInstanceError
            assert task.id == task_id
            assert task.status == TaskStatus.RUNNING
            from sqlalchemy import inspect
            state = inspect(task)
            assert state.persistent, '外层 Task 必须仍 attached 于 scoped session'
        finally:
            scoped.close()

    def test_nested_write_persisted_via_independent_session(self, sqlite_db, grpc_success):
        task_id, tc_rel_id = _seed_task_with_case()
        _CaseEngine()._execute_api_case(task_id, tc_rel_id)

        # 独立会话的兜底写（started_at）必须已落库
        check = database.create_db_session()
        try:
            tc_rel = check.get(TaskCase, tc_rel_id)
            assert tc_rel is not None
            assert tc_rel.started_at is not None
        finally:
            check.close()


class TestCheckQueueDoesNotDetachCallerTask:
    """行为锁：_check_queue 被 control_task（外层持有 Task）嵌套调用时，
    不得 expunge 外层会话上的对象。"""

    def test_caller_task_survives_check_queue(self, sqlite_db):
        _seed_task_with_case()

        eng = _ControlEngine()
        scoped = database.get_db_session()
        try:
            task = scoped.get(Task, 1)
            scoped.commit()  # 模拟 control_task 停止分支提交后的过期状态

            eng._check_queue()

            # 修复前：_check_queue close 共享 session → task 脱管+过期 → 抛错
            assert task.id == 1
        finally:
            scoped.close()


class TestSchedulerSurvivesSharedSessionCloseInStartTask:
    """行为锁：start_task 内部会 close 共享 scoped session（并 commit 过期全部
    实例）。_schedule_pending_tasks 不得持有 ORM 对象跨该调用，否则第二轮
    task.id 即抛 DetachedInstanceError，整轮兜底调度中止。"""

    def test_all_pending_tasks_scheduled(self, sqlite_db):
        s = database.get_db_session()
        try:
            for tid in (1, 2):
                s.add(Task(id=tid, name=f'INT-40 任务{tid}', status=TaskStatus.PENDING, deleted=False))
            s.commit()
        finally:
            s.close()

        eng = _SchedulerEngine()

        def _start_task_like_real(task_id):
            """模拟真实 start_task 对共享 scoped session 的副作用：
            commit（过期全部实例）+ close（expunge 全部实例）。"""
            eng.started.append(task_id)
            sim = database.get_db_session()
            try:
                sim.query(Task).update({Task.updated_at: utc8now()},
                                       synchronize_session=False)
                sim.commit()
            finally:
                sim.close()
            return True, '已启动'

        eng.start_task = _start_task_like_real

        eng._schedule_pending_tasks()

        assert sorted(eng.started) == [1, 2], \
            f'整轮兜底调度必须完成全部候选任务: {eng.started}'


class TestIndependentSessionIsolation:
    """create_db_session 语义锁：独立实例、线程内不与 scoped_session 同享。"""

    def test_creates_distinct_session_per_call(self, sqlite_db):
        s1 = database.create_db_session()
        s2 = database.create_db_session()
        try:
            assert s1 is not s2
            assert s1 is not database.get_db_session()
        finally:
            s1.close()
            s2.close()

    def test_close_does_not_expunge_scoped_session_objects(self, sqlite_db):
        _seed_task_with_case()

        scoped = database.get_db_session()
        try:
            task = scoped.get(Task, 1)
            scoped.commit()  # 过期

            indep = database.create_db_session()
            try:
                indep.get(Task, 1)
            finally:
                indep.close()

            # 独立会话 close 不得影响外层对象（修复前若嵌套用共享会话则此处抛错）
            assert task.id == 1
        finally:
            scoped.close()
