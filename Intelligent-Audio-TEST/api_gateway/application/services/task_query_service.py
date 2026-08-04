import json
import logging
from datetime import datetime, timezone, timedelta

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import (
    Task, Tag, TaskCase, TaskDevice, TaskAPI, TestCase, TestResult,
    TestResultDimension, Log, Dimension,
)
from shared.models.database import db
from shared.utils.response import success_response, error_response, convert_keys_to_camel
from shared.utils.error_codes import ErrorCode
from shared.utils.log_handler import log_not_emit
# 跨服务调用：通过 gRPC ExecutionService 调用任务执行引擎
from api_gateway.infrastructure.grpc_proxies import (
    execution_engine, _ReevaluationExecutorProxy,
)
from shared.utils.result_data_store import load_full_result_data
from shared.infrastructure.storage import storage
from api_gateway.schemas.common import IdData, TaskStatusData
from api_gateway.schemas.task import (
    TaskApiBrief,
    TaskCaseBrief,
    TaskDetailData,
    TaskDeviceBrief,
    TaskListData,
    TaskListItem,
    TaskProgressCurrentCase,
    TaskProgressData,
    TaskReportItem,
    TaskReportsData,
    TaskStartData,
    TaskStatsData,
    TaskUpdateCasesData,
    TaskCreateRequest,
    TaskControlRequest,
    TaskUpdateCasesRequest,
    TaskBatchActionRequest,
    TaskMergeRequest,
)
from shared.utils.query_utils import now_cst
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)


