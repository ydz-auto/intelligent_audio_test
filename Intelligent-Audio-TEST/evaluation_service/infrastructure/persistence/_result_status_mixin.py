# -*- coding: utf-8 -*-
"""用例与任务状态推进混入

负责评估完成后 TaskCase/Task 的状态判定与推进：
完成度检查、最终状态应用、事件发布（事件驱动）与 gRPC 同步回传。
"""
import traceback

from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskStatus, ACTIVE_EVALUATION_STATUSES,
)
from evaluation_service.infrastructure.acl import task_acl_repository


class ResultStatusMixin:
    """TaskCase/Task 状态推进方法"""

    def update_task_case_status(self, result_id, current_result_all_completed, task_id, test_case_id):
        """
        更新TaskCase的状态。在多设备/多API执行时，需确保所有结果都评估完成后再更新最终状态。

        P1.4 改造：所有 Task/TaskCase/TaskDevice/TaskAPI/TestCase/TestResult 的访问
        改为通过 task_acl_repository (gRPC) 调 task_service。
        注意：跨服务调用无原子事务，失败时通过日志告警。

        INT-1752：移除了从未生效的 test_type 参数——预期维度数由用例 config 的
        维度集合判定，不区分 api/e2e；需要 test_type 的分支（如算法结果快照）
        由调用方各自传入，不经本方法传递。

        Args:
            result_id: 测试结果ID
            current_result_all_completed: 当前结果是否全部完成
            task_id: 任务ID
            test_case_id: 用例ID
        """
        try:
            # 1. 获取任务信息（P1.4: gRPC）
            task = task_acl_repository.get_task_by_id(task_id)
            if not task:
                return

            # 2. 读取该用例的路由行（多路由下逐行判定/逐行回写）
            tc_rels = task_acl_repository.get_task_case_by_ids(task_id, [str(test_case_id)])

            # 3. 获取预期结果数量（仅用于 legacy 未绑定行口径）
            expected_count = self._get_expected_result_count(task_id, task, test_case_id)

            # 4. 获取该用例目前已生成的所有测试结果（P1.4: gRPC）
            all_results = task_acl_repository.get_test_results_by_task_and_case(
                task_id=task_id, test_case_id=str(test_case_id)
            )

            # 5. 获取用例配置中预期的评估维度总数（P1.4: gRPC）
            expected_dim_count = self._get_expected_dim_count(test_case_id)

            # 6. 逐行检查是否全部到达终态（执行失败/停止的行本身即终态）
            case_all_finished, failed_row_ids, failed_reasons = self._check_all_results_completed(
                task_id, test_case_id, tc_rels, expected_dim_count, all_results, expected_count
            )

            if not case_all_finished:
                return

            if tc_rels and not any(not getattr(r, 'device_id', None) for r in tc_rels):
                # 7. 逐行写终态：成功行 completed、维度失败行 failed，失败/停止行保持原终态
                self._apply_final_status(task_id, test_case_id, None, None, task,
                                         failed_reasons=failed_reasons,
                                         tc_rels=tc_rels, failed_row_ids=failed_row_ids)
            else:
                # legacy 未绑定行 / 无用例行：按整体结论收口
                new_evaluation_status = (EvaluationStatus.FAILED if failed_row_ids
                                         else EvaluationStatus.COMPLETED)
                new_status = derive_task_case_status(
                    ExecutionStatus.COMPLETED, new_evaluation_status)
                self._apply_final_status(task_id, test_case_id, new_status,
                                         new_evaluation_status, task,
                                         failed_reasons=failed_reasons)
        except Exception as e:
            # INT-2189：原先此处吞掉异常只留一行 ERROR，导致收口逻辑整段跳过、
            # 用例永久停在 evaluating（任务忙等到超时才判 failed）。改为带上
            # stack 再向上抛，由调用方按失败收口（endpoint_worker 兜底落 failed）。
            self._log(
                level='ERROR',
                category='database',
                content=f"更新TaskCase状态失败: {str(e)}\n{traceback.format_exc()}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            raise

    def _get_expected_result_count(self, task_id, task, test_case_id=None):
        """获取预期结果数量（P1.4: gRPC）

        差异#2 收尾：由用例级 device_type 判定（task.type 已废弃）——
        物理用例按被测设备数、API 用例按关联 API 数预期。

        INT-604 多路由：预期数按路由行求和——路由级绑定行（device_id 非空）
        每行预期 1 个结果；legacy 未绑定行（device_id 空）按该路由类型的
        len(devices)/len(apis) 预期，勿沿用首行 device_type（避免多路由下
        只按单侧设备数/API 数推导导致用例永不收敛或过早收敛）。
        """
        from shared.models.common_enums import DeviceType
        expected_count = 0
        tc_dtos = []
        if test_case_id:
            tc_dtos = task_acl_repository.get_task_case_by_ids(task_id, [str(test_case_id)])
        if not tc_dtos:
            return 1
        devices = task_acl_repository.get_task_devices(task_id=task_id)
        apis = task_acl_repository.get_task_apis(task_id=task_id)
        for tc in tc_dtos:
            # 执行已失败/停止的行不会再有结果，不参与预期数（避免期望数永远差一条）
            if (getattr(tc, 'execution_status', None) or '') in (
                    ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
                continue
            device_type = getattr(tc, 'device_type', None) or DeviceType.PHYSICAL.value
            tc_device_id = getattr(tc, 'device_id', None)
            if tc_device_id:
                # 路由级绑定：每路由预期 1 个结果
                expected_count += 1
            elif device_type == DeviceType.PHYSICAL.value:
                expected_count += len(devices)
            else:
                expected_count += len(apis)

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
        """统计数据库中启用且未删除的维度数量（自有 PO，本地查询）

        INT-2189：口径必须与评估链路的加载器
        `EvaluationDimensionRepository.list_active_dimensions_by_ids`
        （deleted == False 且 status == True）完全一致。此前只过滤 status，
        config 仍引用已软删维度时预期数被算大、实际 TRD 行数按加载器口径偏小，
        永久停在「维度未全 (n/m)，继续等待」，而该结果不会再被二次触发 ——
        TaskCase 卡 evaluating、任务忙等到超时判 failed。
        """
        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.orm_models import Dimension
        local_db_session = get_db_session()
        try:
            return local_db_session.query(Dimension).filter(
                Dimension.id.in_(unique_dim_ids),
                Dimension.deleted == False,  # noqa: E712
                Dimension.status == True  # noqa: E712
            ).count()
        finally:
            local_db_session.close()

    def _check_all_results_completed(self, task_id, test_case_id, tc_rels, expected_dim_count,
                                     all_results, expected_count=0):
        """检查用例是否全部路由行到达终态。

        Returns:
            (case_all_finished, failed_row_ids, failed_reasons)

        现代多路由场景（每行绑定 device_id/api_id）逐行判定：
        - 执行已失败/停止的行本身即终态，不会再产结果，直接跳过；
        - 其余行必须有归属自己的结果，且该结果的全部维度评估完成。
        历史未绑定行（device_id 为空）沿用「结果数 vs 预期数」口径，零回归。
        """
        from shared.models.common_enums import DeviceType
        has_legacy_row = any(not getattr(r, 'device_id', None) for r in (tc_rels or []))
        if has_legacy_row or not tc_rels:
            case_all_finished, case_any_failed, failed_reasons = \
                self._check_all_results_completed_by_count(
                    task_id, test_case_id, expected_count, expected_dim_count, all_results)
            # legacy 口径只产出整体结论，sentinel 供调用方走整体收口
            failed_row_ids = {'__legacy__'} if case_any_failed else set()
            return case_all_finished, failed_row_ids, failed_reasons

        results_by_device = {}
        results_by_api = {}
        for res in all_results:
            device_id = getattr(res, 'device_id', None)
            api_id = getattr(res, 'api_id', None)
            if device_id:
                results_by_device[str(device_id)] = res
            if api_id:
                results_by_api[str(api_id)] = res

        case_all_finished = True
        failed_row_ids = set()
        failed_reasons = []

        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.orm_models import TestResultDimension
        local_db_session = get_db_session()
        try:
            for row in tc_rels:
                exec_status = getattr(row, 'execution_status', None) or ''
                if exec_status in (ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
                    # 执行已失败/停止：无结果，终态已由执行侧写入，不参与评估等待
                    continue
                if exec_status != ExecutionStatus.COMPLETED:
                    case_all_finished = False
                    break

                row_type = getattr(row, 'device_type', '') or DeviceType.PHYSICAL.value
                row_bind = str(getattr(row, 'device_id', '') or '')
                if row_type == DeviceType.PHYSICAL.value:
                    res = results_by_device.get(row_bind)
                else:
                    res = results_by_api.get(row_bind)
                if res is None:
                    self._log(
                        level='DEBUG',
                        category='database',
                        content=f"用例 {test_case_id} 路由行 {row.id} 结果未采集，暂不更新状态",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    case_all_finished = False
                    break

                dims = local_db_session.query(TestResultDimension).filter_by(
                    test_result_id=res.id).all()
                if len(dims) < expected_dim_count:
                    self._log(
                        level='DEBUG',
                        category='database',
                        content=(f"用例 {test_case_id} 结果 {res.id} 维度未全 "
                                 f"({len(dims)}/{expected_dim_count})，继续等待"),
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    case_all_finished = False
                    break

                res_finished = True
                res_failed = False
                for dim in dims:
                    if dim.evaluation_status in ACTIVE_EVALUATION_STATUSES:
                        res_finished = False
                        break
                    if dim.evaluation_status == EvaluationStatus.FAILED:
                        res_failed = True
                        if dim.error_message:
                            failed_reasons.append(f"{dim.error_message}")

                if not res_finished:
                    case_all_finished = False
                    break
                if res_failed:
                    failed_row_ids.add(row.id)
        finally:
            local_db_session.close()

        return case_all_finished, failed_row_ids, failed_reasons

    def _check_all_results_completed_by_count(self, task_id, test_case_id, expected_count,
                                              expected_dim_count, all_results):
        """legacy 未绑定行口径：结果数达到预期且所有维度评估完成。"""
        if len(all_results) < expected_count:
            self._log(
                level='DEBUG',
                category='database',
                content=f"用例 {test_case_id} 结果未全 (已采集: {len(all_results)}/{expected_count})，暂不更新状态",
                task_id=task_id,
                test_case_id=test_case_id
            )
            return False, False, []

        case_all_finished = True
        case_any_failed = False
        failed_reasons = []

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
                        if dim.error_message:
                            failed_reasons.append(f"{dim.error_message}")

                # 如果这个 TestResult 还没完成，整体也不能算完成
                if not res_finished:
                    case_all_finished = False
                # 如果这个 TestResult 失败了，整体就标记为失败
                if res_failed:
                    case_any_failed = True
        finally:
            local_db_session.close()

        return case_all_finished, case_any_failed, failed_reasons

    def _apply_final_status(self, task_id, test_case_id, new_status, new_evaluation_status, task,
                            failed_reasons=None, tc_rels=None, failed_row_ids=None):
        """应用最终状态

        P1.4: 通过 gRPC 更新 TaskCase 和 Task
        事件驱动改造: 同时发布 CaseEvaluated 事件到 Redis 事件总线，
        消费方（task_service）订阅后更新状态，替代 gRPC 同步回传的强依赖。
        gRPC 调用保留作为同步路径，事件作为异步通知补充。

        tc_rels 传入时按路由行分别回写（tc_rel_id 精确命中）：成功行 completed、
        维度失败行 failed、执行已失败/停止行保持原终态——避免一行失败把同用例
        成功路由一起改写，也避免评估进度把物理失败行刷回 calculating。
        """
        # 更新TaskCase状态（P1.4: 通过 gRPC）
        # INT-107: 失败时把维度失败原因聚合写入 task_case_relations.error_message
        # INT-604: 多路由下不回写 execution_status（execution_status=None）——
        # 兄弟路由可能仍在执行中，复合 status 由 task_service 按行自身 exec 推导
        from evaluation_service.infrastructure.evaluation_mixin import update_task_case_status_in_db
        from evaluation_service.domain.services.evaluation_utils import compose_case_error_message

        if tc_rels:
            failed_row_ids = failed_row_ids or set()
            update_count = 0
            # 用例级结论：任一执行失败/停止行或维度失败行 → 用例失败
            case_failed = False
            for row in tc_rels:
                exec_status = getattr(row, 'execution_status', None) or ''
                if exec_status in (ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
                    # 执行侧已写终态（含真实失败原因），评估侧不再覆盖
                    case_failed = True
                    continue
                row_eval = (EvaluationStatus.FAILED if row.id in failed_row_ids
                            else EvaluationStatus.COMPLETED)
                if row_eval == EvaluationStatus.FAILED:
                    case_failed = True
                row_status = derive_task_case_status(
                    exec_status or ExecutionStatus.COMPLETED, row_eval)
                row_error = (compose_case_error_message(failed_reasons)
                             if row_eval == EvaluationStatus.FAILED else '')
                update_count += update_task_case_status_in_db(
                    None, task_id, test_case_id, row_status, row_eval,
                    execution_status=None,
                    error_message=row_error,
                    tc_rel_id=row.id,
                )
            new_evaluation_status = (EvaluationStatus.FAILED if case_failed
                                     else EvaluationStatus.COMPLETED)
            new_status = derive_task_case_status(
                ExecutionStatus.COMPLETED, new_evaluation_status)
        else:
            error_message = ''
            if new_evaluation_status == EvaluationStatus.FAILED:
                error_message = compose_case_error_message(failed_reasons)
            update_count = update_task_case_status_in_db(
                None, task_id, test_case_id, new_status, new_evaluation_status,
                execution_status=None,
                error_message=error_message,
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
        # INT-174（对齐 V9.7.10 c30d1b24）：重新评估（reevaluating）期间任务终态
        # 由 ReevaluationExecutor.maybe_finalize 统一收敛（提交成功 ≠ 完成），
        # 用例级收尾只在普通执行链的 evaluating 态翻转任务状态
        if task and task.status == TaskStatus.EVALUATING:
            self._update_task_status_and_notify(task_id, test_case_id, new_status, task)

    def _update_task_status_and_notify(self, task_id, test_case_id, new_status, task):
        """更新 Task 状态并发任务级事件、通知进度（同步路径，保留兼容）"""
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        # INT-116: 任务终态写库失败即"任务永不收敛→引擎无限忙等"，
        # 走内联重试 + 延迟队列兜底
        from evaluation_service.infrastructure.evaluation_mixin import update_task_status_with_retry
        ok = update_task_status_with_retry(task_id, new_status)
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
