# -*- coding: utf-8 -*-
"""任务仓储 — 生命周期操作 Mixin（从 task_repository.py 拆分，P4-5）。

task_lifecycle_service 兼容方法：启动前重置、环境预检、重试用例查找、
结果清理、计数重算、重评数据读取等。
"""
import logging
from typing import List, Optional

from sqlalchemy import case, or_
from sqlalchemy.exc import OperationalError

from shared.models.database import get_db_session
from shared.utils.time_utils import utcnow
from shared.utils.status_utils import derive_task_case_status, task_case_not_removed
from shared.utils.status_constants import (
    ExecutionStatus,
    EvaluationStatus,
    TaskStatus as SharedTaskStatus,
    TaskCaseStatus,
    ACTIVE_EVALUATION_STATUSES,
    INTERRUPTED_TASK_STATUSES,
    INTERRUPTED_EXECUTION_STATUSES,
)
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskDevice
from task_service.infrastructure.persistence.models import TestResult

logger = logging.getLogger(__name__)

# 服务重启导致任务中断的错误提示（对齐 V9.7.10 旧版文案）
_INTERRUPTED_ERROR_MESSAGE = '服务重启导致任务中断'

# INT-305：用例移除留痕（error_message 盖写；recount / 列表按此剔除软删行）
_REMOVED_CASE_MESSAGE = '用例已被移除'


