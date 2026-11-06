# -*- coding: utf-8 -*-
"""INT-117 专项：报告生成静默挂起 — 卡死可观察、失败可上报。

覆盖：
- GenerationTracker 轨迹生命周期（提交/推进阶段/结束移除）
- 看门狗超时判定：CRITICAL 日志（含工作线程调用栈）+ report_generated 失败事件
  仅上报一次，后续扫描按时长倍增退避升级 WARNING
- 队列饥饿：QUEUED 停留超阈值告警一次；滞留至超时同样上报失败事件
- 生成失败路径不再静默：验证失败 ERROR 日志 + 失败事件（带真实错误原因）
- 成功流程阶段埋点贯通、轨迹清理、锁释放
- 线程池提交失败：回收轨迹与锁 + 失败事件 + 明确失败返回
时钟经 monkeypatch gen_mod._now 注入，不依赖真实等待。
"""
import os
import threading

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import report_service.application.services.report_task_generator as gen_mod
from report_service.domain.entities.report import GenerationStage
from shared.models.common_enums import TaskStatus


class FakeLock:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class _T:
    """时间与捕获桩：统一控制 _now 并收集日志/事件。"""

    def __init__(self, monkeypatch, timeout=900, queue_stuck=120):
        self.t = 1000.0
        monkeypatch.setattr(gen_mod, '_now', lambda: self.t)
        self.logs = []
        self.events = []

        def _log(level, module, content, **kw):
            self.logs.append((level, content, kw.get('task_id')))

        monkeypatch.setattr(gen_mod, 'log_and_emit', _log)
        monkeypatch.setattr(
            gen_mod, '_emit_report_event',
            lambda name, data: self.events.append((name, data)))
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_TIMEOUT_SECONDS', timeout)
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_QUEUE_STUCK_SECONDS', queue_stuck)
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_SLOW_STAGE_SECONDS', 60)

    def advance(self, seconds):
        self.t += seconds

    def events_for(self, task_id):
        return [e for _, e in self.events if e.get('taskId') == task_id]

    def logs_for(self, task_id, level=None):
        out = []
        for lv, content, kw_task_id in self.logs:
            matched = kw_task_id == task_id or f'task_id={task_id}' in content
            if matched and (level is None or lv == level):
                out.append((lv, content))
        return out


@pytest.fixture(autouse=True)
def _clean_tracker():
    gen_mod._generation_tracker = gen_mod.GenerationTracker()
    yield
    gen_mod._generation_tracker = gen_mod.GenerationTracker()


class TestGenerationTracker:
    """轨迹注册表生命周期。"""

    def test_mark_submitted_enters_queued(self):
        gen_mod._generation_tracker.mark_submitted(1)
        snap = gen_mod._generation_tracker.snapshot()
        assert len(snap) == 1
        assert snap[0]['stage'] == GenerationStage.QUEUED.value
        assert snap[0]['thread_id'] is None

    def test_mark_stage_advances_and_records_thread(self):
        gen_mod._generation_tracker.mark_submitted(1)
        gen_mod._generation_tracker.mark_stage(
            1, GenerationStage.VALIDATE_TASK, thread_id=threading.get_ident())
        snap = gen_mod._generation_tracker.snapshot()
        assert snap[0]['stage'] == GenerationStage.VALIDATE_TASK.value
        assert snap[0]['thread_id'] == threading.get_ident()

    def test_current_stage_unknown_task_defaults_queued(self):
        assert gen_mod._generation_tracker.current_stage(99) == GenerationStage.QUEUED.value

    def test_finish_removes_entry(self):
        gen_mod._generation_tracker.mark_submitted(1)
        gen_mod._generation_tracker.finish(1)
        assert gen_mod._generation_tracker.snapshot() == []


