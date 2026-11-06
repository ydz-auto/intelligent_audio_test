# -*- coding: utf-8 -*-
"""评估取消命令处理（INT-308）：执行中删除用例 / 任务停止时联动取消评估侧产出。

契约（对齐 issue 验收口径 + 审计打回修复）：
- 跨服务联动走既有 gRPC + 事件通道（不直接跨库操作）；
- 幂等：重复取消返回成功，cancelled_inflight=0；
- 评估已完成的用例"已完成不可取消"，由删除方标记 excluded（删除卡 INT-305）。

方案A：eval_task_registry.cancel_by_case 摘除在途 HTTP 评估任务并标记 case 取消
       （等待/消费/落库三层核销点已接入：api_request_handler / endpoint_worker /
       task_dispatcher）；
方案B：逐个 DELETE {endpoint}/api/cancel_task/{eval_task_id} 通知子服务真正取消
       （best effort，子服务无该接口/不可达记 WARNING，不失败——对齐 INT-174；
       并行执行 + 总耗时上限，不阻塞停止主链——审计#3）。

审计#1 修复（命令语义优先）：reason 为命令语义（task_stopped / case_deleted，
见 EvaluationCancelReason 枚举）时，取消决策**信任请求方**——直接摘除在途
任务并设置 case 取消标记，不以回读的 TaskCase.evaluation_status 作为跳过依据。
背景：task_service 停止链在调用本 handler 前已把用例评估状态翻转为 stopped，
回读状态此时必然非活跃，若据此跳过取消则"已停任务出评估结果"的幽灵数据
恰好发生在主场景（审计实锤）。回读状态仅用于：
- 返回 excluded 信息（评估结果已实际产出的用例，供删除方标记 excluded）；
- reason 为 adhoc（外部临时调用）时保持保守跳过语义。

审计#4 修复：已完成（不可取消）的用例不再发布 case_evaluation_cancelled
事件（事件名与语义一致，消费方不误读）。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FTimeout

from evaluation_service.infrastructure.acl import task_acl_repository
from evaluation_service.infrastructure.evaluation_api.api_request_handler import (
    eval_task_registry,
)
from shared.utils.status_constants import ACTIVE_EVALUATION_STATUSES

logger = logging.getLogger(__name__)


class EvaluationCancelReason:
    """评估取消原因枚举（审计小瑕疵：拒绝魔法字符串，命令语义者信任请求方）"""

    TASK_STOPPED = 'task_stopped'    # 任务停止联动取消（task_service.control_task stop 分支）
    CASE_DELETED = 'case_deleted'    # 执行中删除用例联动取消（删除卡 INT-305 复用）
    # 非命令语义：外部临时调用（如运维脚本），保持"回读状态非活跃则跳过"的保守语义
    ADHOC = 'adhoc'

    _COMMAND_SEMANTIC = frozenset({TASK_STOPPED, CASE_DELETED})

    @classmethod
    def is_command_semantic(cls, reason) -> bool:
        return (reason or '') in cls._COMMAND_SEMANTIC

    @classmethod
    def normalize(cls, reason) -> str:
        return reason if cls.is_command_semantic(reason) else cls.ADHOC


# 方案B 子服务通知并行度与总耗时上限（审计#3：串行 5s×N 拖慢 stop 主链）
_NOTIFY_MAX_WORKERS = 4
_NOTIFY_JOIN_TIMEOUT = 5


def cancel_case_evaluations(task_id, test_case_ids, reason='case_deleted'):
    """取消 (task_id, test_case_ids) 的评估产出（INT-308）。

    Args:
        task_id: 应用任务 ID（int/str）
        test_case_ids: TaskCase.test_case_id 列表（str）
        reason: 取消原因——命令语义（task_stopped/case_deleted）信任请求方，
            直接摘除并标记；adhoc 回读状态保守跳过（见模块 docstring）

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

    reason = EvaluationCancelReason.normalize(reason)
    trust_requester = EvaluationCancelReason.is_command_semantic(reason)

    # 1. 读取各用例当前评估状态（gRPC 调 task_service，不直接跨库）
    #    审计#1 修复（方案 b）：completed 判定仅用于返回 excluded 信息，
    #    不作为跳过取消的依据。命令语义（task_stopped/case_deleted）下，
    #    task_service 停止链在调用本 handler 前已把用例评估状态翻转为
    #    stopped——回读非活跃是常态而非"评估已产出"的证据，据此跳过取消
    #    会让"已停任务出评估结果"的幽灵数据恰好发生在主场景。
    completed_ids = set()
    try:
        tc_rels = task_acl_repository.get_task_case_by_ids(
            task_id=task_id, case_ids=test_case_ids)
        if trust_requester:
            # 命令语义：仅评估已有实际产出（completed/failed/skipped）的用例
            # 计入 completed（结果不可撤回，调用方标记 excluded）；
            # stopped（停止链刚翻转/此前停止，无评估产出）不计入，照常摘除。
            from shared.utils.status_constants import EvaluationStatus
            completed_ids = {
                str(tc.test_case_id) for tc in tc_rels or []
                if (tc.evaluation_status or '') not in ACTIVE_EVALUATION_STATUSES
                and (tc.evaluation_status or '') != EvaluationStatus.STOPPED
            }
        else:
            # adhoc（外部临时调用）：保守语义——回读非活跃即跳过取消（既有行为）
            for tc in tc_rels or []:
                if tc.evaluation_status not in ACTIVE_EVALUATION_STATUSES:
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

    # 3. 审计事件（INT-308：中断评估 + 结果丢弃 + 审计事件；
    #    审计#4：已完成不可取消的用例不发布取消事件，防语义误读）
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
    """方案B：并行 DELETE {endpoint}/api/cancel_task/{eval_task_id}（best effort）

    审计#3：原逐个串行（timeout=5×N）处于 stop 主链同步调用内，多端点多在途
    任务时线性放大耗时。改为线程池并行 + join 总上限 5s，超时的子服务通知
    放弃（结果侧三层核销兜底，不阻断停止主链）。
    """
    targets = [(eval_task_id, endpoint_url)
               for eval_task_id, endpoint_url in old_tasks if endpoint_url]
    if not targets:
        return 0

    notified = 0

    def _notify_one(eval_task_id, endpoint_url):
        try:
            import requests
            cancel_url = f"{endpoint_url.rstrip('/')}/api/cancel_task/{eval_task_id}"
            resp = requests.delete(cancel_url, timeout=5)
            return resp.status_code < 300
        except Exception as e:
            logger.warning(
                "通知子服务取消评估任务失败 task_id=%s, eval_task_id=%s: %s",
                task_id, eval_task_id, e)
            return False

    pool = ThreadPoolExecutor(max_workers=min(_NOTIFY_MAX_WORKERS, len(targets)),
                              thread_name_prefix='eval_cancel_notify_')
    try:
        futures = [pool.submit(_notify_one, tid, url) for tid, url in targets]
        for f in futures:
            try:
                if f.result(timeout=_NOTIFY_JOIN_TIMEOUT):
                    notified += 1
            except _FTimeout:
                logger.warning("通知子服务取消评估任务超时放弃 task_id=%s", task_id)
            except Exception as e:
                logger.warning("通知子服务取消评估任务异常 task_id=%s: %s", task_id, e)
    finally:
        # 不等待残留任务（超时已放弃），防止拖垮停止主链
        pool.shutdown(wait=False, cancel_futures=True)
    return notified


def _publish_cancel_audit(task_id, results, reason):
    """发布 case_evaluation_cancelled 审计事件到 CASE_EVENTS（Redis 不可用时只打日志）

    审计#4：仅对实际取消（cancelled=true）的用例发布；已完成不可取消
    （completed=true, cancelled=false）的用例不发——事件名与语义一致。
    """
    cancelled_items = [item for item in results if item['cancelled']]
    if not cancelled_items:
        return
    try:
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        event_bus = EventBus()
        for item in cancelled_items:
            event_bus.publish(
                EventChannel.CASE_EVENTS,
                EventType.CASE_EVALUATION_CANCELLED,
                {
                    'task_id': str(task_id),
                    'test_case_id': item['test_case_id'],
                    'cancelled': item['cancelled'],
                    'reason': reason,
                },
            )
    except Exception as e:
        logger.warning("发布评估取消审计事件失败 task_id=%s: %s", task_id, e)
