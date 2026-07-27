"""
评估服务通用混入（Mixin）和工具函数，消除各模块间的重复代码
"""
import json
from shared.utils.log_handler import log_and_emit


class EvaluationLoggerMixin:
    """统一日志记录混入，所有评估模块继承此类即可获得 _log 方法"""

    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        log_and_emit(
            level=level,
            module='Evaluation',
            content=content,
            category=kwargs.pop('category', 'execution'),
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )


def get_endpoint_url(endpoint_item):
    """从端点配置项中提取URL，兼容 'url' 和 'endpoint' 两种字段名"""
    if not endpoint_item:
        return None
    return endpoint_item.get('url') or endpoint_item.get('endpoint')


def get_endpoint_field(endpoint_item, field_name, fallback_camel=None, default=None):
    """从端点配置项中提取字段值，兼容下划线和驼峰命名"""
    if not endpoint_item:
        return default
    val = endpoint_item.get(field_name)
    if val is None and fallback_camel:
        val = endpoint_item.get(fallback_camel)
    return val if val is not None else default


def update_task_case_status_in_db(local_db_session, task_id, test_case_id, status,
                                  evaluation_status=None, exclude_stopped=True):
    """
    统一更新 TaskCase 状态，返回影响行数

    Args:
        local_db_session: 数据库会话
        task_id: 任务ID
        test_case_id: 用例ID
        status: 新状态 (completed/failed)
        evaluation_status: 评估状态，默认与 status 一致
        exclude_stopped: 是否排除已停止的任务
    """
    from shared.models.models import TaskCase, utc8now

    if evaluation_status is None:
        evaluation_status = status

    query = local_db_session.query(TaskCase).filter(
        TaskCase.task_id == task_id,
        TaskCase.test_case_id == test_case_id,
    )
    if exclude_stopped:
        query = query.filter(TaskCase.status != 'stopped')

    update_data = {
        'status': status,
        'evaluation_status': evaluation_status,
        'completed_at': utc8now()
    }

    update_count = query.update(update_data, synchronize_session=False)
    return update_count
