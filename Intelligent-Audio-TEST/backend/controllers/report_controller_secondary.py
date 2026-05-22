from flask import request
from backend.models.models import Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCases, ReportMetricStats, ReportComparisonMatrix, Task, TestResult, TestResultDimension, Dimension, TestCase, Audio, API, TaskCase, TaskDevice, TaskAPI, Device, ReportStatus, ReportType, TaskStatus
from backend.models.database import db
from backend.utils.response import success_response, error_response
from backend.utils.error_codes import ErrorCode
from backend.utils.report_utils import ReportUtils
from backend.algorithm.reference_params_generator import ReferenceParamsGenerator
from backend.schemas.report import SecondaryCompareRequest
from datetime import datetime, timedelta, timezone
import json
from backend.controllers.report_controller_base import ReportControllerBase
from backend.schemas.common import IdData

class ReportControllerSecondary(ReportControllerBase):
    # 二次对比分析：将多个任务的数据聚合到一个报告中，格式与任务报告保持一致
    @staticmethod
    def secondary_compare():
        """
        将多个任务的数据聚合到一个报告中，数据格式与任务报告保持一致
        """
        try:
            validated_data = SecondaryCompareRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        report_ids = validated_data.report_ids
        if not report_ids:
            return error_response("缺少必要参数: reportIds")
        description = validated_data.description
        if len(report_ids) < 2:
            return error_response("二次对比至少需要两个报告 ID")

        try:
            # 获取所有报告
            reports = Report.query.filter(Report.id.in_(report_ids)).order_by(Report.created_at.asc()).all()
            if len(reports) < 2:
                return error_response("未找到足够的报告记录进行对比")

            # 收集所有任务的基本信息和执行统计
            task_ids = set()
            for report in reports:
                if report.task_id:
                    task_ids.add(report.task_id)
                elif report.type == 'comparison' and report.summary_info:
                    c_task_ids = report.summary_info.task_ids or []
                    for tid in c_task_ids:
                        task_ids.add(tid)
            
            task_ids = list(task_ids)
            
            # 获取所有任务（如果有），支持 merged 状态的任务（数据不再转移）
            tasks = []
            if task_ids:
                tasks = Task.query.filter(Task.id.in_(task_ids), Task.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value])).all()
            included_task_types = {t.type for t in tasks if getattr(t, "type", None)}
            report_task_type = (
                "api"
                if included_task_types == {"api"}
                else ("e2e" if included_task_types == {"e2e"} else "all")
            )
            
            # 初始化用例分组和标签（默认值）
            case_groups = {"未分类"}
            case_types = {"其他"}
            case_tags = {"无标签"}
            case_categories_list = [{"id": "未分类", "name": "未分类"}]
            case_tags_list = []
            
            # 获取测试用例信息（如果有任务）
            test_cases = []
            if tasks:
                # 获取所有涉及的测试用例ID
                all_case_ids = set()
                for task in tasks:
                    task_cases = TaskCase.query.filter_by(task_id=task.id).all()
                    for tc in task_cases:
                        all_case_ids.add(tc.test_case_id)
                
                # 获取这些测试用例
                if all_case_ids:
                    test_cases = TestCase.query.filter(TestCase.id.in_(list(all_case_ids))).all()
                
                # 提取所有任务的用例分组和标签
                if test_cases:
                    # 转换case_groups为包含id和name的对象列表
                    case_categories_list = []
                    for test_case in test_cases:
                        if test_case.group:
                            category_obj = {
                                "id": test_case.group.id,
                                "name": test_case.group.name or "未命名分组"
                            }
                            if category_obj not in case_categories_list:
                                case_categories_list.append(category_obj)
                    
                    # 转换case_tags为包含id和name的对象列表
                    case_tags_list = []
                    for test_case in test_cases:
                        # 防御性检查: 确保 tags 不为 None
                        tc_tags = getattr(test_case, 'tags', []) or []
                        for tag in tc_tags:
                            tag_obj = {
                                "id": tag.id,
                                "name": tag.name or "未命名标签"
                            }
                            if tag_obj not in case_tags_list:
                                case_tags_list.append(tag_obj)
                    
                    # 转换为集合用于后续处理
                    if case_categories_list:
                        case_groups = {cat["name"] for cat in case_categories_list}
                    else:
                        case_categories_list = [{"id": "default_group", "name": "无分组"}]
                        case_groups = {"无分组"}
                    
                    # 确保 case_tags_list 包含 "无标签"
                    if not case_tags_list:
                        case_tags_list.append({"id": "default_tag", "name": "无标签"})
                    
                    case_tags = {tag["name"] for tag in case_tags_list}
            
            # 收集设备和API信息 - 只统计有实际测试结果的资源
            device_names = set()
            api_names = set()
            resources = set()
            device_list = []
            api_list = []
            
            # 先从测试结果中提取实际使用的设备和API（如果有任务）
            if tasks:
                # 提取所有结果并按 Task 和 Case 分组
                results = TestResult.query.filter(TestResult.task_id.in_(task_ids)).all()
                
                # 先从测试结果中提取实际使用的设备和API
                for t in tasks:
                    # 获取该任务的所有结果
                    task_results = [r for r in results if r.task_id == t.id]
                    for res in task_results:
                        resource = ReportControllerBase.get_resource_name(res, t, use_time_prefix=False)
                        if resource:
                            resources.add(resource)
                    
                    # 提取设备信息
                    task_devices = TaskDevice.query.filter_by(task_id=t.id).all()
                    for td in task_devices:
                        device = db.session.get(Device, td.device_id)
                        if device and not any(d['id'] == device.id for d in device_list):
                            device_list.append(ReportUtils.serialize_device(device))
                    
                    # 提取API信息
                    task_apis = TaskAPI.query.filter_by(task_id=t.id).all()
                    for ta in task_apis:
                        api = db.session.get(API, ta.api_id)
                        if api and not any(a['id'] == api.id for a in api_list):
                            api_list.append(ReportUtils.serialize_api(api))

            # 确保至少有一个资源
            if not resources:
                resources = {"默认资源"}

            # 转换为排序列表，确保确定性
            resource_list = sorted(list(resources))
            resources = resource_list # 使用排序后的列表
            
            # 验证是否有设备或API资源
            if not device_list and not api_list:
                return error_response("二次对比失败: 未找到设备或API资源数据")

            # 提取所有结果并按 Task 和 Case 分组（如果有任务）
            results = []
            if task_ids:
                results = TestResult.query.filter(TestResult.task_id.in_(task_ids)).all()
            
            # 验证是否有测试结果
            if not results:
                return error_response("二次对比失败: 未找到测试结果数据")
            
            res_ids = [r.id for r in results]
            used_dim_ids = set()
            if res_ids:
                rows = db.session.query(TestResultDimension.dimension_id).filter(
                    TestResultDimension.test_result_id.in_(res_ids)
                ).distinct().all()
                used_dim_ids = {r[0] for r in rows if r and r[0] is not None}

            all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
            all_dimensions = [d for d in all_dimensions_all if d.id in used_dim_ids] if used_dim_ids else all_dimensions_all

            all_metrics = []
            for dim in all_dimensions:
                unit = dim.score_unit if dim.score_unit and dim.score_unit.strip() else "%"
                decimal_places = dim.decimal_places if dim.decimal_places is not None else 2
                all_metrics.append({"id": dim.id, "name": dim.name, "unit": unit, "decimal_places": decimal_places})

            if not all_metrics:
                return error_response("二次对比失败: 未找到评估维度数据")
            
            # 验证是否有资源数据
            if not resources:
                return error_response("二次对比失败: 未找到设备或API资源数据")
            
            # 7. 核心指标计算 (Category, Tag, RawData, CaseTypeStats)
            tasks_map = {t.id: t for t in tasks}
            
            core_metrics = ReportUtils.calculate_core_metrics(
                results=results,
                all_dimensions=all_dimensions,
                resources=resources,
                dim_results_map=None,
                tasks_map=tasks_map,
                use_time_prefix=False
            )
            
            metric_data = core_metrics['metric_data']
            tag_metric_data = core_metrics['tag_metric_data']
            raw_data = core_metrics['raw_data']
            case_type_stats = core_metrics['case_type_stats']
            resources = core_metrics['resources'] # 更新可能新增的资源
            resource_headers = ReportUtils.build_resource_headers(
                resources=resources,
                results=results,
                tasks_map=tasks_map,
                use_time_prefix=False,
            )

            # 8. 计算设备和API统计
            device_stats, api_stats = ReportUtils.calculate_device_api_stats(
                results=results,
                all_dimensions=all_dimensions,
                dim_results_map=None
            )

            # 按测试用例ID分组结果
            results_by_case = {}
            for result in results:
                if result.test_case_id not in results_by_case:
                    results_by_case[result.test_case_id] = []
                results_by_case[result.test_case_id].append(result)
            
            # 生成具体用例数据
            cases = []
            for test_case in test_cases:
                # 获取该用例的所有结果
                case_results = results_by_case.get(test_case.id, [])
                
                # 按设备/API分组结果
                case_metrics = {}
                config = test_case.config or {}
                
                # 优先从 test_results.result_data 获取调整后的参考参数
                adjusted_reference_params_api = None
                adjusted_reference_params_e2e = None
                for result in case_results:
                    result_data = result.result_data
                    if result_data:
                        if isinstance(result_data, str) and result_data.strip():
                            import json
                            try:
                                result_data = json.loads(result_data)
                            except json.JSONDecodeError:
                                result_data = None
                        elif not isinstance(result_data, dict):
                            result_data = None
                        if result_data and isinstance(result_data, dict):
                            adjusted_ref = result_data.get('adjusted_reference_params')
                            if adjusted_ref:
                                # 根据测试类型区分
                                test_type = 'e2e' if result.device_id else 'api'
                                if test_type == 'e2e':
                                    adjusted_reference_params_e2e = adjusted_ref
                                else:
                                    adjusted_reference_params_api = adjusted_ref
                
                # 使用调整后的参数或原始配置
                if adjusted_reference_params_api:
                    config_api = {'reference_params': adjusted_reference_params_api}
                else:
                    config_api = config
                if adjusted_reference_params_e2e:
                    config_e2e = {'reference_params': adjusted_reference_params_e2e}
                else:
                    config_e2e = config

                # 获取所有参考参数（统一格式）
                reference_params_api = ReferenceParamsGenerator.get_reference_params_for_report(config_api, 'api')
                reference_params_e2e = ReferenceParamsGenerator.get_reference_params_for_report(config_e2e, 'e2e')
                
                # 合并 API 和 E2E 的参考参数
                reference_params_dict = {}
                all_codes = set(reference_params_api.keys()) | set(reference_params_e2e.keys())
                for code in all_codes:
                    param_api = reference_params_api.get(code, {})
                    param_e2e = reference_params_e2e.get(code, {})
                    reference_params_dict[code] = {
                        "code": code,
                        "type": param_api.get('type') or param_e2e.get('type', 'text'),
                        "api": param_api.get('value') or param_api.get('api'),
                        "e2e": param_e2e.get('value') or param_e2e.get('e2e'),
                        "segments": param_e2e.get('segments', []) or param_api.get('segments', []),
                        "text": param_e2e.get('text') or param_api.get('text', ''),
                        "json": param_e2e.get('json') or param_api.get('json', ''),
                    }

                for result in case_results:
                    # 获取所属任务执行时间前缀
                    task = db.session.get(Task, result.task_id)
                    resource = ReportUtils.get_resource_name(result, task, use_time_prefix=False)
                    
                    if not resource:
                        continue
                    
                    # 获取该结果的所有维度得分
                    dim_values = ReportControllerBase.extract_dimension_values(result.id, all_dimensions)
                    
                    # 保存该资源的指标数据
                    case_metrics[resource] = dim_values
                
                # 提取音频信息 - 统一构建audios数组
                config = test_case.config or {}
                audios_config = config.get('audios', [])
                
                # 获取设备信息用于显示
                device_ids = set()
                for audio_cfg in audios_config:
                    dev_id = audio_cfg.get('device_id')
                    if dev_id:
                        device_ids.add(dev_id)
                
                devices = {}
                if device_ids:
                    device_list = Device.query.filter(Device.id.in_(list(device_ids))).all()
                    devices = {d.id: d.name for d in device_list}
                
                # 构建统一的audios数组
                audios_list = []
                
                # 添加 API 音频
                if report_task_type in ("api", "all"):
                    for cfg in audios_config:
                        if cfg.get('test_type') == 'api':
                            audio_id = cfg.get('audio_id')
                            if audio_id:
                                audio = db.session.get(Audio, audio_id)
                                if audio:
                                    dev_id = cfg.get('device_id')
                                    audios_list.append({
                                        "audio_type": "api",
                                        "id": audio.id,
                                        "filename": audio.original_filename or audio.name,
                                        "duration": audio.duration,
                                        "url": f"/api/v1/audios/{audio.id}/stream",
                                        "spl": cfg.get('spl'),
                                        "play_order": cfg.get('play_order'),
                                        "device_id": dev_id,
                                        "device_name": devices.get(dev_id) if dev_id else None
                                    })
                
                # 添加 E2E 音频
                if report_task_type in ("e2e", "all"):
                    for cfg in audios_config:
                        if cfg.get('test_type') == 'e2e':
                            audio_id = cfg.get('audio_id')
                            if audio_id:
                                audio = db.session.get(Audio, audio_id)
                                if audio:
                                    dev_id = cfg.get('device_id')
                                    audios_list.append({
                                        "audio_type": "e2e",
                                        "id": audio.id,
                                        "filename": audio.original_filename or audio.name,
                                        "duration": audio.duration,
                                        "url": f"/api/v1/audios/{audio.id}/stream",
                                        "spl": cfg.get('spl'),
                                        "play_order": cfg.get('play_order'),
                                        "device_id": dev_id,
                                        "device_name": devices.get(dev_id) if dev_id else None
                                    })
                
                # 添加背景噪声
                background_noise = config.get('background_noise', {})
                if background_noise.get('audio_id'):
                    noise_audio = db.session.get(Audio, background_noise['audio_id'])
                    if noise_audio:
                        audios_list.append({
                            "audio_type": "noise",
                            "id": noise_audio.id,
                            "filename": noise_audio.name,
                            "duration": noise_audio.duration,
                            "url": f"/api/v1/audios/{noise_audio.id}/stream",
                            "noise_spl": background_noise.get('spl')
                        })
                
                # 按 play_order 排序
                audios_list.sort(key=lambda x: (x.get('play_order') is None, x.get('play_order') or 999))
                
                # 构建用例对象
                case_obj = {
                    "id": test_case.id,
                    "name": test_case.name,
                    "description": test_case.description or "",
                    "category": test_case.group.name if test_case.group else "未分类",
                    "tags": [tag.name for tag in (getattr(test_case, 'tags', []) or [])],
                    "metrics": case_metrics,
                    "results": [],
                    "audios": audios_list,
                    "reference_params": reference_params_dict,
                    "logs": "\n".join([result.error_message for result in case_results if result.error_message])
                }
                
                # 添加设备/API结果
                for result in case_results:
                    # 获取所属任务
                    task = db.session.get(Task, result.task_id)
                    # 使用统一函数获取资源名称
                    resource = ReportControllerBase.get_resource_name(result, task, use_time_prefix=False)
                    
                    # 添加结果信息
                    case_obj["results"].append(
                        {
                            "resource": resource,
                            "status": "成功" if result.execution_status == "completed" else "失败",
                            "start_time": result.created_at.isoformat() if result.created_at else None,
                            "end_time": result.created_at.isoformat() if result.created_at else None,
                        }
                    )
                
                cases.append(case_obj)
            
            # 1. 从源任务报告获取用例数据
            source_cases = []
            for report in reports:
                cases_data = ReportCases.query.filter_by(report_id=report.id).first()
                if cases_data and cases_data.cases:
                    if isinstance(cases_data.cases, list):
                        source_cases.extend(cases_data.cases)
                    elif isinstance(cases_data.cases, str):
                        import json
                        source_cases.extend(json.loads(cases_data.cases))
            
            # 如果没有从源报告获取到用例数据，使用构建的 cases
            if not source_cases:
                source_cases = cases
            
            # 聚合统计
            total_cases = sum(t.total_cases for t in tasks) if tasks else 0
            completed_cases = sum(t.completed_cases - t.failed_cases for t in tasks) if tasks else 0
            failed_cases = sum(t.failed_cases for t in tasks) if tasks else 0
            success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

            summary = {
                "report_count": len(reports),
                "task_count": len(tasks),
                "task_type": report_task_type,
                "total_cases": total_cases,
                "completed_cases": completed_cases,
                "failed_cases": failed_cases,
                "overall_success_rate": round(success_rate, 2),
                "tasks_info": [{"id": t.id, "name": t.name, "status": t.status, "type": t.type} for t in tasks],
                "reports_info": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "type": r.type,
                        "status": r.status
                    } for r in reports
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
                "cases": source_cases  # 使用源报告的用例数据
            }
            
            summary = ReportUtils.normalize_summary_metrics(summary)

            # 构建对比矩阵
            comparison_matrix = {}
            if task_ids:
                # 提取所有结果并按 Task 和 Case 分组
                results = TestResult.query.filter(TestResult.task_id.in_(task_ids)).all()
                
                # 获取所有涉及的维度及其权重
                dim_map = {d.id: d for d in all_dimensions}
                
                for res in results:
                    if res.test_case_id not in comparison_matrix:
                        case = db.session.get(TestCase, res.test_case_id)
                        comparison_matrix[res.test_case_id] = {
                            "case_id": res.test_case_id,
                            "case_name": case.name if case else res.test_case_id
                        }

                    # 获取该结果的所有维度得分
                    dimensions = TestResultDimension.query.filter_by(test_result_id=res.id).all()
                    dim_values = {}
                    for d in dimensions:
                        if d.dimension_id in dim_map:
                            dim_values[dim_map[d.dimension_id].name] = d.dimension_value or 0

                    # 确保所有维度都有默认值
                    for dim in all_dimensions:
                        if dim.name not in dim_values:
                            dim_values[dim.name] = 0

                    comparison_matrix[res.test_case_id][f"task_{res.task_id}"] = {
                        "status": 'completed' if res.execution_status == 'completed' else 'failed',
                        "response_time": res.response_time or 0,
                        "values": dim_values
                    }

            comparison_matrix_data = {
                "report_ids": report_ids,
                "report_names": [r.name for r in reports],
                "task_ids": task_ids,
                "task_names": [t.name for t in tasks],
                "matrix": comparison_matrix,
                "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat()
            }

            name = f"二次对比报告_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d%H%M%S')}"
            new_report = Report(
                name=name,
                type=ReportType.SECONDARY_COMPARISON.value,
                description=description,
                status=ReportStatus.DRAFT.value
            )
            db.session.add(new_report)
            db.session.flush()

            summary_info = ReportSummary(
                report_id=new_report.id,
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

            cases_record = ReportCases(
                report_id=new_report.id,
                cases=json.dumps(source_cases, ensure_ascii=False)
            )
            db.session.add(cases_record)

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
                comparison_matrix=json.dumps(comparison_matrix_data, ensure_ascii=False)
            )
            db.session.add(comparison_matrix_record)

            db.session.commit()

            # 直接返回ID，不进行键名转换，让前端适配蛇形命名
            response_data = IdData(id=new_report.id)
            
            return success_response(response_data, message="二次对比报告生成成功", code=ErrorCode.SUCCESS, http_code=201)
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return error_response("二次对比报告生成失败，请稍后重试")
