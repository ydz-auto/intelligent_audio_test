# -*- coding: utf-8 -*-
"""用例与任务状态推进混入

负责评估完成后 TaskCase/Task 的状态判定与推进：
完成度检查、最终状态应用、事件发布（事件驱动）与 gRPC 同步回传。
"""
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskStatus, ACTIVE_EVALUATION_STATUSES,
)
from shared.models.common_enums import TestType
from evaluation_service.infrastructure.acl import task_acl_repository


class ResultStatusMixin:
    """TaskCase/Task 状态推进方法"""

    def update_task_case_status(self, result_id, current_result_all_completed, task_id, test_case_id, test_type=None):
        """
        更新TaskCase的状态。在多设备/多API执行时，需确保所有结果都评估完成后再更新最终状态。

        P1.4 改造：所有 Task/TaskCase/TaskDevice/TaskAPI/TestCase/TestResult 的访问
        改为通过 task_acl_repository (gRPC) 调 task_service。
        注意：跨服务调用无原子事务，失败时通过日志告警。

        Args:
            result_id: 测试结果ID
            current_result_all_completed: 当前结果是否全部完成
            task_id: 任务ID
            test_case_id: 用例ID
            test_type: 测试类型 (api 或 e2e)，用于筛选对应类型的维度
        """
        try:
            # 1. 获取任务信息以确定预期结果数量（P1.4: gRPC）
            task = task_acl_repository.get_task_by_id(task_id)
            if not task:
                return

            # 2. 获取预期结果数量（P1.4: gRPC）
            expected_count = self._get_expected_result_count(task_id, task)

            # 3. 获取该用例目前已生成的所有测试结果（P1.4: gRPC）
            all_results = task_acl_repository.get_test_results_by_task_and_case(
                task_id=task_id, test_case_id=str(test_case_id)
            )

            # 4. 获取用例配置中预期的评估维度总数（P1.4: gRPC）
            expected_dim_count = self._get_expected_dim_count(test_case_id)

            # 5. 检查是否所有预期结果都已采集并完成评估
            case_all_finished, case_any_failed = self._check_all_results_completed(
                task_id, test_case_id, expected_count, expected_dim_count, all_results
            )

            if not case_all_finished:
                return

            # 6. 只有当维度结果搜集全且都评估完成了，才更新最终状态
            new_evaluation_status = EvaluationStatus.FAILED if case_any_failed else EvaluationStatus.COMPLETED
            new_status = derive_task_case_status(ExecutionStatus.COMPLETED, new_evaluation_status)
            self._apply_final_status(task_id, test_case_id, new_status, new_evaluation_status, task)
        except Exception as e:
            self._log(
                level='ERROR',
                category='database',
                content=f"更新TaskCase状态失败: {str(e)}",
                task_id=task_id,
                test_case_id=test_case_id
            )

    def _get_expected_result_count(self, task_id, task):
        """获取预期结果数量（P1.4: gRPC）"""
        expected_count = 0
        if task.type == TestType.E2E.value:
            devices = task_acl_repository.get_task_devices(task_id=task_id)
            expected_count = len(devices)
        else:
            # API 任务通常按选中的 API 数量执行
            apis = task_acl_repository.get_task_apis(task_id=task_id)
            expected_count = len(apis)

        # 兜底逻辑：如果未找到关联，至少预期 1 个结果
        if expected_count == 0:
            expected_count = 1
        return expected_count

    def _get_expected_dim_count(self, test_case_id):
        """获取预期维度数量（从config解析）（P1.4: gRPC 读 TestCase）"""
        test_case = task_acl_repository.get_test_case_detail(str(test_case_id))
        expected_dim_count = 0
        if test_case and test_case.config:
            config = test_case.config
            # 从 rounds[].evaluation.dimensions 读取单轮维度
            # 从 config.dimensions 读取多轮聚合维度
            # 合并两者用于统计预期维度总数
            dim_config = self._collect_dim_config(config)
            all_dim_ids = []

            for item in dim_config:
                dim_id = item.get('id') if isinstance(item, dict) else item
                if dim_id:
                    all_dim_ids.append(dim_id)

            # 仅统计数据库中启用且存在的维度（自有 PO，本地查询）
            if all_dim_ids:
                unique_dim_ids = list(set(all_dim_ids))
                expected_dim_count = self._count_enabled_dimensions(unique_dim_ids)
        return expected_dim_count

    @staticmethod
    def _collect_dim_config(config):
        """合并 rounds[].evaluation.dimensions 与 config.dimensions（按维度ID去重）"""
        dim_config = []
        seen_ids = set()
        rounds = config.get('rounds', [])
        if rounds and isinstance(rounds, list):
            for round_item in rounds:
                if isinstance(round_item, dict):
                    evaluation = round_item.get('evaluation', {})
                    if isinstance(evaluation, dict):
                        round_dims = evaluation.get('dimensions', [])
                        for d in round_dims:
                            dim_id = d.get('id') if isinstance(d, dict) else d
                            if dim_id and dim_id not in seen_ids:
                                seen_ids.add(dim_id)
                                dim_config.append(d)
        top_dims = config.get('dimensions', [])
        for d in top_dims:
            dim_id = d.get('id') if isinstance(d, dict) else d
            if dim_id and dim_id not in seen_ids:
                seen_ids.add(dim_id)
                dim_config.append(d)
        return dim_config

    @staticmethod
    def _count_enabled_dimensions(unique_dim_ids):
        """统计数据库中启用且存在的维度数量（自有 PO，本地查询）"""
        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.orm_models import Dimension
        local_db_session = get_db_session()
        try:
            return local_db_session.query(Dimension).filter(
                Dimension.id.in_(unique_dim_ids),
                Dimension.status == True  # noqa: E712
            ).count()
        finally:
            local_db_session.close()

    def _check_all_results_completed(self, task_id, test_case_id, expected_count, expected_dim_count, all_results):
        """检查所有结果是否完成评估，返回 (case_all_finished, case_any_failed)

        P1.4: all_results 是 dict 列表（来自 gRPC），TestResultDimension 仍本地查询（自有 PO）
        """
        if len(all_results) < expected_count:
            self._log(
                level='DEBUG',
                category='database',
                content=f"用例 {test_case_id} 结果未全 (已采集: {len(all_results)}/{expected_count})，暂不更新状态",
                task_id=task_id,
                test_case_id=test_case_id
            )
            return False, False

        case_all_finished = True
        case_any_failed = False

        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
        local_db_session = get_db_session()
        try:
            for res in all_results:
                res_id = res.id
                # P1.4: TestResultDimension 是本服务自有 PO，本地查询
                dims = local_db_session.query(TestResultDimension).filter_by(test_result_id=res_id).all()

                # 维度记录数量不足，说明评估服务还没创建完所有维度的记录
                if len(dims) < expected_dim_count:
                    self._log(
                        level='DEBUG',
                        module='evaluation',
                        category='database',
                        content=f"用例 {test_case_id} 结果 {res_id} 维度未全 ({len(dims)}/{expected_dim_count})，继续等待",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    case_all_finished = False
                    break

                # 检查这个 TestResult 的所有维度是否都评估完成
                res_finished = True
                res_failed = False
                for dim in dims:
                    # 如果有任何维度还在进行中，说明这个 TestResult 还没完成
                    if dim.evaluation_status in ACTIVE_EVALUATION_STATUSES:
                        res_finished = False
                        break
                    # 如果有任何维度评估失败，这个 TestResult 就是失败的
                    if dim.evaluation_status == EvaluationStatus.FAILED:
                        res_failed = True

                # 如果这个 TestResult 还没完成，整体也不能算完成
                if not res_finished:
                    case_all_finished = False
                # 如果这个 TestResult 失败了，整体就标记为失败
                if res_failed:
                    case_any_failed = True
        finally:
            local_db_session.close()

        return case_all_finished, case_any_failed

    def _apply_final_status(self, task_id, test_case_id, new_status, new_evaluation_status, task):
        """应用最终状态

        P1.4: 通过 gRPC 更新 TaskCase 和 Task
        事件驱动改造: 同时发布 CaseEvaluated 事件到 Redis 事件总线，
        消费方（task_service）订阅后更新状态，替代 gRPC 同步回传的强依赖。
        gRPC 调用保留作为同步路径，事件作为异步通知补充。
        """
        # 更新TaskCase状态（P1.4: 通过 gRPC）
        from evaluation_service.infrastructure.evaluation_mixin import update_task_case_status_in_db
        update_count = update_task_case_status_in_db(
            None, task_id, test_case_id, new_status, new_evaluation_status
        )

        self._log(
            level='INFO',
            category='database',
            content=f"所有设备/API评估完成，更新TaskCase状态: id={test_case_id}, status={new_status}, 影响行数: {update_count}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 发布用例评估完成事件到事件总线（异步通知 task_service）
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        is_success = new_evaluation_status == EvaluationStatus.COMPLETED
        EventBus().publish(
            EventChannel.CASE_EVENTS,
            EventType.CASE_EVALUATION_COMPLETED if is_success else EventType.CASE_FAILED,
            {
                'task_id': str(task_id),
                'test_case_id': str(test_case_id),
                'evaluation_status': new_evaluation_status,
                'case_status': new_status,
                'success': is_success,
            }
        )

        # P1.4: 通过 gRPC 更新 Task 状态（同步路径，保留兼容）
        if task and task.status in (TaskStatus.EVALUATING, TaskStatus.REEVALUATING):
            self._update_task_status_and_notify(task_id, test_case_id, new_status, task)

    def _update_task_status_and_notify(self, task_id, test_case_id, new_status, task):
        """更新 Task 状态并发任务级事件、通知进度（同步路径，保留兼容）"""
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        ok = task_acl_repository.update_task_status(task_id, new_status)
        self._log(
            level='INFO' if ok else 'ERROR',
            category='database',
            content=f"任务状态从 {task.status} 更新为 {new_status}: {'成功' if ok else '失败'}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 发布任务级事件（评估阶段完成）
        task_event_type = EventType.TASK_COMPLETED if new_status == TaskStatus.COMPLETED else (
            EventType.TASK_FAILED if new_status == TaskStatus.FAILED else None
        )
        if task_event_type:
            EventBus().publish(
                EventChannel.TASK_EVENTS,
                task_event_type,
                {
                    'task_id': str(task_id),
                    'status': new_status,
                    'test_case_id': str(test_case_id) if test_case_id else None,
                }
            )

        # 通过 gRPC 调用 task_service 通知进度（同步路径，保留兼容）
        from evaluation_service.infrastructure.acl.task_acl_repository import task_acl_repository
        task_acl_repository.notify_task_progress(task_id, force=True)
