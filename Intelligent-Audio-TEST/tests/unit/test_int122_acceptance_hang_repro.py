# -*- coding: utf-8 -*-
"""INT-122 测试工程师独立验收：真实挂起复现——真实线程池 + 真实看门狗循环。

开发侧 test_int122_compare_generation_watchdog.py 以注入时钟直接调用
_compare_watchdog_scan_once 验证判定逻辑；本文件补验收盲区——**端到端复现事故场景**：

1. 二次对比链路（异步）：真实 ThreadPoolExecutor 工作线程在报告校验阶段真实阻塞
   （模拟事故中 gRPC/DB 永久挂起），真实看门狗循环线程触发：CRITICAL 日志 +
   栈转储**指向真实卡死行** + secondary_compare_generated 失败事件（status=timeout，
   仅一次）；持续卡死按时长倍增退避升 WARNING；解除阻塞后按失败路径收敛、
   去重标记释放、轨迹清理、不再多报。
2. 对比链路（同步）：请求线程在任务校验阶段真实阻塞，看门狗同样观测
   （CRITICAL + 栈转储），但**不**发事件（同步链路由 HTTP 调用方直接感知，
   无既定事件契约）；解除后按失败收敛。
3. 真实队列饥饿：3 个工作线程被占满时新提交滞留 QUEUED——提交侧队列深度 WARNING +
   看门狗饥饿告警（事故第二症状「后续提交全部无产出」的可观察性）。
4. 看门狗扫描异常自捕获，循环线程不死。
5. start/stop 幂等（lifespan 反复启停不叠线、不留僵尸线程）。
不依赖真实等待超时长：阈值全部调至亚秒级，用轮询 Deadline 等待，总耗时 < 15s。
"""
import os
import threading
import time

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import report_service.application.services.report_compare_generator as cmp_mod


def _wait_until(cond, timeout=8.0, interval=0.02, msg=''):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(interval)
    raise AssertionError(f'条件未在 {timeout}s 内满足: {msg}')


@pytest.fixture(autouse=True)
def _isolate_globals():
    """每个用例独立轨迹注册表与去重字典；用例结束停看门狗、等线程退出、复位全局。"""
    cmp_mod._secondary_generation_tracker = cmp_mod.GenerationTracker()
    cmp_mod._generating_secondary.clear()
    yield
    cmp_mod.stop_compare_generation_watchdog()
    th = cmp_mod._compare_watchdog_thread
    if th is not None and th is not threading.current_thread():
        th.join(timeout=3)
        assert not th.is_alive(), '对比看门狗线程未在 3s 内退出'
    cmp_mod._compare_watchdog_thread = None
    cmp_mod._compare_watchdog_stop_event.clear()
    cmp_mod._secondary_generation_tracker = cmp_mod.GenerationTracker()
    cmp_mod._generating_secondary.clear()


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

        monkeypatch.setattr(cmp_mod, 'log_and_emit', _log)
        monkeypatch.setattr(cmp_mod, '_emit_secondary_compare_event', _emit)
        monkeypatch.setattr(cmp_mod.Config, 'REPORT_GEN_TIMEOUT_SECONDS', timeout)
        monkeypatch.setattr(cmp_mod.Config, 'REPORT_GEN_QUEUE_STUCK_SECONDS', queue_stuck)
        monkeypatch.setattr(cmp_mod.Config, 'REPORT_GEN_SLOW_STAGE_SECONDS', 60)
        monkeypatch.setattr(cmp_mod.Config, 'REPORT_GEN_WATCHDOG_INTERVAL_SECONDS', interval)
        self.timeout = timeout

    def events_for(self, report_ids):
        with self._log_lock:
            return [e for _, e in self.events if e.get('reportIds') == list(report_ids)]

    def logs_for(self, track_id, level=None):
        with self._log_lock:
            out = []
            for lv, content, kw_task_id in self.logs:
                matched = kw_task_id == track_id or f'task_id={track_id}' in content
                if matched and (level is None or lv == level):
                    out.append((lv, content))
            return out


