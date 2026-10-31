# -*- coding: utf-8 -*-
"""INT-2282 守卫：任务 resume 必须真正落库并派发。

原缺陷（INT-2227 矩阵实测 M5，任务 467）：API 任务 pause 成功后 resume，
网关返回 `{"success": true, "data": {"status": "paused"}}`，任务永远停在
paused 且无任何派发。两个成因：

1. **状态写被静默丢弃**：resume 分支在写 QUEUED 之前调用了
   `task_repository.get_execution_profile()`，该函数用同一 scope 的
   scoped session 并在 finally `close()`，把 control_task 持有的 `task`
   实例 expunge 成脱管对象；此后 `task.status = QUEUED` + `commit()` 不会
   发出任何 UPDATE——DB 仍是 paused，而函数返回 `success=True`。
2. **入队后无人消费**：`_check_queue()` 只在「停止任务」与「其它任务收尾
   清理」时被调用，调度器 DB 兜底只捞 PENDING。恢复项进了内存队列也永远
   没人取，即使状态写成功也表现为「无派发」。

本文件覆盖（真实 SQLAlchemy + sqlite 文件库，不触 gRPC/Postgres/Redis）：
- 行为锁：resume 后 DB 必须是 queued/running（旧实现停在 paused）。
- 行为锁：resume 入队后必须被消费、起执行线程（旧实现队伍空转）。
- 时序锁：队列项可见时 DB 已是 queued（INT-2231 语义不回退）。
- 行为锁：workers 里只剩死线程时按「不在运行」处理，摘除陈旧槽位后重新派发。
- 行为锁：工作线程存活时走原路恢复（不重复起线程、不入队）。
- 行为锁：重新入队分支必须清除 pause 分支置的分布式暂停标志（否则新线程
  在 api_test_service 执行器里被暂停屏障挡住，任务 running 但用例不推进）。
"""
import os
import tempfile
import threading
import time
from collections import deque

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

import shared.models.database as database
from shared.models.database import Base, get_db_session
from shared.utils.status_constants import TaskStatus
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI
from task_service.core.execution_engine.mixins.task_control import TaskControlMixin


class _ResumeEngine(TaskControlMixin):
    """control_task / _check_queue 所需的最小属性面（与 ExecutionEngine 同构）。"""

    def __init__(self):
        self.queue_lock = threading.Lock()
        self.task_queue = deque()
        self.running_tasks = {}
        self.running_apis = set()
        self.running_e2e = False
        self.workers = {}
        self.stop_flags = {}
        self.pause_flags = {}
        self.task_completion_events = {}
        self.started = []
        self.started_event = threading.Event()
        # 执行线程替身：只记录，不跑真实引擎
        self._task_thread_main = self._fake_thread_main

    def _fake_thread_main(self, task_id, stop_event, pause_event, user_id=None):
        self.started.append(task_id)
        self.started_event.set()

    def _log(self, **kwargs):
        pass

    def _emit_progress(self, task, force=False):
        pass

    def trigger_scheduler_check(self):
        pass


_DB_SEQ = iter(range(10000))


@pytest.fixture()
def sqlite_db(monkeypatch):
    """独立 sqlite 库 + 会话工厂：进程内替换 shared.models.database 的
    _SessionFactory / _scoped_session（测试后还原，不污染其他用例）。"""
    dbfile = os.path.join(
        tempfile.mkdtemp(prefix='int2282_'), f'int2282_{next(_DB_SEQ)}.db')
    engine = create_engine(f'sqlite:///{dbfile}')
    Base.metadata.create_all(
        engine, tables=[Task.__table__, TaskCase.__table__, TaskAPI.__table__])

    factory = sessionmaker(bind=engine, expire_on_commit=True)
    scoped = scoped_session(factory, scopefunc=threading.get_ident)
    monkeypatch.setattr(database, '_SessionFactory', factory)
    monkeypatch.setattr(database, '_scoped_session', scoped)

    yield engine

    scoped.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def _isolate_redis_control_flags(monkeypatch):
    """控制类单测不触真实 Redis：分布式控制标志默认打桩为空操作。

    重新入队分支的修复新增了 clear_task_pause 调用，正常用例不应因此去连 6379；
    需要断言标志语义的用例在用例体内重新 setattr 覆盖。
    """
    import task_service.core.execution_engine.mixins.task_control as tc_mod
    monkeypatch.setattr(tc_mod._dc, 'set_task_pause', lambda *a, **k: None)
    monkeypatch.setattr(tc_mod._dc, 'clear_task_pause', lambda *a, **k: None)
    monkeypatch.setattr(tc_mod._dc, 'is_task_paused', lambda task_id: False)


