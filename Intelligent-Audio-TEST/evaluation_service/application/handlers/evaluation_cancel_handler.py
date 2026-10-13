# -*- coding: utf-8 -*-
"""评估取消命令处理（INT-308）：执行中删除用例 / 任务停止时联动取消评估侧产出。

契约（对齐 issue 验收口径）：
- 跨服务联动走既有 gRPC + 事件通道（不直接跨库操作）；
- 幂等：重复取消返回成功，cancelled_inflight=0；
- 评估已完成的用例"已完成不可取消"，由删除方标记 excluded（删除卡 INT-305）。

方案A：eval_task_registry.cancel_by_case 摘除在途 HTTP 评估任务并标记 case 取消
       （等待/消费/落库三层核销点已接入：api_request_handler / endpoint_worker /
       task_dispatcher）；
方案B：逐个 DELETE {endpoint}/api/cancel_task/{eval_task_id} 通知子服务真正取消
       （best effort，子服务无该接口/不可达记 WARNING，不失败——对齐 INT-174）。
"""
import logging

from evaluation_service.infrastructure.acl import task_acl_repository
from evaluation_service.infrastructure.evaluation_api.api_request_handler import (
    eval_task_registry,
)
from shared.utils.status_constants import ACTIVE_EVALUATION_STATUSES

logger = logging.getLogger(__name__)


def cancel_case_evaluations(task_id, test_case_ids, reason='case_deleted'):
    """取消 (task_id, test_case_ids) 的评估产出（INT-308）。

    Args:
        task_id: 应用任务 ID（int/str）
        test_case_ids: TaskCase.test_case_id 列表（str）
        reason: 取消原因（case_deleted / task_stopped）

    Returns:
        dict: {
            'results': [{'test_case_id', 'cancelled', 'completed',
                         'inflight_removed', 'subservice_notified'}, ...],
            'cancelled_inflight': int,      # 摘除的在途评估任务总数
            'subservice_notified': int,     # 子服务 cancel_task 成功数（best effort）
        }
    """
    task_id = int(task_id)
    test_case_ids = [str(c) for c in (test_case_ids or [])]
    if not test_case_ids:
        return {'results': [], 'cancelled_inflight': 0, 'subservice_notified': 0}

    # 1. 读取各用例当前评估状态（gRPC 调 task_service，不直接跨库）
    completed_ids = set()
    try:
        tc_rels = task_acl_repository.get_task_case_by_ids(
            task_id=task_id, case_ids=test_case_ids)
        for tc in tc_rels or []:
            if tc.evaluation_status not in ACTIVE_EVALUATION_STATUSES:
                # 已终态（completed/failed/skipped/stopped）：评估已产出，不可取消
                completed_ids.add(str(tc.test_case_id))
    except Exception as e:
        # 状态查询失败不阻断取消主流程：在途条目照常摘除（结果侧核销兜底）
        logger.warning("取消评估查询用例状态失败 task_id=%s: %s", task_id, e)

    # 2. 逐用例摘除在途评估任务并标记 case 取消（方案A），通知子服务（方案B）
    results = []
    cancelled_inflight = 0
    subservice_notified = 0
    for tc_id in test_case_ids:
        completed = tc_id in completed_ids
        inflight_removed = 0
        notified = 0
        if not completed:
            old_tasks = eval_task_registry.cancel_by_case(
                task_id, tc_id, reason=reason)
            inflight_removed = len(old_tasks)
            notified = _notify_subservices_cancel(old_tasks, task_id)
            cancelled_inflight += inflight_removed
            subservice_notified += notified
        results.append({
            'test_case_id': tc_id,
            'cancelled': not completed,
            'completed': completed,
            'inflight_removed': inflight_removed,
            'subservice_notified': notified,
        })

    # 3. 审计事件（INT-308：中断评估 + 结果丢弃 + 审计事件）
    _publish_cancel_audit(task_id, results, reason)

    logger.info(
        "评估取消完成 task_id=%s, cases=%s, reason=%s, 在途摘除=%s, 子服务取消=%s",
        task_id, test_case_ids, reason, cancelled_inflight, subservice_notified)
    return {
        'results': results,
        'cancelled_inflight': cancelled_inflight,
        'subservice_notified': subservice_notified,
    }


def _notify_subservices_cancel(old_tasks, task_id):
    """方案B：逐个 DELETE {endpoint}/api/cancel_task/{eval_task_id}（best effort）"""
    notified = 0
    for eval_task_id, endpoint_url in old_tasks:
        if not endpoint_url:
            continue
        try:
            import requests
            cancel_url = f"{endpoint_url.rstrip('/')}/api/cancel_task/{eval_task_id}"
            resp = requests.delete(cancel_url, timeout=5)
            if resp.status_code < 300:
                notified += 1
        except Exception as e:
            logger.warning(
                "通知子服务取消评估任务失败 task_id=%s, eval_task_id=%s: %s",
                task_id, eval_task_id, e)
    return notified


def _publish_cancel_audit(task_id, results, reason):
    """发布 case_evaluation_cancelled 审计事件到 CASE_EVENTS（Redis 不可用时只打日志）"""
    try:
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        event_bus = EventBus()
        for item in results:
            event_bus.publish(
                EventChannel.CASE_EVENTS,
                EventType.CASE_EVALUATION_CANCELLED,
                {
                    'task_id': str(task_id),
                    'test_case_id': item['test_case_id'],
                    'cancelled': item['cancelled'],
                    'completed_irreversible': item['completed'],
                    'reason': reason,
                },
            )
    except Exception as e:
        logger.warning("发布评估取消审计事件失败 task_id=%s: %s", task_id, e)
