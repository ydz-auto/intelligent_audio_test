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


def update_task_case_status_in_db(local_db_session, task_id, test_case_id, status,
                                  evaluation_status=None, exclude_stopped=True):
    """
    统一更新 TaskCase 状态（P1.4 改造：通过 gRPC 调 task_service.UpdateTaskCaseStatus）

    Args:
        local_db_session: 数据库会话（P1.4 后不再使用，保留参数向后兼容）
        task_id: 任务ID
        test_case_id: 用例ID
        status: 新状态 (completed/failed)
        evaluation_status: 评估状态，默认与 status 一致
        exclude_stopped: 是否排除已停止的任务（gRPC 接口暂未支持，服务端处理）

    Returns:
        int: 影响行数（gRPC 调用成功返回 1，失败返回 0）

    注意：
        P1.4 改造后，此函数通过 gRPC 调用 task_service，不再参与本地事务。
        调用方需意识到：更新 TaskCase 是独立的 gRPC 调用，无法在本地事务内回滚。
        失败时通过日志告警，不影响本地 TestResultDimension 的写入。
    """
    from evaluation_service.infrastructure.acl import task_acl_repository

    if evaluation_status is None:
        evaluation_status = status

    success = task_acl_repository.update_task_case_status(
        task_id=task_id,
        case_id=str(test_case_id),
        status=status,
        evaluation_status=evaluation_status,
    )
    return 1 if success else 0