class TestWatchdogTimeout:
    """看门狗超时判定：CRITICAL + 栈转储 + 失败事件一次。"""

    def test_timeout_emits_critical_and_event_once(self, monkeypatch):
        t = _T(monkeypatch, timeout=900)
        gen_mod._generation_tracker.mark_submitted(1)
        gen_mod._generation_tracker.mark_stage(
            1, GenerationStage.PREPARE_DATA, thread_id=threading.get_ident())

        t.advance(901)
        gen_mod._watchdog_scan_once()

        events = t.events_for(1)
        assert len(events) == 1
        assert events[0]['success'] is False
        assert events[0]['status'] == 'timeout'
        assert GenerationStage.PREPARE_DATA.value in events[0]['error']

        criticals = t.logs_for(1, 'CRITICAL')
        assert len(criticals) == 1
        content = criticals[0][1]
        assert '卡死' in content
        assert '调用栈' in content
        # 栈转储取自工作线程当前帧，应含真实代码帧
        assert 'File' in content

        # 再次扫描不重复上报事件
        gen_mod._watchdog_scan_once()
        assert len(t.events_for(1)) == 1

    def test_timeout_backoff_warning_doubles(self, monkeypatch):
        t = _T(monkeypatch, timeout=900)
        gen_mod._generation_tracker.mark_submitted(1)
        gen_mod._generation_tracker.mark_stage(
            1, GenerationStage.VALIDATE_TASK, thread_id=threading.get_ident())

        t.advance(901)
        gen_mod._watchdog_scan_once()  # 首次 CRITICAL + 事件
        assert len(t.logs_for(1, 'WARNING')) == 0

        t.advance(900)  # 总时长 1801 ≥ 900*2 → 第一次退避 WARNING
        gen_mod._watchdog_scan_once()
        assert len(t.logs_for(1, 'WARNING')) == 1

        t.advance(100)  # 未到下一个倍增点（900*4）→ 不再告警
        gen_mod._watchdog_scan_once()
        assert len(t.logs_for(1, 'WARNING')) == 1

    def test_normal_generation_not_flagged(self, monkeypatch):
        t = _T(monkeypatch, timeout=900)
        gen_mod._generation_tracker.mark_submitted(1)
        gen_mod._generation_tracker.mark_stage(
            1, GenerationStage.PERSIST_RECORD, thread_id=threading.get_ident())
        t.advance(120)
        gen_mod._watchdog_scan_once()
        assert t.events_for(1) == []
        assert t.logs_for(1, 'CRITICAL') == []


class TestWatchdogQueueStarvation:
    """队列饥饿：QUEUED 停留超阈值告警；滞留至超时上报失败事件。"""

    def test_queue_stuck_warns_once(self, monkeypatch):
        t = _T(monkeypatch, queue_stuck=120)
        gen_mod._generation_tracker.mark_submitted(2)

        t.advance(121)
        gen_mod._watchdog_scan_once()
        warnings = t.logs_for(2, 'WARNING')
        assert len(warnings) == 1
        assert '排队' in warnings[0][1]

        gen_mod._watchdog_scan_once()
        assert len(t.logs_for(2, 'WARNING')) == 1

    def test_queued_entry_eventually_times_out(self, monkeypatch):
        t = _T(monkeypatch, timeout=900, queue_stuck=120)
        gen_mod._generation_tracker.mark_submitted(3)

        t.advance(901)
        gen_mod._watchdog_scan_once()

        events = t.events_for(3)
        assert len(events) == 1
        assert events[0]['success'] is False
        assert events[0]['status'] == 'timeout'


class TestThreadStackProbe:
    """_thread_stack：卡死定位埋点。"""

    def test_current_thread_returns_stack(self):
        stack = gen_mod._thread_stack(threading.get_ident())
        assert 'File' in stack

    def test_none_thread_id_returns_queued_hint(self):
        assert 'queued' in gen_mod._thread_stack(None)

    def test_unknown_thread_id_returns_exited(self):
        assert gen_mod._thread_stack(999999999) == '<thread exited>'


