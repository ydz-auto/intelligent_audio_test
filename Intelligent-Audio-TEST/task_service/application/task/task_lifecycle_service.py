# -*- coding: utf-8 -*-
"""TaskLifecycleService — 任务生命周期应用服务。

从 TaskCrudService 拆分而来，专门处理任务运行时生命周期操作：
- start: 启动任务
- retry: 重试失败用例
- control: 运行时控制（暂停/恢复/停止/跳过/单用例重试）
- stop: 停止任务
- rextract: 重新提取设备输出

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 生命周期操作内部调用 execution_engine
- 通过 task_repository 访问 DB，不直接持有 session
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from shared.utils.result_data_store import load_full_result_data

from task_service.infrastructure.persistence.task_repository import task_repository

logger = logging.getLogger(__name__)


class TaskLifecycleService:
    """任务生命周期应用服务。"""

    def start(self, task_id: int) -> dict:
        """启动任务。"""
        try:
            # 幂等/状态校验：通过仓储获取 Task ORM
            task = task_repository.get_task_for_start_check(task_id)
            if task is None:
                return {'success': False, 'message': '任务 ID 不存在', 'data': None, 'code': 404}

            # 幂等：已在运行或排队
            if task.status in ('running', 'queued'):
                return {
                    'success': True,
                    'message': '任务已在运行中' if task.status == 'running' else '任务已在队列中',
                    'data': {'id': task.id, 'status': task.status},
                }

            if task.status not in ['pending', 'failed', 'stopped', 'completed']:
                return {'success': False, 'message': '非法的任务状态转换操作', 'data': None, 'code': 400}

            # 重置失败/停止状态（原子提交）
            if task.status in ['failed', 'stopped']:
                if not task_repository.reset_task_for_start(task_id):
                    return {'success': False, 'message': '任务 ID 不存在', 'data': None, 'code': 404}

            # 环境预检
            can_start, err_msg = task_repository.check_environment_for_start(task_id)
            if not can_start:
                return {'success': False, 'message': err_msg, 'data': None, 'code': 400}

            # 调用执行引擎
            from task_service.core.execution_engine import execution_engine
            success, message = execution_engine.start_task(None, task.id)

            if not success:
                return {'success': False, 'message': message, 'data': None, 'code': 500}

            time_estimate = execution_engine.event_manager.calculate_time_estimate(task)

            return {
                'success': True,
                'message': message,
                'data': {
                    'task_id': str(task.id),
                    'start_time': int(datetime.utcnow().timestamp() * 1000),
                    'status': 'queued' if '队列' in message else 'running',
                    'expected_total_time': time_estimate.get('expected_total_time'),
                    'expected_complete_time': time_estimate.get('expected_complete_time'),
                },
            }
        except Exception as e:
            logger.error(f"启动任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def retry(self, task_id: int) -> dict:
        """重新执行失败或未完成的用例。"""
        try:
            task = task_repository.get_task_orm(task_id)
            if task is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}

            if task.status in ['running', 'paused', 'queued']:
                from task_service.core.execution_engine import execution_engine
                execution_engine.control_task(None, task_id, 'stop')

            # 查询需要重试的用例
            retry_cases = task_repository.find_retry_cases(task_id)

            if not retry_cases:
                return {'success': True, 'message': '没有需要重试的用例', 'data': None}

            completed_cases = [tc for tc in retry_cases if tc.execution_status == 'completed']
            incomplete_cases = [tc for tc in retry_cases if tc.execution_status != 'completed']

            # 清理旧结果
            if completed_cases:
                task_repository.cleanup_case_results(
                    task_id, [tc.test_case_id for tc in completed_cases], preserve_test_result=True
                )
            if incomplete_cases:
                task_repository.cleanup_case_results(
                    task_id, [tc.test_case_id for tc in incomplete_cases], preserve_test_result=False
                )

            # 重置 TaskCase 状态（内存修改，稍后提交）
            for tc in completed_cases:
                tc.status = 'pending'
                tc.evaluation_status = 'pending'
                tc.error_message = None
                task_repository.commit_task_case(tc)
            for tc in incomplete_cases:
                tc.status = 'failed'
                tc.execution_status = 'pending'
                tc.evaluation_status = 'pending'
                tc.started_at = None
                tc.completed_at = None
                tc.duration = None
                tc.error_message = None
                task_repository.commit_task_case(tc)

            # 重新统计并重置任务状态
            task_repository.recount_task_cases(task_id)
            task_repository.reset_task_to_pending(task_id)

            # 触发已执行完成用例的重新评估
            if completed_cases:
                self._trigger_reevaluate(task_id, completed_cases)

            # 启动任务
            from task_service.core.execution_engine import execution_engine
            success, message = execution_engine.start_task(None, task.id)

            if not success:
                return {'success': False, 'message': message, 'data': None, 'code': 500}

            return {
                'success': True,
                'message': '重试任务已启动',
                'data': {'task_id': str(task.id), 'status': 'running'},
            }
        except Exception as e:
            logger.error(f"重试任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def control(self, task_id: int, data: dict) -> dict:
        """任务运行时控制。"""
        try:
            action = data.get('action')
            case_id = data.get('case_id')

            if action == 'retry' and not case_id:
                return self.retry(task_id)

            task = task_repository.get_task_orm(task_id)
            if task is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}

            # 单用例控制
            if action in ['skip', 'retry'] and case_id:
                tc = task_repository.find_task_case(task_id, case_id)
                if tc is None:
                    return {'success': False, 'message': '未找到指定用例关联', 'data': None, 'code': 404}

                if tc.execution_status in ['queued', 'running'] or tc.evaluation_status == 'running':
                    return {'success': False, 'message': '用例执行中不允许此操作', 'data': None, 'code': 400}

                if action == 'skip':
                    tc.status = 'skipped'
                    tc.execution_status = 'stopped'
                    tc.evaluation_status = 'stopped'
                    tc.error_message = tc.error_message or '用例被手动跳过'
                    task_repository.commit_task_case(tc)
                else:  # retry
                    if tc.execution_status == 'completed':
                        tc.status = 'pending'
                        tc.evaluation_status = 'pending'
                        tc.error_message = None
                        task_repository.commit_task_case(tc)
                        task_repository.cleanup_case_results(
                            task_id, [case_id], preserve_test_result=True
                        )
                    else:
                        tc.status = 'failed'
                        tc.execution_status = 'pending'
                        tc.evaluation_status = 'pending'
                        tc.started_at = None
                        tc.completed_at = None
                        tc.duration = None
                        tc.error_message = None
                        task_repository.commit_task_case(tc)
                        task_repository.cleanup_case_results(
                            task_id, [case_id], preserve_test_result=False
                        )

                    task_repository.recount_task_cases(task_id)
                    task_repository.reset_task_to_pending(task_id)

                # retry 已执行完成的用例，触发重新评估
                if action == 'retry' and tc.execution_status == 'completed':
                    self._trigger_reevaluate(task_id, [tc])

                # 如果任务当前没在运行，且是 retry，则尝试重启
                task_status = task_repository.get_task_orm(task_id)
                if action == 'retry' and task_status and task_status.status not in ['running', 'paused']:
                    from task_service.core.execution_engine import execution_engine
                    execution_engine.start_task(None, task_id)

                return {'success': True, 'message': f"Action '{action}' executed successfully", 'data': None}

            # 全局任务控制
            from task_service.core.execution_engine import execution_engine
            success, message = execution_engine.control_task(None, task_id, action)
            if not success:
                return {'success': False, 'message': message, 'data': None, 'code': 400}

            updated = task_repository.get_task_orm(task_id)
            return {
                'success': True,
                'message': f"Action '{action}' executed successfully",
                'data': {'task_id': str(task_id), 'status': updated.status if updated else None},
            }
        except Exception as e:
            logger.error(f"控制任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def stop(self, task_id: int) -> dict:
        """停止任务。"""
        try:
            task = task_repository.find_task_for_stop(task_id)
            if task is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}

            from task_service.core.execution_engine import execution_engine
            success, message = execution_engine.control_task(None, task_id, 'stop')
            if not success:
                return {'success': False, 'message': message, 'data': None, 'code': 400}
            return {'success': True, 'message': message, 'data': None}
        except Exception as e:
            logger.error(f"停止任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def rextract(self, task_id: int, data: dict) -> dict:
        """重新提取设备输出。"""
        try:
            execution_status = data.get('execution_status', 'completed')
            evaluation_status = data.get('evaluation_status')

            task = task_repository.find_task_for_reextract(task_id)
            if task is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}
            if task.status not in ['completed', 'failed', 'stopped', 'paused', 'skipped']:
                return {'success': False, 'message': '只有已完成/失败/停止/暂停/跳过的任务才能重新提取', 'data': None, 'code': 400}

            # 通过 gRPC 调用 device_service 的重新提取服务
            from shared.clients.grpc_clients import get_device_result_service_stub
            from shared.proto import device_service_pb2 as e2e_pb
            from shared.utils.grpc_json import loads as _loads
            import json as _json

            stub = get_device_result_service_stub()
            reextract_config = {
                'execution_status': execution_status,
                'evaluation_status': evaluation_status,
            }
            resp = stub.ReextractResult(e2e_pb.ReextractResultRequest(
                task_id=str(task_id),
                reextract_config=_json.dumps(reextract_config),
            ))
            result = _loads(resp.data, {}) if resp.success else {}

            if resp.success:
                message = result.get('message', '重新提取成功')
                reextracted_cases = result.get('reextracted_cases', [])
                return {
                    'success': True,
                    'message': message,
                    'data': {
                        'task_id': task_id,
                        'reextracted_count': len(reextracted_cases),
                        'reextracted_cases': reextracted_cases,
                    },
                }
            fail_msg = result.get('message') or resp.message or '未知错误'
            return {'success': False, 'message': f"重新提取失败: {fail_msg}", 'data': None, 'code': 400}
        except Exception as e:
            logger.error(f"重新提取失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 内部辅助 ====================

    def _trigger_reevaluate(self, task_id, completed_cases):
        """触发已执行完成用例的重新评估。

        注意：此方法内部涉及跨域查询 TestCase / TestResult，后续 gRPC 改造。
        """
        try:
            from shared.clients.grpc_clients import get_evaluation_service_stub
            from shared.proto import evaluation_service_pb2 as eval_pb

            stub = get_evaluation_service_stub()
            test_type = task_repository.get_task_type(task_id)

            for tc in completed_cases:
                test_case_id = tc.test_case_id
                try:
                    # 跨域查询 TestResult（后续 gRPC 改造）
                    result = task_repository.get_test_result_for_reevaluate(task_id, test_case_id)

                    if not result:
                        tc.evaluation_status = 'failed'
                        tc.error_message = '未找到执行结果，无法重新评估'
                        task_repository.commit_task_case(tc)
                        continue

                    if not result.algorithm_result:
                        tc.evaluation_status = 'failed'
                        tc.error_message = '执行结果无 algorithm_result，无法重新评估'
                        task_repository.commit_task_case(tc)
                        continue

                    algo_result = result.algorithm_result or {}
                    while isinstance(algo_result, str):
                        try:
                            algo_result = json.loads(algo_result)
                        except (json.JSONDecodeError, ValueError):
                            algo_result = {}
                    if not isinstance(algo_result, dict):
                        algo_result = {}

                    full_data = load_full_result_data(
                        result.result_data, getattr(result, 'result_data_path', None)
                    )
                    reference_params = full_data.get('adjusted_reference_params', []) if full_data else []

                    # 跨域查询 TestCase（后续 gRPC 改造）
                    test_case = task_repository.get_test_case_orm(test_case_id)
                    algorithm_type = (
                        test_case.algorithm_type
                        if test_case and test_case.algorithm_type
                        else 'translation'
                    )

                    if algo_result and 'rounds' in algo_result:
                        resp = stub.ReevaluateMultiRound(eval_pb.ReevaluateMultiRoundRequest(
                            task_id=str(task_id),
                            result_json=json.dumps(result.id, ensure_ascii=False, default=str),
                            test_case_id=str(test_case_id or ''),
                            algorithm_result=json.dumps(algo_result or {}, ensure_ascii=False, default=str),
                            test_type=test_type or 'api',
                            algorithm_type=algorithm_type or 'translation',
                        ))
                        if not resp.success:
                            raise RuntimeError(resp.message)
                    else:
                        resp = stub.ReevaluateSingle(eval_pb.ReevaluateSingleRequest(
                            task_id=str(task_id),
                            result_id=str(result.id or ''),
                            test_case_id=str(test_case_id or ''),
                            algorithm_result=json.dumps(algo_result or {}, ensure_ascii=False, default=str),
                            reference_params=json.dumps(reference_params or {}, ensure_ascii=False, default=str),
                            test_type=test_type or 'api',
                            algorithm_type=algorithm_type or 'translation',
                        ))
                        if not resp.success:
                            raise RuntimeError(resp.message)
                except Exception as e:
                    import traceback
                    tc.evaluation_status = 'failed'
                    tc.error_message = f'重新评估触发失败: {str(e)}'
                    task_repository.commit_task_case(tc)
                    logger.warning(f'触发重新评估失败: task_id={task_id}, test_case_id={test_case_id}, error={e}, traceback={traceback.format_exc()}')
        except Exception as e:
            logger.error(f"_trigger_reevaluate 执行失败: {e}", exc_info=True)


# 模块级单例
task_lifecycle_service = TaskLifecycleService()
