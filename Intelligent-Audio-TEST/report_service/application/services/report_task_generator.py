# -*- coding: utf-8 -*-
"""任务报告生成器（从 api_gateway 迁移至 report_service）。

承载任务报告生成相关的静态方法，保持原有生成逻辑不变。
迁移要点：
- 移除 PO 直连导入，改由 report_repository 提供原始 PO 查询
- 移除 api_gateway 相关导入（request/schemas/response/error_codes）
- generate_task_report 不再解析 HTTP 请求，改为直接接收参数并返回 dict
- 异步生成逻辑中去掉手动的 commit/rollback，事务由仓储方法自行管理
"""
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor

from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder
from report_service.application.services.report_data_builder import ReportDataBuilder
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_tasks_by_ids,
    _grpc_get_devices_by_ids,
    _grpc_get_apis_by_ids,
    _grpc_list_dimensions_all,
    _grpc_algo_get_field_mapping,
    _dim_id,
)
from report_service.infrastructure.persistence.report_repository import report_repository
from shared.models.common_enums import TaskStatus
from shared.utils.log_handler import log_and_emit
from shared.utils.query_utils import now_cst
from shared.utils.distributed_coordinator import DistributedLock

import os
import json


def _emit_report_event(event_name, data):
    """通过 Redis PubSub 推送报告生成事件，由 api_gateway SSE 端点转发给前端"""
    try:
        from shared.utils.redis_pubsub import RedisPubSub
        RedisPubSub().publish('sse_events', {'event': event_name, 'data': data})
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(f"SSE event emit failed: {_e}")


# 异步报告生成线程池
_report_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='report_gen')
# 报告生成去重锁 key 前缀与 TTL（分布式锁，替代原进程内 set+threading.Lock）
_REPORT_GEN_LOCK_PREFIX = 'report:gen:'
# 30 分钟兜底 TTL，防止持有者崩溃后死锁；正常路径在 finally 中主动释放
_GENERATION_LOCK_TTL = 1800


def _acquire_generation_lock(task_id):
    """非阻塞获取报告生成去重锁（分布式）。

    成功返回 DistributedLock 实例（调用方需在 finally 中 release）；
    已被其它实例占用（正在生成）返回 None。Redis 不可用时降级放行（返回锁实例）。
    """
    lock = DistributedLock(
        key=f'{_REPORT_GEN_LOCK_PREFIX}{task_id}',
        ttl=_GENERATION_LOCK_TTL,
    )
    if lock.acquire(blocking=False):
        return lock
    return None