class TestAsyncGenerationFailurePaths:
    """失败可上报：验证失败/数据准备失败不再静默。"""

    def test_validation_failure_logs_error_and_emits_event(self, monkeypatch):
        t = _T(monkeypatch)
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_validate_task_and_get_results',
            staticmethod(lambda task_id: (
                None, None, ({'success': False, 'message': '未找到指定任务'}, 400))))

        gen_mod._generation_tracker.mark_submitted(11)
        lock = FakeLock()
        gen_mod.ReportTaskGenerator._generate_task_report_async(11, 'n', None, lock)

        errors = t.logs_for(11, 'ERROR')
        assert len(errors) == 1
        assert '未找到指定任务' in errors[0][1]

        events = t.events_for(11)
        assert len(events) == 1
        assert events[0]['success'] is False
        assert events[0]['error'] == '未找到指定任务'
        assert lock.released
        assert gen_mod._generation_tracker.snapshot() == []

    def test_prepare_data_failure_logs_error(self, monkeypatch):
        t = _T(monkeypatch)
        task = {'id': 12, 'name': 't', 'status': 'completed'}
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_validate_task_and_get_results',
            staticmethod(lambda task_id: (task, [{'id': 1}], None)))
        monkeypatch.setattr(
            gen_mod.report_repository, 'get_report_by_task_id_raw',
            lambda task_id: None)
        # _prepare_report_data 内部已发失败事件并返回 None（历史行为），本次只验证补日志
        monkeypatch.setattr(
            gen_mod.ReportTaskGenerator, '_prepare_report_data',
            staticmethod(lambda task, task_id, results: None))

        gen_mod._generation_tracker.mark_submitted(12)
        gen_mod.ReportTaskGenerator._generate_task_report_async(12, 'n', None, FakeLock())

        assert len(t.logs_for(12, 'ERROR')) == 1
        assert gen_mod._generation_tracker.snapshot() == []


class TestAsyncGenerationSuccessFlow:
    """成功流程：阶段埋点贯通、事件携带 reportId、轨迹清理。"""

    def test_success_flow_marks_stages_and_cleans_tracker(self, monkeypatch):
        t = _T(monkeypatch)
        task = {'id': 13, 'name': 't', 'status': 'completed'}
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_validate_task_and_get_results',
            staticmethod(lambda task_id: (task, [{'id': 1}], None)))
        monkeypatch.setattr(
            gen_mod.report_repository, 'get_report_by_task_id_raw',
            lambda task_id: None)
        monkeypatch.setattr(
            gen_mod.ReportTaskGenerator, '_prepare_report_data',
            staticmethod(lambda task, task_id, results: {'k': 'v'}))
        monkeypatch.setattr(
            gen_mod.ReportTaskGenerator, '_build_task_summary',
            staticmethod(lambda task, task_id, results, data: {'summary': 1}))
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_create_report_record',
            staticmethod(lambda name, task_id, desc: 101))
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_create_report_summary',
            staticmethod(lambda report_id, task, summary: (1, 1)))
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_create_report_detail_data',
            staticmethod(lambda report_id, summary: (None, None)))
        update_status_calls = []
        monkeypatch.setattr(
            gen_mod.report_repository, 'update_status',
            lambda report_id, status: update_status_calls.append((report_id, status)))

        gen_mod._generation_tracker.mark_submitted(13)
        lock = FakeLock()
        gen_mod.ReportTaskGenerator._generate_task_report_async(13, '自定义名', None, lock)

        events = t.events_for(13)
        assert len(events) == 1
        assert events[0]['success'] is True
        assert events[0]['status'] == 'completed'
        assert events[0]['reportId'] == 101
        assert update_status_calls == [(101, 'published')]

        # QUEUED 由提交侧 mark_submitted 登记（无 span 日志），工作线程阶段须全部留痕
        # （VALIDATE_REPORTS 为 INT-122 对比链路专属阶段，任务报告链路不使用）
        worker_stages = [s for s in GenerationStage
                         if s not in (GenerationStage.QUEUED, GenerationStage.VALIDATE_REPORTS)]
        stages = [c for _, c, _ in t.logs if 'stage=' in c]
        for stage in worker_stages:
            assert any(f'stage={stage.value}' in c for c in stages), stage.value

        assert lock.released
        assert gen_mod._generation_tracker.snapshot() == []

    def test_exception_path_includes_stage_and_emits_event(self, monkeypatch):
        t = _T(monkeypatch)
        task = {'id': 14, 'name': 't', 'status': 'completed'}
        monkeypatch.setattr(
            gen_mod.ReportDataBuilder, '_validate_task_and_get_results',
            staticmethod(lambda task_id: (task, [{'id': 1}], None)))
        monkeypatch.setattr(
            gen_mod.report_repository, 'get_report_by_task_id_raw',
            lambda task_id: None)

        def _boom(task, task_id, results):
            raise RuntimeError('oss down')

        monkeypatch.setattr(
            gen_mod.ReportTaskGenerator, '_prepare_report_data',
            staticmethod(_boom))

        gen_mod._generation_tracker.mark_submitted(14)
        lock = FakeLock()
        gen_mod.ReportTaskGenerator._generate_task_report_async(14, 'n', None, lock)

        errors = t.logs_for(14, 'ERROR')
        assert len(errors) == 1
        assert f"stage={GenerationStage.PREPARE_DATA.value}" in errors[0][1]
        assert 'oss down' in errors[0][1]

        events = t.events_for(14)
        assert len(events) == 1
        assert events[0]['success'] is False
        assert lock.released
        assert gen_mod._generation_tracker.snapshot() == []


