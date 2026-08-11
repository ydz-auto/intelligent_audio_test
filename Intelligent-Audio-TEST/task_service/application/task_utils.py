from task_service.infrastructure.persistence.task_repository import task_repository


def has_running_e2e_tasks():
    """检查是否有正在运行的 E2E 任务。"""
    return task_repository.count_running_by_type('e2e') > 0
