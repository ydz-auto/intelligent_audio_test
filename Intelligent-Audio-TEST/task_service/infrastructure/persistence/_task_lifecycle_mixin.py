# -*- coding: utf-8 -*-
"""任务仓储 — 生命周期操作 Mixin（从 task_repository.py 拆分，P4-5）。

task_lifecycle_service 兼容方法：启动前重置、环境预检、重试用例查找、
结果清理、计数重算、重评数据读取等。
"""
import logging
from typing import List, Optional

from sqlalchemy import or_

from shared.models.database import get_db_session
from shared.utils.status_utils import derive_task_case_status
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

logger = logging.getLogger(__name__)

# 服务重启导致任务中断的错误提示（对齐 V9.7.10 旧版文案）
_INTERRUPTED_ERROR_MESSAGE = '服务重启导致任务中断'


class TaskLifecycleMixin:
    """任务生命周期辅助操作（供 TaskRepository 组合）"""

    def get_task_for_start_check(self, task_id: int):
        """启动前检查：返回 Task PO（含 status/id），不存在返回 None。"""
        return self.get_task_orm(task_id)

    def reset_task_for_start(self, task_id: int) -> bool:
        """重置失败/停止任务为 pending，清零计数。"""
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
            session.query(TaskCase).filter(
                TaskCase.task_id == task_id
            ).update({
                TaskCase.status: derive_task_case_status(ExecutionStatus.PENDING, EvaluationStatus.PENDING),
                TaskCase.execution_status: ExecutionStatus.PENDING,
                TaskCase.evaluation_status: EvaluationStatus.PENDING,
                TaskCase.started_at: None,
                TaskCase.completed_at: None,
                TaskCase.duration: None,
                TaskCase.error_message: None,
            }, synchronize_session=False)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check_environment_for_start(self, task_id: int):
        """环境预检：检查关联设备和播放设备是否在线。

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
                return True, ''  # 无设备关联，跳过检查
            device_ids = [td.device_id for td in device_rows]
        finally:
            session.close()

        # 通过 gRPC 检查设备状态（gRPC 调用不占用 DB session）
        return self._check_devices_online(device_ids)

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
        """查找需要重试的用例（execution_status != completed 或 status == failed）。"""
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status != ExecutionStatus.COMPLETED,
            ).all()
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
        """删除 TestResult 记录（preserve_test_result=True 时仅清 algorithm_result）。"""
        from task_service.infrastructure.persistence.models import TestResult
        query = session.query(TestResult).filter(
            TestResult.task_id == task_id,
            TestResult.test_case_id.in_(list(case_ids)),
        )
        if preserve_test_result:
            # 只清理 algorithm_result，保留 result_data
            query.update({TestResult.algorithm_result: None}, synchronize_session=False)
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
        """重新统计任务的完成/失败用例数。"""
        session = get_db_session()
        try:
            from sqlalchemy import func as _func
            total = session.query(_func.count(TaskCase.id)).filter(
                TaskCase.task_id == task_id
            ).scalar() or 0
            completed = session.query(_func.count(TaskCase.id)).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status == ExecutionStatus.COMPLETED,
            ).scalar() or 0
            failed = session.query(_func.count(TaskCase.id)).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status == ExecutionStatus.FAILED,
            ).scalar() or 0
            task = session.get(Task, task_id)
            if task:
                task.total_cases = total
                task.completed_cases = completed
                task.failed_cases = failed
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
        """查询单个 TaskCase PO。"""
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.test_case_id == case_id,
            ).first()
        finally:
            session.close()

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
            from shared.models.database import utc8now
            now = utc8now()

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
            task_count = session.query(Task).filter(
                Task.id.in_(task_ids),
            ).update({
                Task.status: SharedTaskStatus.FAILED,
                Task.error_message: _INTERRUPTED_ERROR_MESSAGE,
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
            case_eval_count = session.query(TaskCase).filter(
                TaskCase.task_id.in_(task_ids),
                TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES),
            ).update({
                TaskCase.evaluation_status: EvaluationStatus.FAILED,
                TaskCase.status: TaskCaseStatus.FAILED,
                TaskCase.error_message: _INTERRUPTED_ERROR_MESSAGE,
                TaskCase.completed_at: now,
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
