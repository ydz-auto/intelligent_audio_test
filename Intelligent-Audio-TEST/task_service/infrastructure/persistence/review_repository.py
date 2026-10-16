# -*- coding: utf-8 -*-
"""ReviewRepository - 测试结果人工复核留痕仓储（INT-340）。

职责（单事务内完成 task_service 本地全部落库，保证留痕与状态联动原子）：
- 单个结果复核：更新 TestResult（execution_status + reviewed 标记列）
  + TaskCase（execution/evaluation 状态 + 派生 status）+ 追加复核留痕行
- 任务统计重算：复核后 completed_cases/failed_cases/total_cases 按复核后判定重算
- 复核查询：按结果/任务读留痕历史、复核标记、复核计数（覆盖提醒）
- 批量复核读：按 result_id 列表返回复核标注（结果列表批量回填）

跨服务（evaluation_service TRD 评估状态）由 application 层经 gRPC 联动，
本仓储不触跨域表。
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import OperationalError

from shared.models.database import get_db_session, utc8now
from shared.utils.status_utils import derive_task_case_status, task_case_not_removed
from task_service.infrastructure.persistence.models import (
    Task, TaskCase, TestResult, TestResultReview,
)

logger = logging.getLogger(__name__)


def _read_degrade(default):
    """复核读模型降级装饰器：test_result_reviews 表未建（迁移未应用/精简测试库）
    时返回安全默认值并告警，不阻断任务详情/结果详情主流程（复核标注为辅助读）。
    """
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except OperationalError as e:
                if 'no such table' in str(e):
                    logger.warning(
                        "test_result_reviews 表不存在（迁移未应用），复核读降级: %s", e)
                    return default() if callable(default) else default
                raise
        return _wrapper
    return _decorator


def _review_po_to_dict(po: TestResultReview) -> Dict[str, Any]:
    """复核留痕行 → dict（历史展示 / DTO 透出）。"""
    return {
        'id': po.id,
        'result_id': po.result_id,
        'task_id': po.task_id,
        'test_case_id': po.test_case_id,
        'field_name': po.field_name,
        'old_value': po.old_value,
        'new_value': po.new_value,
        'comment': po.comment,
        'created_by_user_id': po.created_by_user_id,
        'created_at': po.created_at.isoformat() if po.created_at else None,
    }


class ReviewRepository:
    """复核留痕仓储（写模型：复核提交；读模型：历史/标记/计数）。"""

    def apply_review(
        self,
        result_id: int,
        task_id: int,
        test_case_id: Optional[str],
        changes: Dict[str, str],
        comment: str,
        user_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """单结果复核落库（单事务：TestResult + TaskCase + 留痕行）。

        changes: {'execution_status': new, 'evaluation_status': new}（可为空 dict；
        已提供字段若与原值相同则跳过改判，不写留痕行）。

        Returns:
            复核摘要 dict（old/new 对照）或 None（结果不存在）。
        """
        exec_new = changes.get('execution_status')
        eval_new = changes.get('evaluation_status')
        session = get_db_session()
        try:
            result = session.get(TestResult, result_id)
            if result is None:
                return None

            tc = None
            if test_case_id:
                tc = session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id == test_case_id,
                ).first()

            old_exec = result.execution_status
            old_eval = tc.evaluation_status if tc else None
            now = utc8now()

            applied: List[Dict[str, Any]] = []
            if exec_new and exec_new != old_exec:
                result.execution_status = exec_new
                applied.append({'field_name': 'execution_status',
                                'old_value': old_exec, 'new_value': exec_new})
            if eval_new and eval_new != old_eval:
                applied.append({'field_name': 'evaluation_status',
                                'old_value': old_eval, 'new_value': eval_new})

            # 无实际改判（原值已等于目标值）时仅当结果本身未复核才打标记；
            # 已复核再次同值提交视为补备注，留痕行仅在字段实际变化时追加
            if applied:
                action_parts = [f"{f['field_name']}:{f['old_value']}→{f['new_value']}"
                                for f in applied]
                result.reviewed = 1
                result.reviewed_by_user_id = user_id
                result.reviewed_at = now
                result.last_review_comment = comment
                result.last_review_action = '; '.join(action_parts)

                for change in applied:
                    session.add(TestResultReview(
                        result_id=result.id,
                        task_id=task_id,
                        test_case_id=test_case_id,
                        field_name=change['field_name'],
                        old_value=change['old_value'],
                        new_value=change['new_value'],
                        comment=comment,
                        created_by_user_id=user_id,
                        created_at=now,
                    ))

            if tc:
                if exec_new:
                    tc.execution_status = exec_new
                if eval_new:
                    tc.evaluation_status = eval_new
                tc.status = derive_task_case_status(
                    tc.execution_status or 'pending',
                    tc.evaluation_status or 'pending',
                )
                tc.updated_by_user_id = user_id

            session.commit()
            return {
                'result_id': result.id,
                'task_id': task_id,
                'applied': applied,
                'reviewed': bool(applied),
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def recalc_task_stats(self, task_id: int) -> None:
        """复核后按 TaskCase 现状重算任务统计（completed_cases/failed_cases/total_cases）。

        对齐 _post_evaluate_updates 统计口径（FINISHED_CASE_STATUSES 判定）；
        移除留痕行（INT-305）不计数。
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return
            not_removed = task_case_not_removed(TaskCase)
            total = session.query(TaskCase).filter(
                TaskCase.task_id == task_id, not_removed).count()
            completed = session.query(TaskCase).filter(
                TaskCase.task_id == task_id, not_removed,
                TaskCase.status == 'completed').count()
            failed = session.query(TaskCase).filter(
                TaskCase.task_id == task_id, not_removed,
                TaskCase.status == 'failed').count()
            task.total_cases = int(total)
            task.completed_cases = int(completed)
            task.failed_cases = int(failed)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== 读：留痕历史 / 复核计数 / 结果复核标注 ====================
    # 读方法支持传入 session（读模型复用外层 scoped session，避免内层
    # close() 过期外层实体导致 DetachedInstanceError）；未传时自行开合。

    @_read_degrade(list)
    def review_history_by_task(self, task_id: int, session=None) -> List[Dict[str, Any]]:
        """任务全部复核留痕（按时间正序，任务详情复核历史展示）。"""
        _close = session is None
        session = session or get_db_session()
        try:
            pos = session.query(TestResultReview).filter(
                TestResultReview.task_id == task_id,
            ).order_by(TestResultReview.created_at, TestResultReview.id).all()
            return [_review_po_to_dict(po) for po in pos]
        finally:
            if _close:
                session.close()

    @_read_degrade(list)
    def review_history_by_result(self, result_id: int, session=None) -> List[Dict[str, Any]]:
        """单结果复核留痕（多次复核追加历史，不覆盖）。"""
        _close = session is None
        session = session or get_db_session()
        try:
            pos = session.query(TestResultReview).filter(
                TestResultReview.result_id == result_id,
            ).order_by(TestResultReview.created_at, TestResultReview.id).all()
            return [_review_po_to_dict(po) for po in pos]
        finally:
            if _close:
                session.close()

    @_read_degrade(lambda: 0)
    def count_reviewed_results(self, task_id: int, session=None) -> int:
        """任务下已复核结果条数（存在复核留痕的结果去重计数，覆盖提醒用）。

        INT-305：被删用例的 excluded 结果不计入（复核随用例移除不再生效）。
        """
        _close = session is None
        session = session or get_db_session()
        try:
            return session.query(TestResultReview.result_id).filter(
                TestResultReview.task_id == task_id,
                TestResultReview.result_id.in_(
                    session.query(TestResult.id).filter(
                        TestResult.task_id == task_id,
                        TestResult.excluded == 0,
                    ),
                ),
            ).distinct().count() or 0
        finally:
            if _close:
                session.close()

    @_read_degrade(set)
    def reviewed_result_ids(self, task_id: int, session=None) -> set:
        """任务下已复核结果 ID 集合（任务详情 DTO 回填复核标记用；excluded 剔除）。"""
        _close = session is None
        session = session or get_db_session()
        try:
            rows = session.query(TestResultReview.result_id).filter(
                TestResultReview.task_id == task_id,
                TestResultReview.result_id.in_(
                    session.query(TestResult.id).filter(
                        TestResult.task_id == task_id,
                        TestResult.excluded == 0,
                    ),
                ),
            ).distinct().all()
            return {int(r[0]) for r in rows}
        finally:
            if _close:
                session.close()

    @_read_degrade(dict)
    def list_reviewed_summaries(self, result_ids: List[int], session=None) -> Dict[int, Dict[str, Any]]:
        """批量读结果复核摘要（结果列表批量回填：reviewed 标记/最近动作/最近时间）。

        Returns:
            {result_id: {'reviewed': bool, 'reviewed_by_user_id': int|None,
                        'reviewed_at': str|None, 'last_review_comment': str|None,
                        'last_review_action': str|None}}
        """
        ids = [int(r) for r in (result_ids or [])]
        if not ids:
            return {}
        _close = session is None
        session = session or get_db_session()
        try:
            rows = session.query(TestResult).filter(TestResult.id.in_(ids)).all()
            out: Dict[int, Dict[str, Any]] = {}
            for po in rows:
                out[po.id] = {
                    'reviewed': bool(po.reviewed),
                    'reviewed_by_user_id': po.reviewed_by_user_id,
                    'reviewed_at': po.reviewed_at.isoformat() if po.reviewed_at else None,
                    'last_review_comment': po.last_review_comment,
                    'last_review_action': po.last_review_action,
                }
            return out
        finally:
            if _close:
                session.close()


# 模块级单例
review_repository = ReviewRepository()
