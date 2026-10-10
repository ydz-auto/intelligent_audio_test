# -*- coding: utf-8 -*-
"""INT-117 测试工程师独立验收：真实挂起复现——真实线程池 + 真实看门狗循环。

开发侧 test_int117_report_generation_watchdog.py 以注入时钟直接调用内部函数，
验证判定逻辑；本文件补验收盲区——**端到端复现事故场景**：

1. 真实 ThreadPoolExecutor 工作线程在阶段内真实阻塞（模拟事故中 gRPC/DB 永久挂起），
   真实看门狗循环线程触发：CRITICAL 日志 + 栈转储**指向真实卡死行** + report_generated
   失败事件（一次）；持续卡死按时长倍增退避升 WARNING；解除阻塞后轨迹清理、锁释放、
   不再多报。
2. 看门狗扫描异常自捕获，循环线程不死（持续观测能力不因单次异常失效）。
3. start/stop 幂等（lifespan 反复启停不叠线、不留僵尸线程）。
4. 真实队列饥饿：3 个工作线程被占满时新提交滞留 QUEUED——提交侧队列深度 WARNING +
   看门狗饥饿告警（事故第二症状「后续提交全部无产出」的可观察性）。
不依赖真实等待超时长：阈值全部调至亚秒级，用轮询 Deadline 等待，总耗时 < 10s。
"""
import os
import threading
import time

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
        self.release_count = 0

    def release(self):
        self.released = True
        self.release_count += 1


def _wait_until(cond, timeout=8.0, interval=0.02, msg=''):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(interval)
    raise AssertionError(f'条件未在 {timeout}s 内满足: {msg}')


@pytest.fixture(autouse=True)
def _isolate_globals():
    """每个用例独立轨迹注册表；用例结束停看门狗、等线程退出、复位全局。"""
    gen_mod._generation_tracker = gen_mod.GenerationTracker()
    yield
    gen_mod.stop_generation_watchdog()
    th = gen_mod._watchdog_thread
    if th is not None and th is not threading.current_thread():
        th.join(timeout=3)
        assert not th.is_alive(), '看门狗线程未在 3s 内退出'
    gen_mod._watchdog_thread = None
    gen_mod._watchdog_stop_event.clear()
    gen_mod._generation_tracker = gen_mod.GenerationTracker()


class _Capture:
    """日志/事件捕获 + 亚秒阈值配置注入（真实时钟，不注入 _now）。"""

    def __init__(self, monkeypatch, timeout=0.6, queue_stuck=0.25, interval=0.05):
        self.logs = []
        self.events = []
        self._log_lock = threading.Lock()

        def _log(level, module, content, **kw):
            with self._log_lock:
                self.logs.append((level, content, kw.get('task_id')))

        def _emit(name, data):
            with self._log_lock:
                self.events.append((name, dict(data)))

        monkeypatch.setattr(gen_mod, 'log_and_emit', _log)
        monkeypatch.setattr(gen_mod, '_emit_report_event', _emit)
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_TIMEOUT_SECONDS', timeout)
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_QUEUE_STUCK_SECONDS', queue_stuck)
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_SLOW_STAGE_SECONDS', 60)
        monkeypatch.setattr(gen_mod.Config, 'REPORT_GEN_WATCHDOG_INTERVAL_SECONDS', interval)
        self.timeout = timeout

    def events_for(self, task_id):
        with self._log_lock:
            return [e for _, e in self.events if e.get('taskId') == task_id]

    def logs_for(self, task_id, level=None):
        with self._log_lock:
            out = []
            for lv, content, kw_task_id in self.logs:
                matched = kw_task_id == task_id or f'task_id={task_id}' in content
                if matched and (level is None or lv == level):
                    out.append((lv, content))
            return out