class TestSubmission:
    """提交侧：轨迹登记、队列深度观测、提交失败回收。"""

    def test_executor_queue_depth_helper(self, monkeypatch):
        class _FakeQueue:
            def qsize(self):
                return 2

        class _FakeExecutor:
            _work_queue = _FakeQueue()

        class _BareExecutor:
            pass

        monkeypatch.setattr(gen_mod, '_report_executor', _FakeExecutor())
        assert gen_mod._executor_queue_depth() == 2
        monkeypatch.setattr(gen_mod, '_report_executor', _BareExecutor())
        assert gen_mod._executor_queue_depth() is None

    def test_submit_success_registers_tracker_entry(self, monkeypatch):
        t = _T(monkeypatch)
        submitted = []

        class _FakeExecutor:
            def submit(self, fn, *args):
                submitted.append((fn, args))

        monkeypatch.setattr(gen_mod, '_report_executor', _FakeExecutor())
        lock = FakeLock()
        ok = gen_mod._submit_generation(21, lock, 'n', None, '[test] submit')

        assert ok is True
        assert len(submitted) == 1
        snap = gen_mod._generation_tracker.snapshot()
        assert len(snap) == 1
        assert snap[0]['task_id'] == 21
        assert snap[0]['stage'] == GenerationStage.QUEUED.value

    def test_submit_failure_releases_lock_and_reports(self, monkeypatch):
        t = _T(monkeypatch)

        class _BoomExecutor:
            def submit(self, fn, *args):
                raise RuntimeError('pool shutdown')

        monkeypatch.setattr(gen_mod, '_report_executor', _BoomExecutor())
        lock = FakeLock()
        ok = gen_mod._submit_generation(22, lock, None, None, '[test] submit')

        assert ok is False
        assert lock.released
        assert gen_mod._generation_tracker.snapshot() == []
        events = t.events_for(22)
        assert len(events) == 1
        assert events[0]['success'] is False
        assert '提交失败' in events[0]['error']
        assert len(t.logs_for(22, 'ERROR')) == 1

    def test_generate_task_report_returns_failure_when_submit_fails(self, monkeypatch):
        t = _T(monkeypatch)

        class _BoomExecutor:
            def submit(self, fn, *args):
                raise RuntimeError('pool shutdown')

        monkeypatch.setattr(gen_mod, '_report_executor', _BoomExecutor())
        monkeypatch.setattr(
            gen_mod, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': 23, 'status': TaskStatus.COMPLETED.value}])
        monkeypatch.setattr(
            gen_mod.report_repository, 'get_report_by_task_id_raw',
            lambda task_id: None)
        lock = FakeLock()
        monkeypatch.setattr(gen_mod, '_acquire_generation_lock', lambda task_id: lock)

        result = gen_mod.ReportTaskGenerator.generate_task_report(23)

        assert result['success'] is False
        assert lock.released
        assert gen_mod._generation_tracker.snapshot() == []
