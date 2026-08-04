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


class TaskLifecycleService:
    """任务生命周期 Service（CQRS Lifecycle Side）。

    承载 TaskController 中任务启动/重试/控制/重新提取/停止/合并等方法，
    以及私有辅助 _cleanup_case_results / _trigger_reevaluate，保持原有逻辑不变。
    """

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
                    oss_keys = storage.list_objects('case_result', prefix=oss_prefix)
                    for oss_key in oss_keys:
                        storage.delete(f'case_result/{oss_key}')
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

    # 启动任务
    @staticmethod
    def start(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("任务 ID 不存在", code=ErrorCode.NOT_FOUND, http_code=404)

        # 任务已在运行或排队中，直接返回成功（幂等）
        # 场景：前端创建任务后，调度器已自动将其启动为 running/queued，
        # 此时前端再调 /start 应幂等返回成功，而非 400 非法状态
        if task.status in ('running', 'queued'):
            return success_response({
                "id": task.id,
                "status": task.status,
                "message": "任务已在运行中" if task.status == 'running' else "任务已在队列中"
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
            app = None
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
                app = None
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
                errs = TaskLifecycleService._cleanup_case_results(
                    task_id, [tc.test_case_id for tc in completed_cases], preserve_test_result=True
                )
                if errs:
                    cleanup_errors = (cleanup_errors or []) + errs
            if incomplete_cases:
                errs = TaskLifecycleService._cleanup_case_results(
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
                TaskLifecycleService._trigger_reevaluate(task_id, completed_cases)

            # 6. 调用执行引擎启动任务（处理未执行完成的用例 + 等待所有评估完成）
            app = None
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
                return TaskLifecycleService.retry(task_id)

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

                        cleanup_errors = TaskLifecycleService._cleanup_case_results(task_id, [case_id], preserve_test_result=True)
                    else:
                        # 未执行完成的用例：完全重置，重新执行
                        tc.status = 'failed'
                        tc.execution_status = 'pending'
                        tc.evaluation_status = 'pending'
                        tc.started_at = None
                        tc.completed_at = None
                        tc.duration = None
                        tc.error_message = None

                        cleanup_errors = TaskLifecycleService._cleanup_case_results(task_id, [case_id], preserve_test_result=False)

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
                    TaskLifecycleService._trigger_reevaluate(task_id, [tc])

                # 如果任务当前没在运行，且是 retry 操作，则尝试重新启动任务
                if action == 'retry' and task.status not in ['running', 'paused']:
                    app = None
                    execution_engine.start_task(app, task_id)

                return success_response(None, f"Action '{action}' executed successfully")

            # 处理全局任务控制 (pause/resume/stop)
            app = None
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

    # 重新提取设备输出
    @staticmethod
    def rextract(task_id):
        from pydantic import BaseModel, Field
        # 跨服务调用：通过 gRPC DeviceResultService 重新提取设备结果
        from api_gateway.infrastructure.grpc_proxies import get_device_result_reextractor

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
            app = None
            success, message = execution_engine.control_task(app, task_id, 'stop')
            if not success:
                return error_response(message, code=ErrorCode.OPERATION_FAILED, http_code=400)
            return success_response(None, message)
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