class ReportTaskGenerator:
    """任务报告生成（原 ReportCommandService 中 C 组方法）。

    承载任务报告生成相关的静态方法，保持原有逻辑不变。
    """

    @staticmethod
    def generate_task_report(task_id: int, name: str = None, description: str = None) -> dict:
        """生成任务报告。

        迁移说明：不再从 HTTP request 解析参数，改为直接接收参数；
        返回统一 dict 结构 {'success': bool, 'data': {...}, 'message': str}。
        """
        log_and_emit('DEBUG', 'report', f'[generate_task_report] Starting task_id={task_id}', task_id=task_id)

        task = None
        _tasks = _grpc_get_tasks_by_ids([task_id])
        if _tasks:
            task = _tasks[0]
        if not task:
            return {'success': False, 'data': None, 'message': '未找到指定任务'}

        existing_report = report_repository.get_report_by_task_id_raw(task_id)
        if existing_report:
            return {'success': True, 'data': {'id': existing_report.id, 'status': 'exists'}, 'message': '任务报告已存在'}

        task_status = task.get('status') if isinstance(task, dict) else task.status
        if task_status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value]:
            return {'success': False, 'data': None, 'message': '只有任务状态为completed、failed或merged时才能生成报告'}

        # 分布式去重锁：防止多实例并发重复生成同一任务的报告
        lock = _acquire_generation_lock(task_id)
        if lock is None:
            return {'success': True, 'data': {'taskId': task_id, 'status': 'generating'}, 'message': '报告正在生成中'}

        log_and_emit('INFO', 'report', f'[generate_task_report] Submitting async task for task_id={task_id}', task_id=task_id)
        _report_executor.submit(
            ReportTaskGenerator._generate_task_report_async,
            task_id, name, description, lock
        )
        log_and_emit('INFO', 'report', f'[generate_task_report] Async task submitted for task_id={task_id}', task_id=task_id)

        return {'success': True, 'data': {'taskId': task_id, 'status': 'generating'}, 'message': '报告生成中，请稍后刷新'}

    # ===== 事件驱动：订阅 TaskCompleted 事件，自动触发报告生成 =====

    @staticmethod
    def _on_task_completed(payload: dict) -> None:
        """处理 TaskCompleted 事件，自动触发报告生成。

        收到事件后调用 generate_task_report，复用既有生成逻辑（含去重）。
        事件驱动只是补充手段，手动触发能力保持不变。
        """
        task_id = payload.get('task_id')
        if task_id is None:
            log_and_emit('WARNING', 'report', '[on_task_completed] 事件缺少 task_id 字段，已忽略')
            return
        # 事件 payload 中 task_id 可能为字符串，统一转为 int 以匹配 generate_task_report 签名
        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            log_and_emit('WARNING', 'report', f'[on_task_completed] task_id 无法转换为整数: {task_id}，已忽略')
            return

        log_and_emit(
            'INFO', 'report',
            f'[on_task_completed] 收到 TaskCompleted 事件，自动触发报告生成 task_id={task_id}',
            task_id=task_id
        )
        ReportTaskGenerator.generate_task_report(task_id)

    @staticmethod
    def start_event_subscriber() -> threading.Thread:
        """启动事件订阅线程，监听 TaskCompleted 事件。

        在 report_service 启动时调用，后台守护线程阻塞监听 Redis 频道，
        Redis 不可用时自动重连，不影响主服务启动。
        """
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

        event_bus = EventBus()
        thread = event_bus.start_subscriber(
            EventChannel.TASK_EVENTS,
            {EventType.TASK_COMPLETED: ReportTaskGenerator._on_task_completed},
            name='ReportEventSub'
        )
        log_and_emit('INFO', 'report', '[start_event_subscriber] 事件订阅线程已启动，监听 TaskCompleted 事件')
        return thread

    @staticmethod
    def regenerate_report(report_id: int) -> dict:
        """重新生成报告：删除旧报告数据，基于原 task_id 重新生成。

        流程：
        1. 查询旧报告获取 task_id
        2. 检查是否正在生成
        3. 删除旧报告（级联删除 summary_meta, raw_data, cases, metric_stats）
        4. 异步重新生成
        """
        # 查询旧报告
        aggregate = report_repository.get_by_id(report_id)
        if aggregate is None:
            return {'success': False, 'data': None, 'message': '未找到测试报告'}

        task_id = aggregate.task_id
        if not task_id:
            return {'success': False, 'data': None, 'message': '报告未关联任务，无法重新生成'}

        # 分布式去重锁：检查是否正在生成
        lock = _acquire_generation_lock(task_id)
        if lock is None:
            return {'success': True, 'data': {'taskId': task_id, 'status': 'generating'}, 'message': '报告正在生成中'}

        # 删除旧报告（级联删除子表）
        try:
            report_repository.hard_delete(report_id)
            log_and_emit('INFO', 'report', f'[regenerate_report] Deleted old report {report_id}, regenerating for task_id={task_id}', task_id=task_id)
        except Exception as e:
            lock.release()
            log_and_emit('ERROR', 'report', f'[regenerate_report] Failed to delete old report: {e}', task_id=task_id)
            return {'success': False, 'data': None, 'message': '删除旧报告失败，请稍后重试'}

        # 异步重新生成
        _report_executor.submit(
            ReportTaskGenerator._generate_task_report_async,
            task_id, None, None, lock
        )
        log_and_emit('INFO', 'report', f'[regenerate_report] Async task submitted for task_id={task_id}', task_id=task_id)

        return {'success': True, 'data': {'taskId': task_id, 'status': 'generating'}, 'message': '报告重新生成中，请稍后刷新'}

    @staticmethod
    def _collect_field_mappings_snapshot(test_cases, results):
        """收集报告内涉及的所有算法类型，获取字段映射快照。

        返回 {algorithm_type: {result: [...], reference: [...]}} 映射。
        """
        algorithm_types = set()
        for tc in test_cases:
            algo_type = tc.get('algorithm_type') if isinstance(tc, dict) else getattr(tc, 'algorithm_type', None)
            if algo_type:
                algorithm_types.add(algo_type)
        for r in results:
            algo_type = r.get('algorithm_type') if isinstance(r, dict) else getattr(r, 'algorithm_type', None)
            if algo_type:
                algorithm_types.add(algo_type)

        field_mappings = {}
        for algo_type in algorithm_types:
            try:
                mapping = _grpc_algo_get_field_mapping(algo_type)
                if mapping:
                    field_mappings[algo_type] = mapping
            except Exception as e:
                log_and_emit('WARNING', 'report', f'[_collect_field_mappings] Failed to get field mapping for {algo_type}: {e}')
        return field_mappings

    @staticmethod
    def _prepare_report_data(task, task_id, results):
        """准备报告数据。返回 dict 或 None（如果出错，已发射事件）。"""
        source_task_ids = ReportDataBuilder._get_source_task_ids(task)
        task_ids_for_query = source_task_ids if source_task_ids else [task_id]

        def _task_get(key, default=None):
            if isinstance(task, dict):
                return task.get(key, default)
            return getattr(task, key, default)

        total_cases = _task_get('total_cases', 0) or 0
        failed_cases_val = _task_get('failed_cases', 0) or 0
        completed_cases = _task_get('completed_cases', 0) or 0
        completed_cases = completed_cases - failed_cases_val
        success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

        res_ids = [r.id for r in results]

        dim_results_map, dim_stats = ReportDataBuilder._get_dimension_results_batch(res_ids)

        if not dim_results_map:
            _emit_report_event('report_generated', {
                'taskId': task_id,
                'success': False,
                'error': '未找到维度得分数据'
            })
            return None

        all_dimensions_all = _grpc_list_dimensions_all()
        summary_dim_values = ReportDataBuilder._calculate_summary_dimensions(dim_stats)

        if dim_stats:
            all_dimensions = [d for d in all_dimensions_all if _dim_id(d) in dim_stats]
        else:
            all_dimensions = all_dimensions_all

        test_cases, test_case_ids = ReportDataBuilder._get_task_test_cases(task_ids_for_query)
        devices_list, apis_list, device_ids, api_ids = ReportDataBuilder._get_task_resources(task_ids_for_query)

        device_result_types, api_result_types = ReportDataBuilder._get_resource_result_types_batch(
            task_ids_for_query, device_ids, api_ids
        )

        # 通过 gRPC 批量查询 Device / API
        devices_data = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_data = _grpc_get_apis_by_ids(api_ids) if api_ids else {}
        resources = ReportDataBuilder._build_resources_list(
            list(devices_data.values()),
            list(apis_data.values()),
            task, device_result_types, api_result_types
        )

        all_metrics = ReportDataBuilder._build_all_metrics(all_dimensions)

        if not devices_list and not apis_list:
            _emit_report_event('report_generated', {
                'taskId': task_id,
                'success': False,
                'error': '任务没有关联任何设备或API'
            })
            return None

        if not all_metrics:
            _emit_report_event('report_generated', {
                'taskId': task_id,
                'success': False,
                'error': '任务没有关联任何评估维度'
            })
            return None

        task_id_val = _task_get('id', task_id)
        tasks_map = {task_id_val: task}
        if source_task_ids:
            source_tasks = _grpc_get_tasks_by_ids(source_task_ids)
            for st in source_tasks:
                st_id = st.get('id') if isinstance(st, dict) else getattr(st, 'id', None)
                if st_id is not None:
                    tasks_map[st_id] = st

        # 收集算法字段映射快照
        field_mappings = ReportTaskGenerator._collect_field_mappings_snapshot(test_cases, results)

        core_metrics = ReportUtils.calculate_core_metrics(
            results=results,
            all_dimensions=all_dimensions,
            resources=resources,
            dim_results_map=dim_results_map,
            tasks_map=tasks_map,
            use_time_prefix=False
        )

        metric_data = core_metrics['metric_data']
        tag_metric_data = core_metrics['tag_metric_data']
        raw_data = core_metrics['raw_data']
        case_type_stats = core_metrics['case_type_stats']
        resources = core_metrics['resources']

        resource_headers = ReportUtils.build_resource_headers(
            resources=resources,
            results=results,
            tasks_map=tasks_map,
            use_time_prefix=False,
        )

        device_stats, api_stats = ReportUtils.calculate_device_api_stats(
            results=results,
            all_dimensions=all_dimensions,
            dim_results_map=dim_results_map
        )

        cases = ReportDataBuilder._build_case_data(
            test_cases, results, all_dimensions, dim_results_map, task
        )

        case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

        return {
            "total_cases": total_cases,
            "completed_cases": completed_cases,
            "failed_cases": failed_cases_val,
            "success_rate": success_rate,
            "summary_dim_values": summary_dim_values,
            "devices_list": devices_list,
            "apis_list": apis_list,
            "resources": resources,
            "resource_headers": resource_headers,
            "all_metrics": all_metrics,
            "metric_data": metric_data,
            "tag_metric_data": tag_metric_data,
            "raw_data": raw_data,
            "device_stats": device_stats,
            "api_stats": api_stats,
            "case_type_stats": case_type_stats,
            "cases": cases,
            "case_categories_list": case_categories_list,
            "case_tags_list": case_tags_list,
            "source_task_ids": source_task_ids,
            "field_mappings": field_mappings,
        }

    @staticmethod
    def _build_task_summary(task, task_id, results, data_dict):
        """构建 summary dict。"""
        def _task_get(key, default=None):
            if isinstance(task, dict):
                return task.get(key, default)
            return getattr(task, key, default)

        actual_duration = _task_get('actual_duration')
        started_at = _task_get('started_at')
        completed_at = _task_get('completed_at')

        summary = {
            "total_cases": data_dict["total_cases"],
            "completed_cases": data_dict["completed_cases"],
            "failed_cases": data_dict["failed_cases"],
            "overall_success_rate": round(data_dict["success_rate"], 2),
            "dimension_values": data_dict["summary_dim_values"],
            "duration": actual_duration,
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "case_categories": data_dict["case_categories_list"],
            "all_case_tags": data_dict["case_tags_list"],
            "all_tags": data_dict["case_tags_list"],
            "devices": data_dict["devices_list"],
            "apis": data_dict["apis_list"],
            "resources": data_dict["resources"],
            "resource_headers": data_dict["resource_headers"],
            "all_metrics": data_dict["all_metrics"],
            "metric_data": data_dict["metric_data"],
            "tag_metric_data": data_dict["tag_metric_data"],
            "raw_data": data_dict["raw_data"],
            "device_stats": data_dict["device_stats"],
            "api_stats": data_dict["api_stats"],
            "case_type_stats": data_dict["case_type_stats"],
            "cases": data_dict["cases"],
            "source_task_ids": data_dict["source_task_ids"],
            "is_merged": bool(data_dict["source_task_ids"]),
            "field_mappings": data_dict.get("field_mappings", {}),
        }

        summary = ReportUtils.normalize_summary_metrics(summary)
        return summary

    @staticmethod
    def _generate_task_report_async(task_id, name, description, lock):
        """异步生成任务报告。

        迁移说明：去掉手动的 commit/rollback，仓储方法自行管理事务；
        _create_report_record 等由 ReportDataBuilder 委托仓储完成写入。
        去重锁由调用方传入，在 finally 中释放（分布式锁替代原进程内 set）。
        """
        try:
            log_and_emit('INFO', 'report', f'[generate_task_report_async] Starting for task_id={task_id}', task_id=task_id)

            task, results, error = ReportDataBuilder._validate_task_and_get_results(task_id)
            if error:
                _emit_report_event('report_generated', {
                    'taskId': task_id,
                    'success': False,
                    'error': '任务验证失败'
                })
                return

            existing_report = report_repository.get_report_by_task_id_raw(task_id)
            if existing_report:
                _emit_report_event('report_generated', {
                    'taskId': task_id,
                    'reportId': existing_report.id,
                    'success': True,
                    'status': 'exists'
                })
                return

            if not name:
                task_name = task.get('name') if isinstance(task, dict) else getattr(task, 'name', '')
                name = f"任务报告_{task_name}_{now_cst().strftime('%Y%m%d%H%M%S')}"

            data_dict = ReportTaskGenerator._prepare_report_data(task, task_id, results)
            if data_dict is None:
                return

            summary = ReportTaskGenerator._build_task_summary(task, task_id, results, data_dict)

            new_report = ReportDataBuilder._create_report_record(name, task_id, description)
            log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created report id={new_report.id}', task_id=task_id)

            summary_info, summary_meta = ReportDataBuilder._create_report_summary(new_report.id, task, summary)
            log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created summary_info id={summary_info.id}, report_id={summary_info.report_id}', task_id=task_id)

            raw_data_record, metric_stats_record = ReportDataBuilder._create_report_detail_data(new_report.id, summary)
            log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created detail data for report_id={new_report.id}', task_id=task_id)

            report_id = new_report.id

            # 报告生成完成，设置状态为 published
            try:
                report_repository.update_status(report_id, 'published')
                log_and_emit('INFO', 'report', f'[generate_task_report_async] Report status set to published, report_id={report_id}', task_id=task_id)
            except Exception as status_err:
                log_and_emit('WARNING', 'report', f'[generate_task_report_async] Failed to set published status: {status_err}', task_id=task_id)

            log_and_emit('INFO', 'report', f'[generate_task_report_async] Report generated successfully, report_id={report_id}', task_id=task_id)

            emit_data = {
                'taskId': task_id,
                'reportId': report_id,
                'success': True,
                'status': 'completed'
            }
            log_and_emit('INFO', 'report', f'[generate_task_report_async] Emitting report_generated: {emit_data}', task_id=task_id)
            _emit_report_event('report_generated', emit_data)

        except Exception as e:
            log_and_emit('ERROR', 'report', f'[generate_task_report_async] Error: {e}\n{traceback.format_exc()}', task_id=task_id)
            emit_data = {
                'taskId': task_id,
                'success': False,
                'error': '报告生成失败，请稍后重试'
            }
            log_and_emit('INFO', 'report', f'[generate_task_report_async] Emitting error: {emit_data}', task_id=task_id)
            _emit_report_event('report_generated', emit_data)
        finally:
            # 释放分布式去重锁（替代原进程内 set.discard）
            if lock is not None:
                lock.release()
