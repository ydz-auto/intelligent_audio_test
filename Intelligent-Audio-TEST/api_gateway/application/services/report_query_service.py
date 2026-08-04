from api_gateway.infrastructure.request_adapter import request
from fastapi.responses import FileResponse, StreamingResponse
from shared.models.models import (
    Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase,
    ReportMetricStats, ReportComparisonMatrix, Task, TestResult, TestResultDimension,
    Dimension, TestCase, Audio, Device, API, TaskCase, TaskDevice, TaskAPI,
    ReportStatus, ReportType, TaskStatus,
)
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.error_codes import ErrorCode
from shared.utils.log_handler import log_not_emit, log_and_emit
from shared.utils.report.report_utils import ReportUtils
from shared.utils.report.report_query_builder import ReportQueryBuilder
from shared.utils.query_utils import (
    escape_like_pattern, sanitize_keyword, normalize_sort_field,
    normalize_sort_order, now_cst,
)
from shared.utils.result_data_store import load_full_result_data
from shared.infrastructure.storage import storage
from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
from api_gateway.schemas.report import (
    ReportDetailData, ReportListData, ReportListItem, ReportListItemSummary,
    ReportSummarySimplified, ReportListQuery, ReportCaseListQuery,
    ReportSearchCasesRequest, ReportExportRequest, GetCaseAveragesRequest,
)
from datetime import datetime
from sqlalchemy.orm import joinedload, load_only
from sqlalchemy import or_
import os
import zipfile
import json
import io
import pandas as pd


