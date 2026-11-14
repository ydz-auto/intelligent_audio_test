# -*- coding: utf-8 -*-
"""INT-2590：device_service 后台线程轮次收尾 —— 只读事务不得跨轮悬挂。

背景（INT-2588 实测）：宿主 device_service 的 presence 监听线程与 monitor 守护线程
在每轮只读查询后既不 commit 也不 rollback，连接以 ``idle in transaction`` 常驻
12 小时，持有 ``devices`` / ``laboratories`` 的 AccessShareLock，把 db_bootstrap 的
``ALTER TABLE devices ADD COLUMN lab_id`` 顶到锁超时（55P03）。

本文件守三层：
1. presence ``_watch_loop`` 每轮（含 reconcile 抛异常、写路径抛异常、监听流断开）
   结束前清掉当前线程 session；
2. monitor ``DeviceMonitorThread._loop`` 每轮（含 health_check /
   evaluate_alarm_rules 抛异常、两个分支都异常）结束前清掉当前线程 session；
3. 只读解析器 ``_lab_resolver.resolve_lab_names`` 结束即释放只读事务，且不吞
   调用链上未提交的写（end_read_transaction 的安全边界）。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import Column, Integer, String, text

from shared.models import database as db_module
from shared.models.database import get_db_session, remove_db_session

from device_service.application.services import device_presence_service as presence_mod
from device_service.application.services import device_monitor_service as monitor_mod
from device_service.application.services.device_presence_service import DevicePresenceService
from device_service.infrastructure.persistence import _lab_resolver as resolver_mod
from device_service.infrastructure.persistence._lab_resolver import resolve_lab_names


# ==================== 测试替身 ====================

def _spy_remove_db_session(monkeypatch, module):
    """把模块内的 remove_db_session 换成「计数 + 真实清理」的探针。"""
    calls = []

    def spy():
        calls.append(1)
        remove_db_session()

    monkeypatch.setattr(module, 'remove_db_session', spy)
    return calls


class FakeRepo:
    def __init__(self, devices, on_list=None):
        self._devices = devices
        self.status_updates = []
        self.on_list = on_list

    def list_devices(self, page=1, per_page=10, **kwargs):
        if self.on_list is not None:
            self.on_list()
        return {'items': self._devices, 'total': len(self._devices)}

    def update_device_statuses(self, updates):
        self.status_updates.extend(updates)
        return len(updates)


class FakeMonitor:
    def __init__(self, on_record=None):
        self.events = []
        self.on_record = on_record

    def record_status_events(self, events):
        if self.on_record is not None:
            self.on_record()
        self.events.extend(events)
        return events


class OneShotDriver:
    """推送一个快照后结束流（避免进入重连退避的等待）。"""

    def __init__(self, snapshot):
        self.snapshot = snapshot

    def watch_device_snapshots(self, stop_event):
        try:
            yield self.snapshot
        finally:
            # 流结束（正常 StopIteration / 被 close 的 GeneratorExit）都让循环退出
            stop_event.set()


def _online_device():
    return {'id': 1, 'system': 'Android', 'serial_number': 'SN1', 'status': 'online'}


def _build_service(repo, monitor=None):
    return DevicePresenceService(repo=repo, monitor=monitor or FakeMonitor(),
                                 factory=object())


# ==================== presence：_watch_loop 轮次收尾 ====================

def test_presence_watch_loop_ends_round_session(monkeypatch):
    """推 1 个快照 → 一轮 reconcile 后当前线程 session 已被清掉，无未结束事务。"""
    get_db_session()  # 模拟 reconcile 的只读查询在本线程留下的 session
    assert db_module._scoped_session.registry.has() is True
    calls = _spy_remove_db_session(monkeypatch, presence_mod)

    service = _build_service(FakeRepo([_online_device()]))
    service._watch_loop('Android', OneShotDriver({'SN1': 'device'}))

    assert calls, 'presence 轮次结束必须调用 remove_db_session'
    assert db_module._scoped_session.registry.has() is False


def test_presence_watch_loop_ends_round_session_when_reconcile_raises(monkeypatch):
    """reconcile 抛异常（读路径失败）时收尾同样发生。"""
    get_db_session()
    calls = _spy_remove_db_session(monkeypatch, presence_mod)

    service = _build_service(FakeRepo([_online_device()]))

    def boom():
        service._stop_event.set()
        raise RuntimeError('list_devices boom')

    service.repo.on_list = boom
    service._watch_loop('Android', OneShotDriver({'SN1': 'device'}))

    assert calls
    assert db_module._scoped_session.registry.has() is False


def test_presence_watch_loop_ends_round_session_when_write_raises(monkeypatch):
    """写路径（record_status_events）抛异常时收尾同样发生。"""
    get_db_session()
    calls = _spy_remove_db_session(monkeypatch, presence_mod)

    service = _build_service(FakeRepo([_online_device()]))

    def boom():
        service._stop_event.set()
        raise RuntimeError('record_status_events boom')

    service.monitor = FakeMonitor(on_record=boom)
    service._watch_loop('Android', OneShotDriver({'SN1': 'device'}))

    assert calls
    assert db_module._scoped_session.registry.has() is False


def test_presence_watch_loop_ends_round_session_when_stream_breaks(monkeypatch):
    """监听流未产出任何快照就断开（空轮次）时也收尾，再进入重连退避。"""
    get_db_session()
    calls = _spy_remove_db_session(monkeypatch, presence_mod)

    class EmptyStreamDriver:
        def watch_device_snapshots(self, stop_event):
            stop_event.set()
            return
            yield  # pragma: no cover - 使其成为生成器

    service = _build_service(FakeRepo([_online_device()]))
    service._watch_loop('Android', EmptyStreamDriver())

    assert calls
    assert db_module._scoped_session.registry.has() is False


def test_presence_end_round_session_swallows_errors(monkeypatch):
    """收尾失败不得影响监听主流程（只记 debug）。"""
    get_db_session()

    def broken():
        raise RuntimeError('remove boom')

    monkeypatch.setattr(presence_mod, 'remove_db_session', broken)

    service = _build_service(FakeRepo([_online_device()]))
    service._watch_loop('Android', OneShotDriver({'SN1': 'device'}))  # 不抛出即通过


# ==================== monitor：DeviceMonitorThread._loop 轮次收尾 ====================

def _run_one_monitor_round(monkeypatch, make_health, make_evaluate):
    """跑恰一轮监控循环（interval=0 + evaluate 内置 stop_event）。"""
    from device_service.application.commands import device_command_service as command_mod

    thread = monitor_mod.DeviceMonitorThread(interval_seconds=0)
    calls = _spy_remove_db_session(monkeypatch, monitor_mod)
    monkeypatch.setattr(command_mod.device_command_service,
                        'health_check', make_health(thread))
    monkeypatch.setattr(
        monitor_mod, 'device_monitor_service',
        SimpleNamespace(evaluate_alarm_rules=make_evaluate(thread)))
    thread._loop()
    return calls


def test_monitor_loop_ends_round_session(monkeypatch):
    """一轮 health_check + evaluate 之后当前线程 session 已被清掉。"""
    get_db_session()
    assert db_module._scoped_session.registry.has() is True

    def health(_thread):
        def _run():
            get_db_session()  # 本轮读路径留下的 session
        return _run

    def evaluate(thread):
        def _run():
            thread._stop_event.set()
            return []
        return _run

    calls = _run_one_monitor_round(monkeypatch, health, evaluate)

    assert calls
    assert db_module._scoped_session.registry.has() is False


@pytest.mark.parametrize('health_raises,evaluate_raises', [
    (True, False),
    (False, True),
    (True, True),
])
def test_monitor_loop_ends_round_session_when_branches_raise(
        monkeypatch, health_raises, evaluate_raises):
    """health_check / evaluate_alarm_rules 抛异常（含两个都抛）时收尾仍发生。"""
    get_db_session()

    def health(_thread):
        def _run():
            get_db_session()
            if health_raises:
                raise RuntimeError('health boom')
        return _run

    def evaluate(thread):
        def _run():
            thread._stop_event.set()
            if evaluate_raises:
                raise RuntimeError('evaluate boom')
            return []
        return _run

    calls = _run_one_monitor_round(monkeypatch, health, evaluate)

    assert calls
    assert db_module._scoped_session.registry.has() is False


# ==================== 只读解析器：resolve_lab_names 事务收尾 ====================

@pytest.fixture(scope='module')
def lab_tables():
    """进程内 sqlite 临时库建 laboratories 表（用 conftest 兜底的 DATABASE_URL）。

    conftest 兜底的是**进程级共享 sqlite 文件**：本 fixture 的 3 列裸建表若残留，
    后续用例的 ``Base.metadata.create_all()`` 见同名表即跳过，ORM 需要的
    ``code / building / status`` 等列不存在 → 建、查全挂（实测打挂
    test_int537/538/539/540 共 31 例）。故 teardown 必须把本文件建的临时表
    删干净，并把临时模型从进程级 Base.metadata 摘掉，避免后续 create_all
    再建出游离表。
    """
    from shared.models.database import Base, get_engine, init_db

    remove_db_session()
    init_db()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS laboratories'))
        conn.execute(text(
            'CREATE TABLE laboratories (id INTEGER PRIMARY KEY, name TEXT, deleted BOOLEAN)'))
        conn.execute(text(
            "INSERT INTO laboratories (id, name, deleted) VALUES "
            "(1, '一号实验室', 0), (2, '二号实验室', 0), (3, '已删除实验室', 1)"))
    remove_db_session()
    yield
    remove_db_session()
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS laboratories'))
        conn.execute(text('DROP TABLE IF EXISTS int2590_pending_guard'))
    pending = Base.metadata.tables.get('int2590_pending_guard')
    if pending is not None:
        Base.metadata.remove(pending)
    remove_db_session()


def test_resolve_lab_names_ends_read_transaction(lab_tables):
    """只读解析结束事务：in_transaction True → False，连接不留在 idle in transaction。"""
    session = get_db_session()()
    names = resolve_lab_names([1, 2, 3])

    assert names == {1: '一号实验室', 2: '二号实验室'}  # 软删不返回
    assert session.in_transaction() is False


def test_resolve_lab_names_ends_read_transaction_on_lookup_failure(monkeypatch):
    """实验室表不可用（查询异常）时 finally 仍以同一 session 收尾。"""

    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError('relation "laboratories" does not exist')

    broken = BrokenSession()
    seen = []
    monkeypatch.setattr(resolver_mod, 'get_db_session', lambda: broken)
    monkeypatch.setattr(resolver_mod, 'end_read_transaction',
                        lambda session=None: seen.append(session))

    assert resolve_lab_names([1]) == {}
    assert seen == [broken]


def test_resolve_lab_names_keeps_pending_writes(lab_tables):
    """有待提交写时不回滚——只读收口不得吞掉调用链上的写。"""
    from shared.models.database import Base, get_engine

    class _Int2590Pending(Base):
        __tablename__ = 'int2590_pending_guard'
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String(20))

    Base.metadata.create_all(get_engine(), tables=[_Int2590Pending.__table__])
    remove_db_session()

    session = get_db_session()()
    session.add(_Int2590Pending(name='pending-write'))
    session.flush()  # 已 flush 未 commit：INT-1691 的 _UNCOMMITTED_WRITE_KEY 场景
    names = resolve_lab_names([1])

    assert names == {1: '一号实验室'}
    assert session.in_transaction() is True        # 写事务未被吞
    assert session.execute(
        text('SELECT name FROM int2590_pending_guard')).fetchone()[0] == 'pending-write'
    session.rollback()