class TaskLifecycleMixin:
    """任务生命周期辅助操作（供 TaskRepository 组合）"""

    def get_task_for_start_check(self, task_id: int):
        """启动前检查：返回 Task PO（含 status/id），不存在返回 None。"""
        return self.get_task_orm(task_id)

    def reset_task_for_start(self, task_id: int) -> bool:
        """重置失败/停止任务为 pending，清零计数。

        INT-148 缺陷#2：重启路径同步清理关联 TestResult（含 case_pcm 文件）。
        全部 TaskCase 重置为 pending 后将被重新执行，执行/评估提交侧为
        无条件 INSERT（SubmitResult），残留旧行会产生重复/脏结果——与 retry
        路径未完成用例的清理语义（preserve_test_result=False 删除）对齐。
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return False
            task.status = SharedTaskStatus.PENDING
            task.completed_cases = 0
            task.failed_cases = 0
            task.started_at = None
            task.completed_at = None
            task.actual_duration = None
            # 重置所有 TaskCase 为 pending
            # （INT-305：移除留痕行跳过——不复活被删用例、不清除移除留痕）
            session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                task_case_not_removed(TaskCase),
            ).update({
                TaskCase.status: derive_task_case_status(ExecutionStatus.PENDING, EvaluationStatus.PENDING),
                TaskCase.execution_status: ExecutionStatus.PENDING,
                TaskCase.evaluation_status: EvaluationStatus.PENDING,
                TaskCase.started_at: None,
                TaskCase.completed_at: None,
                TaskCase.duration: None,
                TaskCase.error_message: None,
            }, synchronize_session=False)
            # 删除旧 TestResult（重跑将 INSERT 新行，残留旧行导致重复/脏结果）
            # （INT-305：被删用例的 excluded 行一并不留——重跑后用例不再属于本任务）
            case_ids = [
                row[0] for row in session.query(TaskCase.test_case_id).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id.isnot(None),
                ).all()
            ]
            self._delete_test_results(session, task_id, case_ids, preserve_test_result=False)
            session.commit()
            # 提交后清理 case_pcm 旧文件（失败降级忽略，防旧残留干扰新一轮采集）
            if case_ids:
                self._cleanup_case_pcm_dirs(task_id, case_ids)
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check_environment_for_start(self, task_id: int):
        """环境预检：检查关联设备和播放设备是否在线 + API 用例目标 API 在线预检。

        Returns:
            (can_start: bool, error_msg: str)
        """
        session = get_db_session()
        try:
            # 获取任务关联的设备
            device_rows = session.query(TaskDevice).filter(
                TaskDevice.task_id == task_id
            ).all()

            if not device_rows:
                device_ids = []
            else:
                device_ids = [td.device_id for td in device_rows]
        finally:
            session.close()

        # 通过 gRPC 检查设备状态（gRPC 调用不占用 DB session）
        if device_ids:
            can_start, err_msg = self._check_devices_online(device_ids)
            if not can_start:
                return False, err_msg

        # INT-148 缺陷#1：API 任务对目标 API 做在线预检（对齐 V9.7.10）
        return self._check_apis_online(task_id)

    @staticmethod
    def _get_task_api_case_ids(task_id: int):
        """收集任务中 http_api/websocket_api 用例的目标 API ID（去重保序）。"""
        from shared.models.common_enums import DeviceType
        session = get_db_session()
        try:
            rows = session.query(TaskCase.device_id).filter(
                TaskCase.task_id == task_id,
                TaskCase.device_type.in_(
                    [DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value]),
                TaskCase.device_id.isnot(None),
            ).all()
            seen, api_ids = set(), []
            for (device_id,) in rows:
                if device_id is None:
                    continue
                key = str(device_id)
                if key not in seen:
                    seen.add(key)
                    api_ids.append(int(device_id))
            return api_ids
        finally:
            session.close()

    @staticmethod
    def _check_apis_online(task_id: int):
        """API 用例目标 API 在线预检：逐个调用 api_test_service 健康检查。

        明确 offline → 阻断启动并给出报错；gRPC 异常（api_test_service 不可达）
        不阻塞启动（与设备检查降级策略一致，执行期失败由用例错误路径收敛）。
        """
        try:
            api_ids = TaskLifecycleMixin._get_task_api_case_ids(task_id)
        except Exception as e:
            logger.warning(f"API 用例查询异常（跳过 API 预检）: task_id={task_id}, {e}")
            return True, ''
        if not api_ids:
            return True, ''

        from task_service.infrastructure.acl.api_acl_repository import api_acl_repository
        for api_id in api_ids:
            info = api_acl_repository.test_api_connection(api_id)
            if info is None:
                # gRPC 失败：健康检查不可用，不阻塞启动
                logger.warning(f"API 预检不可用（跳过）: task_id={task_id}, api_id={api_id}")
                continue
            if info.get('status') != 'online':
                error_detail = info.get('error') or '健康检查未通过'
                return False, f"被测 API (id={api_id}) 离线，无法启动: {error_detail}"
        return True, ''

    @staticmethod
    def _check_devices_online(device_ids: List[int]):
        """通过 ACL 仓储检查任务关联设备在线状态（gRPC）。"""
        try:
            from task_service.infrastructure.acl.device_acl_repository import device_acl_repository
            devices = device_acl_repository.get_device_statuses(device_ids)

            offline_devices = [d for d in devices if d.get('status') != 'online']

            if offline_devices:
                names = ', '.join(
                    d.get('device_name') or d.get('name') or f"id={d.get('id')}"
                    for d in offline_devices
                )
                return False, f"设备离线，无法启动: {names}"

            return True, ''
        except Exception as e:
            logger.warning(f"设备状态检查异常（跳过）: {e}")
            return True, ''  # gRPC 异常时不阻塞启动

    def get_task_orm(self, task_id: int):
        """获取 Task PO（lifecycle service 用）。"""
        session = get_db_session()
        try:
            return session.query(Task).filter(
                Task.id == task_id,
                Task.deleted == False,  # noqa: E712
            ).first()
        finally:
            session.close()

    def find_retry_cases(self, task_id: int):
        """查找需要重试的用例（execution_status != completed 或 status == failed）。

        INT-305：移除留痕行不参与重试。
        """
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status != ExecutionStatus.COMPLETED,
                task_case_not_removed(TaskCase),
            ).all()
        finally:
            session.close()

    def find_retry_cases_scoped(self, task_id: int, mode: str, selected_case_ids: list):
        """INT-302：按范围模式查找待重执行用例。

        - selected: 仅命中 case_ids 的 task_cases（无论已完成/失败，交由
          调用方按既有 retry 状态机分流处理）；
        - failed_only: 执行失败或评估失败的用例。
        其余用例一律不动（不重置、不清结果、不重新入队）。
        """
        from shared.models.common_enums import RetryScopeMode
        session = get_db_session()
        try:
            q = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                task_case_not_removed(TaskCase),
            )
            if mode == RetryScopeMode.SELECTED.value:
                q = q.filter(TaskCase.test_case_id.in_([str(c) for c in (selected_case_ids or [])]))
            elif mode == RetryScopeMode.FAILED_ONLY.value:
                q = q.filter(or_(
                    TaskCase.execution_status == ExecutionStatus.FAILED,
                    TaskCase.evaluation_status == EvaluationStatus.FAILED,
                ))
            cases = q.all()
            session.expunge_all()
            return cases
        finally:
            session.close()

    def cleanup_case_results(self, task_id: int, case_ids: list,
                             preserve_test_result: bool = False) -> None:
        """清理用例的执行结果。"""
        session = get_db_session()
        try:
            if not case_ids:
                return
            self._delete_test_results(session, task_id, case_ids, preserve_test_result)
            session.commit()

            # 同时清理 case_pcm 目录下的旧 pcm/wav 文件，防止旧残留干扰新一轮采集
            self._cleanup_case_pcm_dirs(task_id, case_ids)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _delete_test_results(session, task_id: int, case_ids: list,
                             preserve_test_result: bool) -> None:
        """删除 TestResult 记录（preserve_test_result=True 时仅清 algorithm_result）。

        INT-340：重执行/重启覆盖人工复核——复核留痕行随旧结果清退，
        复核标记列随行重置（覆盖提醒已在前端硬确认，此处落地覆盖语义：
        重新执行后旧的人工复核结果不再生效）。
        """
        from task_service.infrastructure.persistence.models import TestResult, TestResultReview
        result_ids = [
            rid for (rid,) in session.query(TestResult.id).filter(
                TestResult.task_id == task_id,
                TestResult.test_case_id.in_(list(case_ids)),
            ).all()
        ]
        if result_ids:
            # 复核留痕随旧结果清退；表未建（迁移未应用/精简测试库）时降级忽略
            try:
                session.query(TestResultReview).filter(
                    TestResultReview.result_id.in_(result_ids),
                ).delete(synchronize_session=False)
            except OperationalError:
                logger.warning("test_result_reviews 表不存在，跳过复核留痕清理", exc_info=True)
        query = session.query(TestResult).filter(
            TestResult.task_id == task_id,
            TestResult.test_case_id.in_(list(case_ids)),
        )
        if preserve_test_result:
            # 只清理 algorithm_result + 复核标记，保留 result_data
            query.update({
                TestResult.algorithm_result: None,
                TestResult.reviewed: 0,
                TestResult.reviewed_by_user_id: None,
                TestResult.reviewed_at: None,
                TestResult.last_review_comment: None,
                TestResult.last_review_action: None,
            }, synchronize_session=False)
        else:
            query.delete(synchronize_session=False)

    @staticmethod
    def _cleanup_case_pcm_dirs(task_id: int, case_ids: list) -> None:
        """清理 case_pcm 目录下的旧 pcm/wav 文件（失败降级忽略）。"""
        import os
        import shutil
        try:
            from task_service.config.config import Config
            static_base = getattr(Config, 'STATIC_BASE_PATH', '')
            if not static_base:
                return
            for tc_id in case_ids:
                pcm_dir = os.path.join(static_base, 'case_pcm', str(task_id), str(tc_id))
                if os.path.exists(pcm_dir):
                    try:
                        shutil.rmtree(pcm_dir)
                    except Exception as e:
                        logger.warning(f"删除用例 {tc_id} pcm文件失败: {e}")
        except ImportError:
            pass

    def commit_task_case(self, tc) -> None:
        """提交 TaskCase PO 变更（lifecycle service 修改 PO 后调用）。"""
        session = get_db_session()
        try:
            session.merge(tc)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def recount_task_cases(self, task_id: int) -> None:
        """重新统计任务的总/完成/失败**用例数**。

        INT-305：移除留痕行（error_message = _REMOVED_CASE_MESSAGE 的软删行）
        不计入总数/完成/失败——用例已从任务剔除，计数口径与列表/报告一致。

        INT-2233：口径改为**用例级去重**（`test_case_id`），与建任务时的
        `COUNT(DISTINCT test_case_id)` 及 `task_case_stats.refresh_task_counts_atomic`
        同一来源；多路由任务（一个用例 × 多目标多行）此前按行计数会把同一用例
        数成多条，移除后 total_cases 也不减 1。
        """
        session = get_db_session()
        try:
            from task_service.domain.services.task_case_stats import case_level_counts
            not_removed = task_case_not_removed(TaskCase)
            rows = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                not_removed,
            ).all()
            counts = case_level_counts(rows)
            task = session.get(Task, task_id)
            if task:
                task.total_cases = counts['total']
                task.completed_cases = counts['completed']
                task.failed_cases = counts['failed']
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def reset_task_to_pending(self, task_id: int) -> None:
        """重置任务状态为 pending。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task:
                task.status = SharedTaskStatus.PENDING
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def find_task_case(self, task_id: int, case_id: str):
        """查询单个 TaskCase PO（单行语义：按行控制 skip/retry 等场景）。"""
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.test_case_id == case_id,
            ).first()
        finally:
            session.close()

    def find_task_cases(self, task_id: int, case_id: str) -> list:
        """查询该用例在任务下的**全部路由行**（INT-604 多路由：同一用例 × 多设备/API
        每个 (case, device_type, device_id) 落一行；INT-2233）。

        用例级操作（如移除）必须按全量行收敛，不能只取首行，否则剩余路由行
        仍被详情/列表/统计计入，与报告口径冲突。
        """
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.test_case_id == case_id,
            ).all()
        finally:
            session.close()

    # ==================== INT-305：用例移除 ====================

    def remove_task_case(self, task_id: int, case_id: str,
                         deleted_by_user_id=None) -> dict:
        """移除任务用例（INT-305；INT-2233 全量路由行收敛）。

        分阶段语义由调用方（task_lifecycle_service.remove_case）决定：
        - pending/queued 且无结果产出：物理删除 TaskCase 行
          （该行从未执行过，删除后重跑可重新关联）；
        - 其余（已有执行/评估产出）：软删（error_message 盖写移除留痕）
          + 级联处置 TestResult（excluded 标记，不物理删，保审计）。

        INT-2233：多路由任务（INT-604）同一用例 × 多设备/API 会落多行
        `task_case_relations`。移除必须覆盖 `(task_id, test_case_id)` 下**全部
        未留痕行**，否则剩余行仍被详情/列表/统计计入，而报告已按 excluded
        剔除——同一操作两套结果。物理删/软删按全量行统一判定（存在任一结果
        即整体软删留痕，保审计）。

        Args:
            task_id: 任务 ID
            case_id: TaskCase.test_case_id
            deleted_by_user_id: 操作人（x-user-id 透传；None 保持 NULL）

        Returns:
            {'removed': True, 'had_result': bool, 'purged': bool}；用例不存在返回 None
        """
        session = get_db_session()
        try:
            rows = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.test_case_id == case_id,
            ).all()
            if not rows:
                return None

            # 已留痕行不重复处置（重复移除幂等：只剩留痕行时不再产生副作用）
            live_rows = [tc for tc in rows
                         if (tc.error_message or '') != _REMOVED_CASE_MESSAGE]
            if not live_rows:
                had_result = session.query(TestResult.id).filter(
                    TestResult.task_id == task_id,
                    TestResult.test_case_id == case_id,
                ).first() is not None
                return {'removed': True, 'had_result': had_result, 'purged': False}

            had_result = session.query(TestResult.id).filter(
                TestResult.task_id == task_id,
                TestResult.test_case_id == case_id,
            ).first() is not None

            # 物理删仅当：全量行都无结果、且都未开始执行（任一在跑/有产出即转软删）
            purgeable = (
                not had_result
                and all(tc.execution_status in (ExecutionStatus.PENDING, ExecutionStatus.QUEUED)
                        for tc in live_rows)
            )
            row_ids = [tc.id for tc in live_rows]

            if purgeable:
                # 无结果产出且未开始执行：物理删除全部路由行（重跑可重新关联）
                session.query(TaskCase).filter(TaskCase.id.in_(row_ids)).delete(
                    synchronize_session=False)
                session.commit()
                logger.info("移除任务用例(物理删) task_id=%s case_id=%s rows=%s",
                            task_id, case_id, len(row_ids))
                return {'removed': True, 'had_result': False, 'purged': True}

            # 软删留痕：error_message 盖写移除语义（对齐 skip 的 error_message 用法），
            # 按全量行批量盖写（INT-2233：不能只改首行）
            from shared.models.database import utc8now
            session.query(TaskCase).filter(TaskCase.id.in_(row_ids)).update({
                TaskCase.error_message: _REMOVED_CASE_MESSAGE,
                TaskCase.updated_by_user_id: deleted_by_user_id,
            }, synchronize_session=False)
            # 级联处置 TestResult：excluded 标记（不物理删，保审计；
            # 报告/聚合按 excluded=1 剔除被删用例；
            # excluded_at 盖写排除时间——软删行"何时被移除"的库内持久落点）
            session.query(TestResult).filter(
                TestResult.task_id == task_id,
                TestResult.test_case_id == case_id,
            ).update({
                TestResult.excluded: 1,
                TestResult.excluded_by_user_id: deleted_by_user_id,
                TestResult.excluded_at: utcnow(),
            }, synchronize_session=False)
            session.commit()
            logger.info("移除任务用例(软删留痕) task_id=%s case_id=%s rows=%s",
                        task_id, case_id, len(row_ids))
            return {'removed': True, 'had_result': had_result, 'purged': False}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def count_task_cases_excluding_removed(self, task_id: int) -> int:
        """移除后的用例总数（软删留痕行剔除，供 recount 口径统一）。"""
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                task_case_not_removed(TaskCase),
            ).count()
        finally:
            session.close()

    def touch_task_updated_by(self, task_id: int, user_id=None) -> None:
        """盖写任务行 updated_by_user_id（INT-305：移除用例操作人留痕）。"""
        session = get_db_session()
        try:
            session.query(Task).filter(Task.id == task_id).update(
                {Task.updated_by_user_id: user_id}, synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def record_task_starter(self, task_id: int, user_id=None) -> None:
        """记录任务启动操作人（INT-573：start/retry 实际启动时写入）。

        控制操作（stop/control/remove_case/rextract）校验「owner 或启动人」——
        启动人经此列留痕。user_id 为 None（未认证）时置 NULL，控制回落 owner
        校验。镜像 touch_task_updated_by 的最小列更新模式。
        """
        session = get_db_session()
        try:
            session.query(Task).filter(Task.id == task_id).update(
                {Task.last_started_by_user_id: user_id}, synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def expire_progress_cache(self, task_id: int) -> None:
        """失效共享层进度缓存（INT-305：删除后立即拉新，不等 TTL）。

        task_data_cache 为进程内 TTL 缓存；删除用例后 2s TTL 内的
        task_progress 拉取会读到旧 test_cases 列表，此处主动清空本任务条目。
        """
        try:
            from shared.utils.task_data_cache import _cache, _cache_lock
            with _cache_lock:
                for prefix in ('progress:', 'detail:'):
                    _cache.pop(f'{prefix}{task_id}', None)
        except Exception:
            logger.debug("失效进度缓存失败 task_id=%s", task_id, exc_info=True)

    def find_task_for_stop(self, task_id: int):
        """停止前检查：返回 Task PO。"""
        return self.get_task_orm(task_id)

    def find_task_for_reextract(self, task_id: int):
        """重新提取前检查：返回 Task PO。"""
        return self.get_task_orm(task_id)

    def get_test_result_for_reevaluate(self, task_id: int, test_case_id: str):
        """获取测试结果 PO（用于重新评估）。"""
        session = get_db_session()
        try:
            from task_service.infrastructure.persistence.models import TestResult
            return session.query(TestResult).filter(
                TestResult.task_id == task_id,
                TestResult.test_case_id == test_case_id,
            ).first()
        finally:
            session.close()

    def get_test_case_orm(self, test_case_id: str):
        """获取 TestCase PO（跨域查询，后续改 gRPC）。"""
        session = get_db_session()
        try:
            from task_service.infrastructure.persistence.models.testcase_models import TestCase
            return session.query(TestCase).filter(
                TestCase.id == test_case_id,
            ).first()
        finally:
            session.close()

    def assign_worker_instance(self, task_id: int, instance_id: str):
        """为任务写入归属执行实例（多实例下任务按实例分管）。

        任务创建时由调用方（application 层）选定的最空闲存活实例分配归属。
        归属写入失败不阻塞任务创建：任务保持未归属（worker_instance_id=NULL），
        由任一存活实例接管执行。
        """
        session = get_db_session()
        try:
            session.query(Task).filter(Task.id == task_id).update(
                {Task.worker_instance_id: instance_id}, synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
            logger.warning("分配任务归属实例失败 (task_id=%s, instance_id=%s)", task_id, instance_id)
        finally:
            session.close()

    def mark_interrupted_tasks_failed(self, instance_id: str = None) -> dict:
        """启动恢复：将上次停机遗留的中间态任务及用例/结果标记为失败。

        冷重启后进程内 workers / 执行线程 / 事件订阅全部消失，DB 中处于
        queued/running/evaluating/reevaluating/paused 等中间态的任务不会再有
        执行方推进状态，统一标记为 failed（对齐 V9.7.10 单体版 app.py 的
        启动恢复行为）。

        多实例语义：
        - 只处理**归属本实例（worker_instance_id == instance_id）或未归属
          （worker_instance_id IS NULL）**的中间态任务；
        - 归属其他存活实例的任务**不动**，避免实例 B 冷重启误杀实例 A
          正在运行的任务；
        - 归属已下线实例的任务由调度器「孤儿收养」逻辑重新接管，见
          SchedulerMixin._adopt_orphan_pending_tasks。

        注意：
        - 必须在调度器启动**之前**调用，避免调度器拉起已判失败的残留任务。
        - 任务状态为 PENDING 的记录**不处理**，保留给 DB 兜底调度自动拉起。

        Args:
            instance_id: 本实例标识（task_service:{host}:{port}:{hex}）。
                None 表示未启用归属（单实例/降级），此时处理全部未归属任务。

        Returns:
            dict: {task, task_case_execution, task_case_evaluation, test_result}
                  各表实际更新的行数
        """
        session = get_db_session()
        try:
            now = utcnow()

            # 归属过滤：本实例名下或未归属（NULL）的中间态任务
            ownership_filter = or_(
                Task.worker_instance_id.is_(None),
                Task.worker_instance_id == instance_id,
            )

            # 1. 收集中间态任务 ID（必须在置 failed 之前查询，避免过滤条件失效）
            interrupted_rows = session.query(Task.id).filter(
                Task.deleted == False,  # noqa: E712
                Task.status.in_(INTERRUPTED_TASK_STATUSES),
                ownership_filter,
            ).all()
            task_ids = [row[0] for row in interrupted_rows]

            if not task_ids:
                return {'task': 0, 'task_case_execution': 0,
                        'task_case_evaluation': 0, 'test_result': 0}

            # 2. 任务状态 → failed
            # （Task 无 error_message 列，任务级失败原因仅落 TaskCase.error_message）
            task_count = session.query(Task).filter(
                Task.id.in_(task_ids),
            ).update({
                Task.status: SharedTaskStatus.FAILED,
                Task.completed_at: now,
            }, synchronize_session=False)

            # 3. 用例执行中断 → execution_status failed（推导 status=failed）
            case_exec_count = session.query(TaskCase).filter(
                TaskCase.task_id.in_(task_ids),
                TaskCase.execution_status.in_(INTERRUPTED_EXECUTION_STATUSES),
            ).update({
                TaskCase.execution_status: ExecutionStatus.FAILED,
                TaskCase.status: TaskCaseStatus.FAILED,
                TaskCase.error_message: _INTERRUPTED_ERROR_MESSAGE,
                TaskCase.completed_at: now,
            }, synchronize_session=False)

            # 4. 用例评估中断 → evaluation_status failed（execution 保持 completed，status 推导为 failed）
            # INT-161：已带真实失败原因/完成时间的用例（如执行已失败落库）不覆盖
            # error_message / completed_at，仅补评估终态——启动恢复不得改写
            # 非中间态用例的既有失败原因。
            case_eval_count = session.query(TaskCase).filter(
                TaskCase.task_id.in_(task_ids),
                TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES),
            ).update({
                TaskCase.evaluation_status: EvaluationStatus.FAILED,
                TaskCase.status: TaskCaseStatus.FAILED,
                TaskCase.error_message: case(
                    (or_(TaskCase.error_message.is_(None), TaskCase.error_message == ''),
                     _INTERRUPTED_ERROR_MESSAGE),
                    else_=TaskCase.error_message,
                ),
                TaskCase.completed_at: case(
                    (TaskCase.completed_at.is_(None), now),
                    else_=TaskCase.completed_at,
                ),
            }, synchronize_session=False)

            # 5. 测试结果执行中断 → execution_status failed
            from task_service.infrastructure.persistence.models import TestResult
            result_count = session.query(TestResult).filter(
                TestResult.task_id.in_(task_ids),
                TestResult.execution_status.in_(INTERRUPTED_EXECUTION_STATUSES),
            ).update({
                TestResult.execution_status: ExecutionStatus.FAILED,
                TestResult.error_message: _INTERRUPTED_ERROR_MESSAGE,
            }, synchronize_session=False)

            session.commit()
            return {
                'task': task_count,
                'task_case_execution': case_exec_count,
                'task_case_evaluation': case_eval_count,
                'test_result': result_count,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
