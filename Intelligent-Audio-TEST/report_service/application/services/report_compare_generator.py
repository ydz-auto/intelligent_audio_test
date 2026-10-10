# -*- coding: utf-8 -*-
"""对比报告生成（report_service 版本）。

从 api_gateway/application/services/report/report_compare_generator.py 迁移而来，
保持 ReportCompareGenerator 类原有逻辑不变，仅做以下调整：
- 移除直接数据库访问（PO / get_db_session），改用 report_repository 写入聚合根与子实体
- 移除 api_gateway 专属依赖（response / error_codes / schemas.report / request_adapter），
  compare / secondary_compare 改为接收业务参数并返回 dict
- gRPC helper 统一从 report_service.infrastructure.clients.grpc_clients 导入
- ReportUtils / ReportQueryBuilder / ReportDataBuilder / ReportCompareHelpers
  导入路径切换到 report_service
- 报告类型与状态使用字符串字面量 'comparison' / 'secondary_comparison' / 'draft'
- 保留 ThreadPoolExecutor 与锁，保留 _emit_secondary_compare_event 事件推送

实现采用 Mixin 组合模式（同 report_utils / report_aggregation 拆分先例）：
- ReportCompareDataMixin: 对比报告任务校验 + 数据准备 + 摘要构建
- ReportSecondaryDataMixin: 二次对比报告数据准备 + 摘要构建
- ReportComparePersistMixin: 对比报告与二次对比报告落库写入

INT-122 可观察性（复用 INT-117 模式，commit 0c9382b4）：
- GenerationTracker 轨迹注册表 + _CompareStageSpan 阶段埋点（慢阶段自动升 WARNING）
- 对比链路专属看门狗守护线程：总时长超 REPORT_GEN_TIMEOUT_SECONDS → CRITICAL 日志
  （含工作线程调用栈，精确定位卡死行）+ secondary_compare_generated 失败事件
  （仅一次）；QUEUED 停留超 REPORT_GEN_QUEUE_STUCK_SECONDS → 线程池饥饿告警；
  持续卡死按时长倍增退避升 WARNING 防刷屏
- 失败路径补 ERROR 日志；线程池提交失败回收轨迹与去重标记 + 失败事件 + 明确失败返回
"""

import sys
import traceback
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from shared.utils.log_handler import log_and_emit
from shared.utils.query_utils import now_cst

from report_service.application.services.report_compare_generator_data_mixin import ReportCompareDataMixin
from report_service.application.services.report_compare_generator_secondary_mixin import ReportSecondaryDataMixin
from report_service.application.services.report_compare_generator_persist_mixin import ReportComparePersistMixin
from report_service.application.services.report_compare_helpers import ReportCompareHelpers
from report_service.application.services.report_compare_helpers import (
    _grpc_get_tasks_by_ids, _grpc_get_test_results_by_task_ids,
)
from report_service.application.services.report_task_generator import GenerationTracker, _thread_stack
from report_service.application.services import report_task_generator as _gen_mod
from report_service.config.config import Config
from report_service.domain.entities import ReportAggregate
from report_service.domain.entities.report import GenerationStage
from report_service.infrastructure.persistence.report_repository import report_repository


_secondary_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='secondary_compare')
_generating_secondary = {}
_generating_secondary_lock = threading.Lock()

# 对比链路轨迹注册表（INT-122）：compare（同步）与 secondary_compare（异步）两条链路共用
_secondary_generation_tracker = GenerationTracker()


def _now() -> float:
    """单调时钟：委托轨迹模块同名实现（看门狗与 GenerationTracker 统一取时点，测试单点注入）。"""
    return _gen_mod._now()


def _emit_secondary_compare_event(event_name, data):
    """经 EventBus REPORT_EVENTS 发布二次对比报告生成事件，由 api_gateway 订阅五通道后转发前端"""
    try:
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        event_type = (EventType.REPORT_GENERATED
                      if event_name == 'report_generated'
                      else EventType.SECONDARY_COMPARE_GENERATED)
        EventBus().publish(EventChannel.REPORT_EVENTS, event_type,
                           {'event': event_name, 'data': data})
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(f"SSE event emit failed: {_e}")


def _secondary_track_id(report_key):
    """二次对比轨迹键：与去重键同源，同 report_key 同时仅一条活跃轨迹。"""
    return 'secondary:' + ','.join(str(r) for r in report_key)