def _stub_submit_dependencies(monkeypatch, task_id, lock, validate_fn):
    """generate_task_report 外部依赖替换：任务存在/completed、无既有报告、锁可用。"""
    monkeypatch.setattr(
        gen_mod, '_grpc_get_tasks_by_ids',
        lambda ids: [{'id': task_id, 'status': TaskStatus.COMPLETED.value}])
    monkeypatch.setattr(
        gen_mod.report_repository, 'get_report_by_task_id_raw',
        lambda tid: None)
    monkeypatch.setattr(gen_mod, '_acquire_generation_lock', lambda tid: lock)
    monkeypatch.setattr(
        gen_mod.ReportDataBuilder, '_validate_task_and_get_results',
        staticmethod(validate_fn))


class TestRealHangReproduction:
    """事故场景端到端复现：工作线程真实阻塞，看门狗真实循环发现并上报。"""

    def test_hung_worker_detected_with_stack_pointing_at_hang_site(self, monkeypatch):
        cap = _Capture(monkeypatch, timeout=0.6, interval=0.05)
        hang = threading.Event()
        release = threading.Event()
        lock = FakeLock()
        task_id = 31

        def _int117_hang_site(tid):
            """模拟事故卡死点：验证阶段内 gRPC/DB 调用永久阻塞。"""
            hang.set()
            release.wait(timeout=10)
            return (None, None, ({'success': False, 'message': '解除后按失败收敛'}, 400))

        _stub_submit_dependencies(monkeypatch, task_id, lock, _int117_hang_site)
        gen_mod.start_generation_watchdog()

        result = gen_mod.ReportTaskGenerator.generate_task_report(task_id)
        assert result['success'] is True
        assert result['data']['status'] == 'generating'

        # 工作线程真实取走任务并进入卡死阶段
        _wait_until(lambda: hang.is_set(), msg='工作线程未进入卡死点')
        _wait_until(
            lambda: gen_mod._generation_tracker.current_stage(task_id)
            == GenerationStage.VALIDATE_TASK.value,
            msg='轨迹未推进到 validate_task')

        # 看门狗真实循环应在超时阈值后判卡死：CRITICAL + 栈转储 + 失败事件
        _wait_until(
            lambda: len(cap.events_for(task_id)) == 1
            and cap.events_for(task_id)[0].get('status') == 'timeout',
            msg='看门狗未在阈值后上报超时失败事件')
        criticals = cap.logs_for(task_id, 'CRITICAL')
        assert len(criticals) >= 1
        content = criticals[0][1]
        assert '卡死' in content
        assert '调用栈' in content
        # 核心验收：栈转储必须指向真实卡死行（阻塞函数名出现在转储中）
        assert '_int117_hang_site' in content, '栈转储未定位到真实卡死函数'

        # 持续卡死不重复上报 timeout 事件；随后按倍增退避升 WARNING
        deadline = time.monotonic() + cap.timeout * 2 + 1.0
        while time.monotonic() < deadline:
            time.sleep(0.05)
        timeout_events = [e for e in cap.events_for(task_id) if e.get('status') == 'timeout']
        assert len(timeout_events) == 1, '超时失败事件被重复上报'
        backoff_warnings = [c for _, c in cap.logs_for(task_id, 'WARNING') if '仍在生成中' in c]
        assert len(backoff_warnings) >= 1, '持续卡死未按退避升 WARNING'

        # 解除阻塞：工作线程按失败路径收敛（ERROR + 失败事件 + 轨迹清理 + 锁释放）
        release.set()
        _wait_until(lambda: lock.released, msg='去重锁未在解除阻塞后释放')
        _wait_until(
            lambda: gen_mod._generation_tracker.snapshot() == [],
            msg='解除阻塞后轨迹未清理')
        assert len(cap.logs_for(task_id, 'ERROR')) >= 1
        validation_failures = [e for e in cap.events_for(task_id)
                               if e.get('status') != 'timeout' and e.get('success') is False]
        assert len(validation_failures) == 1
        assert '解除后按失败收敛' in validation_failures[0]['error']

        # 轨迹已移除：看门狗不再对该任务产生任何新输出
        logs_after = len(cap.logs_for(task_id))
        events_after = len(cap.events_for(task_id))
        time.sleep(0.3)
        assert len(cap.logs_for(task_id)) == logs_after
        assert len(cap.events_for(task_id)) == events_after

    def test_queued_submission_reports_starvation_when_workers_saturated(self, monkeypatch):
        cap = _Capture(monkeypatch, timeout=5.0, queue_stuck=0.25, interval=0.05)
        task_id = 42
        lock = FakeLock()

        # 占满全部 3 个工作线程（真实线程池饥饿）
        saturate = threading.Event()
        saturated = []

        def _occupy():
            saturated.append(threading.get_ident())
            saturate.wait(timeout=10)

        futures = [gen_mod._report_executor.submit(_occupy) for _ in range(3)]
        _wait_until(lambda: len(saturated) == 3, msg='3 个工作线程未被占满')

        def _validate(tid):
            return (None, None, ({'success': False, 'message': '饥饿解除后收敛'}, 400))

        _stub_submit_dependencies(monkeypatch, task_id, lock, _validate)
        gen_mod.start_generation_watchdog()

        result = gen_mod.ReportTaskGenerator.generate_task_report(task_id)
        assert result['success'] is True

        # 提交侧队列深度 WARNING + 看门狗 QUEUED 滞留饥饿告警
        submit_warnings = [c for _, c, _ in cap.logs if '待执行队列深度' in c]
        _wait_until(
            lambda: any('排队' in c for _, c in cap.logs_for(task_id, 'WARNING')),
            msg='看门狗未对 QUEUED 滞留发饥饿告警')
        assert len(submit_warnings) >= 1, '提交侧未打印队列深度 WARNING'
        assert gen_mod._generation_tracker.current_stage(task_id) == GenerationStage.QUEUED.value

        # 解除占满后滞留任务执行并按失败路径收敛（不再"无产出"）
        saturate.set()
        for f in futures:
            f.result(timeout=10)
        _wait_until(lambda: lock.released, msg='滞留任务未在占满解除后执行')
        _wait_until(lambda: gen_mod._generation_tracker.snapshot() == [],
                    msg='饥饿解除后轨迹未清理')
        assert any(e.get('success') is False for e in cap.events_for(task_id))


