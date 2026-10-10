# -*- coding: utf-8 -*-
"""INT-122 专项：对比报告生成静默挂起 — 卡死可观察、失败可上报（INT-117 同型）。

覆盖 report_service/application/services/report_compare_generator.py 两条链路：
- compare（同步）：阶段埋点贯通、失败路径 ERROR 日志、异常带卡住阶段、轨迹清理
- secondary_compare（异步）：看门狗超时判定（CRITICAL + 栈转储 + 失败事件仅一次）、
  队列饥饿告警、慢阶段 WARNING、验证/数据准备失败不再静默、提交失败回收轨迹与去重标记
时钟经 monkeypatch gen_mod._now 注入（cmp_mod._now 委托同一实现，单点控制），
不依赖真实等待；看门狗直接调用 _compare_watchdog_scan_once，不启动线程。
"""
import os
import threading

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import report_service.application.services.report_compare_generator as cmp_mod
import report_service.application.services.report_task_generator as gen_mod
from report_service.domain.entities.report import GenerationStage


class _T:
    """时间与捕获桩：统一控制时钟并收集日志/事件。"""

    def __init__(self, monkeypatch, timeout=900, queue_stuck=120):
        self.t = 1000.0
        monkeypatch.setattr(gen_mod, '_now', lambda: self.t)
        self.logs = []
        self.events = []

        def _log(level, module, content, **kw):
            self.logs.append((level, content, kw.get('task_id')))

        monkeypatch.setattr(cmp_mod, 'log_and_emit', _log)
        monkeypatch.setattr(
            cmp_mod, '_emit_secondary_compare_event',
            lambda name, data: self.events.append((name, data)))
        monkeypatch.setattr(cmp_mod.Config, 'REPORT_GEN_TIMEOUT_SECONDS', timeout)
        monkeypatch.setattr(cmp_mod.Config, 'REPORT_GEN_QUEUE_STUCK_SECONDS', queue_stuck)
        monkeypatch.setattr(cmp_mod.Config, 'REPORT_GEN_SLOW_STAGE_SECONDS', 60)

    def advance(self, seconds):
        self.t += seconds

    def events_for(self, report_ids):
        return [e for _, e in self.events if e.get('reportIds') == list(report_ids)]

    def logs_for(self, track_id, level=None):
        out = []
        for lv, content, kw_task_id in self.logs:
            matched = kw_task_id == track_id or f'task_id={track_id}' in content
            if matched and (level is None or lv == level):
                out.append((lv, content))
        return out

    def stage_logs(self):
        return [c for _, c, _ in self.logs if 'stage=' in c]


@pytest.fixture(autouse=True)
def _clean_state():
    cmp_mod._secondary_generation_tracker = cmp_mod.GenerationTracker()
    cmp_mod._generating_secondary.clear()
    yield
    cmp_mod._secondary_generation_tracker = cmp_mod.GenerationTracker()
    cmp_mod._generating_secondary.clear()


class TestTrackerMeta:
    """GenerationTracker meta 扩展（INT-122 失败事件载荷来源）。"""

    def test_mark_submitted_stores_meta(self):
        cmp_mod._secondary_generation_tracker.mark_submitted(
            'secondary:7,8', meta={'chain': 'secondary', 'reportIds': [7, 8]})
        snap = cmp_mod._secondary_generation_tracker.snapshot()
        assert snap[0]['meta'] == {'chain': 'secondary', 'reportIds': [7, 8]}
        assert snap[0]['stage'] == GenerationStage.QUEUED.value

    def test_mark_submitted_default_meta_empty(self):
        cmp_mod._secondary_generation_tracker.mark_submitted('k')
        snap = cmp_mod._secondary_generation_tracker.snapshot()
        assert snap[0]['meta'] == {}


