from flask import request
from backend.models.models import (
    Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase,
    ReportMetricStats, ReportComparisonMatrix, Task,
    ReportStatus, ReportType, TaskStatus
)
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.error_codes import ErrorCode
from backend.utils.report.report_utils import ReportUtils
from backend.utils.report.report_query_builder import ReportQueryBuilder
from backend.utils.common.query_utils import now_cst
from backend.schemas.report import CompareReportsRequest
from backend.controllers.report_controller_base import ReportControllerBase
from backend.schemas.report import ReportIdData
import json
import traceback


class ReportControllerCompare(ReportControllerBase):

    @staticmethod
    def _validate_and_get_tasks(task_ids):
        tasks = Task.query.filter(
            Task.id.in_(task_ids),
            Task.status.in_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value])
        ).all()
        if not tasks:
            return None, error_response("未找到指定任务或任务状态不是completed、failed或merged")
        return tasks, None

    @staticmethod
    def _get_reports_for_tasks(tasks):
        """查找每个任务最新的报告快照，返回 (reports, task_id_to_report)"""
        task_ids = [t.id for t in tasks]
        reports = Report.query.filter(
            Report.task_id.in_(task_ids),
            Report.type == ReportType.TASK.value
        ).order_by(Report.created_at.desc()).all()

        # 每个任务取最新一条报告
        task_id_to_report = {}
        reports_found = []
        for report in reports:
            if report.task_id and report.task_id not in task_id_to_report:
                task_id_to_report[report.task_id] = report
                reports_found.append(report)

        return reports_found, task_id_to_report

    @staticmethod
    def _load_report_snapshots(reports):
        """批量加载报告快照数据"""
        report_ids = [r.id for r in reports]

        all_cases = ReportCase.query.filter(ReportCase.report_id.in_(report_ids)).all()
        all_metric_stats = ReportMetricStats.query.filter(ReportMetricStats.report_id.in_(report_ids)).all()
        all_raw_data = ReportRawData.query.filter(ReportRawData.report_id.in_(report_ids)).all()
        all_summaries = ReportSummary.query.filter(ReportSummary.report_id.in_(report_ids)).all()
        all_summary_metas = ReportSummaryMeta.query.filter(ReportSummaryMeta.report_id.in_(report_ids)).all()

        cases_by_report = {r.id: [] for r in reports}
        for c in all_cases:
            cases_by_report[c.report_id].append(c)

        metric_stats_map = {ms.report_id: ms for ms in all_metric_stats}
        raw_data_map = {rd.report_id: rd for rd in all_raw_data}
        summary_map = {s.report_id: s for s in all_summaries}
        summary_meta_map = {sm.report_id: sm for sm in all_summary_metas}

        return {
            'cases_by_report': cases_by_report,
            'metric_stats_map': metric_stats_map,
            'raw_data_map': raw_data_map,
            'summary_map': summary_map,
            'summary_meta_map': summary_meta_map,
        }

    @staticmethod
    def _merge_cases_from_snapshots(reports, snapshots, task_id_to_report):
        """从快照合并 cases，标注来源 task_id"""
        merged_cases = []
        for report in reports:
            case_records = snapshots['cases_by_report'].get(report.id, [])
            for cr in case_records:
                case_item = {
                    "id": cr.test_case_id,
                    "name": cr.name,
                    "description": cr.description or "",
                    "category": cr.category,
                    "tags": cr.tags or [],
                    "metrics": cr.metrics or {},
                    "results": cr.results or [],
                    "audios": cr.audios or [],
                    "reference_params": cr.reference_params,
                    "algorithm_results": cr.algorithm_results,
                    "algorithm_type": cr.algorithm_type,
                    "logs": cr.logs,
                    "source_report_id": report.id,
                    "source_task_id": report.task_id
                }
                merged_cases.append(case_item)
        return merged_cases

    @staticmethod
    def _merge_metric_data(reports, snapshots):
        """合并 metric_data"""
        merged = []
        for report in reports:
            ms = snapshots['metric_stats_map'].get(report.id)
            if ms and ms.metric_data:
                data = ms.metric_data
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    merged.extend(data)
        return merged

    @staticmethod
    def _merge_tag_metric_data(reports, snapshots):
        """合并 tag_metric_data"""
        merged = []
        for report in reports:
            ms = snapshots['metric_stats_map'].get(report.id)
            if ms and ms.tag_metric_data:
                data = ms.tag_metric_data
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    merged.extend(data)
        return merged

    @staticmethod
    def _merge_raw_data(reports, snapshots):
        """合并 raw_data"""
        merged = []
        for report in reports:
            rd = snapshots['raw_data_map'].get(report.id)
            if rd and rd.raw_data:
                data = rd.raw_data
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    merged.extend(data)
        return merged

    @staticmethod
    def _merge_device_api_stats(reports, snapshots):
        """合并 device_stats / api_stats"""
        merged_device = []
        merged_api = []
        for report in reports:
            ms = snapshots['metric_stats_map'].get(report.id)
            if ms:
                for stats_attr, target in [('device_stats', merged_device), ('api_stats', merged_api)]:
                    data = getattr(ms, stats_attr, None)
                    if data:
                        if isinstance(data, str):
                            data = json.loads(data)
                        if isinstance(data, list):
                            target.extend(data)
        return merged_device, merged_api

    @staticmethod
    def _merge_case_type_stats(reports, snapshots):
        """合并 case_type_stats（去重）"""
        merged = []
        seen_types = set()
        for report in reports:
            ms = snapshots['metric_stats_map'].get(report.id)
            if ms and ms.case_type_stats:
                data = ms.case_type_stats
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            type_name = item.get('type') or item.get('case_type')
                            if type_name not in seen_types:
                                seen_types.add(type_name)
                                merged.append(item)
                        else:
                            merged.append(item)
        return merged

    @staticmethod
    def _merge_devices_apis(reports, snapshots):
        """合并 devices / apis 列表（去重）"""
        merged_devices = []
        merged_apis = []
        seen_device_ids = set()
        seen_api_ids = set()

        for report in reports:
            sm = snapshots['summary_meta_map'].get(report.id)
            if not sm:
                continue
            if sm.devices:
                data = sm.devices
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    for d in data:
                        if isinstance(d, dict):
                            did = d.get('id')
                            if did not in seen_device_ids:
                                seen_device_ids.add(did)
                                merged_devices.append(d)
            if sm.apis:
                data = sm.apis
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    for a in data:
                        if isinstance(a, dict):
                            aid = a.get('id')
                            if aid not in seen_api_ids:
                                seen_api_ids.add(aid)
                                merged_apis.append(a)

        return merged_devices, merged_apis

    @staticmethod
    def _merge_resources(reports, snapshots):
        """合并 resources 列表（去重）"""
        merged = []
        seen = set()
        for report in reports:
            sm = snapshots['summary_meta_map'].get(report.id)
            if not sm or not sm.resources:
                continue
            data = sm.resources
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, list):
                for r in data:
                    if isinstance(r, str):
                        if r not in seen:
                            seen.add(r)
                            merged.append(r)
                    elif isinstance(r, dict):
                        key = r.get('id') or r.get('name') or json.dumps(r, sort_keys=True)
                        if key not in seen:
                            seen.add(key)
                            merged.append(r)
            elif isinstance(data, str):
                for r in data.split(','):
                    r = r.strip()
                    if r and r not in seen:
                        seen.add(r)
                        merged.append(r)
        return merged

    @staticmethod
    def _merge_resource_headers(reports, snapshots):
        """合并 resource_headers"""
        merged = []
        for report in reports:
            sm = snapshots['summary_meta_map'].get(report.id)
            if not sm or not sm.resource_headers:
                continue
            data = sm.resource_headers
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, list):
                merged.extend(data)
        return merged

    @staticmethod
    def _merge_all_metrics(reports, snapshots):
        """合并 all_metrics（按维度 id 去重）"""
        merged = []
        seen_ids = set()
        for report in reports:
            sm = snapshots['summary_meta_map'].get(report.id)
            if not sm or not sm.all_metrics:
                continue
            data = sm.all_metrics
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, list):
                for m in data:
                    if isinstance(m, dict):
                        mid = m.get('id')
                        if mid not in seen_ids:
                            seen_ids.add(mid)
                            merged.append(m)
        return merged

    @staticmethod
    def _merge_field_mappings(reports, snapshots):
        """合并 field_mappings（按 algorithm_type 合并）"""
        merged = {}
        for report in reports:
            sm = snapshots['summary_meta_map'].get(report.id)
            if not sm or not sm.field_mappings:
                continue
            data = sm.field_mappings
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                for algo_type, mapping in data.items():
                    if algo_type not in merged:
                        merged[algo_type] = mapping
        return merged

    @staticmethod
    def _merge_case_categories_and_tags(reports, snapshots):
        """合并 case_categories / all_case_tags（去重）"""
        merged_categories = []
        merged_tags = []
        seen_cat_ids = set()
        seen_tag_ids = set()

        for report in reports:
            sm = snapshots['summary_meta_map'].get(report.id)
            if not sm:
                continue
            if sm.case_categories:
                data = sm.case_categories
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    for c in data:
                        if isinstance(c, dict):
                            cid = c.get('id') or c.get('name')
                            if cid not in seen_cat_ids:
                                seen_cat_ids.add(cid)
                                merged_categories.append(c)
            if sm.all_case_tags:
                data = sm.all_case_tags
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    for t in data:
                        if isinstance(t, dict):
                            tid = t.get('id') or t.get('name')
                            if tid not in seen_tag_ids:
                                seen_tag_ids.add(tid)
                                merged_tags.append(t)

        return merged_categories, merged_tags

    @staticmethod
    def _build_comparison_matrix_from_snapshots(reports, snapshots, merged_cases, tasks):
        """从快照 cases 的 metrics 构建对比矩阵"""
        all_metric_names = set()
        case_map = {}

        for case_item in merged_cases:
            case_id = case_item['id']
            if case_id not in case_map:
                case_map[case_id] = {
                    "case_id": case_id,
                    "case_name": case_item['name'],
                    "task_data": {}  # task_id → {dim_name: avg_value}
                }

            task_id = case_item.get('source_task_id')
            metrics = case_item.get('metrics')
            if not metrics or not task_id:
                continue

            dim_sums = {}
            dim_counts = {}

            if isinstance(metrics, dict):
                # metrics: {resource: {dim_name: value}} 或 {dim_name: value}
                for resource, dim_values in metrics.items():
                    if isinstance(dim_values, dict):
                        for dim_name, dim_value in dim_values.items():
                            all_metric_names.add(dim_name)
                            dim_sums[dim_name] = dim_sums.get(dim_name, 0) + (dim_value or 0)
                            dim_counts[dim_name] = dim_counts.get(dim_name, 0) + 1
                    else:
                        all_metric_names.add(resource)
                        dim_sums[resource] = dim_sums.get(resource, 0) + (dim_values or 0)
                        dim_counts[resource] = dim_counts.get(resource, 0) + 1
            elif isinstance(metrics, list):
                for m_item in metrics:
                    if isinstance(m_item, dict):
                        for dm in m_item.get('metrics', []):
                            if isinstance(dm, dict):
                                dim_name = dm.get('metric', '')
                                all_metric_names.add(dim_name)
                                dim_sums[dim_name] = dim_sums.get(dim_name, 0) + (dm.get('value', 0) or 0)
                                dim_counts[dim_name] = dim_counts.get(dim_name, 0) + 1

            # 计算该任务在该用例下的维度平均值
            avg_values = {}
            for dn in all_metric_names:
                if dn in dim_sums and dim_counts[dn] > 0:
                    avg_values[dn] = dim_sums[dn] / dim_counts[dn]
                else:
                    avg_values[dn] = 0
            case_map[case_id]["task_data"][f"task_{task_id}"] = {
                "status": "completed",
                "values": avg_values
            }

        # 构建最终矩阵
        matrix = {}
        for case_id, case_info in case_map.items():
            row = {
                "case_id": case_id,
                "case_name": case_info["case_name"]
            }
            for task in tasks:
                col_key = f"task_{task.id}"
                if col_key in case_info["task_data"]:
                    row[col_key] = case_info["task_data"][col_key]
                else:
                    row[col_key] = {
                        "status": "completed",
                        "values": {dn: 0 for dn in all_metric_names}
                    }
            matrix[case_id] = row

        return matrix

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

            # 1. 查找每个任务的报告快照
            reports, task_id_to_report = ReportControllerCompare._get_reports_for_tasks(tasks)
            if not reports:
                return error_response("对比失败: 所选任务未生成报告，请先生成任务报告")

            # 检查是否有任务缺少报告
            tasks_without_report = [t for t in tasks if t.id not in task_id_to_report]
            if tasks_without_report:
                missing_names = [t.name for t in tasks_without_report]
                return error_response(f"对比失败: 以下任务未生成报告: {', '.join(missing_names)}")

            included_task_types = {t.type for t in tasks if getattr(t, "type", None)}
            report_task_type = (
                "api"
                if included_task_types == {"api"}
                else ("e2e" if included_task_types == {"e2e"} else "all")
            )

            # 2. 加载所有报告快照
            snapshots = ReportControllerCompare._load_report_snapshots(reports)

            # 3. 从快照聚合数据
            source_cases = ReportControllerCompare._merge_cases_from_snapshots(reports, snapshots, task_id_to_report)
            if not source_cases:
                return error_response("对比失败: 未找到报告用例数据")

            metric_data = ReportControllerCompare._merge_metric_data(reports, snapshots)
            tag_metric_data = ReportControllerCompare._merge_tag_metric_data(reports, snapshots)
            raw_data = ReportControllerCompare._merge_raw_data(reports, snapshots)
            device_stats, api_stats = ReportControllerCompare._merge_device_api_stats(reports, snapshots)
            case_type_stats = ReportControllerCompare._merge_case_type_stats(reports, snapshots)
            devices_list, apis_list = ReportControllerCompare._merge_devices_apis(reports, snapshots)
            resources = ReportControllerCompare._merge_resources(reports, snapshots)
            resource_headers = ReportControllerCompare._merge_resource_headers(reports, snapshots)
            all_metrics = ReportControllerCompare._merge_all_metrics(reports, snapshots)
            field_mappings = ReportControllerCompare._merge_field_mappings(reports, snapshots)
            case_categories_list, case_tags_list = ReportControllerCompare._merge_case_categories_and_tags(reports, snapshots)

            if not devices_list and not apis_list:
                return error_response("对比失败: 未找到设备或API资源数据")

            if not all_metrics:
                return error_response("对比失败: 未找到评估维度数据")

            # 4. 聚合汇总数据（从 Task 快照，因为对比任务以任务为维度）
            total_cases = sum(t.total_cases or 0 for t in tasks)
            completed_cases = sum((t.completed_cases or 0) - (t.failed_cases or 0) for t in tasks)
            failed_cases = sum(t.failed_cases or 0 for t in tasks)
            success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

            # 5. 从快照构建对比矩阵
            comparison_matrix = ReportControllerCompare._build_comparison_matrix_from_snapshots(
                reports, snapshots, source_cases, tasks
            )

            # 6. 创建报告记录
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
                dimension_values=json.dumps([], ensure_ascii=False),
                case_categories=json.dumps(case_categories_list, ensure_ascii=False),
                all_case_tags=json.dumps(case_tags_list, ensure_ascii=False),
                devices=json.dumps(devices_list, ensure_ascii=False),
                apis=json.dumps(apis_list, ensure_ascii=False),
                resources=json.dumps(resources, ensure_ascii=False),
                resource_headers=json.dumps(resource_headers, ensure_ascii=False),
                all_metrics=json.dumps(all_metrics, ensure_ascii=False),
                field_mappings=json.dumps(field_mappings, ensure_ascii=False)
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

            comparison_data = {
                "task_ids": task_ids,
                "task_names": [t.name for t in tasks],
                "matrix": comparison_matrix,
                "generated_at": now_cst().isoformat()
            }

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
            traceback.print_exc()
            return error_response("对比报告生成失败，请稍后重试")
