from flask import request, send_file, current_app
from backend.models.models import Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase, ReportMetricStats, ReportComparisonMatrix, Task, Audio
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.log_handler import log_not_emit
from backend.utils.report.report_utils import ReportUtils
from backend.utils.common.query_utils import escape_like_pattern, sanitize_keyword, normalize_sort_field, normalize_sort_order, now_cst
from backend.utils.common.result_data_store import load_full_result_data
from backend.schemas.report import ReportDetailData, ReportListData, ReportListItem, ReportListItemSummary, ReportSummarySimplified, ReportListQuery, ReportCaseListQuery, ReportSearchCasesRequest
from datetime import datetime
from sqlalchemy.orm import joinedload, load_only
import os
import zipfile
import json
import io

class ReportControllerBase:
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
        from backend.models.models import Audio, PlaybackDevice, Device
        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor

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
        from backend.models.models import TestResultDimension
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
        if not report:
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
        if not report:
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
            expanded_algo = ReportControllerBase._expand_algorithm_results_for_report(
                raw_algo_results, case.algorithm_type
            )
            expanded_ref = ReportControllerBase._expand_reference_params_for_report(raw_ref_params)
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
        from backend.utils.web.log_handler import log_and_emit
        from backend.models.models import TestResult, TaskMergeRelation
        from flask import Response, stream_with_context

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

            response = Response(
                stream_with_context(generate()),
                mimetype='application/zip',
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
        from backend.utils.algorithm.reference_params_generator import ReferenceParamsGenerator
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
            expanded_algo = ReportControllerBase._expand_algorithm_results_for_report(
                raw_algo_results, case.algorithm_type
            )
            expanded_ref = ReportControllerBase._expand_reference_params_for_report(raw_ref_params)
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