class TestSecondaryRealHangReproduction:
    """二次对比链路事故场景端到端复现：工作线程真实阻塞，看门狗真实循环发现并上报。"""

    def test_hung_worker_detected_with_stack_pointing_at_hang_site(self, monkeypatch):
        cap = _Capture(monkeypatch, timeout=0.6, interval=0.05)
        hang = threading.Event()
        release = threading.Event()

        def _int122_hang_site(report_ids):
            """模拟事故卡死点：报告校验阶段内 gRPC/DB 调用永久阻塞。"""
            hang.set()
            release.wait(timeout=10)
            return (None, None, None, '超时解除后收敛')

        monkeypatch.setattr(
            cmp_mod.ReportCompareHelpers, '_validate_reports_and_get_tasks',
            staticmethod(_int122_hang_site))
        cmp_mod.start_compare_generation_watchdog()

        result = cmp_mod.ReportCompareGenerator.secondary_compare([7, 8], None)
        assert result['success'] is True
        assert result['data']['status'] == 'generating'

        # 工作线程真实取走任务并进入卡死阶段；去重标记由卡死线程持有
        _wait_until(lambda: hang.is_set(), msg='工作线程未进入卡死点')
        track_id = 'secondary:7,8'
        _wait_until(
            lambda: cmp_mod._secondary_generation_tracker.current_stage(track_id)
            == 'validate_reports',
            msg='轨迹未推进到 validate_reports')
        assert (7, 8) in cmp_mod._generating_secondary

        # 看门狗真实循环应在超时阈值后判卡死：CRITICAL + 栈转储 + 失败事件（status=timeout）
        _wait_until(
            lambda: len(cap.events_for([7, 8])) == 1
            and cap.events_for([7, 8])[0].get('status') == 'timeout',
            msg='看门狗未在阈值后上报超时失败事件')
        criticals = cap.logs_for(track_id, 'CRITICAL')
        assert len(criticals) >= 1
        content = criticals[0][1]
        assert '卡死' in content
        assert '调用栈' in content
        assert 'validate_reports' in content, 'CRITICAL 未指明卡住阶段'
        # 核心验收：栈转储必须指向真实卡死行（阻塞函数名出现在转储中）
        assert '_int122_hang_site' in content, '栈转储未定位到真实卡死函数'
        # 卡死文案须提示去重标记被卡死线程持有的残余影响（运维处置依据）
        assert '_generating_secondary' in content

        # 持续卡死不重复上报 timeout 事件；随后按倍增退避升 WARNING
        deadline = time.monotonic() + cap.timeout * 3 + 1.0
        while time.monotonic() < deadline:
            time.sleep(0.05)
        timeout_events = [e for e in cap.events_for([7, 8]) if e.get('status') == 'timeout']
        assert len(timeout_events) == 1, '超时失败事件被重复上报'
        _wait_until(
            lambda: any('仍在生成中' in c for _, c in cap.logs_for(track_id, 'WARNING')),
            timeout=4, msg='持续卡死未按退避升 WARNING')

        # 解除阻塞：工作线程按失败路径收敛（ERROR + 失败事件 + 轨迹清理 + 去重标记释放）
        release.set()
        _wait_until(
            lambda: cmp_mod._secondary_generation_tracker.snapshot() == [],
            msg='解除阻塞后轨迹未清理')
        _wait_until(lambda: (7, 8) not in cmp_mod._generating_secondary,
                    msg='去重标记未在解除阻塞后释放')
        errors = cap.logs_for(track_id, 'ERROR')
        assert len(errors) >= 1
        assert '超时解除后收敛' in errors[-1][1]
        all_events = cap.events_for([7, 8])
        assert len(all_events) == 2, f'期望 timeout+validation 两条事件，实际 {len(all_events)}'
        assert all_events[-1]['success'] is False
        assert all_events[-1]['error'] == '超时解除后收敛'

        # 轨迹已移除：看门狗不再对该任务产生任何新输出
        logs_after = len(cap.logs_for(track_id))
        events_after = len(cap.events_for([7, 8]))
        time.sleep(0.3)
        assert len(cap.logs_for(track_id)) == logs_after
        assert len(cap.events_for([7, 8])) == events_after


class TestCompareSyncHangObservation:
    """同步对比链路：请求线程卡死同样被看门狗观测，但无事件契约。"""

    def test_sync_hang_critical_logged_without_event(self, monkeypatch):
        cap = _Capture(monkeypatch, timeout=0.6, interval=0.05)
        hang = threading.Event()
        release = threading.Event()

        def _int122_sync_hang_site(task_ids):
            """模拟事故卡死点：任务校验阶段内 gRPC 调用永久阻塞（请求线程内）。"""
            hang.set()
            release.wait(timeout=10)
            return (None, '超时解除后收敛')

        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_validate_and_get_tasks',
            staticmethod(_int122_sync_hang_site))
        cmp_mod.start_compare_generation_watchdog()

        result_box = {}

        def _run():
            result_box.update(cmp_mod.ReportCompareGenerator.compare([1, 2], 'n'))

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()

        _wait_until(lambda: hang.is_set(), msg='请求线程未进入卡死点')
        snap = cmp_mod._secondary_generation_tracker.snapshot()
        assert len(snap) == 1
        track_id = snap[0]['task_id']
        assert track_id.startswith('compare:1,2:')
        _wait_until(
            lambda: cmp_mod._secondary_generation_tracker.current_stage(track_id)
            == 'validate_task',
            msg='轨迹未推进到 validate_task')

        # 看门狗对同步链路同样 CRITICAL + 栈转储指向真实卡死行
        _wait_until(
            lambda: len(cap.logs_for(track_id, 'CRITICAL')) >= 1,
            msg='看门狗未对同步链路卡死发 CRITICAL')
        content = cap.logs_for(track_id, 'CRITICAL')[0][1]
        assert '卡死' in content
        assert '_int122_sync_hang_site' in content, '栈转储未定位到真实卡死函数'

        # 同步链路无既定事件契约：全程零事件（不另造载荷）
        time.sleep(cap.timeout + 0.4)
        assert cap.events == [], '同步链路不应上报失败事件'

        # 解除阻塞：请求线程按失败收敛、轨迹清理
        release.set()
        worker.join(timeout=10)
        assert not worker.is_alive(), 'compare 调用未在解除阻塞后返回'
        assert result_box['success'] is False
        assert result_box['message'] == '超时解除后收敛'
        errors = cap.logs_for(track_id, 'ERROR')
        assert any('任务验证失败' in c for _, c in errors)
        _wait_until(
            lambda: cmp_mod._secondary_generation_tracker.snapshot() == [],
            msg='解除阻塞后轨迹未清理')


