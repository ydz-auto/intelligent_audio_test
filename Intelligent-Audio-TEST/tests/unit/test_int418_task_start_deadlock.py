# -*- coding: utf-8 -*-
"""INT-418 守卫：任务启动 CAS 失败回滚不得重入非重入 queue_lock（自死锁）。

原缺陷（INT-321 全流程实机走查 py-spy 实锤）：task_control.start_task 的
queue_lock（threading.Lock，非重入）横跨 gRPC 注册与 DB CAS 全路径；CAS
失败回滚分支在已持锁线程上再次 `with self.queue_lock:` → 自死锁。该线程
永久持锁，后续所有 start（gRPC 线程阻塞在锁入口）与 DB 兜底调度
（scheduler.py）全部排队挂死，任务启动链路整体瘫痪直至重启 task_service。

修复：收窄 queue_lock 至纯决策段（队列查重/互斥判定/槽位抢占），gRPC 注册
与 DB CAS 移出锁外；CAS 失败回滚复用 _release_running_slot（内部重新取锁，
非重入问题不复存在）；并新增槽位在途互斥（running_tasks 已有该任务时并发
start 幂等拒绝，防止 CAS 输家误释放胜者槽位）。

本文件覆盖（真实 SQLAlchemy 语义 + sqlite 文件库，不触 gRPC/Postgres/Redis）：
- 机制锁：CAS 失败回滚不再重入锁 —— 对终态（completed）任务 start，
  start_task 有界时间内返回（缺陷版本永久卡死），且 queue_lock 事后仍可
  获取（锁未被毒化）。
- 机制锁：锁内决策段不横跨 gRPC/CAS —— 可执行路径在 gRPC 注册时未持有
  queue_lock（缺陷版本持锁做 gRPC 调用，阻塞调度器与其它 start）。
- 行为锁：槽位在途互斥 —— running_tasks 已有该任务时，并发 start 幂等拒绝，
  不触碰胜者槽位（e2e 单飞/API 互斥不被破坏）。
- 语义锁：task_lifecycle_service.start 对 COMPLETED 显式拒绝（400）并给出
  重新执行指引，不再放行进 CAS 必然失败路径。
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
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI
from task_service.core.execution_engine.mixins.task_control import TaskControlMixin


class _StartEngine(TaskControlMixin):
    """start_task 所需的最小属性面（与 ExecutionEngine 同构）。"""

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
        self.max_queue_size = 100
        self.scheduler_event = threading.Event()

    def _log(self, **kwargs):
        pass

    def trigger_scheduler_check(self):
        self.scheduler_event.set()


_DB_SEQ = iter(range(10000))


@pytest.fixture()
def sqlite_db(monkeypatch):
    """独立 sqlite 库 + 会话工厂：进程内替换 shared.models.database 的
    _SessionFactory / _scoped_session（测试后还原，不污染其他用例）。"""
    dbfile = os.path.join(
        tempfile.mkdtemp(prefix='int418_'), f'int418_{next(_DB_SEQ)}.db')
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


def _seed_task(task_id, status):
    """播种一个指定状态的任务（默认无物理/API 用例画像）。"""
    s = get_db_session()
    try:
        s.add(Task(id=task_id, name=f'T{task_id}', status=status, deleted=False))
        s.commit()
    finally:
        s.close()


class TestCasFailureDoesNotReenterLock:
    """机制锁：CAS 失败回滚不得在持锁线程上重入非重入 queue_lock。

    缺陷版本：CAS（仅匹配 pending/queued）对终态任务恒失败 → 回滚分支
    `with self.queue_lock:` 自死锁，start_task 永久不返回、锁被毒化。
    修复版本：回滚走 _release_running_slot（内部重新取锁），有界返回。
    """

    def test_completed_task_start_returns_without_deadlock(self, sqlite_db):
        _seed_task(1, TaskStatus.COMPLETED)
        eng = _StartEngine()

        result = {}

        def _run():
            result['value'] = eng.start_task(1)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=3)

        assert not t.is_alive(), 'CAS 失败回滚不得自死锁：start_task 必须 3s 内返回'
        assert result['value'] == (False, '任务已被其它实例启动')
        assert eng.running_tasks == {}, 'CAS 失败后不得残留内存槽位'
        assert eng.running_e2e is False
        assert eng.running_apis == set()

        # 锁未被毒化：其它线程可正常获取（缺陷版本此处永久阻塞）
        acquired = eng.queue_lock.acquire(timeout=1)
        assert acquired, 'queue_lock 必须可再次获取（未被自死锁线程占用）'
        eng.queue_lock.release()


class TestLockDoesNotSpanGrpcAndCas:
    """机制锁：queue_lock 收窄到纯决策段，可执行路径的 gRPC 注册在锁外。"""

    def test_grpc_registration_outside_lock(self, sqlite_db, monkeypatch):
        _seed_task(1, TaskStatus.PENDING)
        eng = _StartEngine()
        eng._task_thread_main = lambda *a, **k: None  # worker 线程 no-op

        import task_service.core.execution_engine.mixins.task_control as tc_mod
        lock_states = []

        def _fake_register(task_id, stop_event, pause_event):
            lock_states.append(eng.queue_lock.locked())

        monkeypatch.setattr(tc_mod, '_register_task_events_via_grpc', _fake_register)

        success, message = eng.start_task(1)

        assert success is True and message == '任务已启动'
        assert lock_states == [False], \
            f'gRPC 注册时不得持 queue_lock（旧实现锁横跨 gRPC）: {lock_states}'
        assert eng.running_tasks.get(1) == {'has_physical': False, 'api_ids': []}
        assert eng.workers.get(1) is not None

        # DB 状态已由 CAS 翻转为 running
        s = get_db_session()
        try:
            assert s.get(Task, 1).status == TaskStatus.RUNNING
        finally:
            s.close()


class TestInflightSlotGuard:
    """行为锁：槽位在途（另一线程正在启动同一任务）时并发 start 幂等拒绝。"""

    def test_concurrent_start_same_task_rejected(self, sqlite_db):
        _seed_task(1, TaskStatus.PENDING)
        eng = _StartEngine()
        # 模拟另一线程已抢占槽位（start 在途 / 运行中）
        eng.running_tasks[1] = {'has_physical': True, 'api_ids': []}
        eng.running_e2e = True

        success, message = eng.start_task(1)

        assert success is False
        assert message == '任务已在启动中'
        assert eng.running_tasks.get(1) == {'has_physical': True, 'api_ids': []}, \
            '幂等拒绝不得触碰胜者槽位'
        assert eng.running_e2e is True


class TestLifecycleRejectsCompletedStart:
    """语义锁：COMPLETED 任务 start 显式拒绝（不再放行进 CAS 必然失败路径）。"""

    def test_start_completed_rejected_with_guidance(self, sqlite_db):
        from task_service.application.task.task_lifecycle_service import task_lifecycle_service
        _seed_task(1, TaskStatus.COMPLETED)

        result = task_lifecycle_service.start(1)

        assert result['success'] is False
        assert result['code'] == 400
        assert '重新执行' in result['message'], f'应指引走重新执行语义: {result}'
