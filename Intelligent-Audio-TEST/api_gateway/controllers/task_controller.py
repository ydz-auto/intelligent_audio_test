import json
import logging
from flask import request, current_app
from shared.models.models import Task, Tag, TaskCase, TaskDevice, TaskAPI, TestCase, TestResult, TestResultDimension, Log, Dimension
from shared.models.database import db
from shared.utils.response import success_response, error_response, convert_keys_to_camel
from shared.utils.error_codes import ErrorCode
from shared.utils.log_handler import log_not_emit
# 跨服务调用：通过 gRPC ExecutionService 调用任务执行引擎
from api_gateway.controllers._grpc_proxies import (
    execution_engine, _ReevaluationExecutorProxy,
)
from shared.utils.result_data_store import load_full_result_data
from shared.clients.oss_client import oss
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
from datetime import datetime, timezone, timedelta
from shared.utils.query_utils import now_cst
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)

class TaskController:
    @staticmethod
    def _cleanup_case_results(task_id, case_ids, preserve_test_result=False):
        """清理用例的旧结果

        Args:
            task_id: 任务ID
            case_ids: 用例ID列表
            preserve_test_result: 为True时只清除TestResultDimension，保留TestResult（用于已执行完成的用例只需重新评估）
        """
        import os
        from shared.models.models import TestResult, TestResultDimension, TaskCase

        if not case_ids:
            return None

        errors = []

        # 1. 删除数据库记录
        results = TestResult.query.filter(
            TestResult.task_id == task_id,
            TestResult.test_case_id.in_(case_ids)
        ).all()

        result_ids = [r.id for r in results]
        if result_ids:
            # 先删除子表 TestResultDimension（维度评估记录）
            TestResultDimension.query.filter(
                TestResultDimension.test_result_id.in_(result_ids)
            ).delete(synchronize_session=False)

            if not preserve_test_result:
                # 完全清理：删除主表 TestResult（执行结果）
                TestResult.query.filter(
                    TestResult.id.in_(result_ids)
                ).delete(synchronize_session=False)

        # 2. 删除文件系统中的日志文件（仅在完全清理时）
        if not preserve_test_result:
            task_cases = TaskCase.query.filter(
                TaskCase.task_id == task_id,
                TaskCase.test_case_id.in_(case_ids)
            ).all()

            for tc in task_cases:
                # OSS: 删除 case-result bucket 下 {task_id}/{case_id}/ 的所有文件
                oss_prefix = f'{task_id}/{tc.test_case_id}/'
                try:
                    oss_keys = oss.list_objects('case_result', prefix=oss_prefix)
                    for oss_key in oss_keys:
                        oss.delete('case_result', oss_key)
                except Exception as e:
                    errors.append(f"删除用例 {tc.test_case_id} OSS文件失败: {str(e)}")

        return errors if errors else None

    @staticmethod
    def _trigger_reevaluate(task_id, completed_cases):
        """触发已执行完成用例的重新评估（不重新执行）

        直接调用 ReevaluationExecutor 的评估方法，绕过执行引擎。
        执行引擎的 wait loop 会自动等待 evaluation_status 变为 completed。

        Args:
            task_id: 任务ID
            completed_cases: 已执行完成的 TaskCase 列表（execution_status='completed'）
        """
        if not completed_cases:
            return

        # 跨服务调用：通过 gRPC ExecutionService 重新评估
        from shared.models.models import TestCase

        reevaluation_executor = _ReevaluationExecutorProxy.get_instance()
        task = db.session.get(Task, task_id)
        test_type = task.type if task and task.type else 'api'

        for tc in completed_cases:
            test_case_id = tc.test_case_id
            try:
                result = TestResult.query.filter_by(
                    task_id=task_id,
                    test_case_id=test_case_id
                ).first()

                if not result:
                    tc.evaluation_status = 'failed'
                    tc.error_message = '未找到执行结果，无法重新评估'
                    continue

                if not result.algorithm_result:
                    tc.evaluation_status = 'failed'
                    tc.error_message = '执行结果无 algorithm_result，无法重新评估'
                    continue

                algo_result = result.algorithm_result or {}
                # 循环反序列化，处理可能的双重序列化旧数据
                while isinstance(algo_result, str):
                    try:
                        algo_result = json.loads(algo_result)
                    except (json.JSONDecodeError, ValueError):
                        algo_result = {}
                if not isinstance(algo_result, dict):
                    algo_result = {}
                full_data = load_full_result_data(
                    result.result_data,
                    getattr(result, 'result_data_path', None)
                )
                reference_params = full_data.get(
                    'adjusted_reference_params', []
                ) if full_data else []

                test_case = db.session.get(TestCase, test_case_id)
                algorithm_type = (
                    test_case.algorithm_type
                    if test_case and test_case.algorithm_type
                    else 'translation'
                )

                if algo_result and 'rounds' in algo_result:
                    reevaluation_executor._reevaluate_multi_round(
                        task_id=task_id,
                        result=result.id,
                        test_case_id=test_case_id,
                        algorithm_result=algo_result,
                        test_type=test_type,
                        algorithm_type=algorithm_type,
                    )
                else:
                    reevaluation_executor._reevaluate_single(
                        task_id=task_id,
                        result_id=result.id,
                        test_case_id=test_case_id,
                        algorithm_result=algo_result,
                        reference_params=reference_params,
                        test_type=test_type,
                        algorithm_type=algorithm_type,
                    )

            except Exception as e:
                import traceback
                tc.evaluation_status = 'failed'
                tc.error_message = f'重新评估触发失败: {str(e)}'
                log_not_emit('WARN', 'task_controller', f'触发重新评估失败: task_id={task_id}, test_case_id={test_case_id}, error={str(e)}, traceback={traceback.format_exc()}', category='task')

        db.session.commit()

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
            from api_gateway.controllers.report_controller_task import ReportControllerTask
            audios_list = ReportControllerTask._build_audios_list(case_info) if case_info else []
        except Exception as e:
            logging.getLogger(__name__).warning(f"构建音频列表失败: {e}")
            audios_list = []
        
        # 6. 构建结构化 reference_params
        try:
            from api_gateway.controllers.report_controller_task import ReportControllerTask
            reference_params = ReportControllerTask._get_reference_params(
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
                                    device_audios.append({
                                        'url': audio_data,
                                        'filename': param_code,
                                        'param_code': param_code
                                    })
                                elif isinstance(audio_data, dict):
                                    device_audios.append({
                                        'url': audio_data.get('url') or audio_data.get('path', ''),
                                        'filename': audio_data.get('filename') or audio_data.get('name', param_code),
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

    # 创建新任务
    @staticmethod
    def create():
        req = TaskCreateRequest.model_validate(request.get_json())

        try:
            case_ids = req.case_ids or []
            device_ids = req.device_ids or []
            api_ids = req.api_ids or []
            tags = req.tags or []

            new_task = Task(
                name=req.name,
                description=req.description,
                type=req.type,
                status='pending',
                config=req.config or {},
                total_cases=len(case_ids),
                created_by=req.created_by
            )
            db.session.add(new_task)
            db.session.flush() # 获取 ID

            # 建立用例关联
            for case_id in case_ids:
                task_case = TaskCase(
                    task_id=new_task.id,
                    test_case_id=case_id,
                    status='pending',
                    execution_status='pending',
                    evaluation_status='pending'
                )
                db.session.add(task_case)

            # 建立设备关联
            for device_id in device_ids:
                task_device = TaskDevice(task_id=new_task.id, device_id=device_id)
                db.session.add(task_device)

            # 建立 API 关联
            for api_id in api_ids:
                task_api = TaskAPI(task_id=new_task.id, api_id=api_id)
                db.session.add(task_api)

            # 处理标签
            for tag_name in tags:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                new_task.tags.append(tag)

            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(IdData(id=new_task.id), "任务创建成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # 启动任务
    @staticmethod
    def start(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("任务 ID 不存在", code=ErrorCode.NOT_FOUND, http_code=404)

        if task.status == 'running':
            return success_response({
                "id": task.id,
                "status": task.status,
                "message": "任务已在运行中"
            })

        if task.status not in ['pending', 'failed', 'stopped', 'completed']:
            return error_response("非法的任务状态转换操作", code=ErrorCode.OPERATION_FAILED, http_code=400)

        try:
            # 如果是从failed或stopped状态重启，重置任务和用例状态
            if task.status in ['failed', 'stopped']:
                # 1. 重置任务状态和统计信息
                task.completed_cases = 0
                task.failed_cases = 0
                task.started_at = None
                task.completed_at = None
                task.actual_duration = None
                
                # 2. 重置所有关联用例的状态
                from shared.models.models import TaskCase, TestResult
                
                # 重置TaskCase状态
                TaskCase.query.filter_by(task_id=task_id).update({
                    TaskCase.status: 'pending',  # 初始状态为pending，执行成功后会更新
                    TaskCase.execution_status: 'pending',
                    TaskCase.evaluation_status: 'pending',
                    TaskCase.started_at: None,
                    TaskCase.completed_at: None,
                    TaskCase.duration: None,
                    TaskCase.error_message: None
                })
                
                # 重置TestResult状态
                TestResult.query.filter_by(task_id=task_id).update({
                    TestResult.execution_status: 'pending',
                    TestResult.error_message: None
                })
                
                db.session.commit()
            
            # 3. 环境预检逻辑
            # E2E 检查关联设备是否在线
            if task.type == 'e2e':
                from shared.models.models import Device
                offline_devices = []
                for device in task.devices:
                    if device.status != 'online':
                        offline_devices.append(device.name)
                
                if offline_devices:
                    return error_response(f"设备已被其他任务占用或离线: {', '.join(offline_devices)}", code=ErrorCode.OPERATION_FAILED, http_code=400)
            
            # API 检查关联 API 是否在线 (HEAD 请求模拟)
            elif task.type == 'api':
                for api in task.apis:
                    if api.status != 'online':
                        return error_response(f"API 端点 {api.name} 当前不可用", code=ErrorCode.OPERATION_FAILED, http_code=400)

            # 4. 调用执行引擎启动任务
            app = current_app._get_current_object()
            success, message = execution_engine.start_task(app, task.id)
            
            if not success:
                return error_response(message, code=ErrorCode.TASK_EXECUTION_ERROR)

            # 5. 计算时间预估
            time_estimate = execution_engine.event_manager.calculate_time_estimate(task)

            return success_response(
                TaskStartData(
                    task_id=str(task.id),
                    start_time=int(datetime.utcnow().timestamp() * 1000),
                    status="queued" if "队列" in message else "running",
                    expected_total_time=time_estimate["expected_total_time"],
                    expected_complete_time=time_estimate["expected_complete_time"]
                ),
                message,
            )
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.INTERNAL_ERROR) # 数据库或内部错误

    # 重新执行失败或未完成的用例
    @staticmethod
    def retry(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)

        try:
            from shared.models.models import TaskCase

            if task.status in ['running', 'paused', 'queued']:
                app = current_app._get_current_object()
                execution_engine.control_task(app, task_id, 'stop')
                task = db.session.get(Task, task_id)
            
            fully_succeeded = and_(
                TaskCase.execution_status == 'completed',
                TaskCase.evaluation_status == 'completed',
                TaskCase.status == 'completed'
            )

            retry_cases = TaskCase.query.filter(
                TaskCase.task_id == task_id,
                or_(
                    TaskCase.status == 'failed',
                    TaskCase.execution_status != 'completed',
                    TaskCase.evaluation_status == 'failed'
                ),
                ~fully_succeeded,
                or_(TaskCase.status.is_(None), TaskCase.status != 'skipped')
            ).all()

            if not retry_cases:
                return success_response(None, "没有需要重试的用例")

            # 区分已执行完成（只需重新评估）和未执行完成（需重新执行）的用例
            completed_cases = [tc for tc in retry_cases if tc.execution_status == 'completed']
            incomplete_cases = [tc for tc in retry_cases if tc.execution_status != 'completed']

            # 分别清理：已执行完成的保留 TestResult，只删 TestResultDimension
            cleanup_errors = None
            if completed_cases:
                errs = TaskController._cleanup_case_results(
                    task_id, [tc.test_case_id for tc in completed_cases], preserve_test_result=True
                )
                if errs:
                    cleanup_errors = (cleanup_errors or []) + errs
            if incomplete_cases:
                errs = TaskController._cleanup_case_results(
                    task_id, [tc.test_case_id for tc in incomplete_cases], preserve_test_result=False
                )
                if errs:
                    cleanup_errors = (cleanup_errors or []) + errs
            if cleanup_errors:
                return error_response(
                    f"清理旧结果失败: {'; '.join(cleanup_errors)}",
                    code=ErrorCode.OPERATION_FAILED
                )

            # 3. 重置 TaskCase 状态
            # 已执行完成的用例：保持 execution_status='completed'，只重置评估状态
            for tc in completed_cases:
                tc.status = 'pending'  # 评估完成后由 _post_evaluate_updates 设为 execution_status
                tc.evaluation_status = 'pending'
                tc.error_message = None
            # 未执行完成的用例：完全重置，重新执行
            for tc in incomplete_cases:
                tc.status = 'failed'
                tc.execution_status = 'pending'
                tc.evaluation_status = 'pending'
                tc.started_at = None
                tc.completed_at = None
                tc.duration = None
                tc.error_message = None

            # 4. 更新任务统计信息
            # 重新计算已完成和失败的数量 (基于已经执行成功且状态为completed的用例)
            task.completed_cases = TaskCase.query.filter_by(task_id=task_id, execution_status='completed', status='completed').count()
            task.failed_cases = TaskCase.query.filter_by(task_id=task_id, execution_status='completed', status='failed').count()
            
            # 如果任务之前是失败、停止或完成状态，改回 running (由执行引擎启动)
            if task.status in ['failed', 'stopped', 'completed']:
                task.status = 'pending'
                task.started_at = None
                task.completed_at = None
                task.actual_duration = None
            
            db.session.commit()

            # 5. 触发已执行完成用例的重新评估（绕过执行引擎，直接调用评估）
            if completed_cases:
                TaskController._trigger_reevaluate(task_id, completed_cases)

            # 6. 调用执行引擎启动任务（处理未执行完成的用例 + 等待所有评估完成）
            app = current_app._get_current_object()
            success, message = execution_engine.start_task(app, task.id)
            
            if not success:
                return error_response(message, code=ErrorCode.TASK_EXECUTION_ERROR)

            return success_response(TaskStatusData(task_id=str(task.id), status="running"), "重试任务已启动")
            
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.INTERNAL_ERROR)

    # 任务运行时控制
    @staticmethod
    def control(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)

        req = TaskControlRequest.model_validate(request.get_json())

        action = req.action
        case_id = req.case_id

        try:
            if action == 'retry' and not case_id:
                return TaskController.retry(task_id)

            # 处理针对单个用例的控制 (skip/retry)
            if action in ['skip', 'retry'] and case_id:
                tc = TaskCase.query.filter_by(task_id=task_id, test_case_id=case_id).first()
                if not tc:
                    return error_response("未找到指定用例关联", code=ErrorCode.NOT_FOUND)

                if tc.execution_status in ['queued', 'running'] or tc.evaluation_status == 'running':
                    return error_response("用例执行中不允许此操作", code=ErrorCode.OPERATION_FAILED, http_code=400)
                
                if action == 'skip':
                    tc.status = 'skipped'
                    tc.execution_status = 'stopped'
                    tc.evaluation_status = 'stopped'
                    tc.error_message = tc.error_message or '用例被手动跳过'
                else: # retry
                    if tc.execution_status == 'completed':
                        # 已执行完成的用例：保留 TestResult，只删 TestResultDimension，只重新评估
                        tc.status = 'pending'  # 评估完成后由 _post_evaluate_updates 设为 execution_status
                        tc.evaluation_status = 'pending'
                        tc.error_message = None
                        # execution_status 保持 'completed' 不变

                        cleanup_errors = TaskController._cleanup_case_results(task_id, [case_id], preserve_test_result=True)
                    else:
                        # 未执行完成的用例：完全重置，重新执行
                        tc.status = 'failed'
                        tc.execution_status = 'pending'
                        tc.evaluation_status = 'pending'
                        tc.started_at = None
                        tc.completed_at = None
                        tc.duration = None
                        tc.error_message = None

                        cleanup_errors = TaskController._cleanup_case_results(task_id, [case_id], preserve_test_result=False)

                    if cleanup_errors:
                        return error_response(
                            f"清理旧结果失败: {'; '.join(cleanup_errors)}",
                            code=ErrorCode.OPERATION_FAILED
                        )

                    task.completed_cases = TaskCase.query.filter_by(task_id=task_id, execution_status='completed', status='completed').count()
                    task.failed_cases = TaskCase.query.filter_by(task_id=task_id, execution_status='completed', status='failed').count()
                    if task.status in ['failed', 'stopped', 'completed']:
                        task.status = 'pending'
                        task.started_at = None
                        task.completed_at = None
                        task.actual_duration = None
                
                db.session.commit()

                # 如果是 retry 已执行完成的用例，触发重新评估
                if action == 'retry' and tc.execution_status == 'completed':
                    TaskController._trigger_reevaluate(task_id, [tc])

                # 如果任务当前没在运行，且是 retry 操作，则尝试重新启动任务
                if action == 'retry' and task.status not in ['running', 'paused']:
                    app = current_app._get_current_object()
                    execution_engine.start_task(app, task_id)

                return success_response(None, f"Action '{action}' executed successfully")

            # 处理全局任务控制 (pause/resume/stop)
            app = current_app._get_current_object()
            success, message = execution_engine.control_task(app, task_id, action)
            if not success:
                return error_response(message, code=ErrorCode.OPERATION_FAILED)

            updated = db.session.get(Task, task_id)
            return success_response(
                TaskStatusData(task_id=str(task_id), status=updated.status if updated else None),
                f"Action '{action}' executed successfully",
            )
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.INTERNAL_ERROR)

    # 动态调整用例
    @staticmethod
    def update_cases(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("任务 ID 不存在", code=ErrorCode.NOT_FOUND, http_code=404)

        req = TaskUpdateCasesRequest.model_validate(request.get_json())

        action = req.action
        case_ids = req.case_ids

        try:
            if action == 'add':
                has_running_case = TaskCase.query.filter_by(task_id=task_id, execution_status='running').first() is not None
                if task.status in ['queued', 'running', 'paused'] or has_running_case:
                    return error_response("任务执行中不允许新增用例", code=ErrorCode.OPERATION_FAILED, http_code=400)

            if action == 'add':
                for cid in case_ids:
                    if not TaskCase.query.filter_by(task_id=task_id, test_case_id=cid).first():
                        db.session.add(TaskCase(
                            task_id=task_id,
                            test_case_id=cid,
                            status='pending',
                            execution_status='pending',
                            evaluation_status='pending'
                        ))
            elif action == 'remove':
                TaskCase.query.filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id.in_(case_ids),
                    TaskCase.execution_status == 'pending'
                ).delete(synchronize_session=False)

            # 重新计算总数
            task.total_cases = TaskCase.query.filter_by(task_id=task_id).count()
            task.updated_at = now_cst()
            db.session.commit()
            return success_response(
                TaskUpdateCasesData(task_id=str(task.id), total_count=task.total_cases),
                "Cases updated successfully",
            )
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

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

    # 批量操作
    @staticmethod
    def batch_action():
        req = TaskBatchActionRequest.model_validate(request.get_json())

        action = req.action
        task_ids = req.task_ids

        try:
            if action == 'delete':
                app = current_app._get_current_object()
                
                # 获取所有待删除任务，包括运行中的
                tasks = Task.query.filter(Task.id.in_(task_ids)).all()
                deleted_count = 0
                
                for t in tasks:
                    # 1. 如果任务正在运行，先停止任务
                    if t.status in ['running', 'paused']:
                        execution_engine.control_task(app, t.id, 'stop')
                    
                    # 2. 从任务队列中移除任务
                    execution_engine.remove_from_queue(t.id)
                    
                    # 3. 标记任务为已删除
                    t.deleted = True
                    deleted_count += 1
                
                db.session.commit()
                return success_response(None, f"成功删除 {deleted_count} 个任务")
            elif action == 'export':
                # 导出逻辑：支持 Excel 和 JSON
                format_ = request.args.get('format', 'json')
                tasks = Task.query.filter(Task.id.in_(task_ids)).all()
                
                export_data = []
                for t in tasks:
                    if format_ in ['excel', 'pdf']:
                        export_data.append({
                            "ID": t.id,
                            "任务名称": t.name,
                            "类型": t.type,
                            "状态": t.status,
                            "总用例数": t.total_cases,
                            "完成数": t.completed_cases,
                            "失败数": t.failed_cases,
                            "开始时间": t.started_at.isoformat() if t.started_at else "",
                            "完成时间": t.completed_at.isoformat() if t.completed_at else "",
                            "创建时间": t.created_at.isoformat()
                        })
                    else:
                        export_data.append({
                            "id": t.id,
                            "name": t.name,
                            "type": t.type,
                            "status": t.status,
                            "total_cases": t.total_cases,
                            "completed_cases": t.completed_cases,
                            "failed_cases": t.failed_cases,
                            "started_at": t.started_at.isoformat() if t.started_at else "",
                            "completed_at": t.completed_at.isoformat() if t.completed_at else "",
                            "created_at": t.created_at.isoformat()
                        })

                if not export_data:
                    return error_response("没有可导出的数据", code=ErrorCode.NOT_FOUND, http_code=404)

                if format_ == 'excel':
                    import pandas as pd
                    import io
                    from flask import send_file
                    
                    df = pd.DataFrame(export_data)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Tasks')
                    output.seek(0)
                    
                    return send_file(
                        output,
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True,
                        download_name=f"tasks_export_{now_cst().strftime('%Y%m%d%H%M%S')}.xlsx"
                    )
                
                if format_ == 'pdf':
                    import io
                    from flask import send_file
                    from reportlab.lib import colors
                    from reportlab.lib.pagesizes import A4, landscape
                    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    import os
                    import platform

                    # 注册中文字体 (跨平台候选路径)
                    font_candidates = (
                        ['C:\\Windows\\Fonts\\msyh.ttc', 'C:\\Windows\\Fonts\\simsun.ttc']
                        if platform.system() == 'Windows'
                        else ['/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                              '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
                    )
                    font_path = next((p for p in font_candidates if os.path.exists(p)), None)

                    font_name = "CustomFont"
                    if font_path and os.path.exists(font_path):
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                    else:
                        font_name = "Helvetica" # 回退

                    output = io.BytesIO()
                    doc = SimpleDocTemplate(output, pagesize=landscape(A4))
                    elements = []
                    
                    # 表格数据
                    data = [list(export_data[0].keys())] # 表头
                    for item in export_data:
                        data.append(list(item.values()))
                    
                    # 创建表格
                    table = Table(data)
                    style = TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, -1), font_name),
                        ('FONTSIZE', (0, 0), (-1, 0), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ])
                    table.setStyle(style)
                    elements.append(table)
                    
                    doc.build(elements)
                    output.seek(0)
                    
                    return send_file(
                        output,
                        mimetype='application/pdf',
                        as_attachment=True,
                        download_name=f"tasks_export_{now_cst().strftime('%Y%m%d%H%M%S')}.pdf"
                    )
                
                return success_response(export_data, "数据准备就绪")
            
            db.session.commit()
            return success_response(None, f"批量操作 {action} 执行成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 重新提取设备输出
    @staticmethod
    def rextract(task_id):
        from pydantic import BaseModel, Field
        # 跨服务调用：通过 gRPC DeviceResultService 重新提取设备结果
        from api_gateway.controllers._grpc_proxies import get_device_result_reextractor

        class TaskReextractInput(BaseModel):
            task_id: int = Field(..., validation_alias='task_id')
            execution_status: str = Field('completed', validation_alias='executionStatus')
            evaluation_status: str = Field(None, validation_alias='evaluationStatus')

        try:
            req = TaskReextractInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        task_id = req.task_id
        execution_status = req.execution_status
        evaluation_status = req.evaluation_status

        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到任务", 404)

        if task.status not in ['completed', 'failed', 'stopped', 'paused', 'skipped']:
            return error_response("只有已完成/失败/停止/暂停/跳过的任务才能重新提取")

        try:
            reextractor = get_device_result_reextractor()
            result = reextractor.reextract_for_task(
                task_id,
                execution_status=execution_status,
                evaluation_status=evaluation_status
            )

            if result.get('success'):
                message = result.get('message', '重新提取成功')
                reextracted_cases = result.get('reextracted_cases', [])
                return success_response({
                    'task_id': task_id,
                    'reextracted_count': len(reextracted_cases),
                    'reextracted_cases': reextracted_cases,
                    'message': message
                }, message)
            else:
                return error_response(f"重新提取失败: {result.get('message')}")

        except Exception as e:
            db.session.rollback()
            return error_response(f"重新提取失败: {str(e)}")

    # 停止正在运行的任务 (保持向下兼容或作为 control 的快捷方式)
    @staticmethod
    def stop(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            return error_response("未找到任务", 404)

        try:
            app = current_app._get_current_object()
            success, message = execution_engine.control_task(app, task_id, 'stop')
            if not success:
                return error_response(message, code=ErrorCode.OPERATION_FAILED, http_code=400)
            return success_response(None, message)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 删除任务
    @staticmethod
    def delete(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            return error_response("未找到任务", 404)

        try:
            app = current_app._get_current_object()

            if task.status in ['running', 'paused']:
                # 跨服务调用：通过 gRPC ExecutionService 停止任务
                execution_engine.control_task(app, task_id, 'stop')

            # 2. 从任务队列中移除任务
            execution_engine.remove_from_queue(task_id)
            
            # 3. 标记任务为已删除
            task.deleted = True
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "任务已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def update(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            return error_response("未找到任务", 404)

        try:
            data = request.get_json()
            if not data:
                return error_response("请求数据不能为空", 400)

            if 'name' in data and data['name']:
                task.name = data['name']
            if 'description' in data:
                task.description = data['description']

            db.session.commit()
            return success_response({"id": task.id, "name": task.name}, "任务已更新")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def merge():
        from shared.models.models import TestResult, TaskDevice, TaskAPI, TaskCase, TaskTag, TaskMergeRelation

        req = TaskMergeRequest.model_validate(request.get_json())

        task_ids = req.task_ids

        if not task_ids or len(task_ids) < 2:
            return error_response("合并需要至少两个任务", code=ErrorCode.MISSING_PARAMS)

        try:
            tasks = Task.query.filter(Task.id.in_(task_ids)).all()

            if len(tasks) != len(task_ids):
                return error_response("部分任务未找到", code=ErrorCode.NOT_FOUND)

            for t in tasks:
                if t.status != 'completed':
                    return error_response(f"任务 '{t.name}' 未完成，无法合并", code=ErrorCode.INVALID_STATUS)

            task_names = [t.name for t in tasks]
            merged_name = f"合并任务_{'_'.join(task_names[:3])}{'_等' if len(task_names) > 3 else ''}"

            source_result_counts = {}
            device_ids_set = set()
            api_ids_set = set()
            case_ids_set = set()
            tag_ids_set = set()

            for task in tasks:
                results = TestResult.query.filter_by(task_id=task.id).all()
                source_result_counts[task.id] = len(results)

                for result in results:
                    if result.device_id:
                        device_ids_set.add(result.device_id)
                    if result.api_id:
                        api_ids_set.add(result.api_id)
                    if result.test_case_id:
                        case_ids_set.add(result.test_case_id)

                for tag in task.tags:
                    tag_ids_set.add(tag.id)

            total_cases = sum(t.total_cases for t in tasks)
            completed_cases = sum(t.completed_cases for t in tasks)
            failed_cases = sum(t.failed_cases for t in tasks)

            new_task = Task(
                name=merged_name,
                type='merged',
                status='completed',
                description=f"合并自任务: {', '.join(task_names)}",
                total_cases=total_cases,
                completed_cases=completed_cases,
                failed_cases=failed_cases,
                started_at=min(t.started_at for t in tasks if t.started_at),
                completed_at=max(t.completed_at for t in tasks if t.completed_at),
                actual_duration=max((t.completed_at - t.started_at).total_seconds() for t in tasks if t.started_at and t.completed_at) if any(t.started_at and t.completed_at for t in tasks) else 0
            )

            db.session.add(new_task)
            db.session.flush()

            for device_id in device_ids_set:
                existing = TaskDevice.query.filter_by(task_id=new_task.id, device_id=device_id).first()
                if not existing:
                    task_device = TaskDevice(task_id=new_task.id, device_id=device_id)
                    db.session.add(task_device)

            for api_id in api_ids_set:
                existing = TaskAPI.query.filter_by(task_id=new_task.id, api_id=api_id).first()
                if not existing:
                    task_api = TaskAPI(task_id=new_task.id, api_id=api_id)
                    db.session.add(task_api)

            for case_id in case_ids_set:
                existing = TaskCase.query.filter_by(task_id=new_task.id, test_case_id=case_id).first()
                if not existing:
                    task_case = TaskCase(task_id=new_task.id, test_case_id=case_id, status='completed')
                    db.session.add(task_case)

            for tag_id in tag_ids_set:
                existing = TaskTag.query.filter_by(task_id=new_task.id, tag_id=tag_id).first()
                if not existing:
                    task_tag = TaskTag(task_id=new_task.id, tag_id=tag_id)
                    db.session.add(task_tag)

            for task in tasks:
                task.status = 'merged'
                merge_relation = TaskMergeRelation(
                    merged_task_id=new_task.id,
                    source_task_id=task.id,
                    source_result_count=source_result_counts.get(task.id, 0)
                )
                db.session.add(merge_relation)

            db.session.commit()

            return success_response(
                {"merged_task_id": new_task.id, "merged_task_name": new_task.name},
                f"成功合并 {len(tasks)} 个任务",
                http_code=201
            )
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
