from flask import request
from backend.models.models import (
    Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase,
    ReportMetricStats, ReportComparisonMatrix, Task,
    ReportStatus, ReportType, TaskStatus
)
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.error_codes import ErrorCode
from backend.utils.web.log_handler import log_and_emit
from backend.schemas.report import SecondaryCompareRequest
from backend.schemas.common import IdData
from backend.controllers.report_controller_base import ReportControllerBase
from backend.app import socketio
from backend.utils.common.query_utils import now_cst
import json
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor

_secondary_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='secondary_compare')
_generating_secondary = {}
_generating_secondary_lock = threading.Lock()


class ReportControllerSecondary(ReportControllerBase):

    @staticmethod
    def _validate_reports(report_ids):
        """验证报告存在且至少2个，返回报告列表"""
        reports = Report.query.filter(Report.id.in_(report_ids)).order_by(Report.created_at.asc()).all()
        if len(reports) < 2:
            return None, "二次对比至少需要两个报告"
        return reports, None

    @staticmethod
    def _load_report_snapshots(reports):
        """批量加载报告快照数据，返回聚合后的数据"""
        report_ids = [r.id for r in reports]

        # 批量查询所有快照表
        all_cases = ReportCase.query.filter(ReportCase.report_id.in_(report_ids)).all()
        all_metric_stats = ReportMetricStats.query.filter(ReportMetricStats.report_id.in_(report_ids)).all()
        all_raw_data = ReportRawData.query.filter(ReportRawData.report_id.in_(report_ids)).all()
        all_summaries = ReportSummary.query.filter(ReportSummary.report_id.in_(report_ids)).all()
        all_summary_metas = ReportSummaryMeta.query.filter(ReportSummaryMeta.report_id.in_(report_ids)).all()

        # 按 report_id 索引
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
    def _merge_cases_from_snapshots(reports, snapshots, report_id_to_task_id):
        """从快照合并 cases，给每条 case 标注来源 report_id/task_id"""
        merged_cases = []
        for report in reports:
            case_records = snapshots['cases_by_report'].get(report.id, [])
            task_id = report_id_to_task_id.get(report.id)
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
                    "source_task_id": task_id
                }
                merged_cases.append(case_item)
        return merged_cases

    @staticmethod
    def _merge_metric_data(reports, snapshots):
        """合并 metric_data，每个来源标注 report_id"""
        merged = []
        for report in reports:
            ms = snapshots['metric_stats_map'].get(report.id)
            if ms and ms.metric_data:
                data = ms.metric_data
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            item['source_report_id'] = report.id
                        merged.append(item)
                elif isinstance(data, dict):
                    for key, value in data.items():
                        merged.append({'source_report_id': report.id, 'key': key, 'value': value})
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
        """合并 case_type_stats"""
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
                # resources 可能是逗号分隔的字符串
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

        if not merged_categories:
            merged_categories = [{"id": "default_group", "name": "无分组"}]
        if not merged_tags:
            merged_tags = [{"id": "default_tag", "name": "无标签"}]

        return merged_categories, merged_tags

    @staticmethod
    def _build_comparison_matrix_from_snapshots(reports, snapshots, merged_cases):
        """从快照 cases 的 metrics 构建对比矩阵，不查 TestResult"""
        # 收集所有维度名
        all_metric_names = set()
        case_map = {}  # case_id → {case_name, metrics: {resource: {dim_name: value}}}

        for case_item in merged_cases:
            case_id = case_item['id']
            if case_id not in case_map:
                case_map[case_id] = {
                    "case_id": case_id,
                    "case_name": case_item['name']
                }
            metrics = case_item.get('metrics')
            if not metrics:
                continue
            # metrics 可能是 {resource: {dim_name: value}} 或 list 格式
            if isinstance(metrics, dict):
                for resource, dim_values in metrics.items():
                    if not isinstance(dim_values, dict):
                        # metrics 可能是 {dim_name: value} 直接结构
                        all_metric_names.add(resource)
                        if resource not in case_map[case_id]:
                            case_map[case_id][resource] = dim_values
                        continue
                    for dim_name, dim_value in dim_values.items():
                        all_metric_names.add(dim_name)
                    # 存储 resource → dim_values
                    case_map[case_id].setdefault('resources', {})[resource] = dim_values
            elif isinstance(metrics, list):
                for m_item in metrics:
                    if isinstance(m_item, dict):
                        resource = m_item.get('resource', 'default')
                        for dm in m_item.get('metrics', []):
                            if isinstance(dm, dict):
                                all_metric_names.add(dm.get('metric', ''))
                                case_map[case_id].setdefault('resources', {}).setdefault(resource, {})[dm.get('metric', '')] = dm.get('value', 0)

        # 构建矩阵：每个 report/task 一列
        matrix = {}
        report_ids = [r.id for r in reports]
        report_id_to_task_id = {}
        for report in reports:
            if report.task_id:
                report_id_to_task_id[report.id] = report.task_id

        for case_id, case_info in case_map.items():
            row = {
                "case_id": case_id,
                "case_name": case_info["case_name"]
            }
            # 为每个 report 构建一列
            for report in reports:
                col_key = f"report_{report.id}"
                dim_values = {}
                resources_data = case_info.get('resources', {})
                # 聚合该 report 下所有 resource 的维度值取平均
                dim_sums = {}
                dim_counts = {}
                for res_name, res_dims in resources_data.items():
                    if isinstance(res_dims, dict):
                        for dn, dv in res_dims.items():
                            dim_sums[dn] = dim_sums.get(dn, 0) + (dv or 0)
                            dim_counts[dn] = dim_counts.get(dn, 0) + 1
                for dn in all_metric_names:
                    if dn in dim_sums and dim_counts[dn] > 0:
                        dim_values[dn] = dim_sums[dn] / dim_counts[dn]
                    else:
                        dim_values[dn] = 0
                row[col_key] = {
                    "status": "completed",
                    "values": dim_values
                }
            matrix[case_id] = row

        return {
            "report_ids": [r.id for r in reports],
            "report_names": [r.name for r in reports],
            "matrix": matrix,
            "generated_at": now_cst().isoformat()
        }

    @staticmethod
    def _get_task_ids_from_reports(reports):
        """从报告列表提取 task_id 映射"""
        report_id_to_task_id = {}
        task_ids = []
        for report in reports:
            if report.task_id:
                report_id_to_task_id[report.id] = report.task_id
                if report.task_id not in task_ids:
                    task_ids.append(report.task_id)
        return report_id_to_task_id, task_ids

    @staticmethod
    def _create_secondary_report_records(
        new_report_id, report_ids, reports,
        case_categories_list, case_tags_list,
        devices_list, apis_list, resources, resource_headers, all_metrics,
        raw_data, metric_data, tag_metric_data, case_type_stats,
        device_stats, api_stats, source_cases, comparison_matrix_data,
        total_cases, completed_cases, failed_cases, success_rate,
        field_mappings
    ):
        summary_info = ReportSummary(
            report_id=new_report_id,
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
            all_metrics=json.dumps(all_metrics, ensure_ascii=False),
            field_mappings=json.dumps(field_mappings, ensure_ascii=False)
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

                # 1. 验证报告
                reports, error = ReportControllerSecondary._validate_reports(report_ids)
                if error:
                    with _generating_secondary_lock:
                        _generating_secondary.pop(report_key, None)
                    socketio.emit('secondary_compare_generated', {
                        'reportIds': report_ids,
                        'success': False,
                        'error': error
                    })
                    return

                # 2. 加载所有报告快照
                snapshots = ReportControllerSecondary._load_report_snapshots(reports)

                # 3. 从快照聚合数据
                report_id_to_task_id, task_ids = ReportControllerSecondary._get_task_ids_from_reports(reports)

                source_cases = ReportControllerSecondary._merge_cases_from_snapshots(reports, snapshots, report_id_to_task_id)
                if not source_cases:
                    with _generating_secondary_lock:
                        _generating_secondary.pop(report_key, None)
                    socketio.emit('secondary_compare_generated', {
                        'reportIds': report_ids,
                        'success': False,
                        'error': '未找到报告用例数据'
                    })
                    return

                metric_data = ReportControllerSecondary._merge_metric_data(reports, snapshots)
                tag_metric_data = ReportControllerSecondary._merge_tag_metric_data(reports, snapshots)
                raw_data = ReportControllerSecondary._merge_raw_data(reports, snapshots)
                device_stats, api_stats = ReportControllerSecondary._merge_device_api_stats(reports, snapshots)
                case_type_stats = ReportControllerSecondary._merge_case_type_stats(reports, snapshots)
                devices_list, apis_list = ReportControllerSecondary._merge_devices_apis(reports, snapshots)
                resources = ReportControllerSecondary._merge_resources(reports, snapshots)
                resource_headers = ReportControllerSecondary._merge_resource_headers(reports, snapshots)
                all_metrics = ReportControllerSecondary._merge_all_metrics(reports, snapshots)
                field_mappings = ReportControllerSecondary._merge_field_mappings(reports, snapshots)
                case_categories_list, case_tags_list = ReportControllerSecondary._merge_case_categories_and_tags(reports, snapshots)

                if not devices_list and not apis_list:
                    with _generating_secondary_lock:
                        _generating_secondary.pop(report_key, None)
                    socketio.emit('secondary_compare_generated', {
                        'reportIds': report_ids,
                        'success': False,
                        'error': '未找到设备或API资源数据'
                    })
                    return

                # 4. 从快照构建对比矩阵
                comparison_matrix_data = ReportControllerSecondary._build_comparison_matrix_from_snapshots(
                    reports, snapshots, source_cases
                )

                # 5. 聚合汇总数据（从各报告的 ReportSummary 快照累加）
                total_cases = 0
                completed_cases = 0
                failed_cases = 0
                for report in reports:
                    s = snapshots['summary_map'].get(report.id)
                    if s:
                        total_cases += s.total_cases or 0
                        completed_cases += s.completed_cases or 0
                        failed_cases += s.failed_cases or 0
                success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

                # 6. 创建报告记录
                name = f"二次对比报告_{now_cst().strftime('%Y%m%d%H%M%S')}"
                new_report = Report(
                    name=name,
                    type=ReportType.SECONDARY_COMPARISON.value,
                    description=description,
                    status=ReportStatus.DRAFT.value
                )
                db.session.add(new_report)
                db.session.flush()

                ReportControllerSecondary._create_secondary_report_records(
                    new_report.id, report_ids, reports,
                    case_categories_list, case_tags_list,
                    devices_list, apis_list, resources, resource_headers, all_metrics,
                    raw_data, metric_data, tag_metric_data, case_type_stats,
                    device_stats, api_stats, source_cases, comparison_matrix_data,
                    total_cases, completed_cases, failed_cases, success_rate,
                    field_mappings
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