def _seed_api_task(task_id=1, status=TaskStatus.PAUSED):
    s = get_db_session()
    try:
        s.add(Task(id=task_id, name=f'T{task_id}', status=status, deleted=False))
        s.add(TaskCase(task_id=task_id, test_case_id=f'c{task_id}',
                       device_type='http_api', device_id='api-5'))
        s.add(TaskAPI(task_id=task_id, api_id=5))
        s.commit()
    finally:
        s.close()


def _db_status(task_id):
    s = database.create_db_session()
    try:
        task = s.get(Task, task_id)
        return task.status if task else None
    finally:
        s.close()


def _dead_thread():
    t = threading.Thread(target=lambda: None, name='dead-worker')
    t.start()
    t.join(2)
    assert not t.is_alive()
    return t


class TestResumePersistsAndDispatches:
    """行为锁：resume 必须落库 queued 并被消费起线程。"""

    def test_status_persisted_and_worker_started(self, sqlite_db):
        _seed_api_task(1, TaskStatus.PAUSED)
        eng = _ResumeEngine()

        ok, message = eng.control_task(1, 'resume')

        assert ok is True and message == '任务已恢复'
        # 旧实现：脱管对象赋值不落库，这里停在 paused
        assert _db_status(1) == TaskStatus.RUNNING, \
            'resume 后任务必须离开 paused 并被队列消费者抢占为 running'
        assert eng.started_event.wait(2), 'resume 入队后必须被消费起执行线程'
        assert eng.started == [1]
        assert eng.task_queue == deque()
        assert eng.running_tasks.get(1) == {'has_physical': False, 'api_ids': [5]}

    def test_queue_item_visible_after_status_committed(self, sqlite_db):
        """时序锁（INT-2231 不回退）：队列项出现的瞬间 DB 已是 queued。"""
        _seed_api_task(1, TaskStatus.PAUSED)
        eng = _ResumeEngine()

        observed = []

        class _SpyQueue(deque):
            def append(self, item):
                observed.append(_db_status(item['id']))
                super().append(item)

        eng.task_queue = _SpyQueue()
        # 本用例只看入队时序，不关心消费
        eng._check_queue = lambda: None

        ok, _ = eng.control_task(1, 'resume')

        assert ok is True
        assert observed == [TaskStatus.QUEUED], \
            f'队列项可见时 DB 必须已是 queued（旧实现此处为 paused）: {observed}'
        assert len(eng.task_queue) == 1


class TestResumeWithDeadWorker:
    """行为锁：workers 里只剩死线程 + 陈旧槽位时仍要重新派发。"""

    def test_dead_worker_registration_replaced(self, sqlite_db):
        _seed_api_task(1, TaskStatus.PAUSED)
        eng = _ResumeEngine()
        dead = _dead_thread()
        eng.workers[1] = dead
        eng.stop_flags[1] = threading.Event()
        eng.pause_flags[1] = threading.Event()
        # 暂停期间退出的线程遗留的内存槽位
        eng.running_tasks[1] = {'has_physical': False, 'api_ids': [5]}
        eng.running_apis.update([5])

        ok, message = eng.control_task(1, 'resume')

        assert ok is True and message == '任务已恢复'
        assert eng.started_event.wait(2), '陈旧槽位摘除后必须重新起执行线程'
        assert eng.started == [1]
        assert _db_status(1) == TaskStatus.RUNNING
        assert eng.workers[1] is not dead, '死线程登记必须被新执行线程替换'