class TestWatchdogLoopResilience:
    """看门狗循环自身的存活能力。"""

    def test_scan_exception_does_not_kill_loop(self, monkeypatch):
        cap = _Capture(monkeypatch, interval=0.05)
        calls = []
        real_scan = gen_mod._watchdog_scan_once

        def _flaky_scan():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('注入的扫描异常')
            real_scan()

        monkeypatch.setattr(gen_mod, '_watchdog_scan_once', _flaky_scan)
        thread = gen_mod.start_generation_watchdog()
        _wait_until(lambda: len(calls) >= 4, msg='扫描异常后看门狗循环未继续扫描')
        assert thread.is_alive()
        errors = [c for lv, c, _ in cap.logs if lv == 'ERROR' and '扫描异常' in c]
        assert len(errors) >= 1, '扫描异常未被捕获上报'


class TestWatchdogLifecycle:
    """lifespan 启停契约：幂等、可反复启停。"""

    def test_start_idempotent_and_restarts_after_stop(self):
        t1 = gen_mod.start_generation_watchdog()
        t2 = gen_mod.start_generation_watchdog()
        assert t1 is t2, '重复启动产生了第二个看门狗线程'
        assert t1.is_alive()
        assert t1.daemon, '看门狗必须是守护线程'

        gen_mod.stop_generation_watchdog()
        t1.join(timeout=3)
        assert not t1.is_alive()

        t3 = gen_mod.start_generation_watchdog()
        assert t3 is not t1 and t3.is_alive(), '停止后无法重新启动看门狗'
