from flask import request
from shared.models.models import Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase, ReportMetricStats, Task, TestResult, TestResultDimension, Dimension, TestCase, Audio, Device, API, \
    TaskDevice, TaskAPI, ReportStatus, ReportType, TaskStatus
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.error_codes import ErrorCode
from shared.utils.report.report_utils import ReportUtils
from shared.utils.report.report_query_builder import ReportQueryBuilder
from shared.utils.result_data_store import load_full_result_data
# TODO: 跨服务依赖，应改为 HTTP 调用
from shared.utils.reference_params_generator import ReferenceParamsGenerator
from api_gateway.schemas.report import CompareReportsRequest
from datetime import datetime, timedelta, timezone
from shared.utils.query_utils import now_cst
import json
from api_gateway.controllers.report_controller_base import ReportControllerBase
from api_gateway.schemas.report import ReportIdData


class ReportControllerCompare(ReportControllerBase):
    
    @staticmethod
    def _validate_and_get_tasks(task_ids):
        tasks = Task.query.filter(Task.id.in_(task_ids), Task.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value])).all()
        if not tasks:
            return None, error_response("未找到指定任务或任务状态不是completed、failed或merged")
        return tasks, None

    @staticmethod
    def _get_all_dimensions_with_results(result_ids):
        all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
        
        used_dim_ids = set()
        if result_ids:
            rows = db.session.query(TestResultDimension.dimension_id).filter(
                TestResultDimension.test_result_id.in_(result_ids)
            ).distinct().all()
            used_dim_ids = {r[0] for r in rows if r and r[0] is not None}
        
        all_dimensions = [d for d in all_dimensions_all if d.id in used_dim_ids] if used_dim_ids else all_dimensions_all

        # 过滤掉 visible_in_report=False 的维度（所有 output 参数都不可见的维度）
        from shared.models.algorithm_models import EvaluationDimensionParam
        all_output_dims = EvaluationDimensionParam.query.filter(
            EvaluationDimensionParam.param_direction == 'output',
            EvaluationDimensionParam.deleted == False
        ).with_entities(EvaluationDimensionParam.dimension_id).distinct().all()
        all_output_dim_ids = {r[0] for r in all_output_dims if r and r[0] is not None}

        visible_output_dims = EvaluationDimensionParam.query.filter(
            EvaluationDimensionParam.param_direction == 'output',
            EvaluationDimensionParam.visible_in_report == True,
            EvaluationDimensionParam.deleted == False
        ).with_entities(EvaluationDimensionParam.dimension_id).distinct().all()
        visible_dim_ids = {r[0] for r in visible_output_dims if r and r[0] is not None}

        hidden_dim_ids = all_output_dim_ids - visible_dim_ids
        if hidden_dim_ids:
            all_dimensions = [d for d in all_dimensions if d.id not in hidden_dim_ids]

        return all_dimensions

    @staticmethod
    def _calculate_task_weighted_values(task_ids, results, all_dimensions):
        dim_map = {d.id: d for d in all_dimensions}
        total_weight = sum(d.weight for d in all_dimensions) if all_dimensions else 1
        
        task_weighted_values = {}
        
        res_ids_all = [r.id for r in results]
        dim_results_map, _ = ReportQueryBuilder.get_dimension_results_batch(res_ids_all)
        
        for tid in task_ids:
            task_results = [r for r in results if r.task_id == tid]
            if not task_results:
                task_weighted_values[tid] = 0
                continue

            dim_sums = {}
            dim_counts = {}
            
            for r in task_results:
                result_dims = dim_results_map.get(r.id, [])
                for dr in result_dims:
                    dim_id = dr.dimension_id if hasattr(dr, 'dimension_id') else dr.get('dimension_id')
                    dim_value = dr.dimension_value if hasattr(dr, 'dimension_value') else dr.get('dimension_value')
                    
                    dim_sums[dim_id] = dim_sums.get(dim_id, 0) + (dim_value or 0)
                    dim_counts[dim_id] = dim_counts.get(dim_id, 0) + 1

            weighted_sum = 0
            for dim_id, total_dimension_value in dim_sums.items():
                if dim_id in dim_map:
                    dim = dim_map[dim_id]
                    avg_value = total_dimension_value / dim_counts[dim_id]
                    weighted_sum += avg_value * (dim.weight / total_weight)

            task_weighted_values[tid] = weighted_sum
        
        return task_weighted_values

    @staticmethod
    def _collect_resources_batch(tasks, results):
        resource_names = set()
        device_list = []
        api_list = []
        
        task_ids = [t.id for t in tasks]
        
        task_devices = TaskDevice.query.filter(TaskDevice.task_id.in_(task_ids)).all()
        task_apis = TaskAPI.query.filter(TaskAPI.task_id.in_(task_ids)).all()
        
        device_ids = list(set([td.device_id for td in task_devices]))
        api_ids = list(set([ta.api_id for ta in task_apis]))
        
        devices_by_id = {}
        if device_ids:
            devices = Device.query.filter(Device.id.in_(device_ids)).all()
            devices_by_id = {d.id: d for d in devices}
        
        apis_by_id = {}
        if api_ids:
            apis = API.query.filter(API.id.in_(api_ids)).all()
            apis_by_id = {a.id: a for a in apis}
        
        tasks_map = {t.id: t for t in tasks}
        
        for res in results:
            task = tasks_map.get(res.task_id)
            if task:
                resource = ReportControllerBase.get_resource_name(res, task, use_time_prefix=True)
                if resource:
                    resource_names.add(resource)
        
        added_device_ids = set()
        for td in task_devices:
            if td.device_id not in added_device_ids and td.device_id in devices_by_id:
                device_list.append(ReportUtils.serialize_device(devices_by_id[td.device_id]))
                added_device_ids.add(td.device_id)
        
        added_api_ids = set()
        for ta in task_apis:
            if ta.api_id not in added_api_ids and ta.api_id in apis_by_id:
                api_list.append(ReportUtils.serialize_api(apis_by_id[ta.api_id]))
                added_api_ids.add(ta.api_id)
        
        return resource_names, device_list, api_list

    @staticmethod
    def _build_case_data_compare(test_cases, results, all_dimensions, tasks_map, report_task_type):
        results_by_case = {}
        for result in results:
            if result.test_case_id not in results_by_case:
                results_by_case[result.test_case_id] = []
            results_by_case[result.test_case_id].append(result)
        
        res_ids_all = [r.id for r in results]
        dim_results_map, _ = ReportQueryBuilder.get_dimension_results_batch(res_ids_all)
        
        cases = []
        
        for test_case in test_cases:
            case_results = results_by_case.get(test_case.id, [])
            case_metrics = {}
            config = test_case.config or {}
            
            reference_params_dict = ReportControllerCompare._build_reference_params(case_results, config)
            
            for result in case_results:
                task = tasks_map.get(result.task_id)
                resource = ReportUtils.get_resource_name(result, task, use_time_prefix=True)
                
                if not resource:
                    continue
                
                dim_values = ReportControllerBase.extract_dimension_values(
                    result.id, all_dimensions, dim_results_map=dim_results_map
                )
                case_metrics[resource] = dim_values
            
            audios_list = ReportControllerBase._build_audios_list(test_case, mode='compare')
            
            case_obj = {
                "id": test_case.id,
                "name": test_case.name,
                "description": test_case.description or "",
                "category": test_case.group.name if test_case.group else "未分类",
                "tags": [{"name": tag.name} for tag in (getattr(test_case, 'tags', []) or [])],
                "metrics": case_metrics,
                "results": [],
                "audios": audios_list,
                "reference_params": reference_params_dict,
                "algorithm_results": [],
                "algorithm_type": test_case.algorithm_type,
                "logs": "\n".join([result.error_message for result in case_results if result.error_message])
            }

            for result in case_results:
                task = tasks_map.get(result.task_id)
                resource = ReportControllerBase.get_resource_name(result, task, use_time_prefix=True)

                case_obj["results"].append({
                    "resource": resource,
                    "status": "成功" if result.execution_status == "completed" else "失败",
                    "start_time": result.created_at.isoformat() if result.created_at else None,
                    "end_time": result.created_at.isoformat() if result.created_at else None,
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
                            param_type = ReportControllerBase._infer_param_type(param_key)
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
    def _build_reference_params(case_results, config):
        adjusted_reference_params = None
        
        for result in case_results:
            result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
            if result_data and isinstance(result_data, dict):
                adjusted_ref = result_data.get('adjusted_reference_params')
                if adjusted_ref:
                    adjusted_reference_params = adjusted_ref

        # 双记录架构：使用 adjusted params 覆盖 config 中的 reference_params
        effective_config = config
        if adjusted_reference_params:
            effective_config = {'reference_params': adjusted_reference_params}

        reference_params = ReferenceParamsGenerator.get_reference_params_for_report(effective_config)
        
        reference_params_dict = {}
        for code, param_info in reference_params.items():
            reference_params_dict[code] = {
                "code": code,
                "type": param_info.get('type', 'text'),
                "value": param_info.get('value'),
                "segments": param_info.get('segments', []),
                "text": param_info.get('text', ''),
                "json": param_info.get('json', ''),
            }
        
        return reference_params_dict

    @staticmethod
    def _build_comparison_matrix(results, all_dimensions):
        dim_map = {d.id: d for d in all_dimensions}
        comparison_matrix = {}
        
        test_case_ids = list(set([r.test_case_id for r in results]))
        test_cases = TestCase.query.filter(TestCase.id.in_(test_case_ids)).all()
        test_cases_map = {tc.id: tc for tc in test_cases}
        
        res_ids = [r.id for r in results]
        dim_results_map, _ = ReportQueryBuilder.get_dimension_results_batch(res_ids)
        
        for res in results:
            if res.test_case_id not in comparison_matrix:
                case = test_cases_map.get(res.test_case_id)
                comparison_matrix[res.test_case_id] = {
                    "case_id": res.test_case_id,
                    "case_name": case.name if case else res.test_case_id
                }

            dim_values = {}
            result_dims = dim_results_map.get(res.id, [])
            for d in result_dims:
                dim_id = d.dimension_id if hasattr(d, 'dimension_id') else d.get('dimension_id')
                dim_value = d.dimension_value if hasattr(d, 'dimension_value') else d.get('dimension_value')
                if dim_id in dim_map:
                    dim_values[dim_map[dim_id].name] = dim_value or 0

            for dim in all_dimensions:
                if dim.name not in dim_values:
                    dim_values[dim.name] = 0

            comparison_matrix[res.test_case_id][f"task_{res.task_id}"] = {
                "status": 'completed' if res.execution_status == 'completed' else 'failed',
                "response_time": res.response_time or 0,
                "values": dim_values
            }
        
        return comparison_matrix

    @staticmethod
    def _get_source_cases(tasks):
        source_cases = []
        task_ids = [t.id for t in tasks]
        
        reports = Report.query.filter(Report.task_id.in_(task_ids)).order_by(Report.created_at.desc()).all()
        reports_by_task = {}
        for report in reports:
            if report.task_id not in reports_by_task:
                reports_by_task[report.task_id] = report
        
        for task_id in task_ids:
            report = reports_by_task.get(task_id)
            if report:
                case_records = ReportCase.query.filter_by(report_id=report.id).all()
                for case_record in case_records:
                    case_item = {
                        "id": case_record.test_case_id,
                        "name": case_record.name,
                        "description": case_record.description or "",
                        "category": case_record.category,
                        "tags": case_record.tags or [],
                        "metrics": case_record.metrics or {},
                        "results": case_record.results or [],
                        "audios": case_record.audios or [],
                        "reference_params": case_record.reference_params,
                        "algorithm_results": case_record.algorithm_results,
                        "algorithm_type": case_record.algorithm_type,
                        "logs": case_record.logs
                    }
                    source_cases.append(case_item)
        
        return source_cases

    @staticmethod
    def compare():
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
            tasks, error = ReportControllerCompare._validate_and_get_tasks(task_ids)
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
            all_dimensions = ReportControllerCompare._get_all_dimensions_with_results(res_ids_all)

            task_weighted_values = ReportControllerCompare._calculate_task_weighted_values(
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

            resource_names, device_list, api_list = ReportControllerCompare._collect_resources_batch(tasks, results)

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

            cases = ReportControllerCompare._build_case_data_compare(
                test_cases, results, all_dimensions, tasks_map, report_task_type
            )

            source_cases = ReportControllerCompare._get_source_cases(tasks)
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

            comparison_matrix = ReportControllerCompare._build_comparison_matrix(results, all_dimensions)

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
