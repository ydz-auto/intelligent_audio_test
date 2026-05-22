from flask import request
from backend.models.models import Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCases, ReportMetricStats, Task, TestResult, TestResultDimension, Dimension, TestCase, Audio, Device, API, ReportStatus, ReportType, TaskStatus
from backend.models.database import db
from backend.utils.response import success_response, error_response
from backend.utils.error_codes import ErrorCode
from backend.utils.report_utils import ReportUtils
from backend.utils.log_handler import log_and_emit
from backend.utils.report_query_builder import ReportQueryBuilder
from backend.algorithm.reference_params_generator import ReferenceParamsGenerator
from backend.algorithm.algorithm_result_field_mapper import AlgorithmResultFieldMapper
from backend.schemas.report import GenerateTaskReportRequest, ReportDetailData as ReportDetailDataSchema, ReportSummarySimplified
from datetime import datetime, timedelta, timezone
from backend.controllers.report_controller_base import ReportControllerBase
from backend.app import socketio
import json
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor

_report_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='report_gen')
_generating_tasks = set()
_generating_lock = threading.Lock()

class ReportControllerTask(ReportControllerBase):
    
    @staticmethod
    def _validate_task_and_get_results(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return None, None, error_response("未找到指定任务")
        
        from backend.models.models import TaskMergeRelation
        
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
                    result_type = ReportControllerTask._extract_result_type(result.result_data)
                    device_result_types[result.device_id] = result_type
        
        if api_ids:
            api_results = TestResult.query.filter(
                task_id_filter,
                TestResult.api_id.in_(api_ids)
            ).all()
            
            for result in api_results:
                if result.api_id and result.result_data:
                    result_type = ReportControllerTask._extract_result_type(result.result_data)
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
            
            audios_list = ReportControllerTask._build_audios_list(test_case)
            reference_params_dict = ReportControllerTask._get_reference_params(test_case, case_results, test_type)
            
            for result in case_results:
                resource = ReportControllerBase.get_resource_name(result, task, use_time_prefix=False)
                dim_values = ReportControllerBase.extract_dimension_values(
                    result.id, all_dimensions, dim_results_map=dim_results_map
                )
                
                result_data = result.result_data
                if result_data:
                    if isinstance(result_data, str) and result_data.strip():
                        try:
                            result_data = json.loads(result_data)
                        except json.JSONDecodeError:
                            result_data = None
                    else:
                        result_data = None
                    
                    if isinstance(result_data, dict):
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
                "tags": [tag.name for tag in (getattr(test_case, 'tags', []) or [])],
                "metrics": metrics_list,
                "results": [],
                "audios": audios_list,
                "reference_params": reference_params_dict,
                "algorithm_results": {},
                "algorithm_type": test_case.algorithm_type,
                "logs": "\n".join([result.error_message for result in case_results if result.error_message])
            }
            
            algorithm_type = test_case.algorithm_type
            output_fields = AlgorithmResultFieldMapper.get_output_fields(algorithm_type) if algorithm_type else []
            
            for result in case_results:
                resource = ReportControllerBase.get_resource_name(result, task, use_time_prefix=False)
                
                case_obj["results"].append({
                    "resource": resource,
                    **ReportControllerBase.build_result_info(result),
                })
                
                algo_res = result.algorithm_result
                result_data = result.result_data
                
                if result_data:
                    if isinstance(result_data, str) and result_data.strip():
                        try:
                            result_data = json.loads(result_data)
                        except json.JSONDecodeError:
                            result_data = None
                    else:
                        result_data = None
                else:
                    result_data = None
                
                if not case_obj["algorithm_results"].get(resource):
                    case_obj["algorithm_results"][resource] = {}
                
                if algo_res or result_data:
                    combined_data = {}
                    if algo_res:
                        combined_data.update(algo_res)
                    if result_data:
                        combined_data.update(result_data)
                    
                    for field in output_fields:
                        source_param = field.get('source_param')
                        target_param = field.get('target_param')
                        param_key = target_param or source_param
                        if param_key and combined_data.get(param_key):
                            case_obj["algorithm_results"][resource][param_key] = combined_data.get(param_key)
            
            cases.append(case_obj)
        
        return cases

    @staticmethod
    def _build_audios_list(test_case):
        audios_list = []
        if not test_case.config or 'audios' not in test_case.config:
            return audios_list
            
        test_audios = test_case.config.get('audios', [])
        
        device_ids = set()
        for audio_cfg in test_audios:
            dev_id = audio_cfg.get('playback_device_id')
            if dev_id and dev_id != '':
                device_ids.add(dev_id)
        
        devices = {}
        if device_ids:
            from backend.models.models import PlaybackDevice
            device_list = PlaybackDevice.query.filter(PlaybackDevice.id.in_(list(device_ids))).all()
            devices = {d.id: d.name for d in device_list}
        
        for audio_cfg in test_audios:
            audio_id = audio_cfg.get('audio_id')
            if audio_id:
                audio = db.session.get(Audio, audio_id)
                if audio:
                    dev_id = audio_cfg.get('playback_device_id')
                    if dev_id == '':
                        dev_id = None
                    audio_item = {
                        "testType": audio_cfg.get('test_type'),
                        "id": audio.id,
                        "filename": audio.original_filename or audio.name,
                        "duration": audio.duration,
                        "url": f"/api/audios/play/{audio.id}",
                        "spl": audio_cfg.get('spl'),
                        "playOrder": audio_cfg.get('play_order'),
                        "playbackDeviceId": dev_id,
                        "playbackDeviceName": devices.get(dev_id) if dev_id else None,
                        "label": audio_cfg.get('label'),
                    }
                    audios_list.append(audio_item)
        
        background_noise = test_case.config.get('background_noise', {})
        if background_noise.get('audio_id'):
            noise_audio = db.session.get(Audio, background_noise['audio_id'])
            if noise_audio:
                audios_list.append({
                    "testType": "noise",
                    "id": noise_audio.id,
                    "filename": noise_audio.name,
                    "duration": noise_audio.duration,
                    "url": f"/api/audios/play/{noise_audio.id}",
                    "spl": background_noise.get('spl'),
                    "playOrder": None,
                    "playbackDeviceId": None,
                    "playbackDeviceName": None,
                    "label": None,
                })
        
        audios_list.sort(key=lambda x: (x.get('playOrder') is None, x.get('playOrder') or 999))
        
        dry_audios = [a for a in audios_list if a.get('testType') != 'noise']
        noise_audios = [a for a in audios_list if a.get('testType') == 'noise']
        
        from backend.algorithm.case_parameter_extractor import CaseParameterExtractor
        overlap_time = CaseParameterExtractor.get_overlap_time(test_case.config) if test_case.config else 0
        overlap_rate = CaseParameterExtractor.get_overlap_rate(test_case.config) if test_case.config else 0
        
        timeline_start = 0
        prev_end_time = 0
        
        for audio_item in dry_audios:
            duration = audio_item.get('duration') or 0
            
            if audio_item == dry_audios[0]:
                timeline_start = 0
            else:
                if overlap_time and overlap_time > 0:
                    timeline_start = prev_end_time - overlap_time
                    if timeline_start < 0:
                        timeline_start = 0
                elif overlap_rate is not None and overlap_rate > 0:
                    timeline_start = prev_end_time * (1 - overlap_rate)
                else:
                    timeline_start = prev_end_time
            
            audio_item['timelineStart'] = round(timeline_start, 3)
            audio_item['timelineEnd'] = round(timeline_start + duration, 3)
            prev_end_time = timeline_start + duration
        
        for noise_item in noise_audios:
            noise_item['timelineStart'] = 0
            noise_item['timelineEnd'] = round(noise_item.get('duration') or 0, 3)
        
        return audios_list

    @staticmethod
    def _get_reference_params(test_case, case_results, test_type):
        adjusted_reference_params = None
        for result in case_results:
            result_data = result.result_data
            if result_data:
                if isinstance(result_data, str) and result_data.strip():
                    try:
                        result_data = json.loads(result_data)
                    except json.JSONDecodeError:
                        result_data = None
                if isinstance(result_data, dict):
                    adjusted_reference_params = result_data.get('adjusted_reference_params')
                    if adjusted_reference_params:
                        break
        
        if adjusted_reference_params:
            config_for_ref = {'reference_params': adjusted_reference_params}
        else:
            config_for_ref = test_case.config
        
        return ReferenceParamsGenerator.get_reference_params_for_report(config_for_ref, test_type)

    @staticmethod
    def _build_resources_list(devices, apis, task, device_result_types, api_result_types):
        resources = []
        
        for d in devices:
            result_type = device_result_types.get(d.id, 'default')
            
            class TempResult:
                def __init__(self, device_id, result_type):
                    self.device_id = device_id
                    self.api_id = None
                    self.result_data = {"result_type": result_type}
            
            resource = ReportControllerBase.get_resource_name(TempResult(d.id, result_type), task, use_time_prefix=False)
            resources.append(resource)
        
        for a in apis:
            result_type = api_result_types.get(a.id, 'default')
            
            class TempResult:
                def __init__(self, api_id, result_type):
                    self.api_id = api_id
                    self.device_id = None
                    self.result_data = {"result_type": result_type}
            
            resource = ReportControllerBase.get_resource_name(TempResult(a.id, result_type), task, use_time_prefix=False)
            resources.append(resource)
        
        return resources

    @staticmethod
    def _get_source_task_ids(task):
        if task.type == 'merged' and task.status == TaskStatus.COMPLETED.value:
            from backend.models.models import TaskMergeRelation
            merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task.id).all()
            return [r.source_task_id for r in merge_relations]
        return []

    @staticmethod
    def _get_task_resources(task_ids):
        from backend.models.models import TaskDevice, Device, TaskAPI, API
        
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
        from backend.models.models import TaskCase
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
    def _create_report_record(name, task_id, summary, description, cases):
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

        cases_record = ReportCases(
            report_id=report_id,
            cases=json.dumps(summary.get('cases', []), ensure_ascii=False)
        )
        db.session.add(cases_record)

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
        
        return raw_data_record, cases_record, metric_stats_record

    @staticmethod
    def _build_response(report, task, summary_info, summary_meta, raw_data_record, cases_record, metric_stats_record):
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
            ReportControllerTask._generate_task_report_async,
            task_id, name, description
        )
        log_and_emit('INFO', 'report', f'[generate_task_report] Async task submitted for task_id={task_id}', task_id=task_id)

        return success_response({"taskId": task_id, "status": "generating"}, "报告生成中，请稍后刷新", ErrorCode.SUCCESS)

    @staticmethod
    def _generate_task_report_async(task_id, name, description):
        from backend.app import app as flask_app
        if flask_app is None:
            log_and_emit('ERROR', 'report', f'[generate_task_report_async] Flask app is None, cannot create context', task_id=task_id)
            with _generating_lock:
                _generating_tasks.discard(task_id)
            socketio.emit('report_generated', {
                'taskId': task_id,
                'success': False,
                'error': '服务器内部错误'
            })
            return
            
        with flask_app.app_context():
            try:
                log_and_emit('INFO', 'report', f'[generate_task_report_async] Starting for task_id={task_id}', task_id=task_id)

                task, results, error = ReportControllerTask._validate_task_and_get_results(task_id)
                if error:
                    with _generating_lock:
                        _generating_tasks.discard(task_id)
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'success': False,
                        'error': '任务验证失败'
                    })
                    return

                existing_report = Report.query.filter_by(task_id=task_id).first()
                if existing_report:
                    with _generating_lock:
                        _generating_tasks.discard(task_id)
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'reportId': existing_report.id,
                        'success': True,
                        'status': 'exists'
                    })
                    return

                if not name:
                    name = f"任务报告_{task.name}_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d%H%M%S')}"

                source_task_ids = ReportControllerTask._get_source_task_ids(task)
                task_ids_for_query = source_task_ids if source_task_ids else [task_id]

                total_cases = task.total_cases
                completed_cases = task.completed_cases - task.failed_cases
                failed_cases = task.failed_cases
                success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

                res_ids = [r.id for r in results]
                
                dim_results_map, dim_stats = ReportControllerTask._get_dimension_results_batch(res_ids)
                
                if not dim_results_map:
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'success': False,
                        'error': '未找到维度得分数据'
                    })
                    return

                all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
                summary_dim_values = ReportControllerTask._calculate_summary_dimensions(dim_stats)

                if dim_stats:
                    all_dimensions = [d for d in all_dimensions_all if d.id in dim_stats]
                else:
                    all_dimensions = all_dimensions_all

                test_cases, test_case_ids = ReportControllerTask._get_task_test_cases(task_ids_for_query)
                devices_list, apis_list, device_ids, api_ids = ReportControllerTask._get_task_resources(task_ids_for_query)

                device_result_types, api_result_types = ReportControllerTask._get_resource_result_types_batch(
                    task_ids_for_query, device_ids, api_ids
                )
                
                resources = ReportControllerTask._build_resources_list(
                    [d for d in Device.query.filter(Device.id.in_(device_ids)).all()] if device_ids else [],
                    [a for a in API.query.filter(API.id.in_(api_ids)).all()] if api_ids else [],
                    task, device_result_types, api_result_types
                )

                all_metrics = ReportControllerTask._build_all_metrics(all_dimensions)

                if not devices_list and not apis_list:
                    socketio.emit('report_generated', {
                        'taskId': task_id,
                        'success': False,
                        'error': '任务没有关联任何设备或API'
                    })
                    return

                if not all_metrics:
                    socketio.emit('report_generated', {
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

                cases = ReportControllerTask._build_case_data(
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

                new_report = ReportControllerTask._create_report_record(name, task_id, summary, description, cases)
                log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created report id={new_report.id}', task_id=task_id)
                
                summary_info, summary_meta = ReportControllerTask._create_report_summary(new_report.id, task, summary)
                log_and_emit('DEBUG', 'report', f'[generate_task_report_async] Created summary_info id={summary_info.id}, report_id={summary_info.report_id}', task_id=task_id)
                
                raw_data_record, cases_record, metric_stats_record = ReportControllerTask._create_report_detail_data(new_report.id, summary)
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
                socketio.emit('report_generated', emit_data)

            except Exception as e:
                db.session.rollback()
                log_and_emit('ERROR', 'report', f'[generate_task_report_async] Error: {e}\n{traceback.format_exc()}', task_id=task_id)
                emit_data = {
                    'taskId': task_id,
                    'success': False,
                    'error': '报告生成失败，请稍后重试'
                }
                log_and_emit('INFO', 'report', f'[generate_task_report_async] Emitting error: {emit_data}', task_id=task_id)
                socketio.emit('report_generated', emit_data)
            finally:
                with _generating_lock:
                    _generating_tasks.discard(task_id)