class TestWatchdogTimeout:
    """看门狗超时判定：CRITICAL + 栈转储 + 失败事件一次（仅异步链路）。"""

    def test_secondary_timeout_emits_critical_and_event_once(self, monkeypatch):
        t = _T(monkeypatch, timeout=900)
        track_id = 'secondary:7,8'
        cmp_mod._secondary_generation_tracker.mark_submitted(
            track_id, meta={'chain': 'secondary', 'reportIds': [7, 8]})
        cmp_mod._secondary_generation_tracker.mark_stage(
            track_id, GenerationStage.PREPARE_DATA, thread_id=threading.get_ident())

        t.advance(901)
        cmp_mod._compare_watchdog_scan_once()

        events = t.events_for([7, 8])
        assert len(events) == 1
        assert events[0]['success'] is False
        assert events[0]['status'] == 'timeout'
        assert GenerationStage.PREPARE_DATA.value in events[0]['error']

        criticals = t.logs_for(track_id, 'CRITICAL')
        assert len(criticals) == 1
        content = criticals[0][1]
        assert '卡死' in content
        assert '调用栈' in content
        # 栈转储取自工作线程当前帧，应含真实代码帧
        assert 'File' in content

        # 再次扫描不重复上报事件
        cmp_mod._compare_watchdog_scan_once()
        assert len(t.events_for([7, 8])) == 1

    def test_compare_sync_timeout_no_event(self, monkeypatch):
        t = _T(monkeypatch, timeout=900)
        track_id = 'compare:1,2:abcd1234'
        cmp_mod._secondary_generation_tracker.mark_submitted(
            track_id, meta={'chain': 'compare', 'taskIds': [1, 2]})
        cmp_mod._secondary_generation_tracker.mark_stage(
            track_id, GenerationStage.VALIDATE_TASK, thread_id=threading.get_ident())

        t.advance(901)
        cmp_mod._compare_watchdog_scan_once()

        # 同步链路无既定事件契约：仅 CRITICAL 日志，不发事件
        assert t.events == []
        assert len(t.logs_for(track_id, 'CRITICAL')) == 1

    def test_timeout_backoff_warning_doubles(self, monkeypatch):
        t = _T(monkeypatch, timeout=900)
        track_id = 'secondary:7,8'
        cmp_mod._secondary_generation_tracker.mark_submitted(
            track_id, meta={'chain': 'secondary', 'reportIds': [7, 8]})
        cmp_mod._secondary_generation_tracker.mark_stage(
            track_id, GenerationStage.VALIDATE_REPORTS, thread_id=threading.get_ident())

        t.advance(901)
        cmp_mod._compare_watchdog_scan_once()  # 首次 CRITICAL + 事件
        assert len(t.logs_for(track_id, 'WARNING')) == 0

        t.advance(900)  # 总时长 1801 ≥ 900*2 → 第一次退避 WARNING
        cmp_mod._compare_watchdog_scan_once()
        assert len(t.logs_for(track_id, 'WARNING')) == 1

        t.advance(100)  # 未到下一个倍增点（900*4）→ 不再告警
        cmp_mod._compare_watchdog_scan_once()
        assert len(t.logs_for(track_id, 'WARNING')) == 1

    def test_normal_generation_not_flagged(self, monkeypatch):
        t = _T(monkeypatch, timeout=900)
        track_id = 'secondary:7,8'
        cmp_mod._secondary_generation_tracker.mark_submitted(
            track_id, meta={'chain': 'secondary', 'reportIds': [7, 8]})
        cmp_mod._secondary_generation_tracker.mark_stage(
            track_id, GenerationStage.PERSIST_RECORD, thread_id=threading.get_ident())
        t.advance(120)
        cmp_mod._compare_watchdog_scan_once()
        assert t.events == []
        assert t.logs_for(track_id, 'CRITICAL') == []


