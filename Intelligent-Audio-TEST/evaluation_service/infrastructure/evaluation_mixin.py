"""
评估服务通用混入（Mixin）和工具函数，消除各模块间的重复代码

P0 DDD 改造：EvaluationLoggerMixin 和 get_endpoint_url/get_endpoint_field
已移至 domain/services/ 下，此处仅做向后兼容 re-export。
"""
# 向后兼容 re-export（infrastructure 层内部仍可从此处导入）
from evaluation_service.domain.services.evaluation_logger import EvaluationLoggerMixin  # noqa: F401
from evaluation_service.domain.services.endpoint_helpers import (  # noqa: F401
    get_endpoint_url,
    get_endpoint_field,
)

# 路由行类型（task_case_relations.device_type）：API 侧行的 device_id 列存 api.id
_API_ROUTE_DEVICE_TYPES = ('http_api', 'websocket_api')


def get_result_route_binding(result_id):
    """读取结果行的路由归属 (device_id, api_id)；读不到返回 (None, None)。

    INT-2234：评估写回必须按结果所属路由行精确命中，结果行的 device_id/api_id
    是唯一的归属线索（与 task_case_relations.device_type/device_id 对应）。
    """
    from evaluation_service.infrastructure.acl import task_acl_repository

    try:
        result = task_acl_repository.get_test_result_by_id(result_id)
    except Exception:
        return None, None
    if result is None:
        return None, None
    if isinstance(result, dict):
        return result.get('device_id'), result.get('api_id')
    return getattr(result, 'device_id', None), getattr(result, 'api_id', None)


def match_route_tc_rel_id(rows, device_id=None, api_id=None):
    """在多路由行中按结果归属选出 task_case_relations.id（纯匹配）。

    - 单行：直接命中该行；
    - 多行：physical 行按 device_id、http_api/websocket_api 行按 api_id 匹配；
    - 匹配不到 → None（调用方按旧口径处理，由服务端自行决定命中范围）。
    """
    if not rows:
        return None
    if len(rows) == 1:
        return getattr(rows[0], 'id', None)
    for row in rows:
        row_bind = getattr(row, 'device_id', None)
        row_type = getattr(row, 'device_type', '') or ''
        if device_id is not None and row_type == 'physical' \
                and str(row_bind) == str(device_id):
            return getattr(row, 'id', None)
        if api_id is not None and row_type in _API_ROUTE_DEVICE_TYPES \
                and str(row_bind) == str(api_id):
            return getattr(row, 'id', None)
    return None


def resolve_row_tc_rel_id(rows, result_id=None):
    """在已读取的路由行中按结果归属解析路由行 id（INT-2234）。

    调用方已拿到 tc_rels 时用它，避免重复读；结果归属读不到 → None（旧口径）。
    """
    if not rows:
        return None
    if len(rows) == 1:
        return getattr(rows[0], 'id', None)
    device_id = api_id = None
    if result_id:
        device_id, api_id = get_result_route_binding(result_id)
    return match_route_tc_rel_id(rows, device_id=device_id, api_id=api_id)


def resolve_route_tc_rel_id(task_id, test_case_id, result_id=None):
    """按结果归属解析 task_case_relations.id（INT-2234，多路由精确命中）。

    评估侧所有 TaskCase 写回都应带此 id：不带时 task_service 按
    (task_id, test_case_id) 全量更新，会把同用例兄弟路由行一并改写
    （INT-604「逐行写回」的反面）。解析不出时返回 None，保持旧口径。
    """
    from evaluation_service.infrastructure.acl import task_acl_repository

    try:
        rows = task_acl_repository.get_task_case_by_ids(
            task_id=task_id, case_ids=[str(test_case_id)])
    except Exception:
        return None
    return resolve_row_tc_rel_id(rows, result_id)