class TestResumeRequeueClearsDistributedPause:
    """行为锁（返工 P1）：重新入队分支必须清 pause 分支置的分布式暂停标志。

    pause 分支在 task_control.py 置 `task:pause:{id}`（Redis）；仅「工作线程
    存活」的 resume 分支清它，重新入队分支漏清。于是恢复后新起的执行线程把
    任务带到 api_test_service，`_control_mixin._handle_control` 读到标志就
    阻塞等待恢复——任务 running、队列空、线程活着，用例一步不动。
    """

    def test_requeue_branch_clears_pause_flag(self, sqlite_db, monkeypatch):
        import task_service.core.execution_engine.mixins.task_control as tc_mod

        paused = set()

        def _set(task_id, ttl=86400):
            paused.add(task_id)

        def _clear(task_id):
            paused.discard(task_id)

        def _is_paused(task_id):
            return task_id in paused

        monkeypatch.setattr(tc_mod._dc, 'set_task_pause', _set)
        monkeypatch.setattr(tc_mod._dc, 'clear_task_pause', _clear)
        monkeypatch.setattr(tc_mod._dc, 'is_task_paused', _is_paused)

        _seed_api_task(1, TaskStatus.PAUSED)
        # pause 分支（存活线程路径）留下的分布式暂停标志
        tc_mod._dc.set_task_pause(1)
        assert tc_mod._dc.is_task_paused(1) is True

        eng = _ResumeEngine()
        seen_in_worker = []

        def _probe(task_id, stop_event, pause_event, user_id=None):
            # 新执行线程启动瞬间读到的分布式暂停标志
            seen_in_worker.append(tc_mod._dc.is_task_paused(task_id))
            eng.started.append(task_id)
            eng.started_event.set()

        eng._task_thread_main = _probe

        ok, message = eng.control_task(1, 'resume')

        assert ok is True and message == '任务已恢复'
        assert tc_mod._dc.is_task_paused(1) is False, \
            '重新入队分支必须清除分布式暂停标志，否则执行器卡在暂停屏障'
        assert eng.started_event.wait(2), 'resume 入队后必须被消费起执行线程'
        assert seen_in_worker == [False], \
            '新执行线程启动时不得读到旧的分布式暂停标志'
        assert _db_status(1) == TaskStatus.RUNNING


class TestResumeWithLiveWorker:
    """行为锁：工作线程存活时走原路恢复，不重复起线程、不入队。"""

    def test_live_worker_resumed_in_place(self, sqlite_db, monkeypatch):
        import task_service.core.execution_engine.mixins.task_control as tc_mod

        # 存活线程分支要读/写 e2e 事件并清分布式暂停信号，单测内一律打桩
        monkeypatch.setattr(tc_mod, '_get_task_events_via_grpc',
                            lambda task_id: object())
        monkeypatch.setattr(tc_mod, '_register_task_events_via_grpc',
                            lambda *a, **k: None)
        monkeypatch.setattr(tc_mod._dc, 'clear_task_pause', lambda task_id: None)

        _seed_api_task(1, TaskStatus.PAUSED)
        eng = _ResumeEngine()

        block = threading.Event()

        def _hold(task_id, stop_event, pause_event, user_id=None):
            block.wait(5)

        live = threading.Thread(target=_hold, args=(1, None, None), daemon=True)
        live.start()
        try:
            eng.workers[1] = live
            eng.stop_flags[1] = threading.Event()
            eng.pause_flags[1] = threading.Event()
            eng.pause_flags[1].clear()
            eng.running_tasks[1] = {'has_physical': False, 'api_ids': [5]}
            eng.running_apis.update([5])

            ok, message = eng.control_task(1, 'resume')

            assert ok is True and message == '任务已恢复'
            assert eng.pause_flags[1].is_set(), '存活线程必须被置为继续执行'
            assert eng.task_queue == deque(), '存活线程恢复不得重复入队'
            assert eng.started == [], '存活线程恢复不得另起执行线程'
            assert _db_status(1) == TaskStatus.RUNNING
        finally:
            block.set()
            live.join(2)


class TestResumeWithoutApiCases:
    """纯物理任务无法重建异步等待流程：保持原判定（失败，不误改状态）。"""

    def test_physical_task_resume_rejected(self, sqlite_db):
        s = get_db_session()
        try:
            s.add(Task(id=9, name='T9', status=TaskStatus.PAUSED, deleted=False))
            s.add(TaskCase(task_id=9, test_case_id='c9',
                           device_type='physical', device_id='dev-1'))
            s.commit()
        finally:
            s.close()

        eng = _ResumeEngine()
        ok, message = eng.control_task(9, 'resume')

        assert ok is False and message == '未找到运行中的任务'
        assert _db_status(9) == TaskStatus.PAUSED
        assert eng.task_queue == deque()
        assert eng.started == []
