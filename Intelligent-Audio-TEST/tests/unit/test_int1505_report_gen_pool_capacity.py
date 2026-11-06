# -*- coding: utf-8 -*-
"""INT-1505 专项：报告生成线程池排队饥饿 — 容量配置化 + 队列深度可观测。

覆盖：
- 线程池容量取自 Config（默认 8，原硬编码 3），env 可覆盖（任务 / 对比两条链路）
- 容量语义：提交 N（=配置容量）个生成任务时 N 个同时进入工作线程，
  第 N+1 个才排队 —— 并发多任务生成不再 3 线程排队饥饿
- 可观测：_executor_status / report_generation_status 暴露容量、存活线程、
  队列深度、在途任务；看门狗「排队饥饿」告警带容量与队列深度
- /health 暴露 report_generation 快照（运维/探针无需翻日志）
"""
import importlib
import os
import threading
import time

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import report_service.application.services.report_task_generator as gen_mod
import report_service.config.config as config_mod


class FakeLock:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class _FakeQueue:
    def __init__(self, depth):
        self._depth = depth

    def qsize(self):
        return self._depth


class _FakeExecutor:
    """最小线程池桩：只提供可观测所需的私有属性。"""

    def __init__(self, max_workers, queued, workers):
        self._max_workers = max_workers
        self._work_queue = _FakeQueue(queued)
        self._threads = [_AliveThread(alive) for alive in workers]


class _AliveThread:
    def __init__(self, alive):
        self._alive = alive

    def is_alive(self):
        return self._alive


@pytest.fixture(autouse=True)
def _clean_tracker():
    gen_mod._generation_tracker = gen_mod.GenerationTracker()
    yield
    gen_mod._generation_tracker = gen_mod.GenerationTracker()


class TestPoolCapacityConfig:
    """容量来源：Config（默认 8）+ env 覆盖，两条生成链路各自独立。"""

    def test_default_capacity_is_expanded(self, monkeypatch):
        monkeypatch.delenv('REPORT_GEN_MAX_WORKERS', raising=False)
        monkeypatch.delenv('REPORT_COMPARE_GEN_MAX_WORKERS', raising=False)
        importlib.reload(config_mod)
        try:
            assert config_mod.Config.REPORT_GEN_MAX_WORKERS == 8
            assert config_mod.Config.REPORT_COMPARE_GEN_MAX_WORKERS == 8
        finally:
            importlib.reload(config_mod)

    def test_env_override_parsed(self, monkeypatch):
        monkeypatch.setenv('REPORT_GEN_MAX_WORKERS', '12')
        monkeypatch.setenv('REPORT_COMPARE_GEN_MAX_WORKERS', '6')
        importlib.reload(config_mod)
        try:
            assert config_mod.Config.REPORT_GEN_MAX_WORKERS == 12
            assert config_mod.Config.REPORT_COMPARE_GEN_MAX_WORKERS == 6
        finally:
            monkeypatch.delenv('REPORT_GEN_MAX_WORKERS', raising=False)
            monkeypatch.delenv('REPORT_COMPARE_GEN_MAX_WORKERS', raising=False)
            importlib.reload(config_mod)

    def test_task_pool_capacity_follows_config(self):
        assert gen_mod._report_executor._max_workers == gen_mod.Config.REPORT_GEN_MAX_WORKERS
        assert gen_mod._report_executor._max_workers >= 8

    def test_compare_pool_capacity_follows_config(self):
        import report_service.application.services.report_compare_generator as cmp_mod
        assert cmp_mod._secondary_executor._max_workers == \
            cmp_mod.Config.REPORT_COMPARE_GEN_MAX_WORKERS
        assert cmp_mod._secondary_executor._max_workers >= 8