class TestWatchdogQueueStarvation:
    """队列饥饿：QUEUED 停留超阈值告警；滞留至超时上报失败事件。"""

    def test_queue_stuck_warns_once(self, monkeypatch):
        t = _T(monkeypatch, queue_stuck=120)
        track_id = 'secondary:7,8'
        cmp_mod._secondary_generation_tracker.mark_submitted(
            track_id, meta={'chain': 'secondary', 'reportIds': [7, 8]})

        t.advance(121)
        cmp_mod._compare_watchdog_scan_once()
        warnings = t.logs_for(track_id, 'WARNING')
        assert len(warnings) == 1
        assert '排队' in warnings[0][1]
        assert '队列深度' in warnings[0][1]

        cmp_mod._compare_watchdog_scan_once()
        assert len(t.logs_for(track_id, 'WARNING')) == 1

    def test_queued_entry_eventually_times_out(self, monkeypatch):
        t = _T(monkeypatch, timeout=900, queue_stuck=120)
        cmp_mod._secondary_generation_tracker.mark_submitted(
            'secondary:7,8', meta={'chain': 'secondary', 'reportIds': [7, 8]})

        t.advance(901)
        cmp_mod._compare_watchdog_scan_once()

        events = t.events_for([7, 8])
        assert len(events) == 1
        assert events[0]['success'] is False
        assert events[0]['status'] == 'timeout'


class TestStageSpan:
    """阶段埋点：慢阶段自动升 WARNING。"""

    def test_slow_stage_escalates_to_warning(self, monkeypatch):
        t = _T(monkeypatch)
        cmp_mod._secondary_generation_tracker.mark_submitted('tr')
        with cmp_mod._CompareStageSpan('tr', GenerationStage.PREPARE_DATA, '[test]'):
            t.advance(61)

        warnings = [c for lv, c, _ in t.logs
                    if lv == 'WARNING' and f'stage={GenerationStage.PREPARE_DATA.value}' in c]
        assert len(warnings) == 1
        assert 'done in' in warnings[0]

    def test_fast_stage_stays_debug_and_marks_thread(self, monkeypatch):
        t = _T(monkeypatch)
        cmp_mod._secondary_generation_tracker.mark_submitted('tr')
        with cmp_mod._CompareStageSpan('tr', GenerationStage.BUILD_SUMMARY, '[test]'):
            pass

        assert t.logs_for('tr', 'WARNING') == []
        snap = cmp_mod._secondary_generation_tracker.snapshot()
        assert snap[0]['stage'] == GenerationStage.BUILD_SUMMARY.value
        assert snap[0]['thread_id'] == threading.get_ident()


SECONDARY_SUMMARY_KEYS = (
    'case_categories_list', 'case_tags_list', 'devices_list', 'apis_list',
    'resources', 'resource_headers', 'all_metrics', 'raw_data',
    'metric_data', 'tag_metric_data', 'case_type_stats',
    'device_stats', 'api_stats', 'source_cases', 'comparison_matrix_data',
)


def _fake_secondary_summary():
    return {key: [] for key in SECONDARY_SUMMARY_KEYS}


