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
"""

from shared.models.common_enums import ReportStatus, ReportType, TaskStatus
from shared.utils.log_handler import log_and_emit
from shared.utils.query_utils import now_cst
import json
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor

from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder
from report_service.application.services.report_data_builder import ReportDataBuilder
from report_service.application.services.report_compare_helpers import ReportCompareHelpers
from report_service.application.services.report_compare_helpers import (
    _grpc_get_tasks_by_ids, _grpc_get_test_results_by_task_ids,
)
from report_service.domain.entities import ReportAggregate
from report_service.infrastructure.persistence.report_repository import report_repository

# 复用 grpc_clients 中已定义的 gRPC helper，避免重复实现
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_list_testcases_by_ids, _dim_id, _dim_name, _dim_weight,
    _dim_score_unit, _dim_decimal_places,
)


_secondary_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='secondary_compare')
_generating_secondary = {}
_generating_secondary_lock = threading.Lock()


def _emit_secondary_compare_event(event_name, data):
    """通过 SSE 推送二次对比报告生成事件（替代 socketio.emit）"""
    try:
        from api_gateway.routes.sse_bp import event_cache
        event_cache.add_event(event_name, data)
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(f"SSE event emit failed: {_e}")


class ReportCompareGenerator:
    """对比报告生成（原 ReportCommandService 中 D + E 组方法）。

    承载对比报告与二次对比报告生成相关的静态方法，保持原有逻辑不变。
    """

    # ------------------------------------------------------------------
    # 对比报告生成（原 ReportControllerCompare）
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_and_get_tasks(task_ids):
        """校验任务状态，返回 (tasks, error_message) 或 (None, error)。"""
        all_tasks = _grpc_get_tasks_by_ids(task_ids)
        valid_statuses = {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value}
        tasks = []
        for t in all_tasks:
            status = t.get('status') if isinstance(t, dict) else getattr(t, 'status', None)
            if status in valid_statuses:
                tasks.append(t)
        if not tasks:
            return None, "未找到指定任务或任务状态不是completed、failed或merged"
        return tasks, None

    @staticmethod
    def _prepare_compare_data(tasks, task_ids, results):
        """准备对比数据。返回 (data_dict, None) 或 (None, error_message)。"""
        def _t_get(t, key, default=None):
            if isinstance(t, dict):
                return t.get(key, default)
            return getattr(t, key, default)

        def _r_get(r, key, default=None):
            if isinstance(r, dict):
                return r.get(key, default)
            return getattr(r, key, default)

        included_task_types = {_t_get(t, 'type') for t in tasks if _t_get(t, 'type')}
        report_task_type = (
            "api"
            if included_task_types == {"api"}
            else ("e2e" if included_task_types == {"e2e"} else "all")
        )

        res_ids_all = [_r_get(r, 'id') for r in results]
        all_dimensions = ReportCompareHelpers._get_all_dimensions_with_results(res_ids_all)

        task_weighted_values = ReportCompareHelpers._calculate_task_weighted_values(
            task_ids, results, all_dimensions
        )

        total_cases = sum(_t_get(t, 'total_cases', 0) or 0 for t in tasks)
        completed_cases = sum((_t_get(t, 'completed_cases', 0) or 0) - (_t_get(t, 'failed_cases', 0) or 0) for t in tasks)
        success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

        test_case_ids = set()
        for res in results:
            tc_id = _r_get(res, 'test_case_id')
            if tc_id is not None:
                test_case_ids.add(tc_id)

        test_cases = _grpc_list_testcases_by_ids(list(test_case_ids)) if test_case_ids else []

        case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

        resource_names, device_list, api_list = ReportCompareHelpers._collect_resources_batch(tasks, results)

        if not resource_names:
            resource_names = {"默认资源"}

        resource_list = sorted(list(resource_names))
        resources = resource_list

        if not device_list and not api_list:
            return None, "对比失败: 未找到设备或API资源数据"

        all_metrics = []
        for dim in all_dimensions:
            unit = _dim_score_unit(dim)
            unit = unit if unit and str(unit).strip() else "%"
            decimal_places = _dim_decimal_places(dim)
            decimal_places = decimal_places if decimal_places is not None else 2
            all_metrics.append({"id": _dim_id(dim), "name": _dim_name(dim), "unit": unit, "decimal_places": decimal_places})

        if not all_metrics:
            return None, "对比失败: 未找到评估维度数据"

        if not results:
            return None, "对比失败: 未找到测试结果数据"

        tasks_map = {}
        for t in tasks:
            t_id = _t_get(t, 'id')
            if t_id is not None:
                tasks_map[t_id] = t

        core_metrics = ReportUtils.calculate_core_metrics(
            results=results,
            all_dimensions=all_dimensions,
            resources=resources,
            dim_results_map=None,
            tasks_map=tasks_map,
            use_time_prefix=True
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
            use_time_prefix=True,
        )

        device_stats, api_stats = ReportUtils.calculate_device_api_stats(
            results=results,
            all_dimensions=all_dimensions,
            dim_results_map=None
        )

        cases = ReportCompareHelpers._build_case_data_compare(
            test_cases, results, all_dimensions, tasks_map, report_task_type
        )

        source_cases = ReportCompareHelpers._get_source_cases(tasks)
        if not source_cases:
            source_cases = cases

        comparison_matrix = ReportCompareHelpers._build_comparison_matrix(results, all_dimensions)

        task_names = []
        for t in tasks:
            task_names.append(_t_get(t, 'name', ''))

        comparison_data = {
            "task_ids": task_ids,
            "task_names": task_names,
            "matrix": comparison_matrix,
            "weighted_values": task_weighted_values,
            "generated_at": now_cst().isoformat()
        }

        return {
            "report_task_type": report_task_type,
            "task_weighted_values": task_weighted_values,
            "total_cases": total_cases,
            "success_rate": success_rate,
            "test_cases": test_cases,
            "case_categories_list": case_categories_list,
            "case_tags_list": case_tags_list,
            "device_list": device_list,
            "api_list": api_list,
            "resources": resources,
            "all_metrics": all_metrics,
            "metric_data": metric_data,
            "tag_metric_data": tag_metric_data,
            "raw_data": raw_data,
            "case_type_stats": case_type_stats,
            "device_stats": device_stats,
            "api_stats": api_stats,
            "source_cases": source_cases,
            "resource_headers": resource_headers,
            "comparison_data": comparison_data,
        }, None

    @staticmethod
    def _build_compare_summary(tasks, task_ids, results, data_dict):
        """构建 summary dict。"""
        def _t_get(t, key, default=None):
            if isinstance(t, dict):
                return t.get(key, default)
            return getattr(t, key, default)

        tasks_info = []
        for t in tasks:
            t_id = _t_get(t, 'id')
            tasks_info.append({
                "id": t_id,
                "name": _t_get(t, 'name'),
                "status": _t_get(t, 'status'),
                "type": _t_get(t, 'type'),
                "weighted_value": data_dict["task_weighted_values"].get(t_id, 0)
            })

        summary = {
            "task_count": len(tasks),
            "task_type": data_dict["report_task_type"],
            "total_cases": data_dict["total_cases"],
            "overall_success_rate": round(data_dict["success_rate"], 2),
            "tasks_info": tasks_info,
            "case_categories": data_dict["case_categories_list"],
            "all_case_tags": data_dict["case_tags_list"],
            "all_tags": data_dict["case_tags_list"],
            "devices": data_dict["device_list"],
            "apis": data_dict["api_list"],
            "resources": data_dict["resources"],
            "resource_headers": data_dict["resource_headers"],
            "all_metrics": data_dict["all_metrics"],
            "metric_data": data_dict["metric_data"],
            "tag_metric_data": data_dict["tag_metric_data"],
            "raw_data": data_dict["raw_data"],
            "device_stats": data_dict["device_stats"],
            "api_stats": data_dict["api_stats"],
            "case_type_stats": data_dict["case_type_stats"],
            "cases": data_dict["source_cases"]
        }

        summary = ReportUtils.normalize_summary_metrics(summary)
        return summary

    @staticmethod
    def _persist_compare_report(name, description, summary, source_cases, comparison_data):
        """创建对比报告及其关联子表记录。

        原实现使用 get_db_session().add(...) / commit() 直连 PO；
        迁移后改用 report_repository 对应方法写入，每个方法自管理事务。
        返回 new_report_id。
        """
        # 主报告聚合根：使用字符串字面量保持与现有数据模型一致
        aggregate = ReportAggregate(
            task_id=0,
            report_type='comparison',
            status='draft',
            config={'name': name, 'description': description},
            deleted=False,
        )
        new_report_id = report_repository.add(aggregate)

        # 摘要
        summary_data = {
            'total_cases': summary.get('total_cases', 0),
            'completed_cases': summary.get('total_cases', 0),
            'failed_cases': 0,
            'pass_rate': summary.get('overall_success_rate', 0),
            'duration': 0,
            'started_at': None,
            'completed_at': None,
        }
        report_repository.add_summary(new_report_id, summary_data)

        # 摘要元数据
        meta_data = {
            'dimension_values': json.dumps(summary.get('dimension_values', []), ensure_ascii=False),
            'case_categories': json.dumps(summary.get('case_categories', []), ensure_ascii=False),
            'all_case_tags': json.dumps(summary.get('all_case_tags', []), ensure_ascii=False),
            'devices': json.dumps(summary.get('devices', []), ensure_ascii=False),
            'apis': json.dumps(summary.get('apis', []), ensure_ascii=False),
            'resources': json.dumps(summary.get('resources', []), ensure_ascii=False),
            'resource_headers': json.dumps(summary.get('resource_headers', []), ensure_ascii=False),
            'all_metrics': json.dumps(summary.get('all_metrics', []), ensure_ascii=False),
        }
        report_repository.add_summary_meta(new_report_id, meta_data)

        # 原始数据
        report_repository.add_raw_data(new_report_id, {
            'raw_data': json.dumps(summary.get('raw_data', []), ensure_ascii=False),
        })

        # 用例记录
        for case_item in source_cases:
            if not isinstance(case_item, dict):
                continue
            report_repository.add_case(new_report_id, {
                'test_case_id': case_item.get('id'),
                'name': case_item.get('name'),
                'description': case_item.get('description'),
                'category': case_item.get('category'),
                'tags': case_item.get('tags'),
                'metrics': case_item.get('metrics'),
                'results': case_item.get('results'),
                'audios': case_item.get('audios'),
                'reference_params': case_item.get('reference_params'),
                'algorithm_results': case_item.get('algorithm_results'),
                'algorithm_type': case_item.get('algorithm_type'),
                'logs': case_item.get('logs'),
            })

        # 指标统计
        stats_data = {
            'metric_data': json.dumps(summary.get('metric_data', []), ensure_ascii=False),
            'tag_metric_data': json.dumps(summary.get('tag_metric_data', []), ensure_ascii=False),
            'case_type_stats': json.dumps(summary.get('case_type_stats', []), ensure_ascii=False),
            'device_stats': json.dumps(summary.get('device_stats', []), ensure_ascii=False),
            'api_stats': json.dumps(summary.get('api_stats', []), ensure_ascii=False),
        }
        report_repository.add_metric_stats(new_report_id, stats_data)

        # 对比矩阵
        report_repository.add_comparison_matrix(new_report_id, {
            'comparison_matrix': json.dumps(comparison_data, ensure_ascii=False),
        })

        return new_report_id

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
        """
        if not task_ids:
            return {'success': False, 'data': None, 'message': '缺少必要参数: taskIds'}

        if not name:
            name = f"对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"

        try:
            tasks, error = ReportCompareGenerator._validate_and_get_tasks(task_ids)
            if error:
                return {'success': False, 'data': None, 'message': error}

            results = _grpc_get_test_results_by_task_ids(task_ids)

            data_dict, error = ReportCompareGenerator._prepare_compare_data(tasks, task_ids, results)
            if error:
                return {'success': False, 'data': None, 'message': error}

            summary = ReportCompareGenerator._build_compare_summary(tasks, task_ids, results, data_dict)

            new_report_id = ReportCompareGenerator._persist_compare_report(
                name, description, summary, data_dict["source_cases"], data_dict["comparison_data"]
            )

            return {
                'success': True,
                'data': {'report_id': new_report_id},
                'message': '对比报告生成成功',
            }
        except Exception as e:
            traceback.print_exc()
            return {'success': False, 'data': None, 'message': '对比报告生成失败，请稍后重试'}

    # ------------------------------------------------------------------
    # 二次对比报告生成（原 ReportControllerSecondary）
    # ------------------------------------------------------------------

    @staticmethod
    def _create_secondary_report_records(
        new_report_id, task_ids, tasks, reports,
        case_categories_list, case_tags_list,
        devices_list, apis_list, resources, resource_headers, all_metrics,
        raw_data, metric_data, tag_metric_data, case_type_stats,
        device_stats, api_stats, source_cases, comparison_matrix_data
    ):
        """创建二次对比报告的关联子表记录。

        原实现使用 get_db_session().add(...) 直连 PO；
        迁移后改用 report_repository 对应方法写入。
        """
        def _t_get(t, key, default=0):
            if isinstance(t, dict):
                return t.get(key, default)
            return getattr(t, key, default)

        total_cases = sum(_t_get(t, 'total_cases', 0) or 0 for t in tasks) if tasks else 0
        completed_cases = sum((_t_get(t, 'completed_cases', 0) or 0) - (_t_get(t, 'failed_cases', 0) or 0) for t in tasks) if tasks else 0
        failed_cases = sum(_t_get(t, 'failed_cases', 0) or 0 for t in tasks) if tasks else 0
        success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

        summary_data = {
            'task_ids': task_ids,
            'total_cases': total_cases,
            'completed_cases': completed_cases,
            'failed_cases': failed_cases,
            'pass_rate': round(success_rate, 2),
            'duration': 0,
            'started_at': None,
            'completed_at': None,
        }
        report_repository.add_summary(new_report_id, summary_data)

        meta_data = {
            'dimension_values': json.dumps([], ensure_ascii=False),
            'case_categories': json.dumps(case_categories_list, ensure_ascii=False),
            'all_case_tags': json.dumps(case_tags_list, ensure_ascii=False),
            'devices': json.dumps(devices_list, ensure_ascii=False),
            'apis': json.dumps(apis_list, ensure_ascii=False),
            'resources': json.dumps(resources, ensure_ascii=False),
            'resource_headers': json.dumps(resource_headers, ensure_ascii=False),
            'all_metrics': json.dumps(all_metrics, ensure_ascii=False),
        }
        report_repository.add_summary_meta(new_report_id, meta_data)

        report_repository.add_raw_data(new_report_id, {
            'raw_data': json.dumps(raw_data, ensure_ascii=False),
        })

        for case_item in source_cases:
            if not isinstance(case_item, dict):
                continue
            report_repository.add_case(new_report_id, {
                'test_case_id': case_item.get('id'),
                'name': case_item.get('name'),
                'description': case_item.get('description'),
                'category': case_item.get('category'),
                'tags': case_item.get('tags'),
                'metrics': case_item.get('metrics'),
                'results': case_item.get('results'),
                'audios': case_item.get('audios'),
                'reference_params': case_item.get('reference_params'),
                'algorithm_results': case_item.get('algorithm_results'),
                'algorithm_type': case_item.get('algorithm_type'),
                'logs': case_item.get('logs'),
            })

        stats_data = {
            'metric_data': json.dumps(metric_data, ensure_ascii=False),
            'tag_metric_data': json.dumps(tag_metric_data, ensure_ascii=False),
            'case_type_stats': json.dumps(case_type_stats, ensure_ascii=False),
            'device_stats': json.dumps(device_stats, ensure_ascii=False),
            'api_stats': json.dumps(api_stats, ensure_ascii=False),
        }
        report_repository.add_metric_stats(new_report_id, stats_data)

        report_repository.add_comparison_matrix(new_report_id, {
            'comparison_matrix': json.dumps(comparison_matrix_data, ensure_ascii=False),
        })

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
        _secondary_executor.submit(
            ReportCompareGenerator._secondary_compare_async,
            report_ids, description, report_key
        )

        return {
            'success': True,
            'data': {'reportKey': list(report_key), 'status': 'generating'},
            'message': '对比报告生成中，请稍后',
        }

    @staticmethod
    def _prepare_secondary_data(report_ids, reports, tasks, task_ids):
        """准备二次对比数据。返回 (data_dict, None) 或 (None, error)。"""
        report_task_type = ReportCompareHelpers._get_task_type(tasks)

        results, resources, devices_list, apis_list, device_ids, api_ids, error = \
            ReportCompareHelpers._collect_all_resources(task_ids, tasks)
        if error:
            return None, error

        res_ids = [(r.get('id') if isinstance(r, dict) else getattr(r, 'id', None)) for r in results]
        res_ids = [rid for rid in res_ids if rid is not None]
        all_dimensions, all_metrics, error = ReportCompareHelpers._build_all_dimensions(res_ids)
        if error:
            return None, error

        dim_results_map, _ = ReportDataBuilder._get_dimension_results_batch(res_ids)

        tasks_map = {}
        for t in tasks:
            t_id = t.get('id') if isinstance(t, dict) else getattr(t, 'id', None)
            if t_id is not None:
                tasks_map[t_id] = t
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

        test_cases, _ = ReportDataBuilder._get_task_test_cases(task_ids)
        case_categories_list, case_tags_list = [], []
        if test_cases:
            case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

        if not case_categories_list:
            case_categories_list = [{"id": "default_group", "name": "无分组"}]
        if not case_tags_list:
            case_tags_list = [{"id": "default_tag", "name": "无标签"}]

        source_cases = ReportCompareHelpers._get_source_cases_from_reports(reports)
        if not source_cases:
            cases = ReportDataBuilder._build_case_data(
                test_cases, results, all_dimensions, dim_results_map, tasks[0] if tasks else None
            )
            source_cases = cases

        comparison_matrix_data = ReportCompareHelpers._build_comparison_matrix_secondary(
            task_ids, reports, all_dimensions
        )

        return {
            "report_task_type": report_task_type,
            "results": results,
            "resources": resources,
            "devices_list": devices_list,
            "apis_list": apis_list,
            "device_ids": device_ids,
            "api_ids": api_ids,
            "all_dimensions": all_dimensions,
            "all_metrics": all_metrics,
            "dim_results_map": dim_results_map,
            "metric_data": metric_data,
            "tag_metric_data": tag_metric_data,
            "raw_data": raw_data,
            "case_type_stats": case_type_stats,
            "resource_headers": resource_headers,
            "device_stats": device_stats,
            "api_stats": api_stats,
            "case_categories_list": case_categories_list,
            "case_tags_list": case_tags_list,
            "source_cases": source_cases,
            "comparison_matrix_data": comparison_matrix_data,
        }, None

    @staticmethod
    def _build_secondary_summary(tasks, task_ids, reports, data_dict):
        """构建二次对比 summary。"""
        return {
            "case_categories_list": data_dict["case_categories_list"],
            "case_tags_list": data_dict["case_tags_list"],
            "devices_list": data_dict["devices_list"],
            "apis_list": data_dict["apis_list"],
            "resources": data_dict["resources"],
            "resource_headers": data_dict["resource_headers"],
            "all_metrics": data_dict["all_metrics"],
            "raw_data": data_dict["raw_data"],
            "metric_data": data_dict["metric_data"],
            "tag_metric_data": data_dict["tag_metric_data"],
            "case_type_stats": data_dict["case_type_stats"],
            "device_stats": data_dict["device_stats"],
            "api_stats": data_dict["api_stats"],
            "source_cases": data_dict["source_cases"],
            "comparison_matrix_data": data_dict["comparison_matrix_data"],
        }

    @staticmethod
    def _secondary_compare_async(report_ids, description, report_key):
        """二次对比报告异步生成任务。

        原实现使用 get_db_session().add(new_report) / flush() / commit() /
        rollback() 直连 PO；迁移后改用 report_repository.add 写入主报告聚合根，
        子表记录通过 _create_secondary_report_records 使用 repository 方法写入。
        """
        try:
            log_and_emit('INFO', 'report', f'[secondary_compare_async] Starting for report_ids={report_ids}')

            reports, tasks, task_ids, error = ReportCompareHelpers._validate_reports_and_get_tasks(report_ids)
            if error:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            data_dict, error = ReportCompareGenerator._prepare_secondary_data(report_ids, reports, tasks, task_ids)
            if error:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            summary = ReportCompareGenerator._build_secondary_summary(tasks, task_ids, reports, data_dict)

            name = f"二次对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"
            # 主报告聚合根：使用字符串字面量保持与现有数据模型一致
            aggregate = ReportAggregate(
                task_id=0,
                report_type='secondary_comparison',
                status='draft',
                config={'name': name, 'description': description},
                deleted=False,
            )
            new_report_id = report_repository.add(aggregate)

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

            log_and_emit('INFO', 'report', f'[secondary_compare_async] Report generated successfully, report_id={new_report_id}')

            _emit_secondary_compare_event('secondary_compare_generated', {
                'reportIds': report_ids,
                'reportId': new_report_id,
                'success': True,
                'status': 'completed'
            })

        except Exception as e:
            log_and_emit('ERROR', 'report', f'[secondary_compare_async] Error: {e}\n{traceback.format_exc()}')
            _emit_secondary_compare_event('secondary_compare_generated', {
                'reportIds': report_ids,
                'success': False,
                'error': '对比报告生成失败，请稍后重试'
            })
        finally:
            with _generating_secondary_lock:
                _generating_secondary.pop(report_key, None)