class TaskQueryService:
    """任务查询读侧 Service（CQRS Query Side）。

    承载 TaskController 中所有只读查询方法，保持原有逻辑不变。
    """

    # 获取所有任务，支持分页和过滤
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status')
        type_ = request.args.get('type')
        algorithm_type = request.args.get('algorithm_type')
        search = request.args.get('search')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        query = Task.query.filter_by(deleted=False)
        if status:
            query = query.filter_by(status=status)
        if type_:
            query = query.filter_by(type=type_)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)
        if search:
            query = query.filter(
                db.or_(
                    Task.name.ilike(f'%{search}%'),
                    Task.id.cast(db.String).ilike(f'%{search}%')
                )
            )

        # 时间范围过滤
        if start_date:
            try:
                dt_start = datetime.fromisoformat(start_date)
                query = query.filter(Task.created_at >= dt_start)
            except ValueError:
                pass
        if end_date:
            try:
                dt_end = datetime.fromisoformat(end_date)
                query = query.filter(Task.created_at <= dt_end)
            except ValueError:
                pass

        query = query.order_by(Task.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        tasks = pagination.items

        data = []
        for task in tasks:
            # 查询任务关联的报告
            from shared.models.models import Report
            reports = Report.query.filter_by(task_id=task.id).all()

            # 构建报告信息
            report_info = TaskReportsData(
                count=len(reports),
                reports=[
                    TaskReportItem(
                        id=report.id,
                        name=report.name,
                        status=report.status,
                        type=report.type,
                        created_at=report.created_at.isoformat() if report.created_at else None,
                    )
                    for report in reports
                ],
            )

            # 获取关联设备详情
            devices = []
            for d in task.devices:
                devices.append(TaskDeviceBrief(id=d.id, name=d.name, status=d.status, model=d.model))

            # 获取关联 API 详情
            apis = []
            for a in task.apis:
                apis.append(TaskApiBrief(id=a.id, name=a.name, status=a.status))

            data.append(
                TaskListItem(
                    id=task.id,
                    name=task.name,
                    description=task.description,
                    status=task.status,
                    type=task.type,
                    config=convert_keys_to_camel(task.config) if task.config else {},
                    algorithm_type=task.algorithm_type,
                    algorithm_params=convert_keys_to_camel(task.algorithm_params) if task.algorithm_params else None,
                    started_at=task.started_at.isoformat() if task.started_at else None,
                    completed_at=task.completed_at.isoformat() if task.completed_at else None,
                    total_cases=task.total_cases,
                    case_count=task.total_cases,
                    device_count=len(devices),
                    completed_cases=task.completed_cases,
                    failed_cases=task.failed_cases,
                    tags=[tag.name for tag in task.tags],
                    created_at=task.created_at.isoformat() if task.created_at else None,
                    updated_at=task.updated_at.isoformat() if task.updated_at else None,
                    reports=report_info,
                    devices=devices,
                    apis=apis,
                )
            )

        return success_response(
            TaskListData(
                items=data,
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
            )
        )

    # 获取单个任务详情
    @staticmethod
    def get_one(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)

        # 获取关联用例详情
        cases = []
        task_cases = TaskCase.query.filter_by(task_id=task_id).all()
        for tc in task_cases:
            case_info = db.session.get(TestCase, tc.test_case_id)
            cases.append(
                TaskCaseBrief(
                    case_id=tc.test_case_id,
                    name=case_info.name if case_info else "未知用例",
                    status=tc.status,
                    execution_status=tc.execution_status,
                    evaluation_status=tc.evaluation_status,
                    started_at=tc.started_at.isoformat() if tc.started_at else None,
                    completed_at=tc.completed_at.isoformat() if tc.completed_at else None,
                    duration=tc.duration,
                    error_message=tc.error_message,
                )
            )

        # 获取关联设备详情
        devices = []
        for d in task.devices:
            devices.append(TaskDeviceBrief(id=d.id, name=d.name, status=d.status, model=d.model))

        # 获取关联 API 详情
        apis = []
        for a in task.apis:
            apis.append(TaskApiBrief(id=a.id, name=a.name, status=a.status))

        # 提前提取 tags，避免 calculate_time_estimate 调用后 task 脱离 session 导致 lazy load 失败
        tag_names = [tag.name for tag in task.tags]

        # 计算时间字段
        expected_total_time_str = None
        expected_complete_time_str = None
        used_time_str = None
        try:
            now = datetime.now(timezone(timedelta(hours=8)))
            tz_started = task.started_at.replace(tzinfo=timezone(timedelta(hours=8))) if task.started_at and not task.started_at.tzinfo else task.started_at

            if task.started_at:
                tz_completed = task.completed_at.replace(tzinfo=timezone(timedelta(hours=8))) if task.completed_at and not task.completed_at.tzinfo else task.completed_at
                if tz_completed:
                    elapsed_seconds = max(0.0, (tz_completed - tz_started).total_seconds())
                elif task.status in ('completed', 'failed') and task.updated_at:
                    # 已结束但 completed_at 缺失时，使用 updated_at 作为结束时间，避免时间持续增长
                    tz_updated = task.updated_at.replace(tzinfo=timezone(timedelta(hours=8))) if task.updated_at and not task.updated_at.tzinfo else task.updated_at
                    elapsed_seconds = max(0.0, (tz_updated - tz_started).total_seconds())
                else:
                    elapsed_seconds = max(0.0, (now - tz_started).total_seconds())

                def _format_duration(secs):
                    secs = int(secs)
                    if secs < 60:
                        return f"{secs}秒"
                    elif secs < 3600:
                        m = secs // 60
                        s = secs % 60
                        return f"{m}分钟" + (f"{s}秒" if s > 0 else "")
                    else:
                        h = secs // 3600
                        m = (secs % 3600) // 60
                        return f"{h}小时" + (f"{m}分钟" if m > 0 else "")

                used_time_str = _format_duration(elapsed_seconds)

                time_estimate = execution_engine.event_manager.calculate_time_estimate(task)
                estimated_total_seconds = time_estimate.get('expected_total_time', 0) or 0
                expected_total_time_str = _format_duration(estimated_total_seconds)

                if not tz_completed:
                    expected_complete_dt = now + timedelta(seconds=estimated_total_seconds)
                    expected_complete_time_str = expected_complete_dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    expected_complete_time_str = tz_completed.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logging.getLogger(__name__).warning(f"get_one: 计算时间字段失败: {e}")

        return success_response(
            TaskDetailData(
                id=task.id,
                name=task.name,
                description=task.description,
                status=task.status,
                type=task.type,
                config=convert_keys_to_camel(task.config) if task.config else {},
                algorithm_type=task.algorithm_type,
                algorithm_params=convert_keys_to_camel(task.algorithm_params) if task.algorithm_params else None,
                started_at=task.started_at.isoformat() if task.started_at else None,
                completed_at=task.completed_at.isoformat() if task.completed_at else None,
                expected_total_time=expected_total_time_str,
                expected_complete_time=expected_complete_time_str,
                used_time=used_time_str,
                total_cases=task.total_cases,
                case_count=task.total_cases,
                device_count=len(devices),
                completed_cases=task.completed_cases,
                failed_cases=task.failed_cases,
                tags=tag_names,
                cases=cases,
                devices=devices,
                apis=apis,
                created_at=task.created_at.isoformat() if task.created_at else None,
                updated_at=task.updated_at.isoformat() if task.updated_at else None,
            )
        )

    # 获取单个用例的执行详情 (包含指标，不含日志)
    @staticmethod
    def get_case_detail(task_id, case_id):
        # 1. 获取任务用例关联信息
        tc = TaskCase.query.filter_by(task_id=task_id, test_case_id=case_id).first()
        if not tc:
            return error_response("未找到该任务关联的用例", code=ErrorCode.NOT_FOUND, http_code=404)

        # 2. 获取基础用例信息
        case_info = db.session.get(TestCase, case_id)

        # 3. 获取测试类型（后续构建 reference_params 时需要）
        task = db.session.get(Task, task_id)
        test_type = task.type if task else 'api'

        # 4. 获取执行结果 (可能有多个设备/API的结果，这里取最新的一个或全部)
        results = TestResult.query.filter_by(task_id=task_id, test_case_id=case_id).all()

        processed_results = []
        for result in results:
            # 获取设备名称或 API 名称
            device_name = None
            api_name = None
            if result.device_id:
                from shared.models.models import Device
                device = db.session.get(Device, result.device_id)
                if device:
                    device_name = device.name

            if result.api_id:
                from shared.models.models import API
                api = db.session.get(API, result.api_id)
                if api:
                    api_name = api.name

            # 获取每个结果的维度得分
            dimensions = db.session.query(
                TestResultDimension, Dimension.name
            ).join(
                Dimension, TestResultDimension.dimension_id == Dimension.id
            ).filter(
                TestResultDimension.test_result_id == result.id
            ).all()

            dim_data = []
            for dim, dim_name in dimensions:
                dim_data.append({
                    "id": dim.id,
                    "name": dim_name,
                    "value": dim.dimension_value,
                    "score": dim.score,
                    "status": dim.status,
                    "evaluation_status": dim.evaluation_status,
                    "error_message": dim.error_message,
                    "round_number": getattr(dim, 'round_number', None)
                })

            full_result_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
            processed_results.append({
                "id": result.id,
                "device_id": result.device_id,
                "device_name": device_name,
                "api_id": result.api_id,
                "api_name": api_name,
                "execution_status": result.execution_status,
                "response_time": result.response_time,
                "algorithm_result": result.algorithm_result,
                "asr_result": result.algorithm_result.get('asr_result') if result.algorithm_result else None,
                "translation_result": result.algorithm_result.get('translation_result') if result.algorithm_result else None,
                "result_data": full_result_data,
                "error_message": result.error_message,
                "dimensions": dim_data,
                "created_at": result.created_at.isoformat()
            })

        # 5. 构建音频列表（含交叠时间轴）
        try:
            from api_gateway.application.services.report_query_service import ReportQueryService
            audios_list = ReportQueryService._build_audios_list(case_info) if case_info else []
        except Exception as e:
            logging.getLogger(__name__).warning(f"构建音频列表失败: {e}")
            audios_list = []

        # 6. 构建结构化 reference_params
        try:
            from api_gateway.application.services.report_command_service import ReportCommandService
            reference_params = ReportCommandService._get_reference_params(
                case_info, results, test_type if case_info and case_info.config else 'api'
            )
        except Exception as e:
            logging.getLogger(__name__).warning(f"构建 reference_params 失败: {e}")
            reference_params = {}

        # 7. 构建 algorithm_results（扁平列表，每项含 device/param_code/param_type/label/value）
        algorithm_type = case_info.algorithm_type if case_info and hasattr(case_info, 'algorithm_type') else ''
        algorithm_results = []
        try:
            from shared.algorithm.algorithm_result_field_mapper import AlgorithmResultFieldMapper
            output_fields = AlgorithmResultFieldMapper.get_output_fields(algorithm_type) if algorithm_type else []

            for i, result in enumerate(results):
                pr = processed_results[i]
                resource = pr['device_name'] or pr['api_name'] or f'result_{result.id}'

                algo_res = result.algorithm_result or {}
                r_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                if not isinstance(r_data, dict):
                    r_data = {}

                combined_data = {**algo_res, **r_data}
                for field in output_fields:
                    param_key = field.get('target_param') or field.get('source_param')
                    if not param_key or not combined_data.get(param_key):
                        continue
                    # voice_llm 多轮：从 rounds 数组里按轮展开 question/answer
                    if algorithm_type == 'voice_llm' and param_key == 'rounds':
                        rounds_arr = combined_data.get('rounds') or []
                        if isinstance(rounds_arr, list):
                            for r_idx, r_item in enumerate(rounds_arr):
                                # rounds 里的 round 字段是 0-indexed，展示用 1-indexed
                                raw_round = r_item.get('roundNumber')
                                if raw_round is None:
                                    raw_round = r_item.get('round')
                                rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
                                out = r_item.get('output') or {}
                                for sub_key in ('question', 'answer'):
                                    val = out.get(sub_key)
                                    if val:
                                        algorithm_results.append({
                                            'device': resource,
                                            'param_code': f'{sub_key}@round:{rn}',
                                            'param_type': 'text',
                                            'label': f'{sub_key} (第{rn}轮)',
                                            'value': val,
                                            'round_number': rn,
                                        })
                        # rounds 整体作为 json 字段保留
                        algorithm_results.append({
                            'device': resource,
                            'param_code': param_key,
                            'param_type': field.get('param_type', 'json'),
                            'label': field.get('dimension_name') or param_key,
                            'value': combined_data[param_key]
                        })
                    else:
                        algorithm_results.append({
                            'device': resource,
                            'param_code': param_key,
                            'param_type': field.get('param_type', 'text'),
                            'label': field.get('dimension_name') or param_key,
                            'value': combined_data[param_key]
                        })
        except Exception as e:
            logging.getLogger(__name__).warning(f"构建 algorithm_results 失败: {e}")

        # 8. 构建 devices 列表和 metric_configs
        devices = list(set(
            pr['device_name'] for pr in processed_results if pr.get('device_name')
        ))

        metric_configs = []
        seen_metrics = set()
        for pr in processed_results:
            for dim in pr.get('dimensions', []):
                if dim['name'] and dim['name'] not in seen_metrics:
                    seen_metrics.add(dim['name'])
                    metric_configs.append({
                        'code': dim['name'],
                        'name': dim['name']
                    })

        # 9. 构建完整的 field_mapping（包含 param_type）和 result_audios
        field_mapping = {'result': [], 'reference': []}
        result_audios = {}  # {device_name: [{url, filename, param_code}]}
        try:
            from shared.algorithm.algorithm_result_field_mapper import AlgorithmResultFieldMapper
            if algorithm_type:
                field_mapping = AlgorithmResultFieldMapper.get_field_mapping(algorithm_type)

                # 提取结果音频（param_type 为 audio_file/audio_stream/audio 的字段）
                audio_types = {'audio_file', 'audio_stream', 'audio'}
                result_audio_fields = [
                    f for f in field_mapping.get('result', [])
                    if f.get('param_type') in audio_types
                ]

                if result_audio_fields:
                    for i, result in enumerate(results):
                        pr = processed_results[i]
                        resource = pr['device_name'] or pr['api_name'] or f'result_{result.id}'

                        algo_res = result.algorithm_result or {}
                        r_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
                        if not isinstance(r_data, dict):
                            r_data = {}

                        combined_data = {**algo_res, **r_data}
                        device_audios = []

                        for field in result_audio_fields:
                            param_code = field.get('param_code') or field.get('source_param')
                            audio_data = combined_data.get(param_code)
                            if audio_data:
                                # 处理不同格式
                                if isinstance(audio_data, str):
                                    raw_url = audio_data
                                elif isinstance(audio_data, dict):
                                    raw_url = audio_data.get('url') or audio_data.get('path', '')
                                else:
                                    raw_url = ''
                                # 将 OSS key 转为预签名 URL
                                if raw_url:
                                    try:
                                        presigned = storage.get_url(raw_url, expires=3600)
                                    except Exception:
                                        presigned = raw_url
                                else:
                                    presigned = ''
                                device_audios.append({
                                    'url': presigned,
                                    'filename': audio_data.get('filename') if isinstance(audio_data, dict) else param_code,
                                    'param_code': param_code
                                })

                        if device_audios:
                            result_audios[resource] = device_audios
        except Exception as e:
            logging.getLogger(__name__).warning(f"构建 field_mapping 失败: {e}")

        # 构建响应数据
        response_data = {
            "task_id": task_id,
            "case_id": case_id,
            "case_name": case_info.name if case_info else "未知用例",
            "status": tc.status,
            "execution_status": tc.execution_status,
            "evaluation_status": tc.evaluation_status,
            "started_at": tc.started_at.isoformat() if tc.started_at else None,
            "completed_at": tc.completed_at.isoformat() if tc.completed_at else None,
            "duration": tc.duration,
            "error_message": tc.error_message,
            "audio_list": audios_list,
            "reference_params": reference_params,
            "algorithm_results": algorithm_results,
            "algorithm_type": algorithm_type,
            "devices": devices,
            "metric_configs": metric_configs,
            "field_mapping": field_mapping,
            "result_audios": result_audios,
        }

        return success_response(response_data)

    # 获取单个用例的执行结果 (不含日志)
    @staticmethod
    def get_case_results(task_id, case_id):
        # 验证任务-用例关联
        tc = TaskCase.query.filter_by(task_id=task_id, test_case_id=case_id).first()
        if not tc:
            return error_response("未找到该任务关联的用例", code=ErrorCode.NOT_FOUND, http_code=404)

        case_info = db.session.get(TestCase, case_id)

        # 获取执行结果
        results = TestResult.query.filter_by(task_id=task_id, test_case_id=case_id).all()

        processed_results = []
        for result in results:
            device_name = None
            api_name = None
            if result.device_id:
                from shared.models.models import Device
                device = db.session.get(Device, result.device_id)
                if device:
                    device_name = device.name

            if result.api_id:
                from shared.models.models import API
                api = db.session.get(API, result.api_id)
                if api:
                    api_name = api.name

            dimensions = db.session.query(
                TestResultDimension, Dimension.name
            ).join(
                Dimension, TestResultDimension.dimension_id == Dimension.id
            ).filter(
                TestResultDimension.test_result_id == result.id
            ).all()

            dim_data = []
            for dim, dim_name in dimensions:
                dim_data.append({
                    "id": dim.id,
                    "name": dim_name,
                    "value": dim.dimension_value,
                    "score": dim.score,
                    "status": dim.status,
                    "evaluation_status": dim.evaluation_status,
                    "error_message": dim.error_message,
                    "round_number": getattr(dim, 'round_number', None)
                })

            processed_results.append({
                "id": result.id,
                "device_id": result.device_id,
                "device_name": device_name,
                "api_id": result.api_id,
                "api_name": api_name,
                "execution_status": result.execution_status,
                "response_time": result.response_time,
                "algorithm_result": result.algorithm_result,
                "asr_result": result.algorithm_result.get('asr_result') if result.algorithm_result else None,
                "translation_result": result.algorithm_result.get('translation_result') if result.algorithm_result else None,
                "result_data": load_full_result_data(result.result_data, getattr(result, 'result_data_path', None)),
                "error_message": result.error_message,
                "dimensions": dim_data,
                "created_at": result.created_at.isoformat()
            })

        response_data = {
            "task_id": task_id,
            "case_id": case_id,
            "case_name": case_info.name if case_info else "未知用例",
            "results": processed_results
        }

        return success_response(response_data)

    # 获取任务实时进度 (用于 HTTP 轮询降级)
    @staticmethod
    def get_progress(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)

        # 获取当前正在执行的用例信息
        current_case = TaskCase.query.filter_by(task_id=task_id, execution_status='running').first()
        current_case_data = None
        if current_case:
            case_info = db.session.get(TestCase, current_case.test_case_id)
            current_case_data = TaskProgressCurrentCase(
                case_id=current_case.test_case_id,
                name=case_info.name if case_info else "未知用例",
                step="running",
                started_at=current_case.started_at.isoformat() if current_case.started_at else None,
            )

        return success_response(
            TaskProgressData(
                task_id=str(task.id),
                status=task.status,
                total_cases=task.total_cases,
                completed_cases=task.completed_cases,
                failed_cases=task.failed_cases,
                progress=round(task.completed_cases / task.total_cases * 100, 2) if task.total_cases > 0 else 0,
                current_case=current_case_data,
                updated_at=now_cst().isoformat(),
            )
        )

    # 获取任务统计信息
    @staticmethod
    def stats(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)

        # 1. 基础统计
        total = task.total_cases
        completed = task.completed_cases
        failed = task.failed_cases
        pending = TaskCase.query.filter_by(task_id=task_id, execution_status='pending').count()
        skipped = TaskCase.query.filter_by(task_id=task_id, status='skipped').count()

        # 2. 按标签统计通过率和平均耗时
        tag_stats = {}
        # 关联查询 TaskCase -> TestCase -> Tags
        results = db.session.query(Tag.name, TaskCase.status, TaskCase.duration)\
            .join(TestCase, TaskCase.test_case_id == TestCase.id)\
            .join(TestCase.tags)\
            .filter(TaskCase.task_id == task_id).all()

        for tag_name, status, duration in results:
            if tag_name not in tag_stats:
                tag_stats[tag_name] = {"total": 0, "completed": 0, "durations": []}
            tag_stats[tag_name]["total"] += 1
            if status == 'completed':
                tag_stats[tag_name]["completed"] += 1
            if duration:
                tag_stats[tag_name]["durations"].append(duration)

        for tag_name in tag_stats:
            s = tag_stats[tag_name]
            s["pass_rate"] = round((s["completed"] / s["total"] * 100), 2) if s["total"] > 0 else 0
            s["avg_duration"] = round(sum(s["durations"]) / len(s["durations"]), 2) if s["durations"] else 0
            del s["durations"]

        stats_data = {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "skipped": skipped,
            "pass_rate": round((completed / total * 100), 2) if total > 0 else 0,
            "tag_stats": tag_stats,
            "duration": task.actual_duration or 0
        }
        return success_response(TaskStatsData(**stats_data))
