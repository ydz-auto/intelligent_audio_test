# -*- coding: utf-8 -*-
"""INT-2231 守卫：任务队列消费者 _check_queue 必须校验状态并走 CAS 抢占。

原缺陷：_check_queue 从本地内存队列取出任务后直接写 task.status = RUNNING
并起执行线程，唯一跳过条件是 status == STOPPED，没有任何条件 UPDATE。
多实例下实例 A 因槽位忙把任务入本地队列，任务在实例 B 被 start_task / Redis
队列 CAS 抢占为 running（或已 completed/stopped）后，A 的空闲检查仍会为它
再起一个执行线程 → 同一任务 / 同一物理设备被重复驱动、结果重复落库。

修复：消费时复用与 start_task 相同的条件 UPDATE（status IN (pending, queued)
→ running）；影响行数不为 1 就放弃启动并回滚刚抢到的内存槽位。CAS 移出
queue_lock（INT-418 教训：不得持锁做 DB 写、回滚不得重入非重入锁）。

本文件覆盖（真实 SQLAlchemy 语义 + sqlite 文件库，不触 gRPC/Postgres/Redis）：
- 行为锁：DB 已是 running / completed 的队列项不得起线程、不得改 DB 状态。
- 行为锁：DB 仍 pending 的队列项正常启动并 CAS 翻转为 running。
- 机制锁：CAS 影响行数不为 1（模拟其它实例抢先）时不起线程、回滚槽位。
- 并发锁：两实例共享同一 DB 的同一队列项，只有先抢到 CAS 的一方起线程。
"""
import os
import tempfile
import threading
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
from task_service.infrastructure.persistence.models import Task
from task_service.core.execution_engine.mixins.task_control import TaskControlMixin
import task_service.core.execution_engine.mixins.task_control as tc_mod


class _QueueEngine(TaskControlMixin):
    """_check_queue 所需的最小属性面（与 ExecutionEngine 同构）。"""

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

    def _fake_thread_main(self, task_id, stop_event, pause_event, user_id):
        self.started.append((task_id, user_id))
        self.started_event.set()

    def _log(self, **kwargs):
        pass


_DB_SEQ = iter(range(10000))


@pytest.fixture()
def sqlite_db(monkeypatch):
    """独立 sqlite 库 + 会话工厂：进程内替换 shared.models.database 的
    _SessionFactory / _scoped_session（测试后还原，不污染其他用例）。"""
    dbfile = os.path.join(
        tempfile.mkdtemp(prefix='int2231_'), f'int2231_{next(_DB_SEQ)}.db')
    engine = create_engine(f'sqlite:///{dbfile}')
    Base.metadata.create_all(engine, tables=[Task.__table__])

    factory = sessionmaker(bind=engine)
    scoped = scoped_session(factory, scopefunc=threading.get_ident)
    monkeypatch.setattr(database, '_SessionFactory', factory)
    monkeypatch.setattr(database, '_scoped_session', scoped)

    yield engine

    scoped.close()
    engine.dispose()


def _seed_task(task_id, status):
    s = get_db_session()
    try:
        s.add(Task(id=task_id, name=f'T{task_id}', status=status, deleted=False))
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


def _enqueue(engine, task_id, has_physical=False, api_ids=None):
    engine.task_queue.append({
        'id': task_id,
        'has_physical': has_physical,
        'api_ids': list(api_ids or []),
        'user_id': None,
    })


class TestNonPendingQueueItemNotStarted:
    """行为锁：DB 状态已不是 pending/queued 的队列项不得被消费。"""

    @pytest.mark.parametrize('db_status', [
        TaskStatus.RUNNING,      # 其它实例已抢占
        TaskStatus.COMPLETED,    # 已完成，不得重跑
        TaskStatus.STOPPED,
        TaskStatus.PAUSED,
    ])
    def test_not_started(self, sqlite_db, db_status):
        _seed_task(1, db_status)
        eng = _QueueEngine()
        _enqueue(eng, 1, has_physical=True, api_ids=['api-1'])

        eng._check_queue()

        assert eng.started == [], '状态不允许的任务不得起执行线程'
        assert eng.workers == {}
        assert eng.running_tasks == {}, '不得残留内存槽位'
        assert eng.running_e2e is False
        assert eng.running_apis == set()
        assert eng.task_queue == deque(), '陈旧队列项应被丢弃'
        assert _db_status(1) == db_status, '不得改写 DB 状态'

    def test_deleted_missing_task_not_started(self, sqlite_db):
        """任务行不存在（已硬删）时也不得起线程。"""
        eng = _QueueEngine()
        _enqueue(eng, 999)

        eng._check_queue()

        assert eng.started == []
        assert eng.running_tasks == {}


class TestPendingQueueItemStarted:
    """行为锁：pending 队列项正常启动，并 CAS 翻转为 running。"""

    def test_started_and_cas_to_running(self, sqlite_db):
        _seed_task(1, TaskStatus.PENDING)
        eng = _QueueEngine()
        _enqueue(eng, 1)

        eng._check_queue()

        assert eng.started_event.wait(2), 'pending 任务必须起执行线程'
        assert eng.started == [(1, None)]
        assert _db_status(1) == TaskStatus.RUNNING, 'CAS 必须把状态翻转为 running'
        assert eng.running_tasks.get(1) == {'has_physical': False, 'api_ids': []}

    def test_queued_item_started(self, sqlite_db):
        _seed_task(2, TaskStatus.QUEUED)
        eng = _QueueEngine()
        _enqueue(eng, 2)

        eng._check_queue()

        assert eng.started_event.wait(2)
        assert _db_status(2) == TaskStatus.RUNNING