class TestNoStarvationAtCapacity:
    """容量语义：配置容量的任务同时开工，超出容量才排队（原 3 线程时第 4 个即排队）。"""

    def test_submitted_generations_run_concurrently_up_to_capacity(self, monkeypatch):
        capacity = gen_mod.Config.REPORT_GEN_MAX_WORKERS
        barrier = threading.Barrier(capacity, timeout=10)
        release = threading.Event()
        entered = []
        entered_lock = threading.Lock()

        def _fake_async(task_id, name, description, lock):
            with entered_lock:
                entered.append(task_id)
            barrier.wait()
            release.wait(10)

        monkeypatch.setattr(
            gen_mod.ReportTaskGenerator, '_generate_task_report_async',
            staticmethod(_fake_async))
        monkeypatch.setattr(gen_mod, 'log_and_emit', lambda *a, **kw: None)

        task_ids = [1500 + i for i in range(capacity)]
        try:
            for task_id in task_ids:
                assert gen_mod._submit_generation(
                    task_id, FakeLock(), None, None, '[int1505] submit') is True
            deadline = time.time() + 10
            while len(entered) < capacity and time.time() < deadline:
                time.sleep(0.02)
            assert len(entered) == capacity, (
                f'仅 {len(entered)}/{capacity} 个生成同时进入工作线程（容量未生效，仍排队饥饿）')
            # 排队槽位未溢出：队列深度为 0
            assert gen_mod._executor_queue_depth() in (0, None)
        finally:
            release.set()
            for task_id in task_ids:
                gen_mod._generation_tracker.finish(task_id)

    def test_overflow_goes_to_queue_not_rejection(self, monkeypatch):
        """容量已满时新提交进队列（depth>0），提交仍返回 True 由前端按异步契约等待。"""
        capacity = gen_mod.Config.REPORT_GEN_MAX_WORKERS
        release = threading.Event()
        started = threading.Event()
        running = []

        def _fake_async(task_id, name, description, lock):
            running.append(task_id)
            if len(running) == capacity:
                started.set()
            release.wait(10)

        monkeypatch.setattr(
            gen_mod.ReportTaskGenerator, '_generate_task_report_async',
            staticmethod(_fake_async))
        monkeypatch.setattr(gen_mod, 'log_and_emit', lambda *a, **kw: None)

        task_ids = [1600 + i for i in range(capacity + 1)]
        try:
            for task_id in task_ids:
                assert gen_mod._submit_generation(
                    task_id, FakeLock(), None, None, '[int1505] submit') is True
            assert started.wait(10), '配置容量的工作线程未能同时开工'
            deadline = time.time() + 5
            while not gen_mod._executor_queue_depth() and time.time() < deadline:
                time.sleep(0.02)
            assert gen_mod._executor_queue_depth() == 1
        finally:
            release.set()
            for task_id in task_ids:
                gen_mod._generation_tracker.finish(task_id)


class TestPoolObservability:
    """可观测：容量 / 存活线程 / 队列深度 / 在途任务。"""

    def test_executor_status_reports_capacity_and_depth(self, monkeypatch):
        monkeypatch.setattr(
            gen_mod, '_report_executor',
            _FakeExecutor(max_workers=8, queued=2, workers=[True, True, False]))
        gen_mod._generation_tracker.mark_submitted(31)
        gen_mod._generation_tracker.mark_submitted(32)

        status = gen_mod._executor_status()
        assert status == {
            'max_workers': 8,
            'workers': 2,
            'queued': 2,
            'in_flight': 2,
        }

    def test_executor_status_degrades_when_private_attrs_missing(self, monkeypatch):
        class _Bare:
            pass

        monkeypatch.setattr(gen_mod, '_report_executor', _Bare())
        status = gen_mod._executor_status()
        assert status['max_workers'] is None
        assert status['workers'] is None
        assert status['queued'] is None
        assert status['in_flight'] == 0

    def test_report_generation_status_lists_in_flight_tasks(self, monkeypatch):
        monkeypatch.setattr(
            gen_mod, '_report_executor',
            _FakeExecutor(max_workers=8, queued=0, workers=[True]))
        gen_mod._generation_tracker.mark_submitted(41)

        status = gen_mod.report_generation_status()
        assert status['max_workers'] == 8
        assert status['task_ids'] == [41]

    def test_watchdog_queue_warning_includes_capacity_and_depth(self, monkeypatch):
        now = {'t': 1000.0}
        monkeypatch.setattr(gen_mod, '_now', lambda: now['t'])
        logs = []
        monkeypatch.setattr(
            gen_mod, 'log_and_emit',
            lambda level, module, content, **kw: logs.append((level, content)))
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_TIMEOUT_SECONDS', 900)
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_QUEUE_STUCK_SECONDS', 120)
        monkeypatch.setattr(
            gen_mod, '_report_executor',
            _FakeExecutor(max_workers=8, queued=3, workers=[True, True, True]))

        gen_mod._generation_tracker.mark_submitted(51)
        now['t'] += 121
        gen_mod._watchdog_scan_once()

        warnings = [c for lv, c in logs if lv == 'WARNING']
        assert len(warnings) == 1
        assert '排队' in warnings[0]
        assert 'max_workers=8' in warnings[0]
        assert '队列深度=3' in warnings[0]
        assert '在途生成=1' in warnings[0]


class TestHealthExposesPoolStatus:
    """/health 暴露 report_generation 快照（不启 lifespan，直接调用路由端点）。"""

    def test_health_payload_contains_report_generation(self, monkeypatch):
        from report_service.app import create_app

        monkeypatch.setattr(
            gen_mod, '_report_executor',
            _FakeExecutor(max_workers=8, queued=1, workers=[True]))
        gen_mod._generation_tracker.mark_submitted(61)

        app = create_app()
        health_route = next(
            route for route in app.routes if getattr(route, 'path', None) == '/health')
        payload = health_route.endpoint()

        assert payload['status'] == 'ok'
        assert payload['service'] == 'report_service'
        gen_status = payload['report_generation']
        assert gen_status['max_workers'] == 8
        assert gen_status['queued'] == 1
        assert gen_status['task_ids'] == [61]
