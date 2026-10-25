# -*- coding: utf-8 -*-
"""AiReviewService — 测试结果 AI 复核应用服务（INT-822/INT-800，task_service 域）。

职责（契约定稿 #2 命令侧；#3 evaluation_service LLM 复检 gRPC 为依赖骨架）：
- 发起：每对 (result_id, dimension_id) 落一条记录；幂等复用最近 running/completed
  结论（reused=true）；否则 status=running 异步执行（后台执行骨架经
  evaluation_service 新 gRPC 调 LLM，回写 verdict/confidence/reasoning/completed，
  失败 failed 不落判定，重试=force 再发）
- 采纳：单事务校验记录 status=completed 且未处置 → adopted/adopted_by/adopted_at →
  复用 review_repository.apply_review 落 test_result_reviews 留痕 + 统计重算 +
  TRD 联动（与 POST /tasks/results/review 同一改判契约与准入：终态任务/枚举/comment≥1）
- 驳回：置 rejected/rejected_by/rejected_at，原判定不变
- 审计：ai_reviews 历史按任务/结果/维度/状态过滤（时间倒序）；命令动作落 logs 审计

约定：所有方法返回 dict: {success, message, data, code?}（#4 网关层统一信封）。
AI 复核独立表，不污染人工复核计数/历史/标记（回归红线）。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from shared.models.common_enums import AuditEvent
from shared.utils.status_constants import (
    TaskStatus,
    REVIEWABLE_EVALUATION_STATUSES, REVIEWABLE_EXECUTION_STATUSES,
)

from task_service.application.task.ai_review_executor import ai_review_executor
from task_service.infrastructure.persistence.ai_review_repository import (
    ai_review_repository,
)
from task_service.infrastructure.persistence.review_repository import review_repository
from task_service.infrastructure.persistence.test_result_repository import (
    test_result_repository,
)
from task_service.infrastructure.persistence.task_repository import task_repository
from task_service.infrastructure.acl.evaluation_config_acl_repository import (
    evaluation_config_acl_repository,
)

logger = logging.getLogger(__name__)

# AI 复核任务状态（与表契约一致）
_AI_STATUS_RUNNING = 'running'
_AI_STATUS_COMPLETED = 'completed'


class AiReviewService:
    """AI 复核应用服务（命令侧：发起/历史/采纳/驳回）。"""

    # ==================== 用户上下文 ====================

    @staticmethod
    def _current_user_id() -> Optional[int]:
        from shared.infrastructure.user_context import get_current_user_id
        return get_current_user_id()

    # ==================== 发起 ====================

    def initiate_review(self, data: dict) -> dict:
        """发起 AI 复核（逐 (result_id, dimension_id) 落记录 + 异步执行）。

        data:
        - result_ids: list[int] 必填
        - dimension_ids: list[int] 可选；缺省=结果现有已完成评估的 LLM 判分维度
        - force: bool 可选；true 绕过幂等复用，新建记录重新执行
        """
        try:
            result_ids = [int(r) for r in (data.get('result_ids') or [])]
        except (TypeError, ValueError):
            return {'success': False, 'message': 'result_ids 非法',
                    'data': {'code': 400}, 'code': 400}
        if not result_ids:
            return {'success': False, 'message': 'result_ids 不能为空',
                    'data': {'code': 400}, 'code': 400}
        force = bool(data.get('force'))
        dimension_ids = data.get('dimension_ids')
        if dimension_ids is not None:
            try:
                dimension_ids = [int(d) for d in dimension_ids]
            except (TypeError, ValueError):
                return {'success': False, 'message': 'dimension_ids 非法',
                        'data': {'code': 400}, 'code': 400}

        items: List[Dict[str, Any]] = []
        reused = False
        skipped: List[Dict[str, Any]] = []
        affected_task_ids: List[int] = []
        # 缺省维度口径：LLM 判分维度集一次性拉取（批内复用，避免逐结果 N 次 gRPC）
        llm_dim_id_set: Optional[set] = None if dimension_ids is not None else set(
            evaluation_config_acl_repository.list_llm_judge_dimension_ids())

        for result_id in result_ids:
            result = test_result_repository.get_by_id(result_id)
            if result is None:
                skipped.append({'result_id': result_id, 'message': '结果不存在'})
                continue
            task_id = result.get('task_id')
            task = task_repository.get_task_dict_by_id(task_id) if task_id else None
            if task is None:
                skipped.append({'result_id': result_id, 'message': '结果所属任务不存在'})
                continue
            if task_id not in affected_task_ids:
                affected_task_ids.append(task_id)

            if dimension_ids is None:
                dims = self._resolve_default_dimensions(result_id, llm_dim_id_set)
            else:
                dims = dimension_ids
            if not dims:
                if dimension_ids is None:
                    msg = '结果无已完成评估的 LLM 判分维度'
                else:
                    msg = '结果无可用 AI 复核维度（dimension_ids 为空）'
                skipped.append({'result_id': result_id, 'message': msg})
                continue

            for dim in dims:
                latest = ai_review_repository.latest_by_result_dimension(result_id, dim)
                if (not force) and latest and latest['status'] in (
                        _AI_STATUS_RUNNING, _AI_STATUS_COMPLETED):
                    items.append(latest)
                    reused = True
                    continue
                rec = ai_review_repository.create(
                    result_id=result_id,
                    task_id=task_id,
                    test_case_id=result.get('test_case_id'),
                    dimension_id=dim,
                    status=_AI_STATUS_RUNNING,
                )
                items.append(rec)
                # 后台执行骨架：经 evaluation_service LLM 复检 gRPC 回写结论
                ai_review_executor.submit(rec['id'])

        if not items:
            reason = skipped[0]['message'] if skipped else '全部结果不可发起'
            return {'success': False, 'message': reason,
                    'data': {'code': 400, 'skipped': skipped}, 'code': 400}

        self._write_audit(AuditEvent.AI_REVIEW_INITIATED.value,
                          operator_id=self._current_user_id(),
                          result_ids=result_ids,
                          affected_task_ids=affected_task_ids,
                          force=force,
                          dimension_ids=dimension_ids)

        message = f'已发起 {len(items)} 条 AI 复核'
        if skipped:
            message += f'（{len(skipped)} 条未发起：{skipped[0]["message"]}）'
        return {'success': True, 'message': message, 'data': {
            'items': items,
            'reused': reused,
            'skipped': skipped,
        }}

    # ==================== 历史（审计） ====================

    def review_history(self, task_id: int, filters: Optional[dict] = None) -> dict:
        """任务 AI 复核记录（时间倒序；可选 result_id/dimension_id/status 过滤）。"""
        filters = filters or {}
        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'task_id 非法',
                    'data': {'code': 400}, 'code': 400}
        try:
            rows = ai_review_repository.list_by_task(task_id)
        except Exception as e:
            logger.error(f"AI 复核历史查询失败 task_id={task_id}: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

        try:
            result_id = filters.get('result_id')
            dimension_id = filters.get('dimension_id')
            if result_id is not None:
                result_id = int(result_id)
            if dimension_id is not None:
                dimension_id = int(dimension_id)
        except (TypeError, ValueError):
            return {'success': False, 'message': '过滤参数非法',
                    'data': {'code': 400}, 'code': 400}
        status = (filters.get('status') or '').strip() or None

        if result_id is not None:
            rows = [r for r in rows if r['result_id'] == result_id]
        if dimension_id is not None:
            rows = [r for r in rows if r['dimension_id'] == dimension_id]
        if status:
            rows = [r for r in rows if r['status'] == status]
        return {'success': True, 'message': 'ok', 'data': {'items': rows}}

    # ==================== 采纳 ====================

    def adopt_review(self, review_id: int, data: dict) -> dict:
        """采纳 AI 复核结论（复用 apply_review 落人工复核语义）。

        data: {execution_status?: str, evaluation_status?: str, comment: str 必填}
        前置：记录 status=completed 且未处置；结果所属任务终态；状态枚举合法。
        """
        try:
            review_id = int(review_id)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'review_id 非法',
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

        rec = ai_review_repository.get(review_id)
        if rec is None:
            return {'success': False, 'message': 'AI 复核记录不存在',
                    'data': {'code': 404}, 'code': 404}
        if rec['status'] != _AI_STATUS_COMPLETED:
            return {'success': False,
                    'message': f'AI 复核未完成（当前 {rec["status"]}），不能采纳',
                    'data': {'code': 400}, 'code': 400}
        if rec['adopted'] or rec['rejected']:
            return {'success': False, 'message': 'AI 复核已处置（已采纳/已驳回），不能重复操作',
                    'data': {'code': 400}, 'code': 400}

        # 结果/任务准入（与人工复核同一改判契约：终态任务）
        result = test_result_repository.get_by_id(rec['result_id'])
        if result is None:
            return {'success': False, 'message': '结果不存在',
                    'data': {'code': 404}, 'code': 404}
        task_id = result.get('task_id')
        task = task_repository.get_task_dict_by_id(task_id) if task_id else None
        if task is None:
            return {'success': False, 'message': '结果所属任务不存在',
                    'data': {'code': 404}, 'code': 404}
        if not TaskStatus.is_terminal(task.get('status')):
            return {'success': False,
                    'message': f'任务未到终态（当前 {task.get("status")}），禁止复核',
                    'data': {'code': 400}, 'code': 400}

        user_id = self._current_user_id()
        changes: Dict[str, str] = {}
        if execution_status:
            changes['execution_status'] = execution_status
        if evaluation_status:
            changes['evaluation_status'] = evaluation_status

        # 复用 apply_review 原子落库（TestResult/TaskCase/留痕，单事务）
        try:
            outcome = review_repository.apply_review(
                result_id=rec['result_id'], task_id=task_id,
                test_case_id=rec.get('test_case_id'),
                changes=changes, comment=comment, user_id=user_id,
            )
        except Exception as e:
            logger.error(f"AI 复核采纳落库失败 review_id={review_id}: {e}", exc_info=True)
            return {'success': False, 'message': f'采纳落库失败: {e}',
                    'data': {'code': 500}, 'code': 500}
        if outcome is None:
            return {'success': False, 'message': '结果不存在',
                    'data': {'code': 404}, 'code': 404}

        # 标记 AI 记录采纳（apply_review 成功后处置，保持留痕优先）
        ai_review_repository.adopt(review_id, user_id)

        # 统计重算 + 评估侧 TRD 联动（对齐人工复核）
        try:
            review_repository.recalc_task_stats(task_id)
        except Exception as e:
            logger.error(f"AI 复核采纳后任务统计重算失败 task_id={task_id}: {e}",
                         exc_info=True)
        if evaluation_status:
            self._sync_dimension_review_status([rec['result_id']], evaluation_status)

        self._write_audit(AuditEvent.AI_REVIEW_ADOPTED.value,
                          operator_id=user_id,
                          review_id=review_id,
                          result_ids=[rec['result_id']],
                          affected_task_ids=[task_id],
                          execution_status=execution_status,
                          evaluation_status=evaluation_status,
                          comment=comment)
        self._refresh_stats_cache()

        updated = ai_review_repository.get(review_id)
        message = '已采纳 AI 复核结论'
        if not outcome.get('applied'):
            message = '已采纳 AI 复核结论（状态无变化，仅补备注）'
        return {'success': True, 'message': message,
                'data': {'item': updated, 'applied': outcome.get('applied', [])}}

    # ==================== 驳回 ====================

    def reject_review(self, review_id: int) -> dict:
        """驳回 AI 复核结论（置 rejected/rejected_by/rejected_at，原判定不变）。"""
        try:
            review_id = int(review_id)
        except (TypeError, ValueError):
            return {'success': False, 'message': 'review_id 非法',
                    'data': {'code': 400}, 'code': 400}
        rec = ai_review_repository.get(review_id)
        if rec is None:
            return {'success': False, 'message': 'AI 复核记录不存在',
                    'data': {'code': 404}, 'code': 404}
        if rec['adopted']:
            return {'success': False, 'message': 'AI 复核已采纳，不能驳回',
                    'data': {'code': 400}, 'code': 400}
        if rec['rejected']:
            # 幂等：已驳回返回现状
            return {'success': True, 'message': 'AI 复核已驳回', 'data': rec}

        user_id = self._current_user_id()
        ai_review_repository.reject(review_id, user_id)
        self._write_audit(AuditEvent.AI_REVIEW_REJECTED.value,
                          operator_id=user_id,
                          review_id=review_id,
                          result_ids=[rec['result_id']],
                          affected_task_ids=[rec['task_id']])
        updated = ai_review_repository.get(review_id)
        return {'success': True, 'message': 'AI 复核已驳回，原判定不变', 'data': updated}

    # ==================== 缺省维度解析 ====================

    @staticmethod
    def _resolve_default_dimensions(result_id: int,
                                    llm_dim_id_set: Optional[set] = None) -> List[int]:
        """结果现有已完成评估的 LLM 判分维度（dimension_ids 缺省口径，INT-800）。

        经 evaluation_service 批量查维度评估结果，与 LLM 判分维度集（llm_dim_id_set，
        调用方一次性拉取可批内复用）取交集。查询失败 / 无命中 → 空列表。
        """
        grouped = evaluation_config_acl_repository.get_dimension_results_by_result_ids(
            [result_id])
        rows = grouped.get(result_id, []) if isinstance(grouped, dict) else []
        completed = [
            r for r in rows
            if r.get('evaluation_status') == 'completed'
            and r.get('dimension_id') is not None
        ]
        if not completed:
            return []
        if llm_dim_id_set is None:
            llm_dim_id_set = set(
                evaluation_config_acl_repository.list_llm_judge_dimension_ids())
        return [int(r['dimension_id']) for r in completed
                if int(r['dimension_id']) in llm_dim_id_set]

    # ==================== 评估侧联动（gRPC） ====================

    @staticmethod
    def _sync_dimension_review_status(result_ids: List[int],
                                      evaluation_status: str) -> None:
        """经 evaluation_service gRPC 改判 TRD 评估状态（失败仅日志告警，post_evaluation 口径）。

        对齐 ReviewService 人工复核同款联动：completed→passed，failed→failed。
        """
        from task_service.application.task.review_service import _EVAL_STATUS_TO_DIM_STATUS
        dim_status = _EVAL_STATUS_TO_DIM_STATUS.get(evaluation_status, evaluation_status)
        try:
            resp = evaluation_config_acl_repository.set_dimension_review_status(
                result_ids, evaluation_status, dim_status)
            if not resp.get('success'):
                logger.warning("AI 复核采纳改判 TRD 评估状态未成功: %s", resp.get('message'))
        except Exception as e:
            logger.warning("AI 复核采纳改判 TRD 评估状态失败（告警降级）: %s", e)

    # ==================== 审计 + 统计缓存 ====================

    @staticmethod
    def _write_audit(event: str, **fields) -> None:
        """审计事件落审计文件（category=System，旁路，失败仅告警）。

        INT-1793：S4 直写仓储改调审计写入器（task_service 单写者 H4），
        操作人由写盘侧从 content JSON 提取（H2）。
        """
        from shared.models.common_enums import AuditLogCategory
        content = {'event': event}
        content.update({k: v for k, v in fields.items() if v is not None})
        try:
            from shared.logging.audit_writer import write_audit_event
            write_audit_event(
                event=event,
                category=AuditLogCategory.SYSTEM.value,
                module='ai_review',
                source='ai_review_service',
                content=json.dumps(content, ensure_ascii=False),
            )
        except Exception:
            logger.warning('审计事件 %s 写审计文件失败', event, exc_info=True)

    @staticmethod
    def _refresh_stats_cache() -> None:
        """复核后刷新统计缓存（api_gateway 旁路优化，失败降级忽略）。"""
        try:
            from api_gateway.application.services.stats_cache import refresh_stats_cache
            refresh_stats_cache()
        except Exception:
            logger.debug("AI 复核采纳后刷新统计缓存失败", exc_info=True)


# 模块级单例
ai_review_service = AiReviewService()