def _compare_track_id(task_ids):
    """对比报告（同步请求内执行）轨迹键；无去重约束，随机后缀防并发同参覆盖。"""
    return 'compare:' + ','.join(str(t) for t in sorted(task_ids)) + ':' + uuid.uuid4().hex[:8]


def _executor_queue_depth():
    """线程池待执行队列深度（CPython 私有属性，取不到返回 None）。"""
    try:
        return _secondary_executor._work_queue.qsize()
    except Exception:
        return None


class _CompareStageSpan:
    """阶段埋点上下文管理器（同 INT-117 _StageSpan）：登记阶段、慢阶段 WARNING、完成时长 DEBUG。"""

    def __init__(self, track_id, stage, log_tag):
        self.track_id = track_id
        self.stage = stage
        self.log_tag = log_tag
        self._start = _now()

    def __enter__(self):
        _secondary_generation_tracker.mark_stage(self.track_id, self.stage, threading.get_ident())
        log_and_emit('DEBUG', 'report',
                     f'{self.log_tag} stage={self.stage.value} enter',
                     task_id=self.track_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = _now() - self._start
        if exc_type is None:
            level = 'WARNING' if elapsed > Config.REPORT_GEN_SLOW_STAGE_SECONDS else 'DEBUG'
            log_and_emit(level, 'report',
                         f'{self.log_tag} stage={self.stage.value} done in {elapsed:.1f}s',
                         task_id=self.track_id)
        return False


_compare_watchdog_thread = None
_compare_watchdog_stop_event = threading.Event()


def start_compare_generation_watchdog():
    """启动对比报告生成看门狗守护线程（幂等；report_service lifespan 调用，INT-122）。

    扫描 _secondary_generation_tracker（compare + secondary_compare 两条链路）：
    总时长超 REPORT_GEN_TIMEOUT_SECONDS 判卡死——CRITICAL 日志（含工作线程调用栈）
    + secondary_compare_generated 失败事件仅发一次（异步链路；同步 compare 链路
    由 HTTP 调用方直接感知失败，不另造事件载荷）；QUEUED 停留超
    REPORT_GEN_QUEUE_STUCK_SECONDS 告警线程池饥饿；持续卡死时长倍增退避升 WARNING。
    """
    global _compare_watchdog_thread
    if _compare_watchdog_thread is not None and _compare_watchdog_thread.is_alive():
        return _compare_watchdog_thread
    _compare_watchdog_stop_event.clear()
    _compare_watchdog_thread = threading.Thread(
        target=_compare_watchdog_loop, name='CompareGenWatchdog', daemon=True)
    _compare_watchdog_thread.start()
    log_and_emit(
        'INFO', 'report',
        f'[compare_watchdog] 对比报告生成看门狗已启动：扫描周期 {Config.REPORT_GEN_WATCHDOG_INTERVAL_SECONDS}s，'
        f'超时阈值 {Config.REPORT_GEN_TIMEOUT_SECONDS}s，队列饥饿阈值 {Config.REPORT_GEN_QUEUE_STUCK_SECONDS}s')
    return _compare_watchdog_thread


def stop_compare_generation_watchdog():
    """停止看门狗（lifespan shutdown 调用；未启动时为无害空操作）。"""
    _compare_watchdog_stop_event.set()


def _compare_watchdog_loop():
    interval = Config.REPORT_GEN_WATCHDOG_INTERVAL_SECONDS
    while not _compare_watchdog_stop_event.wait(interval):
        try:
            _compare_watchdog_scan_once()
        except Exception as e:
            log_and_emit('ERROR', 'report',
                         f'[compare_watchdog] 扫描异常: {e}\n{traceback.format_exc()}')


def _compare_watchdog_scan_once():
    """单次扫描：对每条未完成轨迹做队列饥饿与超时判定。"""
    timeout_seconds = Config.REPORT_GEN_TIMEOUT_SECONDS
    queue_stuck_seconds = Config.REPORT_GEN_QUEUE_STUCK_SECONDS
    now = _now()
    for entry in _secondary_generation_tracker.snapshot():
        track_id = entry['task_id']
        stage = entry['stage']
        meta = entry.get('meta') or {}
        queued_elapsed = now - entry['submitted_at']

        if stage == GenerationStage.QUEUED.value:
            if queued_elapsed > queue_stuck_seconds and not entry['queue_warned']:
                _secondary_generation_tracker.mark_queue_warned(track_id)
                log_and_emit(
                    'WARNING', 'report',
                    f'[compare_watchdog] track_id={track_id} 提交后排队 {queued_elapsed:.0f}s 未开始执行'
                    f'（线程池 max_workers={_secondary_executor._max_workers} 可能被占满，'
                    f'队列深度={_executor_queue_depth()}）',
                    task_id=track_id)

        total_elapsed = now - entry['submitted_at']
        if total_elapsed <= timeout_seconds:
            continue

        stage_elapsed = now - entry['stage_since']
        if not entry['timeout_reported']:
            _secondary_generation_tracker.mark_timeout_reported(track_id)
            stack = _thread_stack(entry.get('thread_id'))
            log_and_emit(
                'CRITICAL', 'report',
                f'[compare_watchdog] track_id={track_id} 对比报告生成疑似卡死：总耗时 {total_elapsed:.0f}s '
                f'超过阈值 {timeout_seconds}s，卡在阶段 {stage}（已停留 {stage_elapsed:.0f}s）。'
                f'注意：同组报告的去重标记（_generating_secondary）仍由卡死线程持有'
                f'（进程内字典，无 TTL 兜底），直至线程结束或进程重启，'
                f'期间同组报告重复提交将返回"正在生成中"。'
                f'工作线程调用栈：\n{stack}',
                task_id=track_id)
            if meta.get('chain') == 'secondary':
                # 仅异步链路有既定失败事件契约（前端监听 secondary_compare_generated）；
                # 同步 compare 链路的调用方经 HTTP 响应直接感知结果，不另造事件载荷
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': meta.get('reportIds', []),
                    'success': False,
                    'error': f'二次对比报告生成超时（超过 {timeout_seconds}s 未完成），卡在阶段 {stage}',
                    'status': 'timeout',
                    'stage': stage,
                })
        else:
            # 持续卡死：时长每翻倍升一次 WARNING，避免逐扫描周期刷屏
            warn_count = entry['timeout_warn_count']
            if total_elapsed >= timeout_seconds * (2 ** warn_count):
                _secondary_generation_tracker.mark_timeout_reported(track_id)
                log_and_emit(
                    'WARNING', 'report',
                    f'[compare_watchdog] track_id={track_id} 仍在生成中（总耗时 {total_elapsed:.0f}s，'
                    f'阶段 {stage} 停留 {stage_elapsed:.0f}s），超时失败事件已于此前上报',
                    task_id=track_id)