class TestRealQueueStarvation:
    """真实队列饥饿：工作线程占满 → 新提交滞留 QUEUED → 双侧可观察。"""

    def test_queued_submission_reports_starvation_when_workers_saturated(self, monkeypatch):
        cap = _Capture(monkeypatch, timeout=5.0, queue_stuck=0.25, interval=0.05)

        # 占满全部 3 个工作线程（真实线程池饥饿）
        saturate = threading.Event()
        saturated = []

        def _occupy():
            saturated.append(threading.get_ident())
            saturate.wait(timeout=10)

        futures = [cmp_mod._secondary_executor.submit(_occupy) for _ in range(3)]
        try:
            _wait_until(lambda: len(saturated) == 3, msg='3 个工作线程未被占满')

            def _validate(report_ids):
                return (None, None, None, '饥饿解除后收敛')

            monkeypatch.setattr(
                cmp_mod.ReportCompareHelpers, '_validate_reports_and_get_tasks',
                staticmethod(_validate))
            cmp_mod.start_compare_generation_watchdog()

            result = cmp_mod.ReportCompareGenerator.secondary_compare([7, 8], None)
            assert result['success'] is True

            # 提交侧队列深度 WARNING + 看门狗 QUEUED 滞留饥饿告警
            submit_warnings = [c for lv, c, _ in cap.logs
                               if '待执行队列深度' in c]
            _wait_until(
                lambda: any('排队' in c for _, c in cap.logs_for('secondary:7,8', 'WARNING')),
                msg='看门狗未对 QUEUED 滞留发饥饿告警')
            assert len(submit_warnings) >= 1, '提交侧未打印队列深度 WARNING'
            assert cmp_mod._secondary_generation_tracker.current_stage('secondary:7,8') == 'queued'
        finally:
            saturate.set()
            for f in futures:
                f.result(timeout=10)

        # 解除占满后滞留任务执行并按失败路径收敛（不再"无产出"）
        _wait_until(lambda: (7, 8) not in cmp_mod._generating_secondary,
                    msg='滞留任务未在占满解除后执行收敛')
        _wait_until(lambda: cmp_mod._secondary_generation_tracker.snapshot() == [],
                    msg='饥饿解除后轨迹未清理')
        assert any(e.get('success') is False for e in cap.events_for([7, 8]))


class TestCompareWatchdogLoopResilience:
    """看门狗循环自身的存活能力。"""

    def test_scan_exception_does_not_kill_loop(self, monkeypatch):
        cap = _Capture(monkeypatch, interval=0.05)
        calls = []
        real_scan = cmp_mod._compare_watchdog_scan_once

        def _flaky_scan():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('注入的扫描异常')
            real_scan()

        monkeypatch.setattr(cmp_mod, '_compare_watchdog_scan_once', _flaky_scan)
        thread = cmp_mod.start_compare_generation_watchdog()
        _wait_until(lambda: len(calls) >= 4, msg='扫描异常后看门狗循环未继续扫描')
        assert thread.is_alive()
        errors = [c for lv, c, _ in cap.logs if lv == 'ERROR' and '扫描异常' in c]
        assert len(errors) >= 1, '扫描异常未被捕获上报'


class TestCompareWatchdogLifecycle:
    """lifespan 启停契约：幂等、可反复启停。"""

    def test_start_idempotent_and_restarts_after_stop(self):
        t1 = cmp_mod.start_compare_generation_watchdog()
        t2 = cmp_mod.start_compare_generation_watchdog()
        assert t1 is t2, '重复启动产生了第二个看门狗线程'
        assert t1.is_alive()
        assert t1.daemon, '看门狗必须是守护线程'

        cmp_mod.stop_compare_generation_watchdog()
        t1.join(timeout=3)
        assert not t1.is_alive()

        t3 = cmp_mod.start_compare_generation_watchdog()
        assert t3 is not t1 and t3.is_alive(), '停止后无法重新启动看门狗'
