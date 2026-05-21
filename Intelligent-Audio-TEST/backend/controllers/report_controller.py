from flask import request, send_file, Response, stream_with_context, jsonify
from backend.models.models import Report, ReportSummary, ReportDetailData, Task, TestResult, TestResultDimension, Dimension, TestCase, Audio, Device, API, TaskCase, TaskDevice, TaskAPI, ReportStatus, ReportType
from backend.models.database import db
from backend.utils.response import success_response, error_response, format_response
from backend.utils.error_codes import ErrorCode
from backend.utils.report_utils import ReportUtils
from backend.schemas.report import (
    ReportBatchDeleteRequest,
    ReportExportRequest,
    ReportUpdateRequest,
    GetCaseAveragesRequest
)
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
import json
import io
import pandas as pd

# 导入拆分后的控制器
from backend.controllers.report_controller_base import ReportControllerBase
from backend.controllers.report_controller_task import ReportControllerTask
from backend.controllers.report_controller_compare import ReportControllerCompare
from backend.controllers.report_controller_secondary import ReportControllerSecondary

# 主控制器类，继承基础控制器并整合所有功能
class ReportController(ReportControllerBase):
    # 获取所有测试报告列表（分页与过滤）
    @staticmethod
    def get_all():
        return ReportControllerBase.get_all()

    # 获取单个测试报告详情
    @staticmethod
    def get_one(report_id):
        return ReportControllerBase.get_one(report_id)
    
    # 获取报告的用例列表，支持分页
    @staticmethod
    def get_report_cases(report_id):
        return ReportControllerBase.get_report_cases(report_id)

    @staticmethod
    def search_report_cases(report_id):
        return ReportControllerBase.search_report_cases(report_id)

    # 生成单个任务报告
    @staticmethod
    def generate_task_report():
        return ReportControllerTask.generate_task_report()

    # 生成对比报告
    @staticmethod
    def compare():
        return ReportControllerCompare.compare()

    # 二次对比分析：将多个任务的数据聚合到一个报告中，格式与任务报告保持一致
    @staticmethod
    def secondary_compare():
        return ReportControllerSecondary.secondary_compare()

    # 删除测试报告
    @staticmethod
    def delete(report_id):
        report = db.session.get(Report, report_id)
        if not report:
            return error_response("未找到测试报告", 404)

        try:
            db.session.delete(report)
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
        if not report:
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
            detail_data = ReportDetailData.query.filter_by(report_id=report.id).first()

            if not summary_info or not detail_data:
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

                if 'raw_data' in normalized_incoming:
                    detail_data.raw_data = json.dumps(normalized_incoming['raw_data'], ensure_ascii=False)
                if 'metric_data' in normalized_incoming:
                    detail_data.metric_data = json.dumps(normalized_incoming['metric_data'], ensure_ascii=False)
                if 'tag_metric_data' in normalized_incoming:
                    detail_data.tag_metric_data = json.dumps(normalized_incoming['tag_metric_data'], ensure_ascii=False)
                if 'case_type_stats' in normalized_incoming:
                    detail_data.case_type_stats = json.dumps(normalized_incoming['case_type_stats'], ensure_ascii=False)

            report.updated_at = datetime.now(timezone(timedelta(hours=8)))
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
        if not report:
            return error_response("未找到测试报告", 404)
        try:
            report.status = ReportStatus.PUBLISHED.value
            report.updated_at = datetime.now(timezone(timedelta(hours=8)))
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
            reports = Report.query.filter(Report.id.in_(report_ids)).all()
            if not reports:
                return success_response(None, "未找到指定的测试报告，无需删除")

            for report in reports:
                db.session.delete(report)
            
            db.session.commit()
            return success_response(None, f"成功删除 {len(reports)} 个测试报告")
        except Exception as e:
            db.session.rollback()
            import traceback
            traceback.print_exc()
            return error_response("批量删除报告失败，请稍后重试")

    # 导出测试报告 (CSV/Excel/PDF)
    @staticmethod
    def export():
        try:
            req = ReportExportRequest.model_validate(request.get_json())
        except Exception as e:
            try:
                report_ids_str = request.args.get('ids', '')
                format_type = request.args.get('format', 'csv')
                if not report_ids_str:
                    return error_response("缺少必要参数: ids")
                report_ids = [int(rid.strip()) for rid in str(report_ids_str).split(',') if rid.strip()]
                if not report_ids:
                    return error_response("无效的报告 ID 列表")
            except Exception:
                return error_response(f"请求参数错误: {str(e)}")
        else:
            report_ids = req.ids
            format_type = req.format

        try:
            reports = Report.query.filter(Report.id.in_(report_ids)).all()
            if not reports:
                return error_response("未找到指定报告", 404)

            export_data = []
            for report in reports:
                summary_info = ReportSummary.query.filter_by(report_id=report.id).first()
                if summary_info:
                    total_cases = summary_info.total_cases or 0
                    pass_rate = summary_info.pass_rate or 0
                else:
                    summary = report.summary or {}
                    total_cases = summary.get('total_cases', 0)
                    pass_rate = summary.get('pass_rate', 0)
                export_data.append({
                    "报告ID": str(report.id),
                    "报告名称": report.name,
                    "报告类型": report.type,
                    "生成时间": report.created_at.strftime('%Y-%m-%d %H:%M:%S') if report.created_at else "N/A",
                    "总用例数": str(total_cases),
                    "成功率": f"{pass_rate}%",
                    "分析结论": report.analysis or "无"
                })

            if format_type == 'excel':
                df = pd.DataFrame(export_data)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='报告')
                output.seek(0)
                
                filename = f"reports_export_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')}.xlsx"
                return send_file(
                    output,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True,
                    download_name=filename
                )
            elif format_type == 'pdf':
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import A4, landscape
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
                from reportlab.lib.styles import getSampleStyleSheet
                
                output = io.BytesIO()
                doc = SimpleDocTemplate(output, pagesize=landscape(A4))
                elements = []
                
                data = [list(export_data[0].keys())]
                for item in export_data:
                    data.append(list(item.values()))
                
                table = Table(data)
                style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ])
                table.setStyle(style)
                elements.append(table)
                
                doc.build(elements)
                output.seek(0)
                
                filename = f"reports_export_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')}.pdf"
                return send_file(
                    output,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=filename
                )
            else:
                def generate():
                    yield '\ufeff'.encode('utf-8-sig')
                    headers = list(export_data[0].keys())
                    yield (",".join(headers) + "\n").encode('utf-8-sig')

                    for row in export_data:
                        csv_row = [row[h] for h in headers]
                        csv_row = [f'"{r}"' if ',' in str(r) else str(r) for r in csv_row]
                        yield (",".join(csv_row) + "\n").encode('utf-8-sig')

                filename = f"reports_export_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')}.csv"
                return Response(
                    stream_with_context(generate()),
                    mimetype='text/csv',
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return error_response("导出报告失败，请稍后重试")

    # 按分组和标签获取用例平均值
    @staticmethod
    def get_case_averages_by_filters():
        """
        按分组和标签获取用例平均值，支持组合筛选
        """
        try:
            req = GetCaseAveragesRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}")

        task_id = req.task_id
        category = req.category
        tags = req.tags or []
        categories = req.categories or []
        include_untagged = req.include_untagged or False
        
        try:
            task = db.session.get(Task, task_id)
            if not task:
                return error_response("未找到指定任务")

            from backend.models.models import TaskMergeRelation

            if task.type == 'merged' and task.status == 'completed':
                merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
                if merge_relations:
                    source_task_ids = [r.source_task_id for r in merge_relations]
                    task_cases = TaskCase.query.filter(TaskCase.task_id.in_(source_task_ids)).all()
                    test_case_ids = [tc.test_case_id for tc in task_cases]
                    query = TestCase.query.filter(TestCase.id.in_(test_case_ids))
                    if category and category != 'all':
                        query = query.filter(TestCase.group.has(name=category))
                    if categories and len(categories) > 0:
                        from backend.models.models import TestCaseGroup
                        query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
                    if include_untagged:
                        if tags and len(tags) > 0:
                            from backend.models.models import Tag
                            query = query.filter(or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any()))
                        else:
                            query = query.filter(~TestCase.tags.any())
                    elif tags and len(tags) > 0:
                        from backend.models.models import Tag
                        query = query.join(TestCase.tags).filter(Tag.name.in_(tags))
                    test_cases = query.all()
                    filtered_case_ids = [case.id for case in test_cases]
                    test_results = TestResult.query.filter(
                        TestResult.test_case_id.in_(filtered_case_ids),
                        TestResult.task_id.in_(source_task_ids)
                    ).all()
                else:
                    task_cases = TaskCase.query.filter_by(task_id=task_id).all()
                    test_case_ids = [tc.test_case_id for tc in task_cases]
                    query = TestCase.query.filter(TestCase.id.in_(test_case_ids))
                    if category and category != 'all':
                        query = query.filter(TestCase.group.has(name=category))
                    if categories and len(categories) > 0:
                        from backend.models.models import TestCaseGroup
                        query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
                    if include_untagged:
                        if tags and len(tags) > 0:
                            from backend.models.models import Tag
                            query = query.filter(or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any()))
                        else:
                            query = query.filter(~TestCase.tags.any())
                    elif tags and len(tags) > 0:
                        from backend.models.models import Tag
                        query = query.join(TestCase.tags).filter(Tag.name.in_(tags))
                    test_cases = query.all()
                    filtered_case_ids = [case.id for case in test_cases]
                    test_results = TestResult.query.filter(
                        TestResult.test_case_id.in_(filtered_case_ids),
                        TestResult.task_id == task_id
                    ).all()
            elif task.type == 'merged':
                merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
                if merge_relations:
                    source_task_ids = [r.source_task_id for r in merge_relations]
                    task_cases = TaskCase.query.filter(TaskCase.task_id.in_(source_task_ids)).all()
                    test_case_ids = [tc.test_case_id for tc in task_cases]
                    query = TestCase.query.filter(TestCase.id.in_(test_case_ids))
                    if category and category != 'all':
                        query = query.filter(TestCase.group.has(name=category))
                    if categories and len(categories) > 0:
                        from backend.models.models import TestCaseGroup
                        query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
                    if include_untagged:
                        if tags and len(tags) > 0:
                            from backend.models.models import Tag
                            query = query.filter(or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any()))
                        else:
                            query = query.filter(~TestCase.tags.any())
                    elif tags and len(tags) > 0:
                        from backend.models.models import Tag
                        query = query.join(TestCase.tags).filter(Tag.name.in_(tags))
                    test_cases = query.all()
                    filtered_case_ids = [case.id for case in test_cases]
                    test_results = TestResult.query.filter(
                        TestResult.test_case_id.in_(filtered_case_ids),
                        TestResult.task_id.in_(source_task_ids)
                    ).all()
                else:
                    task_cases = TaskCase.query.filter_by(task_id=task_id).all()
                    test_case_ids = [tc.test_case_id for tc in task_cases]
                    query = TestCase.query.filter(TestCase.id.in_(test_case_ids))
                    if category and category != 'all':
                        query = query.filter(TestCase.group.has(name=category))
                    if categories and len(categories) > 0:
                        from backend.models.models import TestCaseGroup
                        query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
                    if include_untagged:
                        if tags and len(tags) > 0:
                            from backend.models.models import Tag
                            query = query.filter(or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any()))
                        else:
                            query = query.filter(~TestCase.tags.any())
                    elif tags and len(tags) > 0:
                        from backend.models.models import Tag
                        query = query.join(TestCase.tags).filter(Tag.name.in_(tags))
                    test_cases = query.all()
                    filtered_case_ids = [case.id for case in test_cases]
                    test_results = TestResult.query.filter(
                        TestResult.test_case_id.in_(filtered_case_ids),
                        TestResult.task_id == task_id
                    ).all()
            else:
                task_cases = TaskCase.query.filter_by(task_id=task_id).all()
                test_case_ids = [tc.test_case_id for tc in task_cases]
                query = TestCase.query.filter(TestCase.id.in_(test_case_ids))
                if category and category != 'all':
                    query = query.filter(TestCase.group.has(name=category))
                if categories and len(categories) > 0:
                    from backend.models.models import TestCaseGroup
                    query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
                if include_untagged:
                    if tags and len(tags) > 0:
                        from backend.models.models import Tag
                        query = query.filter(or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any()))
                    else:
                        query = query.filter(~TestCase.tags.any())
                elif tags and len(tags) > 0:
                    from backend.models.models import Tag
                    query = query.join(TestCase.tags).filter(Tag.name.in_(tags))
                test_cases = query.all()
                filtered_case_ids = [case.id for case in test_cases]
                test_results = TestResult.query.filter(
                    TestResult.test_case_id.in_(filtered_case_ids),
                    TestResult.task_id == task_id
                ).all()
            
            all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
            used_dim_ids = set()
            res_ids = [r.id for r in test_results]
            if res_ids:
                rows = db.session.query(TestResultDimension.dimension_id).filter(
                    TestResultDimension.test_result_id.in_(res_ids)
                ).distinct().all()
                used_dim_ids = {r[0] for r in rows if r and r[0] is not None}

            all_dimensions = [d for d in all_dimensions_all if d.id in used_dim_ids] if used_dim_ids else all_dimensions_all
            metric_name_to_id = {str(dim.name): int(dim.id) for dim in all_dimensions if getattr(dim, "id", None) is not None and getattr(dim, "name", None) is not None}
            
            dimension_scores = {}
            dimension_counts = {}
            
            for result in test_results:
                dim_values = ReportControllerBase.extract_dimension_values(result.id, all_dimensions)
                for dim_name, score in dim_values.items():
                    if score is not None:
                        if dim_name not in dimension_scores:
                            dimension_scores[dim_name] = 0
                            dimension_counts[dim_name] = 0
                        dimension_scores[dim_name] += score
                        dimension_counts[dim_name] += 1
            
            averages_map = {dim_name: (total / dimension_counts[dim_name]) for dim_name, total in dimension_scores.items() if dimension_counts[dim_name] > 0}
            overall_averages = [
                {"id": metric_name_to_id.get(str(dim_name)), "metric": str(dim_name), "value": value}
                for dim_name, value in sorted(averages_map.items(), key=lambda kv: kv[0])
            ]
            
            from backend.models.models import TaskDevice, Device, TaskAPI, API
            task_devices = TaskDevice.query.filter_by(task_id=task_id).all()
            task_apis = TaskAPI.query.filter_by(task_id=task_id).all()
            
            # 构建带时间前缀的资源列表
            time_prefix = ReportControllerBase.get_task_time_prefix(task)
            resources = []
            resource_headers = []
            for td in task_devices:
                d = db.session.get(Device, td.device_id)
                if d:
                    key = f"{time_prefix}-{d.id}-{d.name.lower()}"
                    resources.append(key)
                    resource_headers.append(
                        {
                            "key": key,
                            "label": ReportUtils._format_resource_label(task, d.name, getattr(d, "app_version", None), use_time_prefix=False) or key,
                            "type": "device",
                            "id": int(d.id),
                            "name": str(d.name),
                            "version": str(getattr(d, "app_version", None)) if getattr(d, "app_version", None) is not None else None,
                            "editable": True,
                        }
                    )
            for ta in task_apis:
                a = db.session.get(API, ta.api_id)
                if a:
                    key = f"{time_prefix}-{a.id}-{a.name.lower()}"
                    resources.append(key)
                    version = ReportUtils._extract_api_version(a)
                    resource_headers.append(
                        {
                            "key": key,
                            "label": ReportUtils._format_resource_label(task, a.name, version, use_time_prefix=False) or key,
                            "type": "api",
                            "id": int(a.id),
                            "name": str(a.name),
                            "version": version,
                            "editable": True,
                        }
                    )
            
            metric_data = {}
            raw_data = {res: {dim.name: [] for dim in all_dimensions} for res in resources}
            
            accumulator = {}
            
            for result in test_results:
                # 使用带时间前缀的资源名称
                resource = ReportControllerBase.get_resource_name(result, task, use_time_prefix=False)
                if resource not in resources:
                    continue
                
                test_case = db.session.get(TestCase, result.test_case_id)
                if not test_case: continue
                
                cat_name = test_case.group.name if test_case.group else "未分类"
                
                if cat_name not in accumulator:
                    accumulator[cat_name] = {}
                if resource not in accumulator[cat_name]:
                    accumulator[cat_name][resource] = {dim.name: {'sum': 0, 'count': 0} for dim in all_dimensions}
                
                dim_values = ReportControllerBase.extract_dimension_values(result.id, all_dimensions)
                for dim_name, score in dim_values.items():
                    if score is not None:
                        accumulator[cat_name][resource][dim_name]['sum'] += score
                        accumulator[cat_name][resource][dim_name]['count'] += 1
                        if dim_name in raw_data[resource]:
                            raw_data[resource][dim_name].append(score)
            
            for cat_name, res_data in accumulator.items():
                metric_data[cat_name] = {}
                for res, dims in res_data.items():
                    metric_data[cat_name][res] = {}
                    for dim_name, stats in dims.items():
                        metric_data[cat_name][res][dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else 0
            
            normal_distribution_data = ReportControllerBase.calculate_normal_distribution(raw_data)
            
            return success_response({
                "total_cases": len(filtered_case_ids),
                "total_results": len(test_results),
                "overall_averages": overall_averages,
                "overall_averages_map": averages_map,
                "metric_data": ReportUtils.flatten_metric_data(metric_data, {}, metric_name_to_id),
                "raw_data": ReportUtils.flatten_raw_data(raw_data),
                "normal_distribution": normal_distribution_data,
                "resources": resources,
                "resource_headers": resource_headers,
                "filters": {
                    "category": category,
                    "tags": tags
                }
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return error_response("获取用例平均值失败，请稍后重试")