class ReportQueryService:
    """报告查询读侧 Service（CQRS Query Side）。

    承载 ReportController 家族中所有只读查询方法与公共辅助方法，
    保持原有逻辑不变，只是从 controller 搬运到 service。
    """

    # ------------------------------------------------------------------
    # 公共辅助方法（原 ReportControllerBase）
    # ------------------------------------------------------------------

    # 公共函数：根据参数键名推断 param_type
    @staticmethod
    def _infer_param_type(param_key: str) -> str:
        key_lower = param_key.lower()
        if 'rttm' in key_lower:
            return 'rttm'
        if 'stm' in key_lower:
            return 'stm'
        if 'audio' in key_lower:
            return 'audio'
        return 'text'

    # 公共函数：构建报告音频列表（统一 task 和 compare 两种模式）
    @staticmethod
    def _build_audios_list(test_case, mode='task'):
        """
        构建 audios_list，支持两种字段命名模式：
        - mode='task':  使用 playback_device_id / playbackDeviceName / testType
        - mode='compare': 使用 device_id / device_name / audio_type
        """
        from shared.models.models import Audio, PlaybackDevice, Device
        from shared.algorithm.case_parameter_extractor import CaseParameterExtractor

        config = test_case.config or {}
        rounds = config.get('rounds', [])
        if not rounds:
            return []

        audios_list = []
        is_compare = (mode == 'compare')

        # 字段名映射
        if is_compare:
            dev_id_key = 'device_id'
            dev_name_key = 'device_name'
            type_key = 'audio_type'
            url_tmpl = '/api/v1/audios/{id}/stream'
            noise_spl_key = 'noise_spl'
            play_order_key = 'play_order'
        else:
            dev_id_key = 'playback_device_id'
            dev_name_key = 'playbackDeviceName'
            type_key = 'testType'
            url_tmpl = '/api/audios/play/{id}'
            noise_spl_key = 'spl'
            play_order_key = 'play_order'

        # 收集所有轮的设备 ID
        all_device_ids = set()
        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue
            for audio_cfg in round_item.get('audios', []):
                dev_id = audio_cfg.get(dev_id_key)
                if dev_id and dev_id != '':
                    all_device_ids.add(dev_id)
            if not is_compare:
                bg_noise = round_item.get('backgroundNoise') or {}
                noise_dev = bg_noise.get(dev_id_key)
                if noise_dev and noise_dev != '':
                    all_device_ids.add(noise_dev)

        devices = {}
        if all_device_ids:
            if is_compare:
                device_list = Device.query.filter(Device.id.in_(list(all_device_ids))).all()
            else:
                device_list = PlaybackDevice.query.filter(PlaybackDevice.id.in_(list(all_device_ids))).all()
            devices = {d.id: d.name for d in device_list}

        tc_test_type = test_case.test_type or 'api'

        per_round_dry = []
        noise_audios = []
        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue
            round_number = round_item.get('roundNumber') or round_item.get('round_number') or 1
            round_dry = []

            for audio_cfg in round_item.get('audios', []):
                audio_id = audio_cfg.get('audio_id')
                if audio_id:
                    audio = db.session.get(Audio, audio_id)
                    if audio:
                        dev_id = audio_cfg.get(dev_id_key)
                        if dev_id == '':
                            dev_id = None
                        audio_item = {
                            type_key: tc_test_type,
                            "id": audio.id,
                            "filename": audio.original_filename or audio.name,
                            "duration": audio.duration,
                            "url": url_tmpl.format(id=audio.id),
                            "spl": audio_cfg.get('spl'),
                            "play_order" if is_compare else "playOrder": audio_cfg.get('play_order'),
                            dev_id_key if is_compare else "playbackDeviceId": dev_id,
                            dev_name_key if is_compare else "playbackDeviceName": devices.get(dev_id) if dev_id else None,
                            "label": audio_cfg.get('label') if not is_compare else None,
                            "roundNumber": round_number,
                        }
                        # 移除 None 值的 label 键（compare 模式不加 label）
                        if is_compare:
                            audio_item.pop('label', None)
                        audios_list.append(audio_item)
                        round_dry.append(audio_item)

            # 噪声
            background_noise = round_item.get('backgroundNoise') or {}
            if background_noise.get('audio_id'):
                noise_audio = db.session.get(Audio, background_noise['audio_id'])
                if noise_audio:
                    noise_item = {
                        type_key: "noise",
                        "id": noise_audio.id,
                        "filename": noise_audio.name,
                        "duration": noise_audio.duration,
                        "url": url_tmpl.format(id=noise_audio.id),
                        noise_spl_key: background_noise.get('spl'),
                        "roundNumber": round_number,
                    }
                    if not is_compare:
                        noise_item["playOrder"] = None
                        noise_item["playbackDeviceId"] = None
                        noise_item["playbackDeviceName"] = None
                        noise_item["label"] = None
                    noise_audios.append(noise_item)

            if is_compare:
                audios_list.extend(round_dry)
            per_round_dry.append(round_dry)

        # 每轮内部排序
        sort_key = play_order_key if is_compare else 'playOrder'
        for round_dry in per_round_dry:
            round_dry.sort(key=lambda x: (x.get(sort_key) is None, x.get(sort_key) or 999))

        # 获取 overlap 参数（取首轮配置）
        first_round = rounds[0] if rounds else {}
        overlap_config = {
            'algorithm_params': first_round.get('algorithmParams', {}) if isinstance(first_round, dict) else {}
        }
        overlap_time = CaseParameterExtractor.get_overlap_time(overlap_config) if overlap_config else 0
        overlap_rate = CaseParameterExtractor.get_overlap_rate(overlap_config) if overlap_config else 0

        # 按轮次计算 timeline
        global_offset = 0
        for round_dry in per_round_dry:
            prev_end_time = 0
            for i, audio_item in enumerate(round_dry):
                duration = audio_item.get('duration') or 0
                if i == 0:
                    timeline_start = global_offset
                else:
                    if overlap_time and overlap_time > 0:
                        timeline_start = prev_end_time - overlap_time
                        if timeline_start < global_offset:
                            timeline_start = global_offset
                    elif overlap_rate is not None and overlap_rate > 0:
                        elapsed = prev_end_time - global_offset
                        timeline_start = global_offset + elapsed * (1 - overlap_rate)
                    else:
                        timeline_start = prev_end_time
                audio_item['timelineStart'] = round(timeline_start, 3)
                audio_item['timelineEnd'] = round(timeline_start + duration, 3)
                prev_end_time = timeline_start + duration
            global_offset = prev_end_time

        for noise_item in noise_audios:
            noise_item['timelineStart'] = 0
            noise_item['timelineEnd'] = round(noise_item.get('duration') or 0, 3)

        audios_list.extend(noise_audios)
        return audios_list

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
        from shared.models.models import TestResultDimension
        dim_values = {}

        if all_dimensions is None:
            log_not_emit('ERROR', 'report_controller_base', f'all_dimensions is None in extract_dimension_values for result {result_id}', category='report')
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
        tc_test_type = test_case.test_type or 'api'

        # 如果指定了类型且不匹配记录类型，直接返回空
        if test_type is not None and test_type != tc_test_type:
            return results

        for audio_cfg in test_audios:
            audio_id = audio_cfg.get('audio_id')
            if audio_id:
                audio = db.session.get(Audio, audio_id)
                if audio:
                    results.append({
                        "id": audio.id,
                        "filename": audio.original_filename or audio.name,
                        "duration": audio.duration,
                        "url": f"/api/v1/audios/{audio.id}/stream",
                        "test_type": tc_test_type
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

    # ------------------------------------------------------------------
    # 查询方法（原 ReportControllerBase）
    # ------------------------------------------------------------------

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

        query = Report.query.filter(Report.deleted == False)

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

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        reports = pagination.items

        report_ids = [r.id for r in reports]
        summaries_map = {}
        if report_ids:
            summaries = db.session.query(
                ReportSummary.report_id,
                ReportSummary.total_cases,
                ReportSummary.completed_cases,
                ReportSummary.failed_cases,
                ReportSummary.pass_rate
            ).filter(ReportSummary.report_id.in_(report_ids)).all()
            summaries_map = {s.report_id: s for s in summaries}

        data = []
        for report in reports:
            task = report.task
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
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
            )
        )

    # 获取单个测试报告详情
    @staticmethod
    def get_one(report_id):
        report = db.session.get(Report, report_id)
        if not report or report.deleted:
            return error_response("未找到测试报告", 404)

        task = db.session.get(Task, report.task_id) if report.task_id else None

        summary_info = ReportSummary.query.filter_by(report_id=report.id).first()
        summary_meta = ReportSummaryMeta.query.filter_by(report_id=report.id).first()
        raw_data = ReportRawData.query.filter_by(report_id=report.id).first()
        metric_stats = ReportMetricStats.query.filter_by(report_id=report.id).first()

        if not summary_info:
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
            "raw_data": to_json(raw_data.raw_data) if raw_data else [],
            "case_categories": to_json(summary_meta.case_categories) if summary_meta else [],
            "all_case_tags": to_json(summary_meta.all_case_tags) if summary_meta else [],
            "resources": to_json(summary_meta.resources) if summary_meta else [],
            "resource_headers": to_json(summary_meta.resource_headers) if summary_meta else [],
            "all_metrics": to_json(summary_meta.all_metrics) if summary_meta else [],
            "device_stats": to_json(metric_stats.device_stats) if metric_stats else [],
            "api_stats": to_json(metric_stats.api_stats) if metric_stats else [],
            "case_type_stats": to_json(metric_stats.case_type_stats) if metric_stats else [],
            "devices": to_json(summary_meta.devices) if summary_meta else [],
            "apis": to_json(summary_meta.apis) if summary_meta else [],
            "metric_data": to_json(metric_stats.metric_data) if metric_stats else {},
            "tag_metric_data": to_json(metric_stats.tag_metric_data) if metric_stats else {},
            "total_cases": summary_info.total_cases or 0,
            "completed_cases": summary_info.completed_cases or 0,
            "failed_cases": summary_info.failed_cases or 0
        }

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
        if not report or report.deleted:
            return error_response("未找到测试报告", 404)

        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = ReportCaseListQuery.model_validate(query_params_dict)

        query = ReportCase.query.filter_by(report_id=report.id)

        keyword = query_params.keyword
        category = query_params.category
        tags = query_params.tags if query_params.tags else []

        if not tags:
            tags_csv = request.args.get('tags')
            if tags_csv:
                tags = [t.strip() for t in str(tags_csv).split(',') if t.strip()]

        if keyword:
            kw = str(keyword).lower()
            query = query.filter(
                db.or_(
                    db.func.lower(ReportCase.name).contains(kw),
                    db.func.lower(ReportCase.description).contains(kw)
                )
            )

        if category:
            query = query.filter(ReportCase.category == str(category))

        if tags:
            for tag in tags:
                query = query.filter(ReportCase.tags.contains([tag]))

        page = query_params.page
        per_page = query_params.per_page

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        items = []
        for case in paginated.items:
            # 对 voice_llm 多轮场景做 question/answer 展开 + 参考参数多轮展开
            raw_algo_results = case.algorithm_results
            raw_ref_params = case.reference_params
            expanded_algo = ReportQueryService._expand_algorithm_results_for_report(
                raw_algo_results, case.algorithm_type
            )
            expanded_ref = ReportQueryService._expand_reference_params_for_report(raw_ref_params)
            items.append({
                "id": case.test_case_id,
                "name": case.name,
                "description": case.description or "",
                "category": case.category,
                "tags": case.tags or [],
                "metrics": case.metrics or {},
                "results": case.results or [],
                "audios": case.audios or [],
                "referenceParams": expanded_ref,
                "algorithmResults": expanded_algo,
                "algorithmType": case.algorithm_type,
                "logs": case.logs
            })

        return success_response({
            "items": items,
            "total": paginated.total,
            "page": page,
            "perPage": per_page,
            "pages": paginated.pages
        })

    @staticmethod
    def download_case_logs(report_id, case_id):
        from shared.models.models import TestResult, TaskMergeRelation

        log_and_emit(
            level='INFO',
            module='report',
            content=f'开始下载用例日志 - report_id: {report_id}, case_id: {case_id}'
        )

        report = db.session.get(Report, report_id)
        if not report or report.deleted:
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
                    # OSS: 列出 case-result bucket 下 {task_id}/{case_id}/ 的所有文件
                    oss_prefix = f'{search_task_id}/{case_id}/'
                    try:
                        oss_keys = storage.list_objects('case_result', prefix=oss_prefix)
                    except Exception:
                        oss_keys = []
                    if oss_keys:
                        found_any = True
                        for oss_key in oss_keys:
                            # 下载文件内容
                            try:
                                file_data = storage.load_bytes(f'case_result/{oss_key}')
                                arcname = oss_key[len(oss_prefix):]  # 去掉前缀
                                if len(task_ids_to_search) > 1:
                                    arcname = os.path.join(f"task_{search_task_id}", arcname)
                                zf.writestr(arcname, file_data)
                            except Exception:
                                continue

                full_data = load_full_result_data(test_result.result_data, getattr(test_result, 'result_data_path', None)) if test_result else {}
                if test_result and full_data and 'adjusted_reference_params' in full_data:
                    adjusted_params = full_data['adjusted_reference_params']
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
            total_size = len(zip_data)

            CHUNK_SIZE = 64 * 1024

            def generate():
                offset = 0
                while offset < total_size:
                    yield zip_data[offset:offset + CHUNK_SIZE]
                    offset += CHUNK_SIZE

            response = StreamingResponse(
                generate(),
                media_type='application/zip',
                headers={
                    'Content-Disposition': f'attachment; filename*=UTF-8\'\'{zip_filename}',
                    'Content-Length': str(total_size),
                    'X-Content-Type-Options': 'nosniff',
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
            log_and_emit(
                level='INFO',
                module='report',
                content=f'用例日志下载成功 - report_id: {report_id}, case_id: {case_id}, size: {total_size}'
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
    def _expand_algorithm_results_for_report(algorithm_results, algorithm_type=None):
        """
        报告页 algorithm_results 后处理：
        对 voice_llm 多轮场景，把 rounds 数组展开成 question@round:N / answer@round:N 文本字段
        兼容 camelCase / snake_case 字段命名
        """
        import logging
        log = logging.getLogger(__name__)
        if not isinstance(algorithm_results, list):
            return algorithm_results
        # 找到 rounds 字段
        rounds_item = None
        for item in algorithm_results:
            if not isinstance(item, dict):
                continue
            code = item.get('paramCode') or item.get('param_code')
            if code == 'rounds':
                rounds_item = item
                break
        if not rounds_item:
            log.warning('[expand_algo] no rounds item found, count=%d', len(algorithm_results))
            return algorithm_results
        rounds_value = rounds_item.get('value')
        log.warning('[expand_algo] rounds_item found, value type=%s, is_list=%s, len=%s',
                    type(rounds_value).__name__, isinstance(rounds_value, list),
                    len(rounds_value) if isinstance(rounds_value, list) else 'N/A')
        if not isinstance(rounds_value, list) or not rounds_value:
            return algorithm_results

        # 构建展开后的新列表：保留非 rounds 字段，rounds 替换为 question@round:N/answer@round:N
        expanded = []
        device = rounds_item.get('device', 'default')
        for item in algorithm_results:
            if item is rounds_item:
                continue
            expanded.append(item)

        for r_idx, r_item in enumerate(rounds_value):
            if not isinstance(r_item, dict):
                continue
            raw_round = r_item.get('roundNumber')
            if raw_round is None:
                raw_round = r_item.get('round')
            rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
            output = r_item.get('output') or {}
            for sub_key in ('question', 'answer'):
                val = output.get(sub_key)
                if val:
                    expanded.append({
                        'device': device,
                        'param_code': f'{sub_key}@round:{rn}',
                        'paramCode': f'{sub_key}@round:{rn}',
                        'param_type': 'text',
                        'paramType': 'text',
                        'label': f'{sub_key} (第{rn}轮)',
                        'value': val,
                        'round_number': rn,
                        'roundNumber': rn,
                    })
        # rounds 整体保留（标记为 json）
        rounds_item_copy = dict(rounds_item)
        rounds_item_copy['param_type'] = 'json'
        rounds_item_copy['paramType'] = 'json'
        expanded.append(rounds_item_copy)
        return expanded

    @staticmethod
    def _expand_reference_params_for_report(reference_params):
        """
        报告页 reference_params 后处理：
        调用 ReferenceParamsGenerator.get_reference_params_for_report 做多轮展开
        兼容 reference_params 是字典（已经是报告格式）或 DB 原始列格式
        """
        if not reference_params:
            return {}
        from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
        try:
            # 如果已经是扁平字典格式（code -> {code, type, value}），直接原样返回
            # 这种格式在老报告 DB 中已存为 {query: {...}, correct_answer: {...}}
            if isinstance(reference_params, dict):
                # 判断是否是 reference_params_col 格式（list of {round_number, reference_params_path}）
                if any(isinstance(v, dict) and ('reference_params_path' in v or 'referenceParamsPath' in v) for v in reference_params.values()):
                    return ReferenceParamsGenerator.get_reference_params_for_report(reference_params)
                # 已经是展开后的字典格式（每个 value 是 {code, type, value}）或含 round_number 多轮格式
                # 直接原样返回
                return reference_params
            if isinstance(reference_params, list):
                return ReferenceParamsGenerator.get_reference_params_for_report(reference_params)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f'_expand_reference_params_for_report failed: {e}', exc_info=True)
        return reference_params

    @staticmethod
    def search_report_cases(report_id):
        report = db.session.get(Report, report_id)
        if not report or report.deleted:
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

        query = ReportCase.query.filter_by(report_id=report.id)

        if keyword:
            kw = str(keyword).lower()
            query = query.filter(
                db.or_(
                    db.func.lower(ReportCase.name).contains(kw),
                    db.func.lower(ReportCase.description).contains(kw)
                )
            )

        if category:
            query = query.filter(ReportCase.category == str(category))

        if tags or include_untagged:
            tag_set = set(str(t) for t in tags)
            if include_untagged and not tag_set:
                query = query.filter(
                    db.or_(
                        ReportCase.tags == None,
                        ReportCase.tags == [],
                        db.func.json_length(ReportCase.tags) == 0
                    )
                )
            elif tag_set:
                for tag in tags:
                    query = query.filter(ReportCase.tags.contains([tag]))

        page = data.page
        per_page = data.per_page
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = 20

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        items = []
        for case in paginated.items:
            # 对 voice_llm 多轮场景做 question/answer 展开 + 参考参数多轮展开
            raw_algo_results = case.algorithm_results
            raw_ref_params = case.reference_params
            expanded_algo = ReportQueryService._expand_algorithm_results_for_report(
                raw_algo_results, case.algorithm_type
            )
            expanded_ref = ReportQueryService._expand_reference_params_for_report(raw_ref_params)
            items.append({
                "id": case.test_case_id,
                "name": case.name,
                "description": case.description or "",
                "category": case.category,
                "tags": case.tags or [],
                "metrics": case.metrics or {},
                "results": case.results or [],
                "audios": case.audios or [],
                "referenceParams": expanded_ref,
                "algorithmResults": expanded_algo,
                "algorithmType": case.algorithm_type,
                "logs": case.logs
            })

        return success_response({
            "items": items,
            "total": paginated.total,
            "page": page,
            "perPage": per_page,
            "pages": paginated.pages
        })

    # ------------------------------------------------------------------
    # 导出查询（原 ReportController）
    # ------------------------------------------------------------------

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
            reports = Report.query.filter(Report.id.in_(report_ids), Report.deleted == False).all()
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

                filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.xlsx"
                return FileResponse(
                    output,
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
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

                filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.pdf"
                return FileResponse(
                    output,
                    media_type='application/pdf',
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
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

                filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.csv"
                return StreamingResponse(
                    generate(),
                    media_type='text/csv',
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return error_response("导出报告失败，请稍后重试")

    # ------------------------------------------------------------------
    # 按分组和标签获取用例平均值（原 ReportController）
    # ------------------------------------------------------------------

    @staticmethod
    def _query_test_cases_and_results(task_id_filter, result_task_filter,
                                       category, categories, tags, include_untagged):
        from shared.models.models import TestCaseGroup, Tag

        if isinstance(task_id_filter, list):
            task_cases = TaskCase.query.filter(TaskCase.task_id.in_(task_id_filter)).all()
        else:
            task_cases = TaskCase.query.filter_by(task_id=task_id_filter).all()

        test_case_ids = [tc.test_case_id for tc in task_cases]
        query = TestCase.query.filter(TestCase.id.in_(test_case_ids))

        if category and category != 'all':
            query = query.filter(TestCase.group.has(name=category))
        if categories and len(categories) > 0:
            query = query.filter(TestCase.group.has(TestCaseGroup.name.in_(categories)))
        if include_untagged:
            if tags and len(tags) > 0:
                query = query.filter(or_(TestCase.tags.any(Tag.name.in_(tags)), ~TestCase.tags.any()))
            else:
                query = query.filter(~TestCase.tags.any())
        elif tags and len(tags) > 0:
            query = query.join(TestCase.tags).filter(Tag.name.in_(tags))

        test_cases = query.all()
        filtered_case_ids = [case.id for case in test_cases]

        if isinstance(result_task_filter, list):
            test_results = TestResult.query.filter(
                TestResult.test_case_id.in_(filtered_case_ids),
                TestResult.task_id.in_(result_task_filter)
            ).all()
        else:
            test_results = TestResult.query.filter(
                TestResult.test_case_id.in_(filtered_case_ids),
                TestResult.task_id == result_task_filter
            ).all()

        return filtered_case_ids, test_results

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

            from shared.models.models import TaskMergeRelation

            if task.type == 'merged':
                merge_relations = TaskMergeRelation.query.filter_by(merged_task_id=task_id).all()
                if merge_relations:
                    source_task_ids = [r.source_task_id for r in merge_relations]
                    task_id_filter = source_task_ids
                    result_task_filter = source_task_ids
                else:
                    task_id_filter = task_id
                    result_task_filter = task_id
            else:
                task_id_filter = task_id
                result_task_filter = task_id

            filtered_case_ids, test_results = ReportQueryService._query_test_cases_and_results(
                task_id_filter, result_task_filter,
                category, categories, tags, include_untagged
            )

            all_dimensions_all = Dimension.query.filter_by(status=True, deleted=False).all()
            used_dim_ids = set()
            res_ids = [r.id for r in test_results]
            if res_ids:
                rows = db.session.query(TestResultDimension.dimension_id).filter(
                    TestResultDimension.test_result_id.in_(res_ids)
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

            # 有 output 参数但没有任何 visible=True 的维度 → 隐藏
            hidden_dim_ids = all_output_dim_ids - visible_dim_ids
            if hidden_dim_ids:
                all_dimensions = [d for d in all_dimensions if d.id not in hidden_dim_ids]
            metric_name_to_id = {str(dim.name): int(dim.id) for dim in all_dimensions if getattr(dim, "id", None) is not None and getattr(dim, "name", None) is not None}

            dimension_scores = {}
            dimension_counts = {}

            for result in test_results:
                dim_values = ReportQueryService.extract_dimension_values(result.id, all_dimensions)
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

            from shared.models.models import TaskDevice, Device, TaskAPI, API
            task_devices = TaskDevice.query.filter_by(task_id=task_id).all()
            task_apis = TaskAPI.query.filter_by(task_id=task_id).all()

            # 构建带时间前缀的资源列表
            time_prefix = ReportQueryService.get_task_time_prefix(task)
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
                resource = ReportQueryService.get_resource_name(result, task, use_time_prefix=False)
                if resource not in resources:
                    continue

                test_case = db.session.get(TestCase, result.test_case_id)
                if not test_case: continue

                cat_name = test_case.group.name if test_case.group else "未分类"

                if cat_name not in accumulator:
                    accumulator[cat_name] = {}
                if resource not in accumulator[cat_name]:
                    accumulator[cat_name][resource] = {dim.name: {'sum': 0, 'count': 0} for dim in all_dimensions}

                dim_values = ReportQueryService.extract_dimension_values(result.id, all_dimensions)
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

            normal_distribution_data = ReportQueryService.calculate_normal_distribution(raw_data)

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

    # ------------------------------------------------------------------
    # 对比报告查询辅助方法（原 ReportControllerCompare，只读部分）
    # ------------------------------------------------------------------

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
                resource = ReportQueryService.get_resource_name(res, task, use_time_prefix=True)
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

            reference_params_dict = ReportQueryService._build_reference_params(case_results, config)

            for result in case_results:
                task = tasks_map.get(result.task_id)
                resource = ReportUtils.get_resource_name(result, task, use_time_prefix=True)

                if not resource:
                    continue

                dim_values = ReportQueryService.extract_dimension_values(
                    result.id, all_dimensions, dim_results_map=dim_results_map
                )
                case_metrics[resource] = dim_values

            audios_list = ReportQueryService._build_audios_list(test_case, mode='compare')

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
                resource = ReportQueryService.get_resource_name(result, task, use_time_prefix=True)

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

    # ------------------------------------------------------------------
    # 二次对比报告查询辅助方法（原 ReportControllerSecondary，只读部分）
    # ------------------------------------------------------------------

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
                resource = ReportQueryService.get_resource_name(res, t, use_time_prefix=False)
                if resource:
                    resources.add(resource)

        if not resources:
            resources = {"默认资源"}
        resources = sorted(list(resources))

        devices_list, apis_list, device_ids, api_ids = ReportCommandService._get_task_resources(task_ids)

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

        if not all_dimensions:
            return None, None, "未找到评估维度数据"

        all_metrics = ReportCommandService._build_all_metrics(all_dimensions)
        return all_dimensions, all_metrics, None

    @staticmethod
    def _build_comparison_matrix_secondary(task_ids, reports, all_dimensions):
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
            "generated_at": now_cst().isoformat()
        }

    @staticmethod
    def _get_source_cases_from_reports(reports):
        source_cases = []
        for report in reports:
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
