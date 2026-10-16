# -*- coding: utf-8 -*-
"""ReviewService — 测试结果人工复核应用服务（INT-340，task_service 域）。

职责（设计文档 §2/§3/§4/§5，前向可行性评审裁定 + 负责人 2026-10-15 拍板）：
- 终态任务单条/批量复核：改判执行状态（completed/failed/stopped/skipped 全集）
  与评估状态（completed/failed 双状态口径），复核备注必填
- 逐条留痕（test_result_reviews 表，多次复核追加历史不覆盖）+ TestResult
  复核标记列 + 操作人/时间/原值/新值
- TaskCase 双状态联动：改判后派生 status 并重算任务统计（completed_cases /
  failed_cases / total_cases）——对齐 _post_evaluate_updates 统计口径
- 评估状态改判跨服务联动：evaluation_service gRPC 更新 TRD（TRD 所有权，
  P5 下沉裁定）；跨服务无原子事务，失败走 post_evaluation.py:28 既有
  「日志告警」口径降级
- 审计事件 MANUAL_REVIEW_SUBMITTED 落 logs（旁路，失败仅告警）

约定：所有方法返回 dict: {success, message, data, code?}。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from shared.models.common_enums import AuditEvent
from shared.utils.status_constants import (
    EvaluationStatus, TaskStatus,
    REVIEWABLE_EVALUATION_STATUSES, REVIEWABLE_EXECUTION_STATUSES,
)

from task_service.infrastructure.persistence.review_repository import review_repository
from task_service.infrastructure.persistence.test_result_repository import test_result_repository
from task_service.infrastructure.persistence.task_repository import task_repository

logger = logging.getLogger(__name__)


# TRD 维度结论映射：评估状态 completed→passed，failed→failed（评审二.3 口径）
_EVAL_STATUS_TO_DIM_STATUS = {
    EvaluationStatus.COMPLETED: 'passed',
    EvaluationStatus.FAILED: 'failed',
}


class ReviewService:
    """人工复核应用服务（命令侧）。"""

    # ==================== 用户上下文 ====================

    @staticmethod
    def _current_user_id() -> Optional[int]:
        from shared.infrastructure.user_context import get_current_user_id
        return get_current_user_id()

    # ==================== 复核提交 ====================

    def submit_review(self, data: dict) -> dict:
        """复核提交（单条/批量）。

        data:
        - result_ids: list[int] 必填（批量复核逐条留痕）
        - execution_status: str 可选（completed/failed/stopped/skipped）
        - evaluation_status: str 可选（completed/failed）
        - comment: str 必填（负责人拍板：复核备注必填）
        """
        try:
            result_ids = [int(r) for r in (data.get('result_ids') or [])]
            if not result_ids:
                return {'success': False, 'message': 'result_ids 不能为空',
                        'data': {'code': 400}, 'code': 400}
            comment = (data.get('comment') or '').strip()
            if not comment:
                return {'success': False, 'message': '复核备注必填',
                        'data': {'code': 400}, 'code': 400}

            execution_status = (data.get('execution_status') or '').strip() or None
            evaluation_status = (data.get('evaluation_status') or '').strip() or None
            if execution_status and execution_status not in REVIEWABLE_EXECUTION_STATUSES:
                return {'success': False,
                        'message': f'执行状态不可改判: {execution_status}'
                                   f'（仅限 {sorted(REVIEWABLE_EXECUTION_STATUSES)}）',
                        'data': {'code': 400}, 'code': 400}
            if evaluation_status and evaluation_status not in REVIEWABLE_EVALUATION_STATUSES:
                return {'success': False,
                        'message': f'评估状态不可改判: {evaluation_status}'
                                   f'（仅限 {sorted(REVIEWABLE_EVALUATION_STATUSES)}）',
                        'data': {'code': 400}, 'code': 400}
            if not execution_status and not evaluation_status:
                return {'success': False, 'message': '执行状态/评估状态至少设置一项',
                        'data': {'code': 400}, 'code': 400}

            user_id = self._current_user_id()
            reviewed: List[Dict[str, Any]] = []
            failed: List[Dict[str, Any]] = []
            affected_task_ids: List[int] = []

            for result_id in result_ids:
                outcome = self._apply_one(
                    result_id=result_id,
                    execution_status=execution_status,
                    evaluation_status=evaluation_status,
                    comment=comment,
                    user_id=user_id,
                )
                if outcome is None:
                    failed.append({'result_id': result_id, 'message': '结果不存在'})
                    continue
                if outcome.get('task_id') not in affected_task_ids:
                    affected_task_ids.append(outcome['task_id'])
                if outcome.get('applied'):
                    reviewed.append(outcome)
                else:
                    # 未生效：优先透出 _apply_one 的校验消息（非终态/落库失败），
                    # 无校验消息时才是「状态无变化（同值复核仅补备注）」
                    failed.append({'result_id': result_id,
                                   'message': outcome.get('message')
                                   or '状态无变化（已复核同值），仅允许补备注'})

            # 复核后按任务重算统计（多次复核同任务仅重算一次）
            for task_id in affected_task_ids:
                try:
                    review_repository.recalc_task_stats(task_id)
                except Exception as e:
                    logger.error(f"复核后任务统计重算失败 task_id={task_id}: {e}", exc_info=True)

            self._write_audit(result_ids, execution_status, evaluation_status,
                              affected_task_ids)
            self._refresh_stats_cache()

            if not reviewed:
                reason = failed[0]['message'] if failed else '全部结果不存在'
                return {'success': False,
                        'message': reason,
                        'data': {'code': 400, 'failed': failed}, 'code': 400}
            message = f'已复核 {len(reviewed)} 条结果'
            if failed:
                message += f'（{len(failed)} 条未生效：{failed[0]["message"]}）'
            return {'success': True, 'message': message, 'data': {
                'reviewed': reviewed,
                'failed': failed,
                'review_count': len(reviewed),
            }}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"人工复核提交失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def _apply_one(self, result_id: int, execution_status: Optional[str],
                   evaluation_status: Optional[str], comment: str,
                   user_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """单结果复核：校验终态 + 本地落库（TestResult/TaskCase/留痕）+ 评估侧联动。"""
        result = test_result_repository.get_by_id(result_id)
        if result is None:
            return None

        task_id = result.get('task_id')
        test_case_id = result.get('test_case_id')
        task = task_repository.get_task_dict_by_id(task_id) if task_id else None
        if task is None:
            return {'result_id': result_id, 'task_id': task_id, 'applied': [],
                    'message': '结果所属任务不存在'}
        if not TaskStatus.is_terminal(task.get('status')):
            return {'result_id': result_id, 'task_id': task_id, 'applied': [],
                    'message': f'任务未到终态（当前 {task.get("status")}），禁止复核'}

        changes: Dict[str, str] = {}
        if execution_status:
            changes['execution_status'] = execution_status
        if evaluation_status:
            changes['evaluation_status'] = evaluation_status

        # 本地落库（单事务：TestResult 状态/标记 + TaskCase 双状态 + 留痕行）
        try:
            outcome = review_repository.apply_review(
                result_id=result_id, task_id=task_id, test_case_id=test_case_id,
                changes=changes, comment=comment, user_id=user_id,
            )
        except Exception as e:
            logger.error(f"复核本地落库失败 result_id={result_id}: {e}", exc_info=True)
            return {'result_id': result_id, 'task_id': task_id, 'applied': [],
                    'message': f'复核落库失败: {e}'}

        # 评估状态改判：跨服务联动 evaluation_service（TRD 所有权），
        # 无原子事务，失败走「日志告警」口径（留痕已落 task_service，不影响主流程）
        if evaluation_status:
            self._sync_dimension_review_status(
                [result_id], evaluation_status)

        return outcome

    # ==================== 评估侧联动（gRPC） ====================

    @staticmethod
    def _sync_dimension_review_status(result_ids: List[int], evaluation_status: str) -> None:
        """经 evaluation_service gRPC 改判 TRD 评估状态（失败仅日志告警，post_evaluation 口径）。"""
        from task_service.infrastructure.acl.evaluation_config_acl_repository import (
            evaluation_config_acl_repository,
        )
        dim_status = _EVAL_STATUS_TO_DIM_STATUS.get(evaluation_status, evaluation_status)
        try:
            resp = evaluation_config_acl_repository.set_dimension_review_status(
                result_ids, evaluation_status, dim_status)
            if not resp.get('success'):
                logger.warning("复核改判 TRD 评估状态未成功: %s", resp.get('message'))
        except Exception as e:
            logger.warning("复核改判 TRD 评估状态失败（告警降级）: %s", e)

    # ==================== 审计 + 统计缓存 ====================

    @staticmethod
    def _write_audit(result_ids: List[int], execution_status: Optional[str],
                     evaluation_status: Optional[str],
                     affected_task_ids: List[int]) -> None:
        """审计事件落 logs 表（category=System，旁路，失败仅告警）。"""
        from task_service.infrastructure.persistence.log_repository import log_repository
        try:
            log_repository.batch_create([{
                'module': 'task_review',
                'source': 'review_service',
                'content': json.dumps({
                    'event': AuditEvent.MANUAL_REVIEW_SUBMITTED.value,
                    'result_ids': result_ids,
                    'affected_task_ids': affected_task_ids,
                    'execution_status': execution_status,
                    'evaluation_status': evaluation_status,
                    'result': 'success',
                }, ensure_ascii=False),
            }])
        except Exception:
            logger.warning('审计事件 %s 落库失败', AuditEvent.MANUAL_REVIEW_SUBMITTED.value,
                           exc_info=True)

    @staticmethod
    def _refresh_stats_cache() -> None:
        """复核后刷新统计缓存（api_gateway 旁路优化，失败降级忽略）。"""
        try:
            from api_gateway.application.services.stats_cache import refresh_stats_cache
            refresh_stats_cache()
        except Exception:
            logger.debug("复核后刷新统计缓存失败", exc_info=True)

    # ==================== 复核查询（读侧，无副作用） ====================

    def review_count(self, task_id: int) -> dict:
        """覆盖提醒计数：任务下已复核结果条数（任务详情查询挂点）。"""
        try:
            count = review_repository.count_reviewed_results(int(task_id))
            return {'success': True, 'message': 'ok', 'data': {'review_count': count}}
        except Exception as e:
            logger.error(f"复核计数查询失败 task_id={task_id}: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def review_history(self, task_id: int) -> dict:
        """任务复核历史（多次复核追加不覆盖，任务详情页展示）。"""
        try:
            items = review_repository.review_history_by_task(int(task_id))
            return {'success': True, 'message': 'ok', 'data': {'items': items}}
        except Exception as e:
            logger.error(f"复核历史查询失败 task_id={task_id}: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}


# 模块级单例
review_service = ReviewService()
