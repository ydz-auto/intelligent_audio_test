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
from shared.utils.json_utils import deserialize_algorithm_result
from shared.utils.status_utils import derive_task_case_status
from shared.models.common_enums import TestType
# INT-302 重执行范围模式（枚举化，拒绝魔法字符串）：缺省 all 保持整任务语义
from shared.models.common_enums import RetryScopeMode
from shared.utils.status_constants import (
    TaskStatus, ExecutionStatus, EvaluationStatus, TaskCaseStatus, ACTIVE_EXECUTION_STATUSES,
    FINISHED_TASK_STATUSES,
)

from task_service.infrastructure.persistence.task_repository import task_repository

logger = logging.getLogger(__name__)

# INT-305：用例移除留痕常量（与仓储层 _REMOVED_CASE_MESSAGE 同值，软删行判定依据）
REMOVED_CASE_MESSAGE = '用例已被移除'


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
            if task.status in (TaskStatus.RUNNING, TaskStatus.QUEUED):
                return {
                    'success': True,
                    'message': '任务已在运行中' if task.status == TaskStatus.RUNNING else '任务已在队列中',
                    'data': {'id': task.id, 'status': task.status},
                }

            if task.status not in [TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.STOPPED, TaskStatus.COMPLETED]:
                return {'success': False, 'message': '非法的任务状态转换操作', 'data': None, 'code': 400}

            # 重置失败/停止状态（原子提交）
            if task.status in [TaskStatus.FAILED, TaskStatus.STOPPED]:
                if not task_repository.reset_task_for_start(task_id):
                    return {'success': False, 'message': '任务 ID 不存在', 'data': None, 'code': 404}

            # 环境预检
            can_start, err_msg = task_repository.check_environment_for_start(task_id)
            if not can_start:
                return {'success': False, 'message': err_msg, 'data': None, 'code': 400}

            # 调用执行引擎
            from task_service.core.execution_engine import execution_engine
            success, message = execution_engine.start_task(task.id)

            if not success:
                return {'success': False, 'message': message, 'data': None, 'code': 500}

            time_estimate = execution_engine.event_manager.calculate_time_estimate(task)

            return {
                'success': True,
                'message': message,
                'data': {
                    'task_id': str(task.id),
                    'start_time': int(datetime.utcnow().timestamp() * 1000),
                    'status': TaskStatus.QUEUED if '队列' in message else TaskStatus.RUNNING,
                    'expected_total_time': time_estimate.get('expected_total_time'),
                    'expected_complete_time': time_estimate.get('expected_complete_time'),
                },
            }
        except Exception as e:
            logger.error(f"启动任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def retry(self, task_id: int, options: dict = None) -> dict:
        """重新执行失败或未完成的用例。

        INT-302：options 可选 {case_ids: [str], mode: 'selected'|'failed_only'|'all'}——
        selected 时仅重执行指定用例（状态机对齐既有 retry 语义：结果重置、
        队列重新入队）；failed_only 仅执行失败/评估失败用例；缺省 all 保持
        整任务语义（既有调用方零改动）。
        """
        options = options or {}
        mode = options.get('mode') or RetryScopeMode.ALL.value
        selected_case_ids = [str(c) for c in (options.get('case_ids') or [])]
        if mode == RetryScopeMode.SELECTED.value and not selected_case_ids:
            return {'success': False, 'message': '选择用例重执行时 case_ids 不能为空', 'data': None, 'code': 400}
        if mode not in (RetryScopeMode.ALL.value, RetryScopeMode.SELECTED.value, RetryScopeMode.FAILED_ONLY.value):
            return {'success': False, 'message': f'非法的重执行范围: {mode}', 'data': None, 'code': 400}

        try:
            task = task_repository.get_task_orm(task_id)
            if task is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}

            if task.status in [TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.QUEUED]:
                from task_service.core.execution_engine import execution_engine
                execution_engine.control_task(task_id, 'stop')

            # 查询需要重试的用例（整任务语义沿用 find_retry_cases；范围模式走 scoped 查询）
            if mode == RetryScopeMode.ALL.value:
                retry_cases = task_repository.find_retry_cases(task_id)
            else:
                retry_cases = task_repository.find_retry_cases_scoped(task_id, mode, selected_case_ids)

            if not retry_cases:
                return {'success': True, 'message': '没有需要重试的用例', 'data': None}

            completed_cases = [tc for tc in retry_cases if tc.execution_status == ExecutionStatus.COMPLETED]
            incomplete_cases = [tc for tc in retry_cases if tc.execution_status != ExecutionStatus.COMPLETED]

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
                tc.evaluation_status = EvaluationStatus.PENDING
                tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status)
                tc.error_message = None
                task_repository.commit_task_case(tc)
            for tc in incomplete_cases:
                tc.execution_status = ExecutionStatus.PENDING
                tc.evaluation_status = EvaluationStatus.PENDING
                tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status)
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
            success, message = execution_engine.start_task(task.id)

            if not success:
                return {'success': False, 'message': message, 'data': None, 'code': 500}

            return {
                'success': True,
                'message': '重试任务已启动',
                'data': {
                    'task_id': str(task.id),
                    'status': TaskStatus.RUNNING,
                    'retry_mode': mode,
                    'retry_case_count': len(retry_cases),
                },
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

                if tc.execution_status in ACTIVE_EXECUTION_STATUSES or tc.evaluation_status == EvaluationStatus.RUNNING:
                    return {'success': False, 'message': '用例执行中不允许此操作', 'data': None, 'code': 400}

                if action == 'skip':
                    tc.execution_status = ExecutionStatus.STOPPED
                    tc.evaluation_status = EvaluationStatus.STOPPED
                    tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status)
                    tc.error_message = tc.error_message or '用例被手动跳过'
                    task_repository.commit_task_case(tc)
                else:  # retry
                    if tc.execution_status == ExecutionStatus.COMPLETED:
                        tc.evaluation_status = EvaluationStatus.PENDING
                        tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status)
                        tc.error_message = None
                        task_repository.commit_task_case(tc)
                        task_repository.cleanup_case_results(
                            task_id, [case_id], preserve_test_result=True
                        )
                    else:
                        tc.execution_status = ExecutionStatus.PENDING
                        tc.evaluation_status = EvaluationStatus.PENDING
                        tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status)
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
                if action == 'retry' and tc.execution_status == ExecutionStatus.COMPLETED:
                    self._trigger_reevaluate(task_id, [tc])

                # 如果任务当前没在运行，且是 retry，则尝试重启
                task_status = task_repository.get_task_orm(task_id)
                if action == 'retry' and task_status and task_status.status not in [TaskStatus.RUNNING, TaskStatus.PAUSED]:
                    from task_service.core.execution_engine import execution_engine
                    execution_engine.start_task(task_id)

                return {'success': True, 'message': f"Action '{action}' executed successfully", 'data': None}

            # 全局任务控制
            from task_service.core.execution_engine import execution_engine
            success, message = execution_engine.control_task(task_id, action)
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
            success, message = execution_engine.control_task(task_id, 'stop')
            if not success:
                return {'success': False, 'message': message, 'data': None, 'code': 400}
            return {'success': True, 'message': message, 'data': None}
        except Exception as e:
            logger.error(f"停止任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def remove_case(self, task_id: int, case_id: str) -> dict:
        """移除任务用例（INT-305：执行详情模态窗删除用例，四阶段全允许）。

        按任务阶段分语义：
        - 待执行（pending/queued）：物理删除 TaskCase 行 + 引擎队列/领取摘除，
          计数重算；
        - 执行中（running/evaluating/reevaluating/paused）：置用例级中断信号
          （执行器轮次边界检测后收敛）→ 联动取消评估侧产出（复用 INT-308
          CancelEvaluation reason=case_deleted）→ 软删留痕 + TestResult excluded
          → 计数重算 → 中断事件推送；
        - 已完成/评估完成（completed/failed/stopped）：软删留痕 + TestResult
          excluded（保审计）→ 计数重算 → 触发报告重算。

        全程审计事件（操作人经 x-user-id metadata 透传，get_current_user_id 读取）。

        Returns:
            dict: {success, message, data, code?}
        """
        try:
            task = task_repository.get_task_orm(task_id)
            if task is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}

            tc = task_repository.find_task_case(task_id, case_id)
            if tc is None:
                return {'success': False, 'message': '未找到该任务关联的用例', 'data': None, 'code': 404}

            # 已移除留痕行幂等成功（重复删除不报错）
            if (tc.error_message or '') == REMOVED_CASE_MESSAGE:
                return {'success': True, 'message': '用例已被移除', 'data': {'removed': True, 'idempotent': True}}

            from shared.infrastructure.user_context import get_current_user_id
            operator_id = get_current_user_id()

            # 阶段语义判定（enum 化，拒绝魔法字符串集合裸写——复用状态集合常量）
            is_active_task = task.status in (TaskStatus.RUNNING, TaskStatus.QUEUED,
                                             TaskStatus.EVALUATING, TaskStatus.REEVALUATE_QUEUED,
                                             TaskStatus.REEVALUATING, TaskStatus.PAUSED)

            # 1. 执行中：先置用例级中断信号（执行器轮次边界/长阻塞点检测收敛）
            if is_active_task and tc.execution_status in ACTIVE_EXECUTION_STATUSES:
                from shared.utils import distributed_coordinator as _dc
                _dc.set_task_case_stop(task_id, case_id)

            # 2. 联动取消评估侧产出（INT-308 复用：case_deleted 命令语义信任请求方，
            #    评估已实际产出的用例返回 completed 由本侧标记 excluded）
            cancel_result = None
            if is_active_task:
                try:
                    from shared.clients.grpc_clients import cancel_case_evaluations
                    cancel_result = cancel_case_evaluations(
                        task_id, [case_id], reason='case_deleted')
                except Exception as e:
                    logger.warning("移除用例联动取消评估失败(不阻塞删除) task_id=%s case=%s: %s",
                                   task_id, case_id, e)

            # 3. 移除 TaskCase + 级联处置 TestResult（仓储内按有无结果分软删/物理删）
            removal = task_repository.remove_task_case(task_id, case_id, deleted_by_user_id=operator_id)
            if removal is None:
                return {'success': False, 'message': '未找到该任务关联的用例', 'data': None, 'code': 404}

            # 4. 计数重算（recount 按移除留痕行剔除口径）
            task_repository.recount_task_cases(task_id)

            # 5. 执行中：任务行 updated_by 留痕 + 唤醒等待线程推进收敛 + 进度推送
            if is_active_task:
                task_repository.touch_task_updated_by(task_id, operator_id)
                try:
                    from task_service.core.execution_engine import execution_engine
                    execution_engine.notify_case_completed(task_id)
                    task_repository.expire_progress_cache(task_id)
                    execution_engine._emit_progress(task_id, force=True)
                except Exception as e:
                    logger.warning("移除用例后推送进度失败(不阻塞删除) task_id=%s: %s", task_id, e)

            # 6. 终态任务：触发报告重算（report_service RegenerateTaskReport：
            #    重建时 valid_case_ids 以 TaskCase 现存行为准，被删用例自动剔除）
            report_requeued = False
            if task.status in FINISHED_TASK_STATUSES:
                report_requeued = self._trigger_report_recalculate(task_id)

            # 7. 审计事件（CASE_EVENTS / case_removed，操作人透传）
            self._publish_removal_audit(task_id, case_id, operator_id,
                                        removed_semantics=removal.get('purged', False),
                                        eval_cancel=cancel_result,
                                        report_requeued=report_requeued)

            logger.info("移除任务用例完成 task_id=%s case_id=%s operator=%s purged=%s report_requeued=%s",
                        task_id, case_id, operator_id, removal.get('purged'), report_requeued)
            return {
                'success': True,
                'message': '用例已移除',
                'data': {
                    'task_id': str(task_id),
                    'case_id': str(case_id),
                    'purged': removal.get('purged', False),
                    'report_requeued': report_requeued,
                    'operator_id': operator_id,
                },
            }
        except Exception as e:
            logger.error(f"移除任务用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def _trigger_report_recalculate(self, task_id: int) -> bool:
        """终态任务用例变更后触发报告重算（report_service 再生成）。

        经 report_service.ReportConfigService.RegenerateTaskReport RPC：
        报告不存在时幂等成功（no-op）；生成锁被持有时排队语义由
        report_service 内部去重锁承载。失败降级 WARNING（不阻塞删除主链，
        报告可手动重新生成）。
        """
        try:
            from task_service.infrastructure.acl.report_acl_repository import report_acl_repository
            return report_acl_repository.recalculate_task_report(task_id)
        except Exception as e:
            logger.warning("触发报告重算失败(降级跳过，可手动重生成) task_id=%s: %s", task_id, e)
            return False

    def _publish_removal_audit(self, task_id, case_id, operator_id,
                               removed_semantics, eval_cancel, report_requeued):
        """发布 case_removed 审计事件到 CASE_EVENTS（Redis 不可用时只打日志）。"""
        try:
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            event_bus = EventBus()
            event_bus.publish(
                EventChannel.CASE_EVENTS,
                EventType.CASE_REMOVED,
                {
                    'task_id': str(task_id),
                    'test_case_id': str(case_id),
                    'operator_id': operator_id,
                    'purged': bool(removed_semantics),
                    'eval_cancel': (eval_cancel or {}).get('data', {}),
                    'report_requeued': bool(report_requeued),
                    'removed_at': datetime.utcnow().isoformat() + 'Z',
                },
            )
        except Exception as e:
            logger.warning("发布用例移除审计事件失败 task_id=%s case=%s: %s", task_id, case_id, e)

    def rextract(self, task_id: int, data: dict) -> dict:
        """重新提取设备输出。"""
        try:
            execution_status = data.get('execution_status', ExecutionStatus.COMPLETED)
            evaluation_status = data.get('evaluation_status')

            task = task_repository.find_task_for_reextract(task_id)
            if task is None:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}
            if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED, TaskStatus.PAUSED, TaskStatus.SKIPPED]:
                return {'success': False, 'message': '只有已完成/失败/停止/暂停/跳过的任务才能重新提取', 'data': None, 'code': 400}

            # 通过 ACL 仓储调用 device_service 的重新提取服务
            from task_service.infrastructure.acl.evaluation_acl_repository import evaluation_acl_repository
            _eval_repo = evaluation_acl_repository
            result = _eval_repo.reextract_result(
                task_id=task_id,
                execution_status=execution_status,
                evaluation_status=evaluation_status,
            )

            if result['success']:
                data = result['data']
                message = data.get('message', '重新提取成功')
                reextracted_cases = data.get('reextracted_cases', [])
                return {
                    'success': True,
                    'message': message,
                    'data': {
                        'task_id': task_id,
                        'reextracted_count': len(reextracted_cases),
                        'reextracted_cases': reextracted_cases,
                    },
                }
            fail_msg = result['data'].get('message') or result['message'] or '未知错误'
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
            from task_service.infrastructure.acl.evaluation_acl_repository import evaluation_acl_repository
            from shared.models.common_enums import DeviceType
            _eval_repo = evaluation_acl_repository

            for tc in completed_cases:
                test_case_id = tc.test_case_id
                try:
                    # 评估口径值由用例级 device_type 派生（差异#2 收尾：
                    # task.type 已废弃；gRPC 契约字段 test_type 保留）
                    test_type = (
                        TestType.E2E.value
                        if (tc.device_type or DeviceType.PHYSICAL.value) == DeviceType.PHYSICAL.value
                        else TestType.API.value
                    )

                    # 跨域查询 TestResult（后续 gRPC 改造）
                    result = task_repository.get_test_result_for_reevaluate(task_id, test_case_id)

                    if not result:
                        tc.evaluation_status = EvaluationStatus.FAILED
                        tc.error_message = '未找到执行结果，无法重新评估'
                        task_repository.commit_task_case(tc)
                        continue

                    if not result.algorithm_result:
                        tc.evaluation_status = EvaluationStatus.FAILED
                        tc.error_message = '执行结果无 algorithm_result，无法重新评估'
                        task_repository.commit_task_case(tc)
                        continue

                    algo_result = deserialize_algorithm_result(result.algorithm_result or {})

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
                        resp = _eval_repo.reevaluate_multi_round(
                            task_id=task_id,
                            result_id=result.id,
                            test_case_id=test_case_id,
                            algorithm_result=algo_result,
                            test_type=test_type or 'api',
                            algorithm_type=algorithm_type or 'translation',
                        )
                        if not resp.success:
                            raise RuntimeError(resp.message)
                    else:
                        resp = _eval_repo.reevaluate_single(
                            task_id=task_id,
                            result_id=result.id,
                            test_case_id=test_case_id,
                            algorithm_result=algo_result,
                            reference_params=reference_params,
                            test_type=test_type or 'api',
                            algorithm_type=algorithm_type or 'translation',
                        )
                        if not resp.success:
                            raise RuntimeError(resp.message)
                except Exception as e:
                    import traceback
                    tc.evaluation_status = EvaluationStatus.FAILED
                    tc.error_message = f'重新评估触发失败: {str(e)}'
                    task_repository.commit_task_case(tc)
                    logger.warning(f'触发重新评估失败: task_id={task_id}, test_case_id={test_case_id}, error={e}, traceback={traceback.format_exc()}')
        except Exception as e:
            logger.error(f"_trigger_reevaluate 执行失败: {e}", exc_info=True)


# 模块级单例
task_lifecycle_service = TaskLifecycleService()