def _submit_secondary_generation(report_ids, report_key, description):
    """登记轨迹并提交线程池（同 INT-117 _submit_generation 模式）。

    提交失败回收轨迹与去重标记 + 失败事件 + 返回 False（调用方明确失败返回）。
    """
    track_id = _secondary_track_id(report_key)
    _secondary_generation_tracker.mark_submitted(
        track_id, meta={'chain': 'secondary', 'reportIds': list(report_key)})
    try:
        _secondary_executor.submit(
            ReportCompareGenerator._secondary_compare_async,
            report_ids, description, report_key
        )
    except Exception as submit_err:
        _secondary_generation_tracker.finish(track_id)
        with _generating_secondary_lock:
            _generating_secondary.pop(report_key, None)
        log_and_emit('ERROR', 'report',
                     f'[secondary_compare] 提交失败: {submit_err}', task_id=track_id)
        _emit_secondary_compare_event('secondary_compare_generated', {
            'reportIds': report_ids,
            'success': False,
            'error': f'二次对比报告生成任务提交失败: {submit_err}',
        })
        return False
    depth = _executor_queue_depth()
    if depth:
        log_and_emit(
            'WARNING', 'report',
            f'[secondary_compare] 已提交，但线程池待执行队列深度={depth}'
            f'（工作线程可能被占满，本次生成将延迟执行）',
            task_id=track_id)
    return True