class TestSecondaryFailurePaths:
    """异步链路失败可上报：验证失败/数据准备失败/异常不再静默。"""

    def test_validation_failure_logs_error_and_emits_event(self, monkeypatch):
        t = _T(monkeypatch)
        monkeypatch.setattr(
            cmp_mod.ReportCompareHelpers, '_validate_reports_and_get_tasks',
            staticmethod(lambda report_ids: (None, None, None, '二次对比至少需要两个报告')))

        cmp_mod._generating_secondary[(7, 8)] = True
        cmp_mod._secondary_generation_tracker.mark_submitted(
            'secondary:7,8', meta={'chain': 'secondary', 'reportIds': [7, 8]})
        cmp_mod.ReportCompareGenerator._secondary_compare_async([7, 8], None, (7, 8))

        errors = t.logs_for('secondary:7,8', 'ERROR')
        assert len(errors) == 1
        assert '二次对比至少需要两个报告' in errors[0][1]

        events = t.events_for([7, 8])
        assert len(events) == 1
        assert events[0]['success'] is False
        assert events[0]['error'] == '二次对比至少需要两个报告'
        assert (7, 8) not in cmp_mod._generating_secondary
        assert cmp_mod._secondary_generation_tracker.snapshot() == []

    def test_prepare_data_failure_logs_error(self, monkeypatch):
        t = _T(monkeypatch)
        monkeypatch.setattr(
            cmp_mod.ReportCompareHelpers, '_validate_reports_and_get_tasks',
            staticmethod(lambda report_ids: ([{'id': 7}, {'id': 8}], [{'id': 1}], [1], None)))
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_prepare_secondary_data',
            staticmethod(lambda report_ids, reports, tasks, task_ids:
                         (None, '对比失败: 未找到测试结果数据')))

        cmp_mod._generating_secondary[(7, 8)] = True
        cmp_mod._secondary_generation_tracker.mark_submitted(
            'secondary:7,8', meta={'chain': 'secondary', 'reportIds': [7, 8]})
        cmp_mod.ReportCompareGenerator._secondary_compare_async([7, 8], None, (7, 8))

        errors = t.logs_for('secondary:7,8', 'ERROR')
        assert len(errors) == 1
        assert '对比失败: 未找到测试结果数据' in errors[0][1]

        events = t.events_for([7, 8])
        assert len(events) == 1
        assert events[0]['success'] is False
        assert (7, 8) not in cmp_mod._generating_secondary
        assert cmp_mod._secondary_generation_tracker.snapshot() == []

    def test_exception_path_includes_stage_and_emits_event(self, monkeypatch):
        t = _T(monkeypatch)
        monkeypatch.setattr(
            cmp_mod.ReportCompareHelpers, '_validate_reports_and_get_tasks',
            staticmethod(lambda report_ids: ([{'id': 7}, {'id': 8}], [{'id': 1}], [1], None)))

        def _boom(report_ids, reports, tasks, task_ids):
            raise RuntimeError('grpc down')

        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_prepare_secondary_data',
            staticmethod(_boom))

        cmp_mod._generating_secondary[(7, 8)] = True
        cmp_mod._secondary_generation_tracker.mark_submitted(
            'secondary:7,8', meta={'chain': 'secondary', 'reportIds': [7, 8]})
        cmp_mod.ReportCompareGenerator._secondary_compare_async([7, 8], None, (7, 8))

        errors = t.logs_for('secondary:7,8', 'ERROR')
        assert len(errors) == 1
        assert f"stage={GenerationStage.PREPARE_DATA.value}" in errors[0][1]
        assert 'grpc down' in errors[0][1]

        events = t.events_for([7, 8])
        assert len(events) == 1
        assert events[0]['success'] is False
        assert (7, 8) not in cmp_mod._generating_secondary
        assert cmp_mod._secondary_generation_tracker.snapshot() == []


