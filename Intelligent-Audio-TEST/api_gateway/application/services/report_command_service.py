from api_gateway.infrastructure.request_adapter import request
from shared.models.models import (
    Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase,
    ReportMetricStats, ReportComparisonMatrix, Task, TestResult, TestResultDimension,
    Dimension, TestCase, Audio, Device, API, TaskCase, TaskDevice, TaskAPI,
    ReportStatus, ReportType, TaskStatus,
)
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.error_codes import ErrorCode
from shared.utils.report.report_utils import ReportUtils
from shared.utils.log_handler import log_and_emit
from shared.utils.report.report_query_builder import ReportQueryBuilder
from shared.utils.result_data_store import load_full_result_data
from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
from api_gateway.schemas.report import (
    ReportBatchDeleteRequest,
    ReportUpdateRequest,
    GenerateTaskReportRequest,
    CompareReportsRequest,
    SecondaryCompareRequest,
    ReportDetailData as ReportDetailDataSchema,
    ReportSummarySimplified,
    ReportIdData,
)
from api_gateway.schemas.common import IdData
from datetime import datetime, timedelta, timezone
from shared.utils.query_utils import now_cst
from sqlalchemy.orm import joinedload
import json
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor


def _emit_report_event(event_name, data):
    """通过 SSE 推送报告生成事件（替代 socketio.emit）"""
    try:
        from api_gateway.routes.sse_bp import event_cache
        event_cache.add_event(event_name, data)
    except Exception:
        pass


_report_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='report_gen')
_generating_tasks = set()
_generating_lock = threading.Lock()

_secondary_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='secondary_compare')
_generating_secondary = {}
_generating_secondary_lock = threading.Lock()


def _emit_secondary_compare_event(event_name, data):
    """通过 SSE 推送二次对比报告生成事件（替代 socketio.emit）"""
    try:
        from api_gateway.routes.sse_bp import event_cache
        event_cache.add_event(event_name, data)
    except Exception:
        pass