def update_task_case_status_with_retry(task_id, case_id, status='',
                                       execution_status='',
                                       evaluation_status='',
                                       error_message='',
                                       tc_rel_id=None):
    """带可靠性的 TaskCase 状态写库（INT-116）。

    ACL 仓储内已对传输级失败做内联重试；本包装在其仍失败（task_service
    持续不可用等）时转入延迟重试队列，由后台线程按指数退避持续补写，
    杜绝 task_case_relations 永久停留在 evaluating/queued 等中间态。

    INT-604：tc_rel_id 可选——多路由下按路由行精确命中。

    Returns:
        bool: 是否已确认落库成功（False 表示已入延迟队列，最终落库与否见日志）
    """
    from evaluation_service.infrastructure.acl import task_acl_repository
    from evaluation_service.infrastructure.acl.task_case_status_retry import (
        task_status_retry_queue,
    )

    success = False
    try:
        success = task_acl_repository.update_task_case_status(
            task_id=task_id,
            case_id=str(case_id),
            status=status,
            execution_status=execution_status,
            evaluation_status=evaluation_status,
            error_message=error_message,
            tc_rel_id=tc_rel_id,
        )
    except Exception:
        pass
    if success:
        return True

    task_status_retry_queue.enqueue_case_status(
        task_id=task_id, case_id=str(case_id), status=status,
        evaluation_status=evaluation_status, error_message=error_message,
        tc_rel_id=tc_rel_id,
    )
    import logging
    logging.getLogger(__name__).warning(
        'TaskCase 状态写库失败已转延迟重试队列: task_id=%s case_id=%s '
        'status=%s evaluation_status=%s',
        task_id, case_id, status, evaluation_status,
    )
    return False


def update_task_status_with_retry(task_id, status):
    """带可靠性的 Task 状态写库（INT-116）：仓储内联重试仍失败转延迟队列。

    Returns:
        bool: 是否已确认落库成功
    """
    from evaluation_service.infrastructure.acl import task_acl_repository
    from evaluation_service.infrastructure.acl.task_case_status_retry import (
        task_status_retry_queue,
    )

    success = False
    try:
        success = task_acl_repository.update_task_status(task_id, status)
    except Exception:
        pass
    if success:
        return True

    task_status_retry_queue.enqueue_task_status(task_id=task_id, status=status)
    import logging
    logging.getLogger(__name__).warning(
        'Task 状态写库失败已转延迟重试队列: task_id=%s status=%s',
        task_id, status,
    )
    return False


def update_task_case_status_in_db(local_db_session, task_id, test_case_id, status,
                                  evaluation_status=None, execution_status=None,
                                  exclude_stopped=True, error_message='', tc_rel_id=None):
    """
    统一更新 TaskCase 状态（P1.4 改造：通过 gRPC 调 task_service.UpdateTaskCaseStatus）

    Args:
        local_db_session: 数据库会话（P1.4 后不再使用，保留参数向后兼容）
        task_id: 任务ID
        test_case_id: 用例ID
        status: 新状态（仅作向后兼容参数，实际由 derive_task_case_status 推导）
        evaluation_status: 评估状态，默认与 status 一致
        execution_status: 执行状态。评估侧写回不持有执行事实，默认 None 表示
            「不回写 execution_status」——多路由下兄弟路由可能仍在执行中，
            由 task_service 按行自身执行状态推导复合 status（INT-604/INT-2234）。
            历史默认值 ExecutionStatus.COMPLETED 会把同用例所有路由行强写执行完成。
        exclude_stopped: 是否排除已停止的任务（gRPC 接口暂未支持，服务端处理）
        error_message: 失败原因（INT-107：评估失败时写入 task_case_relations.error_message，
            服务端仅在非空时写入，不会覆盖已有值）
        tc_rel_id: INT-604 可选，task_case_relations.id——多路由下按路由行精确命中

    Returns:
        int: 影响行数（gRPC 调用成功返回 1，失败转延迟队列返回 0）

    注意：
        P1.4 改造后，此函数通过 gRPC 调用 task_service，不再参与本地事务。
        调用方需意识到：更新 TaskCase 是独立的 gRPC 调用，无法在本地事务内回滚。
        INT-116：写库失败先内联重试，仍失败转延迟重试队列补写，不再静默丢失。
    """
    from shared.utils.status_utils import derive_task_case_status

    if evaluation_status is None:
        evaluation_status = status

    if execution_status is None:
        # INT-604：仅回写评估终态，status 交由 task_service 按行自身 exec 推导
        success = update_task_case_status_with_retry(
            task_id=task_id,
            case_id=str(test_case_id),
            status='',
            evaluation_status=evaluation_status,
            error_message=error_message or '',
            tc_rel_id=tc_rel_id,
        )
        return 1 if success else 0

    derived_status = derive_task_case_status(execution_status, evaluation_status)

    success = update_task_case_status_with_retry(
        task_id=task_id,
        case_id=str(test_case_id),
        status=derived_status,
        execution_status=execution_status,
        evaluation_status=evaluation_status,
        error_message=error_message or '',
        tc_rel_id=tc_rel_id,
    )
    return 1 if success else 0
