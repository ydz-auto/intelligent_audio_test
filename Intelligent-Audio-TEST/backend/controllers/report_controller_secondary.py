from flask import request
from backend.models.models import (
    Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCases,
    ReportMetricStats, ReportComparisonMatrix, Task, TestResult, TestResultDimension,
    Dimension, TestCase, TaskCase, TaskDevice, TaskAPI, Device, API,
    ReportStatus, ReportType, TaskStatus
)
from backend.models.database import db
from backend.utils.response import success_response, error_response
from backend.utils.error_codes import ErrorCode
from backend.utils.report_utils import ReportUtils
from backend.utils.log_handler import log_and_emit
from backend.algorithm.reference_params_generator import ReferenceParamsGenerator
from backend.schemas.report import SecondaryCompareRequest
from backend.schemas.common import IdData
from backend.controllers.report_controller_base import ReportControllerBase
from backend.controllers.report_controller_task import ReportControllerTask
from backend.app import socketio
from datetime import datetime, timedelta, timezone
import json
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor

_secondary_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='secondary_compare')
_generating_secondary = {}
_generating_secondary_lock = threading.Lock()


class ReportControllerSecondary(ReportControllerBase):

    @staticmethod
    def _validate_reports_and_get_tasks(report_ids):
        reports = Report.query.filter(Report.id.in_(report_ids)).order_by(Report.created_at.asc()).all()
        if len(reports) < 2:
            return None, None, None, "二次对比至少需要两个报告"

        task_ids = set()
        for report in reports:
            if report.task_id:
                task_ids.add(report.task_id)
            elif report.type in ('comparison', 'secondary_comparison'):
                summary_info = getattr(report, 'summary_info', None)
                if summary_info and summary_info.task_ids:
                    for tid in summary_info.task_ids:
                        task_ids.add(tid)

        task_ids = list(task_ids)
        tasks = []
        if task_ids:
            tasks = Task.query.filter(
                Task.id.in_(task_ids),
                Task.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value])
            ).all()

        if not tasks:
            return None, None, None, "未找到关联的任务数据"

        return reports, tasks, task_ids, None

    @staticmethod
    def _get_task_type(tasks):
        included_task_types = {t.type for t in tasks if getattr(t, "type", None)}
        if included_task_types == {"api"}:
            return "api"
        elif included_task_types == {"e2e"}:
            return "e2e"
        return "all"

    @staticmethod
    def _collect_all_resources(task_ids, tasks):
        results = TestResult.query.filter(TestResult.task_id.in_(task_ids)).all()
        if not results:
            return None, None, None, None, None, "未找到测试结果数据"

        resources = set()
        for t in tasks:
            task_results = [r for r in results if r.task_id == t.id]
            for res in task_results:
                resource = ReportControllerBase.get_resource_name(res, t, use_time_prefix=False)
                if resource:
                    resources.add(resource)

        if not resources:
            resources = {"默认资源"}
        resources = sorted(list(resources))

        devices_list, apis_list, device_ids, api_ids = ReportControllerTask._get_task_resources(task_ids)

        if not devices_list and not apis_list:
            return None, None, None, None, None, "未找到设备或API资源数据"

        return results, resources, devices_list, apis_list, device_ids, api_ids, None

    @staticmethod
    def _build_all_dimensions(result_ids):
        used_dim_ids = set()
        if result_ids:
            rows = db.session.query(TestResultDimension.dimension_id).filter(
                TestResultDimension.test_result_id.in_(result_ids)
            ).distinct().all()
            used_dim_ids = {r[0] for r in rows if r and r[0] is not None}

        all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
        all_dimensions = [d for d in all_dimensions_all if d.id in used_dim_ids] if used_dim_ids else all_dimensions_all

        if not all_dimensions:
            return None, None, "未找到评估维度数据"

        all_metrics = ReportControllerTask._build_all_metrics(all_dimensions)
        return all_dimensions, all_metrics, None

    @staticmethod
    def _build_comparison_matrix(task_ids, reports, all_dimensions):
        comparison_matrix = {}
        if not task_ids:
            return {}

        results = TestResult.query.filter(TestResult.task_id.in_(task_ids)).all()
        dim_map = {d.id: d for d in all_dimensions}

        for res in results:
            if res.test_case_id not in comparison_matrix:
                case = db.session.get(TestCase, res.test_case_id)
                comparison_matrix[res.test_case_id] = {
                    "case_id": res.test_case_id,
                    "case_name": case.name if case else res.test_case_id
                }

            dimensions = TestResultDimension.query.filter_by(test_result_id=res.id).all()
            dim_values = {}
            for d in dimensions:
                if d.dimension_id in dim_map:
                    dim_values[dim_map[d.dimension_id].name] = d.dimension_value or 0

            for dim in all_dimensions:
                if dim.name not in dim_values:
                    dim_values[dim.name] = 0

            comparison_matrix[res.test_case_id][f"task_{res.task_id}"] = {
                "status": 'completed' if res.execution_status == 'completed' else 'failed',
                "response_time": res.response_time or 0,
                "values": dim_values
            }

        return {
            "report_ids": [r.id for r in reports],
            "report_names": [r.name for r in reports],
            "task_ids": task_ids,
            "task_names": [],
            "matrix": comparison_matrix,
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat()
        }

    @staticmethod
    def _get_source_cases_from_reports(reports):
        source_cases = []
        for report in reports:
            cases_data = ReportCases.query.filter_by(report_id=report.id).first()
            if cases_data and cases_data.cases:
                if isinstance(cases_data.cases, list):
                    source_cases.extend(cases_data.cases)
                elif isinstance(cases_data.cases, str):
                    source_cases.extend(json.loads(cases_data.cases))
        return source_cases

    @staticmethod
    def _create_secondary_report_records(
        new_report_id, task_ids, tasks, reports,
        case_categories_list, case_tags_list,
        devices_list, apis_list, resources, resource_headers, all_metrics,
        raw_data, metric_data, tag_metric_data, case_type_stats,
        device_stats, api_stats, source_cases, comparison_matrix_data
    ):
        total_cases = sum(t.total_cases for t in tasks) if tasks else 0
        completed_cases = sum(t.completed_cases - t.failed_cases for t in tasks) if tasks else 0
        failed_cases = sum(t.failed_cases for t in tasks) if tasks else 0
        success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

        summary_info = ReportSummary(
            report_id=new_report_id,
            task_ids=task_ids,
            total_cases=total_cases,
            completed_cases=completed_cases,
            failed_cases=failed_cases,
            pass_rate=round(success_rate, 2),
            duration=0,
            started_at=None,
            completed_at=None
        )
        db.session.add(summary_info)

        summary_meta = ReportSummaryMeta(
            report_id=new_report_id,
            dimension_values=json.dumps([], ensure_ascii=False),
            case_categories=json.dumps(case_categories_list, ensure_ascii=False),
            all_case_tags=json.dumps(case_tags_list, ensure_ascii=False),
            devices=json.dumps(devices_list, ensure_ascii=False),
            apis=json.dumps(apis_list, ensure_ascii=False),
            resources=json.dumps(resources, ensure_ascii=False),
            resource_headers=json.dumps(resource_headers, ensure_ascii=False),
            all_metrics=json.dumps(all_metrics, ensure_ascii=False)
        )
        db.session.add(summary_meta)

        raw_data_record = ReportRawData(
            report_id=new_report_id,
            raw_data=json.dumps(raw_data, ensure_ascii=False)
        )
        db.session.add(raw_data_record)

        cases_record = ReportCases(
            report_id=new_report_id,
            cases=json.dumps(source_cases, ensure_ascii=False)
        )
        db.session.add(cases_record)

        metric_stats_record = ReportMetricStats(
            report_id=new_report_id,
            metric_data=json.dumps(metric_data, ensure_ascii=False),
            tag_metric_data=json.dumps(tag_metric_data, ensure_ascii=False),
            case_type_stats=json.dumps(case_type_stats, ensure_ascii=False),
            device_stats=json.dumps(device_stats, ensure_ascii=False),
            api_stats=json.dumps(api_stats, ensure_ascii=False)
        )
        db.session.add(metric_stats_record)

        comparison_matrix_record = ReportComparisonMatrix(
            report_id=new_report_id,
            comparison_matrix=json.dumps(comparison_matrix_data, ensure_ascii=False)
        )
        db.session.add(comparison_matrix_record)

        return summary_info

    def secondary_compare():
        try:
            validated_data = SecondaryCompareRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        report_ids = validated_data.report_ids
        description = validated_data.description

        if not report_ids:
            return error_response("缺少必要参数: reportIds")
        if len(report_ids) < 2:
            return error_response("二次对比至少需要两个报告 ID")

        report_key = tuple(sorted(report_ids))

        with _generating_secondary_lock:
            if report_key in _generating_secondary:
                return success_response(
                    {"reportKey": list(report_key), "status": "generating"},
                    "对比报告正在生成中",
                    ErrorCode.SUCCESS
                )
            _generating_secondary[report_key] = True

        log_and_emit('INFO', 'report', f'[secondary_compare] Submitting async task for report_ids={report_ids}')
        _secondary_executor.submit(
            ReportControllerSecondary._secondary_compare_async,
            report_ids, description, report_key
        )

        return success_response(
            {"reportKey": list(report_key), "status": "generating"},
            "对比报告生成中，请稍后",
            ErrorCode.SUCCESS
        )

    @staticmethod
    def _secondary_compare_async(report_ids, description, report_key):
        from backend.app import app as flask_app
        if flask_app is None:
            log_and_emit('ERROR', 'report', '[secondary_compare_async] Flask app is None')
            with _generating_secondary_lock:
                _generating_secondary.pop(report_key, None)
            socketio.emit('secondary_compare_generated', {
                'reportIds': report_ids,
                'success': False,
                'error': '服务器内部错误'
            })
            return

        with flask_app.app_context():
            try:
                log_and_emit('INFO', 'report', f'[secondary_compare_async] Starting for report_ids={report_ids}')

                reports, tasks, task_ids, error = ReportControllerSecondary._validate_reports_and_get_tasks(report_ids)
                if error:
                    with _generating_secondary_lock:
                        _generating_secondary.pop(report_key, None)
                    socketio.emit('secondary_compare_generated', {
                        'reportIds': report_ids,
                        'success': False,
                        'error': error
                    })
                    return

                report_task_type = ReportControllerSecondary._get_task_type(tasks)

                results, resources, devices_list, apis_list, device_ids, api_ids, error = \
                    ReportControllerSecondary._collect_all_resources(task_ids, tasks)
                if error:
                    with _generating_secondary_lock:
                        _generating_secondary.pop(report_key, None)
                    socketio.emit('secondary_compare_generated', {
                        'reportIds': report_ids,
                        'success': False,
                        'error': error
                    })
                    return

                res_ids = [r.id for r in results]
                all_dimensions, all_metrics, error = ReportControllerSecondary._build_all_dimensions(res_ids)
                if error:
                    with _generating_secondary_lock:
                        _generating_secondary.pop(report_key, None)
                    socketio.emit('secondary_compare_generated', {
                        'reportIds': report_ids,
                        'success': False,
                        'error': error
                    })
                    return

                dim_results_map, _ = ReportControllerTask._get_dimension_results_batch(res_ids)

                tasks_map = {t.id: t for t in tasks}
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

                test_cases, _ = ReportControllerTask._get_task_test_cases(task_ids)
                case_categories_list, case_tags_list = [], []
                if test_cases:
                    from backend.utils.report_query_builder import ReportQueryBuilder
                    case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

                if not case_categories_list:
                    case_categories_list = [{"id": "default_group", "name": "无分组"}]
                if not case_tags_list:
                    case_tags_list = [{"id": "default_tag", "name": "无标签"}]

                source_cases = ReportControllerSecondary._get_source_cases_from_reports(reports)
                if not source_cases:
                    cases = ReportControllerTask._build_case_data(
                        test_cases, results, all_dimensions, dim_results_map, tasks[0] if tasks else None
                    )
                    source_cases = cases

                comparison_matrix_data = ReportControllerSecondary._build_comparison_matrix(
                    task_ids, reports, all_dimensions
                )

                name = f"二次对比报告_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d%H%M%S')}"
                new_report = Report(
                    name=name,
                    type=ReportType.SECONDARY_COMPARISON.value,
                    description=description,
                    status=ReportStatus.DRAFT.value
                )
                db.session.add(new_report)
                db.session.flush()

                ReportControllerSecondary._create_secondary_report_records(
                    new_report.id, task_ids, tasks, reports,
                    case_categories_list, case_tags_list,
                    devices_list, apis_list, resources, resource_headers, all_metrics,
                    raw_data, metric_data, tag_metric_data, case_type_stats,
                    device_stats, api_stats, source_cases, comparison_matrix_data
                )

                db.session.commit()
                log_and_emit('INFO', 'report', f'[secondary_compare_async] Report generated successfully, report_id={new_report.id}')

                socketio.emit('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'reportId': new_report.id,
                    'success': True,
                    'status': 'completed'
                })

            except Exception as e:
                db.session.rollback()
                log_and_emit('ERROR', 'report', f'[secondary_compare_async] Error: {e}\n{traceback.format_exc()}')
                socketio.emit('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': '对比报告生成失败，请稍后重试'
                })
            finally:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