class TestSecondarySuccessFlow:
    """成功流程：阶段埋点贯通、事件携带 reportId、轨迹与去重清理。"""

    def test_success_flow_marks_stages_and_cleans_state(self, monkeypatch):
        t = _T(monkeypatch)
        monkeypatch.setattr(
            cmp_mod.ReportCompareHelpers, '_validate_reports_and_get_tasks',
            staticmethod(lambda report_ids: ([{'id': 7}, {'id': 8}], [{'id': 1}], [1], None)))
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_prepare_secondary_data',
            staticmethod(lambda report_ids, reports, tasks, task_ids: ({'k': 'v'}, None)))
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_build_secondary_summary',
            staticmethod(lambda tasks, task_ids, reports, data: _fake_secondary_summary()))
        monkeypatch.setattr(cmp_mod.report_repository, 'add', lambda aggregate: 101)
        records_calls = []
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_create_secondary_report_records',
            staticmethod(lambda *args: records_calls.append(args)))

        cmp_mod._generating_secondary[(7, 8)] = True
        cmp_mod._secondary_generation_tracker.mark_submitted(
            'secondary:7,8', meta={'chain': 'secondary', 'reportIds': [7, 8]})
        cmp_mod.ReportCompareGenerator._secondary_compare_async([7, 8], None, (7, 8))

        events = t.events_for([7, 8])
        assert len(events) == 1
        assert events[0]['success'] is True
        assert events[0]['status'] == 'completed'
        assert events[0]['reportId'] == 101
        assert len(records_calls) == 1

        worker_stages = [
            GenerationStage.VALIDATE_REPORTS, GenerationStage.PREPARE_DATA,
            GenerationStage.BUILD_SUMMARY, GenerationStage.PERSIST_RECORD,
            GenerationStage.PERSIST_DETAIL, GenerationStage.EMIT_DONE,
        ]
        stages = t.stage_logs()
        for stage in worker_stages:
            assert any(f'stage={stage.value}' in c for c in stages), stage.value

        assert (7, 8) not in cmp_mod._generating_secondary
        assert cmp_mod._secondary_generation_tracker.snapshot() == []


class TestSubmission:
    """提交侧：轨迹登记、队列深度观测、提交失败回收。"""

    def test_submit_success_registers_tracker_entry(self, monkeypatch):
        t = _T(monkeypatch)
        submitted = []

        class _FakeExecutor:
            def submit(self, fn, *args):
                submitted.append((fn, args))

        monkeypatch.setattr(cmp_mod, '_secondary_executor', _FakeExecutor())
        cmp_mod._generating_secondary[(7, 8)] = True

        ok = cmp_mod._submit_secondary_generation([7, 8], (7, 8), None)

        assert ok is True
        assert len(submitted) == 1
        snap = cmp_mod._secondary_generation_tracker.snapshot()
        assert len(snap) == 1
        assert snap[0]['task_id'] == 'secondary:7,8'
        assert snap[0]['stage'] == GenerationStage.QUEUED.value
        assert snap[0]['meta'] == {'chain': 'secondary', 'reportIds': [7, 8]}
        assert (7, 8) in cmp_mod._generating_secondary

    def test_submit_failure_reclaims_tracker_and_dedup(self, monkeypatch):
        t = _T(monkeypatch)

        class _BoomExecutor:
            def submit(self, fn, *args):
                raise RuntimeError('pool shutdown')

        monkeypatch.setattr(cmp_mod, '_secondary_executor', _BoomExecutor())
        cmp_mod._generating_secondary[(7, 8)] = True

        ok = cmp_mod._submit_secondary_generation([7, 8], (7, 8), None)

        assert ok is False
        assert cmp_mod._secondary_generation_tracker.snapshot() == []
        assert (7, 8) not in cmp_mod._generating_secondary
        events = t.events_for([7, 8])
        assert len(events) == 1
        assert events[0]['success'] is False
        assert '提交失败' in events[0]['error']
        assert len(t.logs_for('secondary:7,8', 'ERROR')) == 1

    def test_secondary_compare_returns_failure_when_submit_fails(self, monkeypatch):
        t = _T(monkeypatch)

        class _BoomExecutor:
            def submit(self, fn, *args):
                raise RuntimeError('pool shutdown')

        monkeypatch.setattr(cmp_mod, '_secondary_executor', _BoomExecutor())

        result = cmp_mod.ReportCompareGenerator.secondary_compare([7, 8])

        assert result['success'] is False
        assert '提交失败' in result['message']
        assert (7, 8) not in cmp_mod._generating_secondary
        assert cmp_mod._secondary_generation_tracker.snapshot() == []

    def test_secondary_compare_dedup_short_circuit(self, monkeypatch):
        t = _T(monkeypatch)
        submitted = []

        class _FakeExecutor:
            def submit(self, fn, *args):
                submitted.append((fn, args))

        monkeypatch.setattr(cmp_mod, '_secondary_executor', _FakeExecutor())
        cmp_mod._generating_secondary[(7, 8)] = True

        result = cmp_mod.ReportCompareGenerator.secondary_compare([8, 7])

        assert result['success'] is True
        assert result['data']['status'] == 'generating'
        assert submitted == []
        assert cmp_mod._secondary_generation_tracker.snapshot() == []