class ReportCommandService:
    """报告写操作 Service（CQRS Command Side）。

    承载 ReportController 家族中所有写操作与生成报告方法，
    保持原有逻辑不变，只是从 controller 搬运到 service。
    """

    # ------------------------------------------------------------------
    # CRUD 写操作（原 ReportController）
    # ------------------------------------------------------------------

    # 删除测试报告
    @staticmethod
    def delete(report_id):
        report = db.session.get(Report, report_id)
        if not report or report.deleted:
            return error_response("未找到测试报告", 404)

        try:
            now = now_cst()
            report.deleted = True
            report.deleted_at = now
            report.updated_at = now
            db.session.commit()
            return success_response(None, "测试报告已删除")
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return error_response("删除报告失败，请稍后重试")

    @staticmethod
    def update(report_id):
        report = db.session.get(Report, report_id)
        if not report or report.deleted:
            return error_response("未找到测试报告", 404)

        try:
            req = ReportUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        def pick(*keys):
            for k in keys:
                val = getattr(req, k, None)
                if val is not None:
                    return val
            return None

        name = pick("name", "title")
        description = req.description
        analysis = pick("analysis", "conclusion")
        status = req.status
        incoming_summary = req.summary

        def normalize_summary_keys(summary_dict):
            if not isinstance(summary_dict, dict):
                return None
            mapping = {
                "caseCategories": "case_categories",
                "allCaseTags": "all_case_tags",
                "allTags": "all_tags",
                "resourceHeaders": "resource_headers",
                "allMetrics": "all_metrics",
                "metricData": "metric_data",
                "tagMetricData": "tag_metric_data",
                "rawData": "raw_data",
                "deviceStats": "device_stats",
                "apiStats": "api_stats",
                "caseTypeStats": "case_type_stats",
            }
            normalized = {}
            for k, v in summary_dict.items():
                normalized[mapping.get(k, k)] = v
            return normalized

        try:
            if name is not None:
                report.name = str(name)
            if description is not None:
                report.description = str(description)
            if analysis is not None:
                report.analysis = str(analysis)
            if status is not None:
                report.status = str(status)

            summary_info = ReportSummary.query.filter_by(report_id=report.id).first()
            summary_meta = ReportSummaryMeta.query.filter_by(report_id=report.id).first()
            raw_data_record = ReportRawData.query.filter_by(report_id=report.id).first()
            metric_stats_record = ReportMetricStats.query.filter_by(report_id=report.id).first()

            if not summary_info:
                return error_response("报告数据未迁移，请先运行迁移脚本", 500)

            if incoming_summary is not None:
                normalized_incoming = normalize_summary_keys(incoming_summary)
                if normalized_incoming is None:
                    return error_response("summary 字段格式错误，应为对象")

                if 'total_cases' in normalized_incoming:
                    summary_info.total_cases = normalized_incoming['total_cases']
                if 'completed_cases' in normalized_incoming:
                    summary_info.completed_cases = normalized_incoming['completed_cases']
                if 'failed_cases' in normalized_incoming:
                    summary_info.failed_cases = normalized_incoming['failed_cases']
                if 'pass_rate' in normalized_incoming:
                    summary_info.pass_rate = normalized_incoming['pass_rate']

                if raw_data_record and 'raw_data' in normalized_incoming:
                    raw_data_record.raw_data = json.dumps(normalized_incoming['raw_data'], ensure_ascii=False)
                if metric_stats_record:
                    if 'metric_data' in normalized_incoming:
                        metric_stats_record.metric_data = json.dumps(normalized_incoming['metric_data'], ensure_ascii=False)
                    if 'tag_metric_data' in normalized_incoming:
                        metric_stats_record.tag_metric_data = json.dumps(normalized_incoming['tag_metric_data'], ensure_ascii=False)
                    if 'case_type_stats' in normalized_incoming:
                        metric_stats_record.case_type_stats = json.dumps(normalized_incoming['case_type_stats'], ensure_ascii=False)

            report.updated_at = now_cst()
            db.session.commit()

            def to_json(val):
                if val is None:
                    return []
                if isinstance(val, (list, dict)):
                    return val
                if isinstance(val, str):
                    return json.loads(val)
                return val if isinstance(val, list) else []

            simplified_summary = {
                "raw_data": to_json(raw_data_record.raw_data) if raw_data_record else [],
                "case_categories": to_json(summary_meta.case_categories) if summary_meta else [],
                "all_case_tags": to_json(summary_meta.all_case_tags) if summary_meta else [],
                "resources": to_json(summary_meta.resources) if summary_meta else [],
                "resource_headers": to_json(summary_meta.resource_headers) if summary_meta else [],
                "all_metrics": to_json(summary_meta.all_metrics) if summary_meta else [],
                "device_stats": to_json(metric_stats_record.device_stats) if metric_stats_record else [],
                "api_stats": to_json(metric_stats_record.api_stats) if metric_stats_record else [],
                "case_type_stats": to_json(metric_stats_record.case_type_stats) if metric_stats_record else [],
                "devices": to_json(summary_meta.devices) if summary_meta else [],
                "apis": to_json(summary_meta.apis) if summary_meta else [],
                "metric_data": to_json(metric_stats_record.metric_data) if metric_stats_record else {},
                "tag_metric_data": to_json(metric_stats_record.tag_metric_data) if metric_stats_record else {},
                "total_cases": summary_info.total_cases or 0,
                "completed_cases": summary_info.completed_cases or 0,
                "failed_cases": summary_info.failed_cases or 0,
            }

            task = db.session.get(Task, report.task_id) if report.task_id else None
            return success_response(
                {
                    "id": report.id,
                    "name": report.name,
                    "type": report.type,
                    "task_id": report.task_id,
                    "task_name": task.name if task else "对比报告/趋势报告",
                    "summary": simplified_summary,
                    "description": report.description,
                    "status": report.status,
                    "analysis": report.analysis,
                    "created_at": report.created_at.isoformat() if report.created_at else None,
                    "updated_at": report.updated_at.isoformat() if report.updated_at else None,
                },
                "测试报告已更新",
            )
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return error_response("更新报告失败，请稍后重试")

    @staticmethod
    def publish(report_id):
        report = db.session.get(Report, report_id)
        if not report or report.deleted:
            return error_response("未找到测试报告", 404)
        try:
            report.status = ReportStatus.PUBLISHED.value
            report.updated_at = now_cst()
            db.session.commit()
            return success_response({"id": report.id, "status": report.status}, "报告已发布")
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return error_response("发布报告失败，请稍后重试")

    # 批量删除测试报告
    @staticmethod
    def batch_delete():
        try:
            req = ReportBatchDeleteRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        report_ids = req.report_ids

        if not report_ids:
            return error_response("缺少必要参数: reportIds")

        if len(report_ids) > 100:
            return error_response("单次最多删除100个报告")

        try:
            reports = Report.query.filter(Report.id.in_(report_ids), Report.deleted == False).all()
            if not reports:
                return success_response(None, "未找到指定的测试报告，无需删除")

            now = now_cst()
            report_ids_to_delete = [r.id for r in reports]
            Report.query.filter(Report.id.in_(report_ids_to_delete)).update(
                {"deleted": True, "deleted_at": now, "updated_at": now},
                synchronize_session=False
            )

            db.session.commit()
            return success_response(None, f"成功删除 {len(reports)} 个测试报告")
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return error_response("批量删除报告失败，请稍后重试")

    # ------------------------------------------------------------------
    # 任务报告生成辅助方法（原 ReportControllerTask）
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_task_and_get_results(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return None, None, error_response("未找到指定任务")

        from shared.models.models import TaskMergeRelation

        if task.type == 'merged' and task.status == TaskStatus.COMPLETED.value:
            merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
            if merge_relations:
                source_task_ids = [r.source_task_id for r in merge_relations]
                results = TestResult.query.filter(TestResult.task_id.in_(source_task_ids)).all()
            else:
                results = TestResult.query.filter_by(task_id=task_id).all()
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None

        elif task.type == 'merged':
            merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
            if merge_relations:
                source_task_ids = [r.source_task_id for r in merge_relations]
                results = TestResult.query.filter(TestResult.task_id.in_(source_task_ids)).all()
            else:
                results = TestResult.query.filter_by(task_id=task_id).all()
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None

        elif task.status == TaskStatus.MERGED.value:
            merge_relations = TaskMergeRelation.query.filter_by(source_task_id=task_id).all()
            if merge_relations:
                merged_task_id = merge_relations[0].merged_task_id
                source_relations = TaskMergeRelation.query.filter_by(merged_task_id=merged_task_id).all()
                source_task_ids = [r.source_task_id for r in source_relations]
                results = TestResult.query.filter(TestResult.task_id.in_(source_task_ids)).all()
            else:
                results = TestResult.query.filter_by(task_id=task_id).all()
            if not results:
                return None, None, error_response("生成失败: 任务没有测试结果数据")
            return task, results, None

        elif task.status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
            return None, None, error_response("只有任务状态为completed、failed或merged时才能生成报告")

        results = TestResult.query.filter_by(task_id=task_id).all()
        if not results:
            return None, None, error_response("生成失败: 任务没有测试结果数据")

        return task, results, None

    @staticmethod
    def _get_dimension_results_batch(result_ids):
        if not result_ids:
            return {}, []

        dim_results = db.session.query(
            TestResultDimension.test_result_id,
            TestResultDimension.dimension_id,
            TestResultDimension.dimension_value,
            Dimension.name.label('dimension_name')
        ).join(Dimension, TestResultDimension.dimension_id == Dimension.id)\
         .filter(TestResultDimension.test_result_id.in_(result_ids)).all()

        if not dim_results:
            return {}, []

        dim_results_map = {}
        dim_stats = {}

        for dr in dim_results:
            if dr.test_result_id not in dim_results_map:
                dim_results_map[dr.test_result_id] = []
            dim_results_map[dr.test_result_id].append(dr)

            if dr.dimension_id not in dim_stats:
                dim_stats[dr.dimension_id] = {
                    "name": dr.dimension_name,
                    "total_dimension_value": 0,
                    "count": 0
                }
            dim_stats[dr.dimension_id]["total_dimension_value"] += dr.dimension_value or 0
            dim_stats[dr.dimension_id]["count"] += 1

        return dim_results_map, dim_stats

    @staticmethod
    def _get_resource_result_types_batch(task_id_or_ids, device_ids, api_ids):
        device_result_types = {}
        api_result_types = {}

        if isinstance(task_id_or_ids, list):
            task_id_filter = TestResult.task_id.in_(task_id_or_ids)
        else:
            task_id_filter = TestResult.task_id == task_id_or_ids

        if device_ids:
            device_results = TestResult.query.filter(
                task_id_filter,
                TestResult.device_id.in_(device_ids)
            ).all()

            for result in device_results:
                if result.device_id and result.result_data:
                    full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                    result_type = ReportCommandService._extract_result_type(full_data)
                    device_result_types[result.device_id] = result_type

        if api_ids:
            api_results = TestResult.query.filter(
                task_id_filter,
                TestResult.api_id.in_(api_ids)
            ).all()

            for result in api_results:
                if result.api_id and result.result_data:
                    full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                    result_type = ReportCommandService._extract_result_type(full_data)
                    api_result_types[result.api_id] = result_type

        return device_result_types, api_result_types

    @staticmethod
    def _extract_result_type(result_data):
        if not result_data:
            return 'default'
        try:
            if isinstance(result_data, str) and result_data.strip():
                result_data_dict = json.loads(result_data)
            elif isinstance(result_data, dict):
                result_data_dict = result_data
            else:
                return 'default'
            return result_data_dict.get('result_type', 'default') if isinstance(result_data_dict, dict) else 'default'
        except Exception:
            return 'default'

    @staticmethod
    def _build_case_data(test_cases, results, all_dimensions, dim_results_map, task):
        from api_gateway.application.services.report_query_service import ReportQueryService

        results_by_case = {}
        for result in results:
            if result.test_case_id not in results_by_case:
                results_by_case[result.test_case_id] = []
            results_by_case[result.test_case_id].append(result)

        cases = []

        for test_case in test_cases:
            case_results = results_by_case.get(test_case.id, [])
            resource_metrics_map = {}
            test_type = 'api' if case_results and case_results[0].api_id else 'e2e'

            audios_list = ReportQueryService._build_audios_list(test_case, mode='task')
            reference_params_dict = ReportCommandService._get_reference_params(test_case, case_results, test_type)

            for result in case_results:
                resource = ReportQueryService.get_resource_name(result, task, use_time_prefix=False)
                dim_values = ReportQueryService.extract_dimension_values(
                    result.id, all_dimensions, dim_results_map=dim_results_map
                )

                result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                if result_data and isinstance(result_data, dict):
                    eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
                    if isinstance(eval_data, dict):
                        for dim_name, dim_value in eval_data.items():
                            if dim_name not in dim_values or dim_values.get(dim_name) is None:
                                dim_values[dim_name] = dim_value

                resource_metrics = []
                for dim_name, dim_value in dim_values.items():
                    if dim_value is not None:
                        dim_id = None
                        for dim in all_dimensions:
                            if dim.name == dim_name:
                                dim_id = dim.id
                                break
                        resource_metrics.append({
                            "id": dim_id,
                            "metric": dim_name,
                            "value": dim_value
                        })
                if resource_metrics:
                    resource_metrics_map[resource] = resource_metrics

            metrics_list = []
            for resource, metrics_data in resource_metrics_map.items():
                metrics_list.append({
                    "resource": resource,
                    "metrics": metrics_data
                })

            case_obj = {
                "id": test_case.id,
                "name": test_case.name,
                "description": test_case.description or "",
                "category": test_case.group.name if test_case.group else "未分类",
                "tags": [{"name": tag.name} for tag in (getattr(test_case, 'tags', []) or [])],
                "metrics": metrics_list,
                "results": [],
                "audios": audios_list,
                "reference_params": reference_params_dict,
                "algorithm_results": [],
                "algorithm_type": test_case.algorithm_type,
                "logs": "\n".join([result.error_message for result in case_results if result.error_message])
            }

            for result in case_results:
                resource = ReportQueryService.get_resource_name(result, task, use_time_prefix=False)

                case_obj["results"].append({
                    "resource": resource,
                    **ReportQueryService.build_result_info(result),
                })

                algo_res = result.algorithm_result
                result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                if not isinstance(result_data, dict):
                    result_data = None

                if algo_res or result_data:
                    combined_data = {}
                    if algo_res:
                        combined_data.update(algo_res)
                    if result_data:
                        combined_data.update(result_data)

                    # 扁平列表格式，与 task_controller.py 一致
                    for param_key, param_value in combined_data.items():
                        if param_key and param_value is not None:
                            param_type = ReportQueryService._infer_param_type(param_key)
                            case_obj["algorithm_results"].append({
                                'device': resource,
                                'param_code': param_key,
                                'param_type': param_type,
                                'label': param_key,
                                'value': param_value
                            })

            cases.append(case_obj)

        return cases

    @staticmethod
    def _get_reference_params(test_case, case_results, test_type):
        adjusted_reference_params = None
        for result in case_results:
            result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
            if result_data and isinstance(result_data, dict):
                adjusted_reference_params = result_data.get('adjusted_reference_params')
                if adjusted_reference_params:
                    break

        if adjusted_reference_params:
            config_for_ref = {'reference_params': adjusted_reference_params}
        else:
            # 优先从独立列读取，兼容旧 config
            ref_col = getattr(test_case, 'reference_params', None)
            if ref_col:
                return ReferenceParamsGenerator.get_reference_params_for_report(ref_col)
            config_for_ref = test_case.config

        return ReferenceParamsGenerator.get_reference_params_for_report(config_for_ref)

    @staticmethod
    def _build_resources_list(devices, apis, task, device_result_types, api_result_types):
        from api_gateway.application.services.report_query_service import ReportQueryService

        resources = []

        for d in devices:
            result_type = device_result_types.get(d.id, 'default')

            class TempResult:
                def __init__(self, device_id, result_type):
                    self.device_id = device_id
                    self.api_id = None
                    self.result_data = {"result_type": result_type}

            resource = ReportQueryService.get_resource_name(TempResult(d.id, result_type), task, use_time_prefix=False)
            resources.append(resource)

        for a in apis:
            result_type = api_result_types.get(a.id, 'default')

            class TempResult:
                def __init__(self, api_id, result_type):
                    self.api_id = api_id
                    self.device_id = None
                    self.result_data = {"result_type": result_type}

            resource = ReportQueryService.get_resource_name(TempResult(a.id, result_type), task, use_time_prefix=False)
            resources.append(resource)

        return resources

    @staticmethod
    def _get_source_task_ids(task):
        if task.type == 'merged' and task.status == TaskStatus.COMPLETED.value:
            from shared.models.models import TaskMergeRelation
            merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task.id).all()
            return [r.source_task_id for r in merge_relations]
        return []

    @staticmethod
    def _get_task_resources(task_ids):
        from shared.models.models import TaskDevice, Device, TaskAPI, API

        if isinstance(task_ids, int):
            task_ids = [task_ids]

        task_devices = TaskDevice.query.filter(TaskDevice.task_id.in_(task_ids)).all()
        device_ids = list(set([td.device_id for td in task_devices]))
        devices = Device.query.filter(Device.id.in_(device_ids)).all() if device_ids else []
        devices_list = [ReportUtils.serialize_device(d) for d in devices if d]

        task_apis = TaskAPI.query.filter(TaskAPI.task_id.in_(task_ids)).all()
        api_ids = list(set([ta.api_id for ta in task_apis]))
        apis = API.query.filter(API.id.in_(api_ids)).all() if api_ids else []
        apis_list = [ReportUtils.serialize_api(a) for a in apis if a]

        return devices_list, apis_list, device_ids, api_ids

    @staticmethod
    def _get_task_test_cases(task_ids):
        from shared.models.models import TaskCase
        from sqlalchemy.orm import joinedload

        if isinstance(task_ids, int):
            task_ids = [task_ids]

        task_cases = TaskCase.query.filter(TaskCase.task_id.in_(task_ids)).all()
        test_case_ids = list(set([tc.test_case_id for tc in task_cases]))
        test_cases = TestCase.query.options(
            joinedload(TestCase.tags),
            joinedload(TestCase.group)
        ).filter(TestCase.id.in_(test_case_ids)).all()
        return test_cases, test_case_ids

    @staticmethod
    def _calculate_summary_dimensions(dim_stats):
        summary_dim_values = []
        for d_id, stat in dim_stats.items():
            avg_value = (stat["total_dimension_value"] / stat["count"]) if stat["count"] > 0 else 0
            summary_dim_values.append({
                "id": d_id,
                "name": stat["name"],
                "average_value": avg_value
            })
        return summary_dim_values

    @staticmethod
    def _build_all_metrics(all_dimensions):
        all_metrics = []
        for dim in all_dimensions:
            unit = dim.score_unit if dim.score_unit and dim.score_unit.strip() else "%"
            decimal_places = dim.decimal_places if dim.decimal_places is not None else 2
            all_metrics.append({"id": dim.id, "name": dim.name, "unit": unit, "decimal_places": decimal_places})
        return all_metrics

    @staticmethod
    def _create_report_record(name, task_id, description):
        new_report = Report(
            name=name,
            type=ReportType.TASK.value,
            task_id=task_id,
            description=description,
            status=ReportStatus.DRAFT.value
        )
        db.session.add(new_report)
        db.session.flush()
        return new_report

    @staticmethod
    def _create_report_summary(report_id, task, summary):
        total_cases = summary.get('total_cases', 0)
        completed_cases = summary.get('completed_cases', 0)

        summary_info = ReportSummary(
            report_id=report_id,
            total_cases=total_cases,
            completed_cases=completed_cases,
            failed_cases=summary.get('failed_cases', 0),
            pass_rate=round((completed_cases / total_cases * 100), 2) if total_cases > 0 else 0,
            duration=task.actual_duration,
            started_at=task.started_at,
            completed_at=task.completed_at
        )
        db.session.add(summary_info)

        summary_meta = ReportSummaryMeta(
            report_id=report_id,
            dimension_values=json.dumps(summary.get('dimension_values', []), ensure_ascii=False),
            case_categories=json.dumps(summary.get('case_categories', []), ensure_ascii=False),
            all_case_tags=json.dumps(summary.get('all_case_tags', []), ensure_ascii=False),
            devices=json.dumps(summary.get('devices', []), ensure_ascii=False),
            apis=json.dumps(summary.get('apis', []), ensure_ascii=False),
            resources=json.dumps(summary.get('resources', []), ensure_ascii=False),
            resource_headers=json.dumps(summary.get('resource_headers', []), ensure_ascii=False),
            all_metrics=json.dumps(summary.get('all_metrics', []), ensure_ascii=False)
        )
        db.session.add(summary_meta)

        return summary_info, summary_meta

    @staticmethod
    def _create_report_detail_data(report_id, summary):
        raw_data_record = ReportRawData(
            report_id=report_id,
            raw_data=json.dumps(summary.get('raw_data', []), ensure_ascii=False)
        )
        db.session.add(raw_data_record)

        cases = summary.get('cases', [])
        if isinstance(cases, str):
            cases = json.loads(cases)
        for case_item in cases:
            if not isinstance(case_item, dict):
                continue
            case_record = ReportCase(
                report_id=report_id,
                test_case_id=case_item.get('id'),
                name=case_item.get('name'),
                description=case_item.get('description'),
                category=case_item.get('category'),
                tags=case_item.get('tags'),
                metrics=case_item.get('metrics'),
                results=case_item.get('results'),
                audios=case_item.get('audios'),
                reference_params=case_item.get('reference_params'),
                algorithm_results=case_item.get('algorithm_results'),
                algorithm_type=case_item.get('algorithm_type'),
                logs=case_item.get('logs')
            )
            db.session.add(case_record)

        metric_stats_record = ReportMetricStats(
            report_id=report_id,
            metric_data=json.dumps(summary.get('metric_data', []), ensure_ascii=False),
            tag_metric_data=json.dumps(summary.get('tag_metric_data', []), ensure_ascii=False),
            tag_category_metric_data=json.dumps(summary.get('tag_category_metric_data', {}), ensure_ascii=False),
            case_type_stats=json.dumps(summary.get('case_type_stats', []), ensure_ascii=False),
            device_stats=json.dumps(summary.get('device_stats', []), ensure_ascii=False),
            api_stats=json.dumps(summary.get('api_stats', []), ensure_ascii=False)
        )
        db.session.add(metric_stats_record)

        return raw_data_record, metric_stats_record

    @staticmethod
    def _build_response(report, task, summary_info, summary_meta, raw_data_record, metric_stats_record):
        def to_json(val):
            if val is None:
                return []
            if isinstance(val, (list, dict)):
                return val
            if isinstance(val, str):
                return json.loads(val)
            return val if isinstance(val, list) else []

        simplified_summary = ReportSummarySimplified(
            raw_data=to_json(raw_data_record.raw_data) if raw_data_record else [],
            metric_data=to_json(metric_stats_record.metric_data) if metric_stats_record else [],
            tag_metric_data=to_json(metric_stats_record.tag_metric_data) if metric_stats_record else [],
            case_categories=to_json(summary_meta.case_categories) if summary_meta else [],
            all_case_tags=to_json(summary_meta.all_case_tags) if summary_meta else [],
            resources=to_json(summary_meta.resources) if summary_meta else [],
            resource_headers=to_json(summary_meta.resource_headers) if summary_meta else [],
            all_metrics=to_json(summary_meta.all_metrics) if summary_meta else [],
            device_stats=to_json(metric_stats_record.device_stats) if metric_stats_record else [],
            api_stats=to_json(metric_stats_record.api_stats) if metric_stats_record else [],
            case_type_stats=to_json(metric_stats_record.case_type_stats) if metric_stats_record else [],
            devices=to_json(summary_meta.devices) if summary_meta else [],
            apis=to_json(summary_meta.apis) if summary_meta else [],
            total_cases=summary_info.total_cases if summary_info else 0,
            completed_cases=summary_info.completed_cases if summary_info else 0,
            failed_cases=summary_info.failed_cases if summary_info else 0
        )

        response_schema = ReportDetailDataSchema(
            id=report.id,
            name=report.name,
            type=report.type,
            task_id=report.task_id,
            task_name=task.name if task else "对比报告/趋势报告",
            summary=simplified_summary,
            description=report.description,
            status=report.status,
            analysis=report.analysis,
            created_at=report.created_at.isoformat() if report.created_at else None,
            updated_at=report.updated_at.isoformat() if report.updated_at else None
        )

        return response_schema.model_dump(by_alias=True)

    # ------------------------------------------------------------------
    # 生成任务报告（原 ReportControllerTask）
    # ------------------------------------------------------------------

    def generate_task_report():
        try:
            validated_data = GenerateTaskReportRequest.model_validate(request.get_json())
        except Exception as e:
            log_and_emit('ERROR', 'report', f'[generate_task_report] Validation error: {e}\n{traceback.format_exc()}')
            return error_response(f"请求参数错误: {str(e)}")

        task_id = validated_data.task_id
        name = validated_data.name
        description = validated_data.description

        log_and_emit('DEBUG', 'report', f'[generate_task_report] Starting task_id={task_id}', task_id=task_id)

        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到指定任务")

        existing_report = Report.query.filter_by(task_id=task_id).first()
        if existing_report:
            return success_response({"id": existing_report.id, "status": "exists"}, "任务报告已存在", ErrorCode.SUCCESS)

        if task.status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value]:
            return error_response("只有任务状态为completed、failed或merged时才能生成报告")

        with _generating_lock:
            if task_id in _generating_tasks:
                return success_response({"taskId": task_id, "status": "generating"}, "报告正在生成中", ErrorCode.SUCCESS)
            _generating_tasks.add(task_id)

        log_and_emit('INFO', 'report', f'[generate_task_report] Submitting async task for task_id={task_id}', task_id=task_id)
        _report_executor.submit(
            ReportCommandService._generate_task_report_async,
            task_id, name, description
        )
        log_and_emit('INFO', 'report', f'[generate_task_report] Async task submitted for task_id={task_id}', task_id=task_id)

        return success_response({"taskId": task_id, "status": "generating"}, "报告生成中，请稍后刷新", ErrorCode.SUCCESS)

    @staticmethod
    def _generate_task_report_async(task_id, name, description):
        from api_gateway.application.services.report_query_service import ReportQueryService
        # FastAPI: 不再需要 app context，直接执行
        try:
            log_and_emit('INFO', 'report', f'[generate_task_report_async] Starting for task_id={task_id}', task_id=task_id)

            task, results, error = ReportCommandService._validate_task_and_get_results(task_id)
            if error:
                with _generating_lock:
                    _generating_tasks.discard(task_id)
                _emit_report_event('report_generated', {
                    'taskId': task_id,
                    'success': False,
                    'error': '任务验证失败'
                })
                return

            existing_report = Report.query.filter_by(task_id=task_id).first()
            if existing_report:
                with _generating_lock:
                    _generating_tasks.discard(task_id)
                _emit_report_event('report_generated', {
                    'taskId': task_id,
                    'reportId': existing_report.id,
                    'success': True,
                    'status': 'exists'
                })
                return

            if not name:
                name = f"任务报告_{task.name}_{now_cst().strftime('%Y%m%d%H%M%S')}"

            source_task_ids = ReportCommandService._get_source_task_ids(task)
            task_ids_for_query = source_task_ids if source_task_ids else [task_id]

            total_cases = task.total_cases
            completed_cases = task.completed_cases - task.failed_cases
            failed_cases = task.failed_cases
            success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

            res_ids = [r.id for r in results]

            dim_results_map, dim_stats = ReportCommandService._get_dimension_results_batch(res_ids)

            if not dim_results_map:
                _emit_report_event('report_generated', {
                    'taskId': task_id,
                    'success': False,
                    'error': '未找到维度得分数据'
                })
                return

            all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
            summary_dim_values = ReportCommandService._calculate_summary_dimensions(dim_stats)

            if dim_stats:
                all_dimensions = [d for d in all_dimensions_all if d.id in dim_stats]
            else:
                all_dimensions = all_dimensions_all

            test_cases, test_case_ids = ReportCommandService._get_task_test_cases(task_ids_for_query)
            devices_list, apis_list, device_ids, api_ids = ReportCommandService._get_task_resources(task_ids_for_query)

            device_result_types, api_result_types = ReportCommandService._get_resource_result_types_batch(
                task_ids_for_query, device_ids, api_ids
            )

            resources = ReportCommandService._build_resources_list(
                [d for d in Device.query.filter(Device.id.in_(device_ids)).all()] if device_ids else [],
                [a for a in API.query.filter(API.id.in_(api_ids)).all()] if api_ids else [],
                task, device_result_types, api_result_types
            )

            all_metrics = ReportCommandService._build_all_metrics(all_dimensions)

            if not devices_list and not apis_list:
                _emit_report_event('report_generated', {
                    'taskId': task_id,
                    'success': False,
                    'error': '任务没有关联任何设备或API'
                })
                return

            if not all_metrics:
                _emit_report_event('report_generated', {
                    'taskId': task_id,
                    'success': False,
                    'error': '任务没有关联任何评估维度'
                })
                return

            tasks_map = {task.id: task}
            if source_task_ids:
                source_tasks = Task.query.filter(Task.id.in_(source_task_ids)).all()
                for st in source_tasks:
                    tasks_map[st.id] = st

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

            cases = ReportCommandService._build_case_data(
                test_cases, results, all_dimensions, dim_results_map, task
            )

            case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

            summary = {
                "total_cases": total_cases,
                "completed_cases": completed_cases,
                "failed_cases": failed_cases,
                "overall_success_rate": round(success_rate, 2),
                "dimension_values": summary_dim_values,
                "duration": task.actual_duration,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "case_categories": case_categories_list,
                "all_case_tags": case_tags_list,
                "all_tags": case_tags_list,
                "devices": devices_list,
                "apis": apis_list,
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
                "source_task_ids": source_task_ids,
                "is_merged": bool(source_task_ids)
            }

            summary = ReportUtils.normalize_summary_metrics(summary)

            new_report = ReportCommandService._create_report_record(name, task_id, description)
            log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created report id={new_report.id}', task_id=task_id)

            summary_info, summary_meta = ReportCommandService._create_report_summary(new_report.id, task, summary)
            log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created summary_info id={summary_info.id}, report_id={summary_info.report_id}', task_id=task_id)

            raw_data_record, metric_stats_record = ReportCommandService._create_report_detail_data(new_report.id, summary)
            log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created detail data for report_id={new_report.id}', task_id=task_id)

            report_id = new_report.id
            db.session.commit()

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
            db.session.rollback()
            log_and_emit('ERROR', 'report', f'[generate_task_report_async] Error: {e}\n{traceback.format_exc()}', task_id=task_id)
            emit_data = {
                'taskId': task_id,
                'success': False,
                'error': '报告生成失败，请稍后重试'
            }
            log_and_emit('INFO', 'report', f'[generate_task_report_async] Emitting error: {emit_data}', task_id=task_id)
            _emit_report_event('report_generated', emit_data)
        finally:
            with _generating_lock:
                _generating_tasks.discard(task_id)

    # ------------------------------------------------------------------
    # 对比报告生成（原 ReportControllerCompare）
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_and_get_tasks(task_ids):
        tasks = Task.query.filter(Task.id.in_(task_ids), Task.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value])).all()
        if not tasks:
            return None, error_response("未找到指定任务或任务状态不是completed、failed或merged")
        return tasks, None

    @staticmethod
    def compare():
        from api_gateway.application.services.report_query_service import ReportQueryService

        try:
            validated_data = CompareReportsRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        task_ids = validated_data.task_ids
        if not task_ids:
            return error_response("缺少必要参数: taskIds")
        name = validated_data.name or f"对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"
        description = validated_data.description

        try:
            tasks, error = ReportCommandService._validate_and_get_tasks(task_ids)
            if error:
                return error

            included_task_types = {t.type for t in tasks if getattr(t, "type", None)}
            report_task_type = (
                "api"
                if included_task_types == {"api"}
                else ("e2e" if included_task_types == {"e2e"} else "all")
            )

            results = TestResult.query.filter(TestResult.task_id.in_(task_ids)).all()

            res_ids_all = [r.id for r in results]
            all_dimensions = ReportQueryService._get_all_dimensions_with_results(res_ids_all)

            task_weighted_values = ReportQueryService._calculate_task_weighted_values(
                task_ids, results, all_dimensions
            )

            total_cases = sum(t.total_cases for t in tasks)
            completed_cases = sum(t.completed_cases - t.failed_cases for t in tasks)
            success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

            test_case_ids = set()
            for res in results:
                test_case_ids.add(res.test_case_id)

            test_cases = TestCase.query.filter(TestCase.id.in_(test_case_ids)).all()

            case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

            resource_names, device_list, api_list = ReportQueryService._collect_resources_batch(tasks, results)

            if not resource_names:
                resource_names = {"默认资源"}

            resource_list = sorted(list(resource_names))
            resources = resource_list

            if not device_list and not api_list:
                return error_response("对比失败: 未找到设备或API资源数据")

            all_metrics = []
            for dim in all_dimensions:
                unit = dim.score_unit if dim.score_unit and dim.score_unit.strip() else "%"
                decimal_places = dim.decimal_places if dim.decimal_places is not None else 2
                all_metrics.append({"id": dim.id, "name": dim.name, "unit": unit, "decimal_places": decimal_places})

            if not all_metrics:
                return error_response("对比失败: 未找到评估维度数据")

            if not results:
                return error_response("对比失败: 未找到测试结果数据")

            tasks_map = {t.id: t for t in tasks}

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

            cases = ReportQueryService._build_case_data_compare(
                test_cases, results, all_dimensions, tasks_map, report_task_type
            )

            source_cases = ReportQueryService._get_source_cases(tasks)
            if not source_cases:
                source_cases = cases

            summary = {
                "task_count": len(tasks),
                "task_type": report_task_type,
                "total_cases": total_cases,
                "overall_success_rate": round(success_rate, 2),
                "tasks_info": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "status": t.status,
                        "type": t.type,
                        "weighted_value": task_weighted_values.get(t.id, 0)
                    } for t in tasks
                ],
                "case_categories": case_categories_list,
                "all_case_tags": case_tags_list,
                "all_tags": case_tags_list,
                "devices": device_list,
                "apis": api_list,
                "resources": resources,
                "resource_headers": resource_headers,
                "all_metrics": all_metrics,
                "metric_data": metric_data,
                "tag_metric_data": tag_metric_data,
                "raw_data": raw_data,
                "device_stats": device_stats,
                "api_stats": api_stats,
                "case_type_stats": case_type_stats,
                "cases": source_cases
            }

            summary = ReportUtils.normalize_summary_metrics(summary)

            comparison_matrix = ReportQueryService._build_comparison_matrix(results, all_dimensions)

            comparison_data = {
                "task_ids": task_ids,
                "task_names": [t.name for t in tasks],
                "matrix": comparison_matrix,
                "weighted_values": task_weighted_values,
                "generated_at": now_cst().isoformat()
            }

            new_report = Report(
                name=name,
                type=ReportType.COMPARISON.value,
                description=description,
                status=ReportStatus.DRAFT.value
            )
            db.session.add(new_report)
            db.session.flush()

            summary_info = ReportSummary(
                report_id=new_report.id,
                total_cases=total_cases,
                completed_cases=total_cases,
                failed_cases=0,
                pass_rate=round(success_rate, 2),
                duration=0,
                started_at=None,
                completed_at=None
            )
            db.session.add(summary_info)

            summary_meta = ReportSummaryMeta(
                report_id=new_report.id,
                dimension_values=json.dumps(summary.get('dimension_values', []), ensure_ascii=False),
                case_categories=json.dumps(case_categories_list, ensure_ascii=False),
                all_case_tags=json.dumps(case_tags_list, ensure_ascii=False),
                devices=json.dumps(device_list, ensure_ascii=False),
                apis=json.dumps(api_list, ensure_ascii=False),
                resources=json.dumps(resources, ensure_ascii=False),
                resource_headers=json.dumps(resource_headers, ensure_ascii=False),
                all_metrics=json.dumps(all_metrics, ensure_ascii=False)
            )
            db.session.add(summary_meta)

            raw_data_record = ReportRawData(
                report_id=new_report.id,
                raw_data=json.dumps(raw_data, ensure_ascii=False)
            )
            db.session.add(raw_data_record)

            for case_item in source_cases:
                if not isinstance(case_item, dict):
                    continue
                case_record = ReportCase(
                    report_id=new_report.id,
                    test_case_id=case_item.get('id'),
                    name=case_item.get('name'),
                    description=case_item.get('description'),
                    category=case_item.get('category'),
                    tags=case_item.get('tags'),
                    metrics=case_item.get('metrics'),
                    results=case_item.get('results'),
                    audios=case_item.get('audios'),
                    reference_params=case_item.get('reference_params'),
                    algorithm_results=case_item.get('algorithm_results'),
                    algorithm_type=case_item.get('algorithm_type'),
                    logs=case_item.get('logs')
                )
                db.session.add(case_record)

            metric_stats_record = ReportMetricStats(
                report_id=new_report.id,
                metric_data=json.dumps(metric_data, ensure_ascii=False),
                tag_metric_data=json.dumps(tag_metric_data, ensure_ascii=False),
                case_type_stats=json.dumps(case_type_stats, ensure_ascii=False),
                device_stats=json.dumps(device_stats, ensure_ascii=False),
                api_stats=json.dumps(api_stats, ensure_ascii=False)
            )
            db.session.add(metric_stats_record)

            comparison_matrix_record = ReportComparisonMatrix(
                report_id=new_report.id,
                comparison_matrix=json.dumps(comparison_data, ensure_ascii=False)
            )
            db.session.add(comparison_matrix_record)

            db.session.commit()

            response_data = ReportIdData(report_id=new_report.id)

            return success_response(response_data, message="对比报告生成成功", code=ErrorCode.SUCCESS, http_code=201)
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return error_response("对比报告生成失败，请稍后重试")

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

        for case_item in source_cases:
            if not isinstance(case_item, dict):
                continue
            case_record = ReportCase(
                report_id=new_report_id,
                test_case_id=case_item.get('id'),
                name=case_item.get('name'),
                description=case_item.get('description'),
                category=case_item.get('category'),
                tags=case_item.get('tags'),
                metrics=case_item.get('metrics'),
                results=case_item.get('results'),
                audios=case_item.get('audios'),
                reference_params=case_item.get('reference_params'),
                algorithm_results=case_item.get('algorithm_results'),
                algorithm_type=case_item.get('algorithm_type'),
                logs=case_item.get('logs')
            )
            db.session.add(case_record)

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
            ReportCommandService._secondary_compare_async,
            report_ids, description, report_key
        )

        return success_response(
            {"reportKey": list(report_key), "status": "generating"},
            "对比报告生成中，请稍后",
            ErrorCode.SUCCESS
        )

    @staticmethod
    def _secondary_compare_async(report_ids, description, report_key):
        from api_gateway.application.services.report_query_service import ReportQueryService
        # FastAPI: 不再需要 app context，直接执行
        try:
            log_and_emit('INFO', 'report', f'[secondary_compare_async] Starting for report_ids={report_ids}')

            reports, tasks, task_ids, error = ReportQueryService._validate_reports_and_get_tasks(report_ids)
            if error:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            report_task_type = ReportQueryService._get_task_type(tasks)

            results, resources, devices_list, apis_list, device_ids, api_ids, error = \
                ReportQueryService._collect_all_resources(task_ids, tasks)
            if error:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            res_ids = [r.id for r in results]
            all_dimensions, all_metrics, error = ReportQueryService._build_all_dimensions(res_ids)
            if error:
                with _generating_secondary_lock:
                    _generating_secondary.pop(report_key, None)
                _emit_secondary_compare_event('secondary_compare_generated', {
                    'reportIds': report_ids,
                    'success': False,
                    'error': error
                })
                return

            dim_results_map, _ = ReportCommandService._get_dimension_results_batch(res_ids)

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

            test_cases, _ = ReportCommandService._get_task_test_cases(task_ids)
            case_categories_list, case_tags_list = [], []
            if test_cases:
                from shared.utils.report.report_query_builder import ReportQueryBuilder
                case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

            if not case_categories_list:
                case_categories_list = [{"id": "default_group", "name": "无分组"}]
            if not case_tags_list:
                case_tags_list = [{"id": "default_tag", "name": "无标签"}]

            source_cases = ReportQueryService._get_source_cases_from_reports(reports)
            if not source_cases:
                cases = ReportCommandService._build_case_data(
                    test_cases, results, all_dimensions, dim_results_map, tasks[0] if tasks else None
                )
                source_cases = cases

            comparison_matrix_data = ReportQueryService._build_comparison_matrix_secondary(
                task_ids, reports, all_dimensions
            )

            name = f"二次对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"
            new_report = Report(
                name=name,
                type=ReportType.SECONDARY_COMPARISON.value,
                description=description,
                status=ReportStatus.DRAFT.value
            )
            db.session.add(new_report)
            db.session.flush()

            ReportCommandService._create_secondary_report_records(
                new_report.id, task_ids, tasks, reports,
                case_categories_list, case_tags_list,
                devices_list, apis_list, resources, resource_headers, all_metrics,
                raw_data, metric_data, tag_metric_data, case_type_stats,
                device_stats, api_stats, source_cases, comparison_matrix_data
            )

            db.session.commit()
            log_and_emit('INFO', 'report', f'[secondary_compare_async] Report generated successfully, report_id={new_report.id}')

            _emit_secondary_compare_event('secondary_compare_generated', {
                'reportIds': report_ids,
                'reportId': new_report.id,
                'success': True,
                'status': 'completed'
            })

        except Exception as e:
            db.session.rollback()
            log_and_emit('ERROR', 'report', f'[secondary_compare_async] Error: {e}\n{traceback.format_exc()}')
            _emit_secondary_compare_event('secondary_compare_generated', {
                'reportIds': report_ids,
                'success': False,
                'error': '对比报告生成失败，请稍后重试'
            })
        finally:
            with _generating_secondary_lock:
                _generating_secondary.pop(report_key, None)
