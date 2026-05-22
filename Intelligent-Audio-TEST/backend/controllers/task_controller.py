from flask import request, current_app
from backend.models.models import Task, Tag, TaskCase, TaskDevice, TaskAPI, TestCase, TestResult, TestResultDimension, Log, Dimension
from backend.models.database import db
from backend.utils.response import success_response, error_response, convert_keys_to_camel
from backend.utils.error_codes import ErrorCode
from backend.utils.execution_engine import execution_engine
from backend.schemas.common import IdData, TaskStatusData
from backend.schemas.task import (
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
from sqlalchemy import and_, or_
from backend.algorithm.reference_params_generator import ReferenceParamsGenerator

class TaskController:
    @staticmethod
    def _cleanup_case_results(task_id, case_ids):
        import os
        import shutil
        from backend.models.models import TestResult, TestResultDimension, TaskCase
        from backend.config import Config

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
            TestResultDimension.query.filter(
                TestResultDimension.test_result_id.in_(result_ids)
            ).delete(synchronize_session=False)

            TestResult.query.filter(
                TestResult.id.in_(result_ids)
            ).delete(synchronize_session=False)

        # 2. 删除文件系统中的日志文件
        # 获取所有相关的 TaskCase 记录以获取 device_id
        task_cases = TaskCase.query.filter(
            TaskCase.task_id == task_id,
            TaskCase.test_case_id.in_(case_ids)
        ).all()

        for tc in task_cases:
            # 构建日志文件路径
            local_dir = os.path.join(Config.STATIC_BASE_PATH, 'case_result', f'{task_id}', f'{tc.test_case_id}')
            if os.path.exists(local_dir):
                try:
                    shutil.rmtree(local_dir)
                except Exception as e:
                    errors.append(f"删除用例 {tc.test_case_id} 日志文件失败: {str(e)}")

        return errors if errors else None

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
            from backend.models.models import Report
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
                total_cases=task.total_cases,
                case_count=task.total_cases,
                device_count=len(devices),
                completed_cases=task.completed_cases,
                failed_cases=task.failed_cases,
                tags=[tag.name for tag in task.tags],
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
        
        # 3. 获取参考ASR文本和参考翻译文本
        reference_asr_text = None
        reference_translation_text = None
        
        if case_info and case_info.config:
            try:
                # 从用例配置中获取配置
                config = case_info.config
                if isinstance(config, str):
                    import json
                    config = json.loads(config)
                
                # 从配置中获取音频ID
                audio_id = None
                if isinstance(config, dict):
                    # 检查不同的配置结构
                    if 'audioId' in config:
                        audio_id = config['audioId']
                    elif 'audio_id' in config:
                        audio_id = config['audio_id']
                    elif 'audio' in config:
                        if isinstance(config['audio'], dict) and 'id' in config['audio']:
                            audio_id = config['audio']['id']
                    elif 'audioConfig' in config:
                        if isinstance(config['audioConfig'], dict):
                            audio_config = config['audioConfig']
                            if 'audioId' in audio_config:
                                audio_id = audio_config['audioId']
                            elif 'audio_id' in audio_config:
                                audio_id = audio_config['audio_id']
                
                # 根据测试类型从配置中获取参考文本，优先使用配置中的参考文本
                task = db.session.get(Task, task_id)
                test_type = task.type if task else 'api'
                case_config = config
                asr_ref = ReferenceParamsGenerator.get_reference_text(case_config, 'asr_reference_text', test_type)
                preset_trans = ReferenceParamsGenerator.get_reference_text(case_config, 'translation_reference_text', test_type)
                
                # 获取音频对象，用于默认值
                audio = None
                if audio_id:
                    from backend.models.models import Audio, AudioAnnotation
                    audio = db.session.get(Audio, audio_id)
                
                # 如果配置中没有参考文本，则使用音频对象的默认值
                if not asr_ref and audio:
                    asr_ref = audio.asr_text
                
                # 获取翻译对象，用于默认值 (从 AudioAnnotation 中获取)
                translation_obj = None
                td_id = config.get('translation_direction_id') if isinstance(config, dict) else None
                if audio_id:
                    from backend.models.models import AudioAnnotation
                    annotations = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False).all()
                    if td_id:
                        for ann in annotations:
                            if ann.target_language:
                                direction = TranslationDirection.query.get(td_id)
                                if direction and ann.target_language == direction.target_language:
                                    translation_obj = ann
                                    break
                    else:
                        for ann in annotations:
                            if ann.format == 'json' and ann.data:
                                translation_obj = ann
                                break
                
                # 如果配置中没有参考翻译文本，则使用翻译对象的默认值
                if not preset_trans and translation_obj:
                    preset_trans = translation_obj.data.get('text') if translation_obj.data else None
                
                # 设置最终的参考文本
                reference_asr_text = asr_ref
                reference_translation_text = preset_trans
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error getting reference texts: {e}")
        
        # 4. 获取执行结果 (可能有多个设备/API的结果，这里取最新的一个或全部)
        results = TestResult.query.filter_by(task_id=task_id, test_case_id=case_id).all()
        
        processed_results = []
        for result in results:
            # 获取设备名称或 API 名称
            device_name = None
            api_name = None
            if result.device_id:
                from backend.models.models import Device
                device = db.session.get(Device, result.device_id)
                if device:
                    device_name = device.name
            
            if result.api_id:
                from backend.models.models import API
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
                "error_message": dim.error_message
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
                "reference_asr_text": reference_asr_text,
                "reference_translation_text": reference_translation_text,
                "result_data": result.result_data,
                "error_message": result.error_message,
                "dimensions": dim_data,
                "created_at": result.created_at.isoformat()
            })
        
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
            "reference_asr_text": reference_asr_text,
            "reference_translation_text": reference_translation_text,
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
        
        # 获取参考文本
        reference_asr_text = None
        reference_translation_text = None
        if case_info and case_info.config:
            try:
                config = case_info.config
                if isinstance(config, str):
                    import json
                    config = json.loads(config)
                
                audio_id = None
                if isinstance(config, dict):
                    if 'audioId' in config:
                        audio_id = config['audioId']
                    elif 'audio_id' in config:
                        audio_id = config['audio_id']
                    elif 'audio' in config:
                        if isinstance(config['audio'], dict) and 'id' in config['audio']:
                            audio_id = config['audio']['id']
                    elif 'audioConfig' in config:
                        if isinstance(config['audioConfig'], dict):
                            audio_config = config['audioConfig']
                            if 'audioId' in audio_config:
                                audio_id = audio_config['audioId']
                            elif 'audio_id' in audio_config:
                                audio_id = audio_config['audio_id']
                
                task = db.session.get(Task, task_id)
                test_type = task.type if task else 'api'
                asr_ref = ReferenceParamsGenerator.get_reference_text(config, 'asr_reference_text', test_type)
                preset_trans = ReferenceParamsGenerator.get_reference_text(config, 'translation_reference_text', test_type)
                
                if audio_id and not asr_ref:
                    from backend.models.models import Audio
                    audio = db.session.get(Audio, audio_id)
                    if audio:
                        asr_ref = audio.asr_text
                
                if audio_id and not preset_trans:
                    from backend.models.models import AudioAnnotation
                    td_id = config.get('translation_direction_id') if isinstance(config, dict) else None
                    annotations = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False).all()
                    if td_id:
                        for ann in annotations:
                            if ann.target_language:
                                direction = TranslationDirection.query.get(td_id)
                                if direction and ann.target_language == direction.target_language:
                                    preset_trans = ann.data.get('text') if ann.data else None
                                    break
                    else:
                        for ann in annotations:
                            if ann.format == 'json' and ann.data:
                                preset_trans = ann.data.get('text')
                                break
                
                reference_asr_text = asr_ref
                reference_translation_text = preset_trans
            except Exception:
                pass
        
        # 获取执行结果
        results = TestResult.query.filter_by(task_id=task_id, test_case_id=case_id).all()
        
        processed_results = []
        for result in results:
            device_name = None
            api_name = None
            if result.device_id:
                from backend.models.models import Device
                device = db.session.get(Device, result.device_id)
                if device:
                    device_name = device.name
            
            if result.api_id:
                from backend.models.models import API
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
                    "error_message": dim.error_message
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
                "reference_asr_text": reference_asr_text,
                "reference_translation_text": reference_translation_text,
                "result_data": result.result_data,
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
                updated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
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

            from backend.utils.stats_cache import refresh_stats_cache
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
                from backend.models.models import TaskCase, TestResult
                
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
                from backend.models.models import Device
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
            from backend.models.models import TaskCase

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

            retry_case_ids = [tc.test_case_id for tc in retry_cases]

            cleanup_errors = TaskController._cleanup_case_results(task_id, retry_case_ids)
            if cleanup_errors:
                return error_response(
                    f"清理旧结果失败: {'; '.join(cleanup_errors)}",
                    code=ErrorCode.OPERATION_FAILED
                )

            # 3. 重置 TaskCase 状态
            for tc in retry_cases:
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

            # 5. 调用执行引擎启动任务
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
                    # status字段只能是completed或failed，不能是pending
                    tc.status = 'failed'  # 重试时先标记为失败，执行时会重新评估
                    tc.execution_status = 'pending'
                    tc.evaluation_status = 'pending'
                    tc.started_at = None
                    tc.completed_at = None
                    tc.duration = None
                    tc.error_message = None

                    cleanup_errors = TaskController._cleanup_case_results(task_id, [case_id])
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
            task.updated_at = datetime.now(timezone(timedelta(hours=8)))
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
                        download_name=f"tasks_export_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d%H%M%S')}.xlsx"
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

                    # 注册中文字体 (Windows 常用路径)
                    font_path = "C:\\Windows\\Fonts\\msyh.ttc" # 微软雅黑
                    if not os.path.exists(font_path):
                        font_path = "C:\\Windows\\Fonts\\simsun.ttc" # 宋体
                    
                    font_name = "CustomFont"
                    if os.path.exists(font_path):
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
                        download_name=f"tasks_export_{datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d%H%M%S')}.pdf"
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
        from backend.utils.device_result_reextractor import get_device_result_reextractor

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
                from backend.utils.execution_engine import execution_engine as ee
                stop_future = ee.api_task_pool.submit(
                    execution_engine.control_task,
                    app, task_id, 'stop'
                )
                try:
                    stop_future.result(timeout=5)
                except Exception:
                    pass
            
            # 2. 从任务队列中移除任务
            execution_engine.remove_from_queue(task_id)
            
            # 3. 标记任务为已删除
            task.deleted = True
            db.session.commit()

            from backend.utils.stats_cache import refresh_stats_cache
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
        from backend.models.models import TestResult, TaskDevice, TaskAPI, TaskCase, TaskTag, TaskMergeRelation

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