class TestCompareSyncFlow:
    """同步对比链路：阶段埋点贯通、失败路径 ERROR 日志、轨迹清理。"""

    def _patch_success_flow(self, monkeypatch):
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_validate_and_get_tasks',
            staticmethod(lambda task_ids: ([{'id': 1}, {'id': 2}], None)))
        monkeypatch.setattr(
            cmp_mod, '_grpc_get_test_results_by_task_ids',
            lambda task_ids: [{'id': 11}])
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_prepare_compare_data',
            staticmethod(lambda tasks, task_ids, results:
                         ({'source_cases': [{'id': 1}], 'comparison_data': {}}, None)))
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_build_compare_summary',
            staticmethod(lambda tasks, task_ids, results, data: {'summary': 1}))
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_persist_compare_report',
            staticmethod(lambda name, desc, summary, cases, matrix: 55))

    def test_success_flow_marks_stages_and_cleans_tracker(self, monkeypatch):
        t = _T(monkeypatch)
        self._patch_success_flow(monkeypatch)

        result = cmp_mod.ReportCompareGenerator.compare([1, 2], 'n')

        assert result['success'] is True
        assert result['data']['report_id'] == 55
        assert cmp_mod._secondary_generation_tracker.snapshot() == []

        stages = t.stage_logs()
        for stage in (GenerationStage.VALIDATE_TASK, GenerationStage.PREPARE_DATA,
                      GenerationStage.BUILD_SUMMARY, GenerationStage.PERSIST_RECORD):
            assert any(f'stage={stage.value}' in c for c in stages), stage.value

    def test_validation_failure_logs_error(self, monkeypatch):
        t = _T(monkeypatch)
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_validate_and_get_tasks',
            staticmethod(lambda task_ids:
                         (None, '未找到指定任务或任务状态不是completed、failed或merged')))

        result = cmp_mod.ReportCompareGenerator.compare([1, 2], 'n')

        assert result['success'] is False
        assert result['message'] == '未找到指定任务或任务状态不是completed、failed或merged'
        errors = [c for lv, c, _ in t.logs if lv == 'ERROR' and '任务验证失败' in c]
        assert len(errors) == 1
        assert cmp_mod._secondary_generation_tracker.snapshot() == []

    def test_exception_path_includes_stage(self, monkeypatch):
        t = _T(monkeypatch)
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_validate_and_get_tasks',
            staticmethod(lambda task_ids: ([{'id': 1}], None)))
        monkeypatch.setattr(
            cmp_mod, '_grpc_get_test_results_by_task_ids',
            lambda task_ids: [{'id': 11}])
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_prepare_compare_data',
            staticmethod(lambda tasks, task_ids, results: ({'source_cases': [], 'comparison_data': {}}, None)))
        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_build_compare_summary',
            staticmethod(lambda tasks, task_ids, results, data: {'summary': 1}))

        def _boom(name, desc, summary, cases, matrix):
            raise RuntimeError('db down')

        monkeypatch.setattr(
            cmp_mod.ReportCompareGenerator, '_persist_compare_report',
            staticmethod(_boom))

        result = cmp_mod.ReportCompareGenerator.compare([1, 2], 'n')

        assert result['success'] is False
        assert result['message'] == '对比报告生成失败，请稍后重试'
        errors = [c for lv, c, _ in t.logs if lv == 'ERROR' and 'db down' in c]
        assert len(errors) == 1
        assert f"stage={GenerationStage.PERSIST_RECORD.value}" in errors[0]
        assert cmp_mod._secondary_generation_tracker.snapshot() == []
