from flask import request, send_file, current_app
from backend.models.models import Report, ReportSummary, ReportDetailData as ReportDetailDataModel, Task, Audio
from backend.models.database import db
from backend.utils.response import success_response, error_response
from backend.utils.report_utils import ReportUtils
from backend.utils.query_utils import escape_like_pattern, sanitize_keyword, normalize_sort_field, normalize_sort_order
from backend.schemas.report import ReportDetailData, ReportListData, ReportListItem, ReportListItemSummary, ReportSummarySimplified, ReportListQuery, ReportCaseListQuery, ReportSearchCasesRequest
from datetime import datetime
from sqlalchemy.orm import joinedload, load_only
import os
import zipfile
import json
import io

class ReportControllerBase:
    # 公共函数：解析API请求体JSON
    @staticmethod
    def parse_api_request(api_request):
        if isinstance(api_request, str):
            import json
            try:
                api_request = json.loads(api_request)
            except json.JSONDecodeError:
                pass
        return api_request
    

    # 公共函数：获取任务执行标识前缀
    @staticmethod
    def get_task_time_prefix(task):
        return ReportUtils.get_task_time_prefix(task)

    # 公共函数：获取设备或API名称作为资源，使用ID+名称确保唯一性
    @staticmethod
    def get_resource_name(result, task=None, use_time_prefix=False):
        return ReportUtils.get_resource_name(result, task, use_time_prefix)
    
    # 公共函数：提取维度得分
    @staticmethod
    def extract_dimension_values(result_id, all_dimensions, dim_results_map=None, fill_missing=True):
        from backend.models.models import TestResultDimension
        dim_values = {}
        
        if all_dimensions is None:
            print(f"ERROR: all_dimensions is None in extract_dimension_values for result {result_id}")
            return dim_values

        if dim_results_map is not None:
            # 使用预先查询好的映射表，避免循环内查询数据库
            result_dims = dim_results_map.get(result_id, [])
            
            # 支持字典格式或对象格式
            for d in result_dims:
                if isinstance(d, dict):
                    dim_name = d.get('name')
                    dim_val = d.get('value')
                elif hasattr(d, 'dimension_name'):
                    dim_name = d.dimension_name
                    dim_val = d.dimension_value
                else:
                    dim_name = None
                    dim_val = None
                
                if dim_name is not None:
                    dim_values[dim_name] = dim_val
            
            if fill_missing:
                for dim in all_dimensions:
                    if dim.name not in dim_values:
                        dim_values[dim.name] = None
        else:
            # 兼容模式：如果没提供映射表，则回退到查询数据库
            for dim in all_dimensions:
                dim_result = TestResultDimension.query.filter_by(
                    test_result_id=result_id, dimension_id=dim.id
                ).first()
                dim_values[dim.name] = dim_result.dimension_value if dim_result and dim_result.dimension_value is not None else None
        return dim_values
    
    # 公共函数：构建结果信息
    @staticmethod
    def build_result_info(result):
        return {
            "status": "成功" if result.execution_status == "completed" else "失败",
            "start_time": result.created_at.isoformat() if result.created_at else None,
            "end_time": result.created_at.isoformat() if result.created_at else None
        }
    
    # 公共函数：提取音频列表
    @staticmethod
    def _extract_audios_list(test_case, test_type=None):
        """
        从用例配置中提取所有匹配的音频信息列表
        """
        if not test_case.config or 'audios' not in test_case.config:
            return []
            
        test_audios = test_case.config.get('audios', [])
        if not test_audios:
            return []
            
        results = []
        
        for audio_cfg in test_audios:
            # 如果指定了类型，则匹配类型；否则返回所有
            if test_type is None or audio_cfg.get('test_type') == test_type:
                audio_id = audio_cfg.get('audio_id')
                if audio_id:
                    audio = db.session.get(Audio, audio_id)
                    if audio:
                        results.append({
                            "id": audio.id,
                            "filename": audio.original_filename or audio.name,
                            "duration": audio.duration,
                            "url": f"/api/v1/audios/{audio.id}/stream",
                            "test_type": audio_cfg.get('test_type')
                        })
        return results

    # 公共函数：计算正态分布数据
    @staticmethod
    def calculate_normal_distribution(raw_data):
        """
        计算正态分布数据，包括统计信息、区间百分比和分布曲线
        
        参数：
        raw_data: dict - 原始数据，格式为 {resource: {dim_name: [values]}}
        
        返回：
        dict - 正态分布数据，格式为 {resource: {dim_name: {statistics, interval_percentages, distribution}}}
        """
        import numpy as np
        normal_distribution_data = {}
        
        for resource in raw_data:
            normal_distribution_data[resource] = {}
            for dim_name in raw_data[resource]:
                values = raw_data[resource][dim_name]
                count = len(values)
                
                if count > 0:
                    # 处理原始数据中的NaN值
                    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
                    
                    # 计算基本统计信息
                    mean = np.mean(values)
                    std = np.std(values)
                    min_val = np.min(values)
                    max_val = np.max(values)
                    median = np.median(values)
                    
                    # 计算四分位数
                    if count >= 4:
                        q1 = np.percentile(values, 25)
                        q3 = np.percentile(values, 75)
                    elif count >= 2:
                        q1 = values[0]
                        q3 = values[-1]
                    else:
                        q1 = values[0]
                        q3 = values[0]
                    
                    # 计算区间百分比
                    if count > 1 and std > 0:
                        # 正方向区间百分比
                        within_plus_1std = len([v for v in values if v <= mean + std]) / count * 100
                        within_plus_2std = len([v for v in values if v <= mean + 2 * std]) / count * 100
                        within_plus_3std = len([v for v in values if v <= mean + 3 * std]) / count * 100
                        beyond_plus_3std = len([v for v in values if v > mean + 3 * std]) / count * 100
                        
                        # 负方向区间百分比
                        within_minus_1std = len([v for v in values if v >= mean - std]) / count * 100
                        within_minus_2std = len([v for v in values if v >= mean - 2 * std]) / count * 100
                        within_minus_3std = len([v for v in values if v >= mean - 3 * std]) / count * 100
                        beyond_minus_3std = len([v for v in values if v < mean - 3 * std]) / count * 100
                    else:
                        # 只有一个数据点或标准差为0时，所有区间百分比为0
                        within_plus_1std = 0.0
                        within_plus_2std = 0.0
                        within_plus_3std = 0.0
                        beyond_plus_3std = 0.0
                        within_minus_1std = 0.0
                        within_minus_2std = 0.0
                        within_minus_3std = 0.0
                        beyond_minus_3std = 0.0
                    
                    # 处理统计信息中的NaN值
                    mean = float(round(float(np.nan_to_num(mean, nan=0.0)), 2))
                    std = float(round(float(np.nan_to_num(std, nan=0.0)), 2))
                    min_val = float(round(float(np.nan_to_num(min_val, nan=0.0)), 2))
                    q1 = float(round(float(np.nan_to_num(q1, nan=0.0)), 2))
                    median = float(round(float(np.nan_to_num(median, nan=0.0)), 2))
                    q3 = float(round(float(np.nan_to_num(q3, nan=0.0)), 2))
                    max_val = float(round(float(np.nan_to_num(max_val, nan=0.0)), 2))
                    
                    normal_distribution_data[resource][dim_name] = {
                        "raw_values": values.tolist(),
                        "statistics": {
                            "count": count,
                            "mean": mean,
                            "std": std,
                            "min": min_val,
                            "q1": q1,
                            "median": median,
                            "q3": q3,
                            "max": max_val
                        },
                        "interval_percentages": {
                            "positive": {
                                "within_plus_1std": float(round(np.nan_to_num(within_plus_1std, nan=0.0), 1)),
                                "within_plus_2std": float(round(np.nan_to_num(within_plus_2std, nan=0.0), 1)),
                                "within_plus_3std": float(round(np.nan_to_num(within_plus_3std, nan=0.0), 1)),
                                "beyond_plus_3std": float(round(np.nan_to_num(beyond_plus_3std, nan=0.0), 1))
                            },
                            "negative": {
                                "within_minus_1std": float(round(np.nan_to_num(within_minus_1std, nan=0.0), 1)),
                                "within_minus_2std": float(round(np.nan_to_num(within_minus_2std, nan=0.0), 1)),
                                "within_minus_3std": float(round(np.nan_to_num(within_minus_3std, nan=0.0), 1)),
                                "beyond_minus_3std": float(round(np.nan_to_num(beyond_minus_3std, nan=0.0), 1))
                            }
                        }
                    }
                else:
                    # 没有数据点
                    normal_distribution_data[resource][dim_name] = {
                        "raw_values": [],
                        "statistics": {
                            "count": 0,
                            "mean": 0,
                            "std": 0,
                            "min": 0,
                            "q1": 0,
                            "median": 0,
                            "q3": 0,
                            "max": 0
                        },
                        "interval_percentages": {
                            "positive": {
                                "within_plus_1std": 0.0,
                                "within_plus_2std": 0.0,
                                "within_plus_3std": 0.0,
                                "beyond_plus_3std": 0.0
                            },
                            "negative": {
                                "within_minus_1std": 0.0,
                                "within_minus_2std": 0.0,
                                "within_minus_3std": 0.0,
                                "beyond_minus_3std": 0.0
                            }
                        }
                    }
        
        return normal_distribution_data
    
    # 获取所有测试报告列表（分页与过滤）
    @staticmethod
    def get_all():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = ReportListQuery.model_validate(query_params_dict)
        
        page = query_params.page
        per_page = query_params.per_page if query_params.per_page else 10
        report_type = query_params.report_type
        status = query_params.status
        keyword = query_params.keyword
        start_time = query_params.start_time
        end_time = query_params.end_time
        algorithm_type = query_params.algorithm_type
        sort_by = query_params.sort_by
        order = query_params.order
        
        query = Report.query
        
        need_join_task = algorithm_type and algorithm_type != 'all'
        if need_join_task:
            query = query.join(Task, Report.task_id == Task.id).filter(Task.algorithm_type == algorithm_type)
        
        if report_type and report_type != 'all':
            query = query.filter(Report.type == report_type)
        if status and status != 'all':
            query = query.filter(Report.status == status)
        if keyword:
            safe_keyword = sanitize_keyword(keyword)
            if safe_keyword:
                escaped_keyword = escape_like_pattern(safe_keyword)
                query = query.filter(Report.name.like(f"%{escaped_keyword}%"))
        if start_time and start_time != 'null':
            try:
                query = query.filter(Report.created_at >= datetime.fromisoformat(start_time))
            except ValueError:
                pass
        if end_time and end_time != 'null':
            try:
                query = query.filter(Report.created_at <= datetime.fromisoformat(end_time))
            except ValueError:
                pass

        allowed_sort_fields = ['created_at', 'name', 'type', 'status', 'updated_at']
        safe_sort_by = normalize_sort_field(sort_by, allowed_sort_fields, 'created_at')
        safe_order = normalize_sort_order(order, 'desc')
        
        sort_attr = getattr(Report, safe_sort_by)
        
        if safe_order == 'asc':
            query = query.order_by(sort_attr.asc())
        else:
            query = query.order_by(sort_attr.desc())
        
        import time
        
        count_start = time.time()
        total = query.count()
        count_elapsed = round((time.time() - count_start) * 1000, 2)
        print(f"[PERF] COUNT query elapsed: {count_elapsed}ms, total: {total}")
        
        data_start = time.time()
        reports = query.offset((page - 1) * per_page).limit(per_page).all()
        data_elapsed = round((time.time() - data_start) * 1000, 2)
        print(f"[PERF] Data query elapsed: {data_elapsed}ms, items: {len(reports)}")
        
        report_ids = [r.id for r in reports]
        summaries_map = {}
        if report_ids:
            summary_start = time.time()
            summaries = ReportSummary.query.filter(ReportSummary.report_id.in_(report_ids)).all()
            summaries_map = {s.report_id: s for s in summaries}
            summary_elapsed = round((time.time() - summary_start) * 1000, 2)
            print(f"[PERF] load summaries elapsed: {summary_elapsed}ms, count: {len(summaries)}")
        
        task_ids = [r.task_id for r in reports if r.task_id]
        tasks_map = {}
        if task_ids:
            task_start = time.time()
            tasks = Task.query.filter(Task.id.in_(task_ids)).all()
            tasks_map = {t.id: t for t in tasks}
            task_elapsed = round((time.time() - task_start) * 1000, 2)
            print(f"[PERF] load tasks elapsed: {task_elapsed}ms, count: {len(tasks)}")

        data = []
        for report in reports:
            task = tasks_map.get(report.task_id) if report.task_id else None
            summary_info = summaries_map.get(report.id)

            if not summary_info:
                continue

            total_cases = summary_info.total_cases or 0
            completed_cases = summary_info.completed_cases or 0
            failed_cases = summary_info.failed_cases or 0
            pass_rate = summary_info.pass_rate or 0
            if pass_rate == 0 and total_cases > 0:
                pass_rate = round((completed_cases / total_cases) * 100, 2) if total_cases > 0 else 0

            raw_summary = {}
            task_count = None

            data.append(
                ReportListItem(
                    id=report.id,
                    name=report.name,
                    type=report.type,
                    task_id=report.task_id,
                    task_name=task.name if task else ("对比报告" if report.type == 'comparison' else "趋势报告"),
                    algorithm_type=task.algorithm_type if task else None,
                    summary=ReportListItemSummary(
                        total_cases=total_cases,
                        completed_cases=completed_cases,
                        failed_cases=failed_cases,
                        pass_rate=pass_rate,
                        task_count=task_count,
                    ),
                    description=report.description,
                    status=report.status,
                    created_at=report.created_at.isoformat(),
                    updated_at=report.updated_at.isoformat() if report.updated_at else None,
                )
            )
        
        return success_response(
            ReportListData(
                items=data,
                total=total,
                page=page,
                per_page=per_page,
                pages=(total + per_page - 1) // per_page if total > 0 else 0,
            )
        )

    # 获取单个测试报告详情
    @staticmethod
    def get_one(report_id):
        report = db.session.get(Report, report_id)
        if not report:
            return error_response("未找到测试报告", 404)

        task = db.session.get(Task, report.task_id) if report.task_id else None

        summary_info = ReportSummary.query.filter_by(report_id=report.id).first()
        detail_data = ReportDetailDataModel.query.filter_by(report_id=report.id).first()

        if not summary_info or not detail_data:
            return error_response("报告数据未迁移，请先运行迁移脚本", 500)

        def to_json(val):
            if val is None:
                return []
            if isinstance(val, (list, dict)):
                return val
            if isinstance(val, str):
                import json
                return json.loads(val)
            return val if isinstance(val, list) else []

        def to_json_obj(val):
            if val is None:
                return {}
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                import json
                return json.loads(val)
            return val if isinstance(val, dict) else {}

        simplified_summary = {
            "raw_data": to_json(detail_data.raw_data),
            "case_categories": to_json(summary_info.case_categories),
            "all_case_tags": to_json(summary_info.all_case_tags),
            "resources": to_json(summary_info.resources),
            "resource_headers": to_json(summary_info.resource_headers),
            "all_metrics": to_json(summary_info.all_metrics),
            "device_stats": to_json(detail_data.device_stats),
            "api_stats": to_json(detail_data.api_stats),
            "case_type_stats": to_json(detail_data.case_type_stats),
            "devices": to_json(summary_info.devices),
            "apis": to_json(summary_info.apis),
            "metric_data": to_json(detail_data.metric_data),
            "tag_metric_data": to_json(detail_data.tag_metric_data),
            "total_cases": summary_info.total_cases or 0,
            "completed_cases": summary_info.completed_cases or 0,
            "failed_cases": summary_info.failed_cases or 0
        }

        if 'cases' in simplified_summary:
            del simplified_summary['cases']

        return success_response(
            ReportDetailData(
                id=report.id,
                name=report.name,
                type=report.type,
                task_id=report.task_id,
                task_type=task.type if task else (simplified_summary.get('task_type') or (report.type if report.type in ['api', 'e2e'] else None)),
                task_name=task.name if task else "对比报告/趋势报告",
                algorithm_type=task.algorithm_type if task else None,
                summary=ReportSummarySimplified(**simplified_summary),
                description=report.description,
                status=report.status,
                analysis=report.analysis,
                created_at=report.created_at.isoformat(),
                updated_at=report.updated_at.isoformat() if report.updated_at else None,
            )
        )
    
    # 获取报告的用例列表，支持分页
    @staticmethod
    def get_report_cases(report_id):
        report = db.session.get(Report, report_id)
        if not report:
            return error_response("未找到测试报告", 404)
        
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = ReportCaseListQuery.model_validate(query_params_dict)

        detail_data = ReportDetailDataModel.query.filter_by(report_id=report.id).first()
        if not detail_data:
            return error_response("报告数据未迁移，请先运行迁移脚本", 500)

        def to_json(val):
            if val is None:
                return []
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                import json
                return json.loads(val)
            return []

        cases = to_json(detail_data.cases)

        keyword = query_params.keyword
        category = query_params.category
        tags = query_params.tags if query_params.tags else []
        
        if not tags:
            tags_csv = request.args.get('tags')
            if tags_csv:
                tags = [t.strip() for t in str(tags_csv).split(',') if t.strip()]
        
        if keyword:
            kw = str(keyword).lower()
            cases = [
                c for c in cases
                if isinstance(c, dict)
                and (
                    kw in str(c.get('name', '')).lower()
                    or kw in str(c.get('description', '')).lower()
                )
            ]
        
        if category:
            cases = [
                c for c in cases
                if isinstance(c, dict) and str(c.get('category', '')) == str(category)
            ]
        
        if tags:
            tag_set = set(str(t) for t in tags)
            filtered = []
            for c in cases:
                if not isinstance(c, dict):
                    continue
                case_tags = c.get('tags') or []
                case_tag_names = []
                if isinstance(case_tags, list):
                    for t in case_tags:
                        case_tag_names.append(str(t.get('name')) if isinstance(t, dict) else str(t))
                if tag_set.intersection(case_tag_names):
                    filtered.append(c)
            cases = filtered
        
        # 分页参数
        page = query_params.page
        per_page = query_params.per_page
        
        # 计算分页
        total = len(cases)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_cases = cases[start:end]
        
        # 计算总页数
        pages = (total + per_page - 1) // per_page
        
        return success_response({
            "items": paginated_cases,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages
        })

    @staticmethod
    def download_case_logs(report_id, case_id):
        from backend.utils.log_handler import log_and_emit
        from backend.models.models import TestResult, TaskMergeRelation
        from flask import Response

        log_and_emit(
            level='INFO',
            module='report',
            content=f'开始下载用例日志 - report_id: {report_id}, case_id: {case_id}'
        )
        
        report = db.session.get(Report, report_id)
        if not report:
            log_and_emit(
                level='WARNING',
                module='report',
                content=f'下载用例日志失败 - 未找到报告: report_id={report_id}'
            )
            return error_response("未找到测试报告", 404)

        task_id = report.task_id
        if not task_id:
            log_and_emit(
                level='WARNING',
                module='report',
                content=f'下载用例日志失败 - 报告没有关联任务ID: report_id={report_id}'
            )
            return error_response("该报告没有关联的任务ID", 400)

        static_base_path = current_app.config.get('STATIC_BASE_PATH')
        if not static_base_path:
            log_and_emit(
                level='ERROR',
                module='report',
                content='下载用例日志失败 - 服务器未配置静态文件路径'
            )
            return error_response("服务器未配置静态文件路径", 500)

        merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
        task_ids_to_search = [task_id]
        if merge_relations:
            task_ids_to_search = [r.source_task_id for r in merge_relations]

        zip_filename = f"case_{case_id}_logs.zip"

        try:
            test_result = TestResult.query.filter(
                TestResult.task_id.in_(task_ids_to_search),
                TestResult.test_case_id == case_id
            ).first()

            zip_buffer = io.BytesIO()
            found_any = False
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for search_task_id in task_ids_to_search:
                    local_dir = os.path.join(static_base_path, 'case_result', str(search_task_id), str(case_id))
                    
                    if os.path.exists(local_dir):
                        found_any = True
                        for root, dirs, files in os.walk(local_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, local_dir)
                                if len(task_ids_to_search) > 1:
                                    arcname = os.path.join(f"task_{search_task_id}", arcname)
                                zf.write(file_path, arcname)

                if test_result and test_result.result_data and 'adjusted_reference_params' in test_result.result_data:
                    adjusted_params = test_result.result_data['adjusted_reference_params']
                    if adjusted_params:
                        params_json = json.dumps(adjusted_params, ensure_ascii=False, indent=2)
                        zf.writestr("adjusted_reference_params.json", params_json)

            if not found_any:
                log_and_emit(
                    level='WARNING',
                    module='report',
                    content=f'下载用例日志失败 - 未找到用例日志目录，搜索任务IDs: {task_ids_to_search}'
                )
                return error_response(f"未找到用例日志目录", 404)

            zip_buffer.seek(0)
            zip_data = zip_buffer.getvalue()

            response = Response(
                zip_data,
                mimetype='application/zip',
                headers={
                    'Content-Disposition': f'attachment; filename*=UTF-8\'\'{zip_filename}',
                    'Content-Length': str(len(zip_data)),
                    'X-Content-Type-Options': 'nosniff',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
            log_and_emit(
                level='INFO',
                module='report',
                content=f'用例日志下载成功 - report_id: {report_id}, case_id: {case_id}'
            )
            return response
        except Exception as e:
            log_and_emit(
                level='ERROR',
                module='report',
                content=f'下载用例日志失败 - report_id: {report_id}, case_id: {case_id}, error: {str(e)}'
            )
            return error_response(f"创建ZIP文件失败: {str(e)}", 500)

    @staticmethod
    def search_report_cases(report_id):
        report = db.session.get(Report, report_id)
        if not report:
            return error_response("未找到测试报告", 404)
        
        json_data = request.get_json() or {}
        
        data = ReportSearchCasesRequest.model_validate(json_data)
        
        keyword = data.keyword
        category = data.category
        include_untagged = data.include_untagged or False
        
        raw_tags = data.tags or []
        tags = []
        if isinstance(raw_tags, list):
            for t in raw_tags:
                if t is None:
                    continue
                parts = [p.strip() for p in str(t).split(',') if p.strip()]
                tags.extend(parts)
        else:
            tags = [t.strip() for t in str(raw_tags).split(',') if t.strip()]

        detail_data = ReportDetailDataModel.query.filter_by(report_id=report.id).first()
        if not detail_data:
            return error_response("报告数据未迁移，请先运行迁移脚本", 500)

        def to_json_cases(val):
            if val is None:
                return []
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                import json
                return json.loads(val)
            return []

        cases = to_json_cases(detail_data.cases)

        # 应用筛选条件
        if keyword:
            kw = str(keyword).lower()
            cases = [
                c for c in cases
                if isinstance(c, dict)
                and (
                    kw in str(c.get('name', '')).lower()
                    or kw in str(c.get('description', '')).lower()
                )
            ]
        
        if category:
            cases = [
                c for c in cases
                if isinstance(c, dict) and str(c.get('category', '')) == str(category)
            ]
        
        if tags or include_untagged:
            tag_set = set(str(t) for t in tags)
            filtered = []
            for c in cases:
                if not isinstance(c, dict):
                    continue
                case_tags = c.get('tags') or []
                case_tag_names = []
                if isinstance(case_tags, list):
                    for t in case_tags:
                        case_tag_names.append(str(t.get('name')) if isinstance(t, dict) else str(t))
                
                is_untagged = len(case_tag_names) == 0
                has_tag_match = bool(tag_set.intersection(case_tag_names)) if tag_set else False
                
                if include_untagged:
                    if (tag_set and (has_tag_match or is_untagged)) or (not tag_set and is_untagged):
                        filtered.append(c)
                else:
                    if has_tag_match:
                        filtered.append(c)
            cases = filtered
        
        page = data.page
        per_page = data.per_page
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = 20
        
        total = len(cases)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_cases = cases[start:end]
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        
        return success_response({
            "items": paginated_cases,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages
        })
