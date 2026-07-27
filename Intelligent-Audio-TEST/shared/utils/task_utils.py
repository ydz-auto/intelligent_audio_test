from shared.models.models import Task


def has_running_e2e_tasks():
    running_count = Task.query.filter(
        Task.type == 'e2e',
        Task.status.in_(['queued', 'pending', 'running']),
        Task.deleted == False
    ).count()
    return running_count > 0