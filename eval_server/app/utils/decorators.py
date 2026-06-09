import functools
import threading
from .concurrency import ConcurrencyManager

def limit_task_concurrency(func):
    """
    装饰器：自动管理任务的并发计数。
    期望被装饰的函数接收一个包含 'task_type' 键的对象作为参数。
    """
    @functools.wraps(func)
    def wrapper(task, *args, **kwargs):
        task_type = task.get('task_type')
        try:
            return func(task, *args, **kwargs)
        finally:
            if task_type:
                ConcurrencyManager.decrement(task_type)
    return wrapper