class ReportCompareGenerator(
    ReportCompareDataMixin,
    ReportSecondaryDataMixin,
    ReportComparePersistMixin,
):
    """对比报告生成（原 ReportCommandService 中 D + E 组方法）。

    承载对比报告与二次对比报告生成相关的静态方法，保持原有逻辑不变。
    """

    @staticmethod
    def compare(task_ids: list, name: str = None, description: str = None) -> dict:
        """生成对比报告。

        原实现从 HTTP request 解析参数并返回 (response, http_code)；
        迁移后改为接收业务参数并返回 dict，由接口层负责 HTTP 适配。

        Args:
            task_ids: 任务 ID 列表
            name: 报告名称（可选，缺省时自动生成）
            description: 报告描述（可选）

        Returns:
            dict: {'success': bool, 'data': {'report_id': ...}, 'message': str}

        INT-122 可观察性：同步链路全程 _CompareStageSpan 阶段埋点并登记轨迹
        （看门狗覆盖请求线程卡死场景），失败路径补 ERROR 日志，不再仅 print_exc。
        """
        if not task_ids:
            return {'success': False, 'data': None, 'message': '缺少必要参数: taskIds'}

        if not name:
            name = f"对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"

        track_id = _compare_track_id(task_ids)
        _secondary_generation_tracker.mark_submitted(
            track_id, meta={'chain': 'compare', 'taskIds': list(task_ids)})
        try:
            with _CompareStageSpan(track_id, GenerationStage.VALIDATE_TASK, '[compare]'):
                tasks, error = ReportCompareGenerator._validate_and_get_tasks(task_ids)
                if not error:
                    results = _grpc_get_test_results_by_task_ids(task_ids)
            if error:
                log_and_emit('ERROR', 'report',
                             f'[compare] 任务验证失败: {error}', task_id=track_id)
                return {'success': False, 'data': None, 'message': error}

            with _CompareStageSpan(track_id, GenerationStage.PREPARE_DATA, '[compare]'):
                data_dict, error = ReportCompareGenerator._prepare_compare_data(tasks, task_ids, results)
            if error:
                log_and_emit('ERROR', 'report',
                             f'[compare] 对比数据准备失败: {error}', task_id=track_id)
                return {'success': False, 'data': None, 'message': error}

            with _CompareStageSpan(track_id, GenerationStage.BUILD_SUMMARY, '[compare]'):
                summary = ReportCompareGenerator._build_compare_summary(tasks, task_ids, results, data_dict)

            with _CompareStageSpan(track_id, GenerationStage.PERSIST_RECORD, '[compare]'):
                new_report_id = ReportCompareGenerator._persist_compare_report(
                    name, description, summary, data_dict["source_cases"], data_dict["comparison_data"]
                )

            log_and_emit('INFO', 'report',
                         f'[compare] Compare report generated successfully, report_id={new_report_id}',
                         task_id=track_id)

            return {
                'success': True,
                'data': {'report_id': new_report_id},
                'message': '对比报告生成成功',
            }
        except Exception as e:
            stage = _secondary_generation_tracker.current_stage(track_id)
            log_and_emit('ERROR', 'report',
                         f'[compare] Error (stage={stage}): {e}\n{traceback.format_exc()}',
                         task_id=track_id)
            return {'success': False, 'data': None, 'message': '对比报告生成失败，请稍后重试'}
        finally:
            _secondary_generation_tracker.finish(track_id)

    @staticmethod
    def secondary_compare(report_ids: list, description: str = None) -> dict:
        """提交二次对比报告生成（异步）。

        原实现从 HTTP request 解析参数并返回 (response, http_code)；
        迁移后改为接收业务参数并返回 dict，由接口层负责 HTTP 适配。

        Args:
            report_ids: 报告 ID 列表（至少 2 个）
            description: 报告描述（可选）

        Returns:
            dict: {'success': bool, 'data': {'reportKey': [...], 'status': '...'}, 'message': str}
        """
        if not report_ids:
            return {'success': False, 'data': None, 'message': '缺少必要参数: reportIds'}
        if len(report_ids) < 2:
            return {'success': False, 'data': None, 'message': '二次对比至少需要两个报告 ID'}

        report_key = tuple(sorted(report_ids))

        with _generating_secondary_lock:
            if report_key in _generating_secondary:
                return {
                    'success': True,
                    'data': {'reportKey': list(report_key), 'status': 'generating'},
                    'message': '对比报告正在生成中',
                }
            _generating_secondary[report_key] = True

        log_and_emit('INFO', 'report', f'[secondary_compare] Submitting async task for report_ids={report_ids}')
        if not _submit_secondary_generation(report_ids, report_key, description):
            return {'success': False, 'data': None, 'message': '二次对比报告生成任务提交失败，请稍后重试'}

        return {
            'success': True,
            'data': {'reportKey': list(report_key), 'status': 'generating'},
            'message': '对比报告生成中，请稍后',
        }

    @staticmethod
    def _secondary_compare_async(report_ids, description, report_key):
        """二次对比报告异步生成任务。

        原实现使用 get_db_session().add(new_report) / flush() / commit() /
        rollback() 直连 PO；迁移后改用 report_repository.add 写入主报告聚合根，
        子表记录通过 _create_secondary_report_records 使用 repository 方法写入。

        INT-122 可观察性：每个阶段经 _CompareStageSpan 埋点（轨迹注册表 + 慢阶段
        WARNING + 时长日志）；失败路径（验证失败/数据准备失败/异常）一律 ERROR
        日志 + secondary_compare_generated 失败事件，不再静默返回。
        """
        track_id = _secondary_track_id(report_key)
        try:
            log_and_emit('INFO', 'report',
                         f'[secondary_compare_async] Starting for report_ids={report_ids}',
                         task_id=track_id)

            with _CompareStageSpan(track_id, GenerationStage.VALIDATE_REPORTS, '[secondary_compare_async]'):
                reports, tasks, task_ids, error = ReportCompareHelpers._validate_reports_and_get_tasks(report_ids)
            if error:
                log_and_emit('ERROR', 'report',
                             f'[secondary_compare_async] 报告验证失败: {error}', task_id=track_id)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            with _CompareStageSpan(track_id, GenerationStage.PREPARE_DATA, '[secondary_compare_async]'):
                data_dict, error = ReportCompareGenerator._prepare_secondary_data(report_ids, reports, tasks, task_ids)
            if error:
                log_and_emit('ERROR', 'report',
                             f'[secondary_compare_async] 二次对比数据准备失败: {error}', task_id=track_id)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            with _CompareStageSpan(track_id, GenerationStage.BUILD_SUMMARY, '[secondary_compare_async]'):
                summary = ReportCompareGenerator._build_secondary_summary(tasks, task_ids, reports, data_dict)

            with _CompareStageSpan(track_id, GenerationStage.PERSIST_RECORD, '[secondary_compare_async]'):
                name = f"二次对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"
                # 主报告聚合根：id 由仓储层分配（新建传 0，同 report_handlers 既有模式）
                aggregate = ReportAggregate(
                    id=0,
                    task_id=0,
                    report_type='secondary_comparison',
                    status='draft',
                    config={'name': name, 'description': description},
                    deleted=False,
                )
                new_report_id = report_repository.add(aggregate)

            with _CompareStageSpan(track_id, GenerationStage.PERSIST_DETAIL, '[secondary_compare_async]'):
                ReportCompareGenerator._create_secondary_report_records(
                    new_report_id, task_ids, tasks, reports,
                    summary["case_categories_list"], summary["case_tags_list"],
                    summary["devices_list"], summary["apis_list"], summary["resources"],
                    summary["resource_headers"], summary["all_metrics"],
                    summary["raw_data"], summary["metric_data"], summary["tag_metric_data"],
                    summary["case_type_stats"],
                    summary["device_stats"], summary["api_stats"], summary["source_cases"],
                    summary["comparison_matrix_data"]
                )

            log_and_emit('INFO', 'report',
                         f'[secondary_compare_async] Report generated successfully, report_id={new_report_id}',
                         task_id=track_id)

            with _CompareStageSpan(track_id, GenerationStage.EMIT_DONE, '[secondary_compare_async]'):
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'reportId': new_report_id,
                    'success': True,
                    'status': 'completed'
                })

        except Exception as e:
            stage = _secondary_generation_tracker.current_stage(track_id)
            log_and_emit('ERROR', 'report',
                         f'[secondary_compare_async] Error (stage={stage}): {e}\n{traceback.format_exc()}',
                         task_id=track_id)
            _emit_secondary_compare_event('secondary_compare_generated', {
                'reportIds': report_ids,
                'success': False,
                'error': '对比报告生成失败，请稍后重试'
            })
        finally:
            _secondary_generation_tracker.finish(track_id)
            with _generating_secondary_lock:
                _generating_secondary.pop(report_key, None)