class _CasLoseSession:
    """预读看到 pending，但条件 UPDATE 影响行数为 0（模拟其它实例抢先）。"""

    def __init__(self, inner):
        self._inner = inner

    def get(self, *args, **kwargs):
        return self._inner.get(*args, **kwargs)

    def query(self, *args, **kwargs):
        inner_q = self._inner.query(*args, **kwargs)

        class _Query:
            def filter(self, *criteria, **kw):
                inner_q.filter(*criteria, **kw)
                return self

            def update(self, values=None, synchronize_session=False):
                return 0

        return _Query()

    def commit(self):
        self._inner.commit()

    def rollback(self):
        self._inner.rollback()

    def close(self):
        self._inner.close()


class TestCasLoserRollsBackSlot:
    """机制锁：CAS 影响行数 != 1 时不得起线程，且刚抢到的槽位必须回滚。"""

    def test_cas_loser_no_thread_and_slot_released(self, sqlite_db, monkeypatch):
        _seed_task(1, TaskStatus.PENDING)
        eng = _QueueEngine()
        _enqueue(eng, 1, has_physical=True, api_ids=['api-1'])

        real_factory = database._SessionFactory
        monkeypatch.setattr(
            tc_mod, 'create_db_session',
            lambda: _CasLoseSession(real_factory()))

        eng._check_queue()

        assert eng.started == [], 'CAS 输家不得起执行线程'
        assert eng.workers == {}
        assert eng.running_tasks == {}, 'CAS 失败必须回滚刚抢到的槽位'
        assert eng.running_e2e is False, '物理单飞槽位必须释放'
        assert eng.running_apis == set(), 'API 互斥占用必须释放'
        assert _db_status(1) == TaskStatus.PENDING, 'CAS 未命中不得改写状态'


class TestResumeEnqueueAtomic:
    """行为锁：resume 入队时 DB 必须已是 QUEUED。

    消费者按状态预判丢弃陈旧队列项，若 resume 先入队、后提交 QUEUED，
    恰好落在两步之间的 _check_queue 会把恢复项当陈旧项丢弃，任务永久
    停在 QUEUED 且无执行线程。状态写入必须与入队在同一把 queue_lock 内。

    判定方式：在「队列项出现的瞬间」（入队调用内）用独立会话读 DB 状态，
    必须已是 queued——与是否真的发生线程调度无关，确定性可复现。
    """

    def test_status_committed_before_item_visible(self, sqlite_db, monkeypatch):
        _seed_task(1, TaskStatus.PAUSED)
        eng = _QueueEngine()
        eng._emit_progress = lambda task: None
        eng.trigger_scheduler_check = lambda: None

        from task_service.infrastructure.persistence import task_repository as repo_mod
        monkeypatch.setattr(
            repo_mod.task_repository, 'get_execution_profile',
            lambda task_id: {'has_physical': False, 'api_ids': ['api-1']})

        observed = []

        class _SpyQueue(deque):
            """入队瞬间观测 DB 状态——模拟消费者在锁释放第一时间取队列。"""

            def append(self, item):
                observed.append(_db_status(item['id']))
                super().append(item)

        eng.task_queue = _SpyQueue()

        ok, message = eng.control_task(1, 'resume')

        assert ok is True and message == '任务已恢复'
        assert observed == [TaskStatus.QUEUED], \
            f'队列项可见时 DB 必须已是 queued（旧实现此处为 paused）: {observed}'
        assert _db_status(1) == TaskStatus.QUEUED, '入队时 DB 必须已是 queued'
        assert len(eng.task_queue) == 1

        # 恢复后的队列项必须能被消费者正常拉起（状态晚写时会被当陈旧项丢弃）
        eng._check_queue()

        assert eng.started_event.wait(2), '恢复入队的任务必须被消费启动'
        assert _db_status(1) == TaskStatus.RUNNING


        # 恢复后的队列项必须能被消费者正常拉起（状态晚写时会被当陈旧项丢弃）
        eng._check_queue()

        assert eng.started_event.wait(2), '恢复入队的任务必须被消费启动'
        assert _db_status(1) == TaskStatus.RUNNING


class TestTwoInstancesOnlyOneStarts:
    """并发锁：两实例共享 DB，同一队列项只允许一方起线程。"""

    def test_only_first_instance_starts(self, sqlite_db):
        _seed_task(1, TaskStatus.QUEUED)

        engine_a = _QueueEngine()
        engine_b = _QueueEngine()
        _enqueue(engine_a, 1, has_physical=True)
        _enqueue(engine_b, 1, has_physical=True)

        engine_a._check_queue()
        assert engine_a.started_event.wait(2)
        engine_b._check_queue()

        assert engine_a.started == [(1, None)]
        assert engine_b.started == [], '同一任务不得被第二个实例重复执行'
        assert engine_b.running_tasks == {}
        assert _db_status(1) == TaskStatus.RUNNING

    def test_second_instance_cas_loser_when_precheck_stale(self, sqlite_db, monkeypatch):
        """预判读到 pending 但 CAS 时已被抢先：同样不得起线程。"""
        _seed_task(1, TaskStatus.PENDING)
        eng = _QueueEngine()
        _enqueue(eng, 1, has_physical=True)

        real_factory = database._SessionFactory
        monkeypatch.setattr(
            tc_mod, 'create_db_session',
            lambda: _CasLoseSession(real_factory()))

        eng._check_queue()

        assert eng.started == []
        assert eng.running_tasks == {}
        assert eng.running_e2e is False
